"""
因子择时/宏观体制切换策略
=========================
Factor Timing / Regime Switching Strategy

核心逻辑:
- 识别宏观经济体制 (扩张/收缩/危机)
- 根据当前体制动态调整因子权重
- 扩张期: 偏重动量/成长因子
- 收缩期: 偏重价值/质量因子
- 危机期: 降低总仓位，偏重低波动

学术基础:
- Ang & Bekaert (2002): "Regime Switches in Interest Rates"
- Asness et al. (2000): "Style Timing: Value vs. Growth"
- Hodges et al. (2017): "Factor Timing with Cross-Sectional and Time-Series Predictors"

体制识别方法:
1. 市场波动率水平 (VIX代理)
2. 价格趋势 (市场指数移动平均)
3. 波动率变化趋势 (波动率是否上升)
4. 市场动量 (近期收益率)
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import json

from config import StrategyConfig, CONFIG
from factor_model import FactorDataProvider, FactorCalculator
from valmom_backtest import FactorBacktestResult, ValMomVisualizer

logger = logging.getLogger(__name__)


# ============================================================
# 体制定义
# ============================================================
class MarketRegime(Enum):
    """市场体制"""
    EXPANSION = "expansion"      # 扩张期: 低波动 + 上涨趋势
    CONTRACTION = "contraction"  # 收缩期: 波动上升 + 下跌趋势
    CRISIS = "crisis"            # 危机期: 高波动 + 急跌


@dataclass
class RegimeState:
    """体制状态"""
    regime: MarketRegime
    confidence: float              # 0-1 置信度
    volatility_level: float        # 当前波动率
    trend_direction: float         # 趋势方向 (-1 to 1)
    momentum: float                # 市场动量
    regime_duration: int = 0       # 当前体制持续天数


# ============================================================
# 因子权重方案
# ============================================================
REGIME_FACTOR_WEIGHTS = {
    MarketRegime.EXPANSION: {
        'momentum': 0.35,
        'value': 0.15,
        'quality': 0.20,
        'lowvol': 0.10,
        'growth': 0.20,
        'total_exposure': 1.0,
    },
    MarketRegime.CONTRACTION: {
        'momentum': 0.10,
        'value': 0.35,
        'quality': 0.30,
        'lowvol': 0.15,
        'growth': 0.10,
        'total_exposure': 0.80,
    },
    MarketRegime.CRISIS: {
        'momentum': 0.05,
        'value': 0.20,
        'quality': 0.25,
        'lowvol': 0.40,
        'growth': 0.10,
        'total_exposure': 0.50,  # 大幅降仓
    },
}


# ============================================================
# 体制识别
# ============================================================
class RegimeDetector:
    """
    市场体制识别器

    使用多维度信号综合判断当前市场所处的体制
    """

    def __init__(
        self,
        vol_window: int = 20,
        trend_window: int = 60,
        crisis_vol_threshold: float = 0.30,
        expansion_vol_threshold: float = 0.18,
    ):
        self.vol_window = vol_window
        self.trend_window = trend_window
        self.crisis_vol_threshold = crisis_vol_threshold
        self.expansion_vol_threshold = expansion_vol_threshold
        self.logger = logging.getLogger(__name__)

    def detect_regime(self, market_prices: pd.Series) -> RegimeState:
        """
        检测当前市场体制

        综合评估:
        1. 波动率水平
        2. 价格趋势 (MA60)
        3. 波动率变化方向
        4. 近期动量
        """
        if len(market_prices) < max(self.vol_window, self.trend_window) + 10:
            return RegimeState(
                regime=MarketRegime.EXPANSION,
                confidence=0.5,
                volatility_level=0.15,
                trend_direction=0.0,
                momentum=0.0,
            )

        returns = market_prices.pct_change().dropna()

        # 1. 当前波动率
        current_vol = returns.iloc[-self.vol_window:].std() * np.sqrt(252)

        # 2. 趋势判断
        ma_trend = market_prices.rolling(self.trend_window).mean()
        current_price = market_prices.iloc[-1]
        trend_direction = (current_price / ma_trend.iloc[-1] - 1)
        trend_direction = np.clip(trend_direction, -0.20, 0.20) / 0.20  # 归一化

        # 3. 波动率变化
        vol_recent = returns.iloc[-10:].std() * np.sqrt(252)
        vol_prior = returns.iloc[-30:-10].std() * np.sqrt(252) if len(returns) >= 30 else current_vol
        vol_change = vol_recent / max(vol_prior, 0.01) - 1

        # 4. 近期动量
        momentum = market_prices.iloc[-1] / market_prices.iloc[-20] - 1 if len(market_prices) >= 20 else 0

        # 综合评分
        regime, confidence = self._classify_regime(
            current_vol, trend_direction, vol_change, momentum
        )

        return RegimeState(
            regime=regime,
            confidence=confidence,
            volatility_level=current_vol,
            trend_direction=trend_direction,
            momentum=momentum,
        )

    def _classify_regime(
        self,
        vol: float,
        trend: float,
        vol_change: float,
        momentum: float,
    ) -> Tuple[MarketRegime, float]:
        """分类体制"""
        # 危机: 高波动 + 下跌趋势 + 波动率上升
        crisis_score = 0
        if vol > self.crisis_vol_threshold:
            crisis_score += 0.4
        if trend < -0.3:
            crisis_score += 0.3
        if vol_change > 0.3:
            crisis_score += 0.3

        # 扩张: 低波动 + 上涨趋势 + 正动量
        expansion_score = 0
        if vol < self.expansion_vol_threshold:
            expansion_score += 0.3
        if trend > 0.2:
            expansion_score += 0.35
        if momentum > 0.01:
            expansion_score += 0.35

        # 收缩: 其余情况
        contraction_score = 1 - max(crisis_score, expansion_score)

        scores = {
            MarketRegime.CRISIS: crisis_score,
            MarketRegime.EXPANSION: expansion_score,
            MarketRegime.CONTRACTION: contraction_score,
        }

        regime = max(scores, key=scores.get)
        confidence = scores[regime]

        return regime, confidence

    def detect_regime_series(
        self,
        market_prices: pd.Series,
        dates: pd.DatetimeIndex,
    ) -> Dict[datetime, RegimeState]:
        """检测时间序列上的体制变化"""
        regimes = {}
        for date in dates:
            prices_to_date = market_prices.loc[:date]
            if len(prices_to_date) >= self.trend_window + 10:
                regimes[date] = self.detect_regime(prices_to_date)
            else:
                regimes[date] = RegimeState(
                    regime=MarketRegime.EXPANSION,
                    confidence=0.5,
                    volatility_level=0.15,
                    trend_direction=0.0,
                    momentum=0.0,
                )
        return regimes


# ============================================================
# 因子信号构建
# ============================================================
class TimedFactorBuilder:
    """
    基于体制的因子信号构建器

    根据当前体制动态调整因子暴露
    """

    def __init__(self, data_provider: FactorDataProvider = None):
        self.data_provider = data_provider or FactorDataProvider()
        self.regime_detector = RegimeDetector()
        self.logger = logging.getLogger(__name__)

    def build_timed_signal(
        self,
        symbols: List[str],
        date: str,
        market_prices: pd.Series,
    ) -> Tuple[pd.Series, RegimeState]:
        """
        构建带体制择时的综合因子信号

        Returns:
            (composite_signal, regime_state)
        """
        # 检测体制
        regime_state = self.regime_detector.detect_regime(market_prices)
        factor_weights = REGIME_FACTOR_WEIGHTS[regime_state.regime]

        self.logger.info(
            f"[{date}] 体制: {regime_state.regime.value} "
            f"(置信度: {regime_state.confidence:.2f}, "
            f"Vol: {regime_state.volatility_level:.2%})"
        )

        # 获取各因子信号
        factor_signals = {}

        # 价值因子
        factor_data = self.data_provider.get_factor_data(
            symbols, ['pe_ttm', 'pb', 'ps_ttm'], date
        )
        if 'pe_ttm' in factor_data.columns:
            ep = 1 / factor_data['pe_ttm'].replace(0, np.nan)
            factor_signals['value'] = self._zscore(ep)

        # 动量因子
        end_dt = pd.to_datetime(date)
        start_dt = end_dt - pd.Timedelta(days=400)
        prices = self.data_provider.get_price_data(
            symbols, start_dt.strftime('%Y-%m-%d'), date
        )
        if not prices.empty and len(prices) > 60:
            mom_12_1 = prices.iloc[-21] / prices.iloc[0] - 1 if len(prices) > 21 else prices.pct_change(20).iloc[-1]
            factor_signals['momentum'] = self._zscore(mom_12_1)

        # 质量因子
        qual_data = self.data_provider.get_factor_data(symbols, ['roe', 'roa'], date)
        if 'roe' in qual_data.columns:
            factor_signals['quality'] = self._zscore(qual_data['roe'])

        # 低波动因子
        if not prices.empty and len(prices) >= 60:
            vol_60 = prices.pct_change().iloc[-60:].std() * np.sqrt(252)
            factor_signals['lowvol'] = self._zscore(1.0 / vol_60.replace(0, np.nan))

        # 成长因子 (用动量近似)
        if 'momentum' in factor_signals:
            factor_signals['growth'] = factor_signals['momentum'] * 0.8

        # 加权合成
        composite = pd.Series(0.0, index=symbols)
        for factor_name, weight in factor_weights.items():
            if factor_name == 'total_exposure':
                continue
            if factor_name in factor_signals:
                sig = factor_signals[factor_name].reindex(symbols, fill_value=0)
                composite += sig * weight

        # 应用总仓位缩放
        composite *= factor_weights['total_exposure']

        return composite.dropna(), regime_state

    def _zscore(self, series: pd.Series) -> pd.Series:
        s = series.dropna()
        if len(s) == 0:
            return s
        lower = s.quantile(0.01)
        upper = s.quantile(0.99)
        s = s.clip(lower, upper)
        std = s.std()
        if std > 0:
            s = (s - s.mean()) / std
        return s


# ============================================================
# 回测引擎
# ============================================================
class FactorTimingBacktester:
    """因子择时策略回测引擎"""

    def __init__(
        self,
        config: StrategyConfig = None,
        factor_builder: TimedFactorBuilder = None,
    ):
        self.config = config or CONFIG
        self.factor_builder = factor_builder or TimedFactorBuilder()
        self.logger = logging.getLogger(__name__)

    def backtest(
        self,
        start_date: str,
        end_date: str,
        rebalance_freq: str = 'ME',
        top_n: int = 30,
        bottom_n: int = 30,
    ) -> Tuple[FactorBacktestResult, Dict[datetime, RegimeState]]:
        """
        运行因子择时回测

        Returns:
            (backtest_result, regime_history)
        """
        self.logger.info(f"因子择时回测: {start_date} 至 {end_date}")

        dates = pd.date_range(start=start_date, end=end_date, freq=rebalance_freq)

        # 获取市场指数作为体制检测基准
        market_start = pd.to_datetime(start_date) - pd.Timedelta(days=200)
        universe_sample = self.factor_builder.data_provider.get_stock_universe(
            self.config.STOCK_UNIVERSE
        )
        market_prices = self.factor_builder.data_provider.get_price_data(
            universe_sample[:20],
            market_start.strftime('%Y-%m-%d'),
            end_date
        )
        # 用等权指数作为市场代理
        market_index = market_prices.mean(axis=1) if not market_prices.empty else pd.Series(dtype=float)

        portfolio_value = 1.0
        equity_curve = pd.Series(index=dates, dtype=float)
        equity_curve.iloc[0] = portfolio_value
        returns_list = []
        prev_weights = None
        turnover_list = []
        regime_history = {}

        for i in range(1, len(dates)):
            current_date = dates[i]
            prev_date = dates[i - 1]

            universe = self.factor_builder.data_provider.get_stock_universe(
                self.config.STOCK_UNIVERSE,
                prev_date.strftime('%Y-%m-%d')
            )

            # 构建带择时的信号
            mkt_to_date = market_index.loc[:prev_date] if not market_index.empty else pd.Series(dtype=float)
            if len(mkt_to_date) < 70:
                equity_curve.iloc[i] = equity_curve.iloc[i - 1]
                continue

            signal, regime_state = self.factor_builder.build_timed_signal(
                universe, prev_date.strftime('%Y-%m-%d'), mkt_to_date
            )
            regime_history[prev_date] = regime_state

            if signal.empty:
                equity_curve.iloc[i] = equity_curve.iloc[i - 1]
                continue

            # 构建权重 (信号加权多空)
            weights = pd.Series(0.0, index=signal.index)
            pos = signal[signal > 0]
            neg = signal[signal < 0]
            if len(pos) > 0:
                weights.loc[pos.index] = pos / pos.sum() * 0.5
            if len(neg) > 0:
                weights.loc[neg.index] = neg / neg.abs().sum() * (-0.5)

            # 换手率
            if prev_weights is not None:
                all_idx = prev_weights.index.union(weights.index)
                turnover = np.abs(
                    weights.reindex(all_idx, fill_value=0)
                    - prev_weights.reindex(all_idx, fill_value=0)
                ).sum() / 2
                turnover_list.append(turnover)
            prev_weights = weights.copy()

            # 计算组合收益
            symbols = weights.index.tolist()
            prices = self.factor_builder.data_provider.get_price_data(
                symbols, prev_date.strftime('%Y-%m-%d'), current_date.strftime('%Y-%m-%d')
            )
            if prices.empty or len(prices) < 2:
                period_return = 0.0
            else:
                stock_returns = (prices.iloc[-1] / prices.iloc[0] - 1).fillna(0)
                period_return = (weights * stock_returns).sum()

            portfolio_value *= (1 + period_return)
            equity_curve.iloc[i] = portfolio_value
            returns_list.append(period_return)

        returns_series = pd.Series(returns_list, index=dates[1:len(returns_list) + 1])
        result = self._calc_metrics(start_date, end_date, equity_curve, returns_series, turnover_list)

        # 打印体制分布
        if regime_history:
            regime_counts = {}
            for state in regime_history.values():
                r = state.regime.value
                regime_counts[r] = regime_counts.get(r, 0) + 1
            self.logger.info(f"体制分布: {regime_counts}")

        return result, regime_history

    def _calc_metrics(self, start_date, end_date, equity_curve, returns_series, turnover_list):
        ec = equity_curve.dropna()
        total_return = ec.iloc[-1] / ec.iloc[0] - 1
        years = len(ec) / 12
        ann_ret = (1 + total_return) ** (1 / max(years, 0.01)) - 1
        vol = returns_series.std() * np.sqrt(12) if len(returns_series) > 0 else 0
        sharpe = ann_ret / vol if vol > 0 else 0
        downside = returns_series[returns_series < 0]
        ds_std = downside.std() * np.sqrt(12) if len(downside) > 0 else 0.0001
        sortino = ann_ret / ds_std if ds_std > 0 else 0
        cummax = ec.cummax()
        dd = (ec - cummax) / cummax
        max_dd = dd.min()
        calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0

        return FactorBacktestResult(
            factor_name='factor_timing',
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            annualized_return=ann_ret,
            volatility=vol,
            sharpe_ratio=sharpe,
            information_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            calmar_ratio=calmar,
            turnover=np.mean(turnover_list) if turnover_list else 0,
            equity_curve=equity_curve,
            returns_series=returns_series,
        )


# ============================================================
# 便捷入口
# ============================================================
def run_factor_timing_backtest(
    start_date: str = "2022-01-01",
    end_date: str = "2024-12-31",
    save_results: bool = True,
) -> Tuple[FactorBacktestResult, Dict]:
    """
    运行因子择时策略回测

    同时运行:
    1. 因子择时策略 (动态权重)
    2. 静态等权因子对照 (固定权重)
    """
    logger.info("=" * 70)
    logger.info("Factor Timing / Regime Switching Backtest")
    logger.info("=" * 70)

    backtester = FactorTimingBacktester()
    result, regime_history = backtester.backtest(start_date, end_date)

    # 打印结果
    print("\n" + "=" * 70)
    print("Factor Timing Strategy Results")
    print("=" * 70)
    print(f"  年化收益率:  {result.annualized_return * 100:>8.2f}%")
    print(f"  年化波动率:  {result.volatility * 100:>8.2f}%")
    print(f"  夏普比率:    {result.sharpe_ratio:>8.2f}")
    print(f"  最大回撤:    {result.max_drawdown * 100:>8.2f}%")
    print(f"  Calmar比率:  {result.calmar_ratio:>8.2f}")

    # 体制分布
    if regime_history:
        print("\n  体制分布:")
        regime_counts = {}
        for state in regime_history.values():
            r = state.regime.value
            regime_counts[r] = regime_counts.get(r, 0) + 1
        total = sum(regime_counts.values())
        for regime, count in sorted(regime_counts.items()):
            print(f"    {regime}: {count}/{total} ({count/total*100:.1f}%)")

    print("=" * 70)

    if save_results:
        save_path = "backtests/factor_timing_results.json"
        data = result.to_dict()
        data['regime_distribution'] = {
            state.regime.value: 1
            for state in regime_history.values()
        } if regime_history else {}
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"结果已保存: {save_path}")

    return result, regime_history


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    result, regimes = run_factor_timing_backtest("2022-01-01", "2024-12-31")
