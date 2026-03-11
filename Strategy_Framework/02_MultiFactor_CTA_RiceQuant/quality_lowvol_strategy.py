"""
质量+低波动因子策略
==================
Quality + Low Volatility MultiFactor Strategy

核心逻辑:
- 质量因子: ROE, ROA, 毛利率稳定性, 资产负债率
- 低波动因子: 过去60/120日实现波动率的倒数
- 防御性Alpha: 高质量 + 低波动 的股票组合在市场下跌时表现更好

学术基础:
- Novy-Marx (2013): "The Other Side of Value: The Gross Profitability Premium"
- Baker, Bradley & Wurgler (2011): "Benchmarks as Limits to Arbitrage"
- Frazzini & Pedersen (2014): "Betting Against Beta"

信号构建:
- Quality Score = 0.30*ROE + 0.25*ROA + 0.25*GrossMarginStability + 0.20*LowLeverage
- LowVol Score = 0.50*InvVol60 + 0.50*InvVol120
- Composite = 0.60*Quality + 0.40*LowVol
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
# 配置
# ============================================================
QUALITY_LOWVOL_CONFIG = {
    # 质量因子权重
    'quality_weights': {
        'roe': 0.30,
        'roa': 0.25,
        'gross_margin_stability': 0.25,
        'low_leverage': 0.20,
    },
    # 低波动因子权重
    'lowvol_weights': {
        'inv_vol_60': 0.50,
        'inv_vol_120': 0.50,
    },
    # 复合权重
    'composite_weights': {
        'quality': 0.60,
        'lowvol': 0.40,
    },
    # 回测参数
    'rebalance_freq': 'ME',
    'top_n': 30,
    'bottom_n': 30,
}


# ============================================================
# 因子构建
# ============================================================
class QualityLowVolFactorBuilder:
    """
    质量+低波动因子构建器

    质量因子衡量公司基本面的稳健程度
    低波动因子利用低波动异象 (Low Volatility Anomaly)
    """

    def __init__(self, data_provider: FactorDataProvider = None):
        self.data_provider = data_provider or FactorDataProvider()
        self.calculator = FactorCalculator()
        self.logger = logging.getLogger(__name__)

    def build_quality_signal(
        self,
        symbols: List[str],
        date: str,
    ) -> pd.Series:
        """
        构建质量因子信号

        因子组成:
        1. ROE (净资产收益率) - 越高越好
        2. ROA (总资产收益率) - 越高越好
        3. 毛利率稳定性 - 过去4季度毛利率标准差的倒数
        4. 低杠杆 - 资产负债率的倒数
        """
        quality_factors = ['roe', 'roa', 'gross_profit_margin']
        factor_data = self.data_provider.get_factor_data(symbols, quality_factors, date)

        scores = pd.DataFrame(index=symbols)

        # ROE
        if 'roe' in factor_data.columns:
            scores['roe'] = self._winsorize_and_zscore(factor_data['roe'])

        # ROA
        if 'roa' in factor_data.columns:
            scores['roa'] = self._winsorize_and_zscore(factor_data['roa'])

        # 毛利率稳定性 (用当前毛利率水平作为代理，高毛利通常更稳定)
        if 'gross_profit_margin' in factor_data.columns:
            scores['gross_margin_stability'] = self._winsorize_and_zscore(
                factor_data['gross_profit_margin']
            )

        # 低杠杆 (用ROA/ROE比值近似，比值越高杠杆越低)
        if 'roe' in factor_data.columns and 'roa' in factor_data.columns:
            roe_vals = factor_data['roe'].replace(0, np.nan)
            leverage_inv = factor_data['roa'] / roe_vals
            scores['low_leverage'] = self._winsorize_and_zscore(leverage_inv)

        # 加权合成
        weights = QUALITY_LOWVOL_CONFIG['quality_weights']
        quality_signal = pd.Series(0.0, index=symbols)

        for factor, weight in weights.items():
            if factor in scores.columns:
                quality_signal += scores[factor].fillna(0) * weight

        return quality_signal.dropna()

    def build_lowvol_signal(
        self,
        symbols: List[str],
        date: str,
    ) -> pd.Series:
        """
        构建低波动因子信号

        低波动异象 (Low Volatility Anomaly):
        - 低波动股票的风险调整后收益高于高波动股票
        - 原因: 彩票偏好、杠杆约束、基准追踪

        使用波动率的倒数，使得低波动股票得分更高
        """
        # 获取价格数据
        end_date = pd.to_datetime(date)
        start_date = end_date - pd.Timedelta(days=180)

        prices = self.data_provider.get_price_data(
            symbols,
            start_date.strftime('%Y-%m-%d'),
            date
        )

        if prices.empty:
            return pd.Series(dtype=float)

        returns = prices.pct_change().dropna()

        scores = pd.DataFrame(index=symbols)

        # 60日波动率倒数
        if len(returns) >= 60:
            vol_60 = returns.iloc[-60:].std() * np.sqrt(252)
            inv_vol_60 = 1.0 / vol_60.replace(0, np.nan)
            scores['inv_vol_60'] = self._winsorize_and_zscore(inv_vol_60)

        # 120日波动率倒数
        if len(returns) >= 120:
            vol_120 = returns.iloc[-120:].std() * np.sqrt(252)
            inv_vol_120 = 1.0 / vol_120.replace(0, np.nan)
            scores['inv_vol_120'] = self._winsorize_and_zscore(inv_vol_120)

        # 加权合成
        weights = QUALITY_LOWVOL_CONFIG['lowvol_weights']
        lowvol_signal = pd.Series(0.0, index=symbols)

        for factor, weight in weights.items():
            if factor in scores.columns:
                lowvol_signal += scores[factor].fillna(0) * weight

        return lowvol_signal.dropna()

    def build_composite_signal(
        self,
        quality_signal: pd.Series,
        lowvol_signal: pd.Series,
    ) -> pd.Series:
        """
        构建复合信号: Quality + LowVol

        60% Quality + 40% LowVol (质量为主)
        """
        common = quality_signal.index.intersection(lowvol_signal.index)

        q_aligned = self._winsorize_and_zscore(quality_signal.loc[common])
        lv_aligned = self._winsorize_and_zscore(lowvol_signal.loc[common])

        weights = QUALITY_LOWVOL_CONFIG['composite_weights']
        composite = weights['quality'] * q_aligned + weights['lowvol'] * lv_aligned

        return composite

    def _winsorize_and_zscore(self, series: pd.Series) -> pd.Series:
        """去极值 + Z-score标准化"""
        s = series.copy().dropna()
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
class QualityLowVolBacktester:
    """
    Quality+LowVol 回测引擎

    与ValMomBacktester结构一致，方便对比
    """

    def __init__(
        self,
        config: StrategyConfig = None,
        factor_builder: QualityLowVolFactorBuilder = None,
    ):
        self.config = config or CONFIG
        self.factor_builder = factor_builder or QualityLowVolFactorBuilder()
        self.logger = logging.getLogger(__name__)

    def backtest_factor(
        self,
        factor_name: str,  # 'quality', 'lowvol', 'composite'
        start_date: str,
        end_date: str,
        rebalance_freq: str = 'ME',
        top_n: int = 30,
        bottom_n: int = 30,
        signal_weighted: bool = True,
    ) -> FactorBacktestResult:
        """
        单因子回测

        Args:
            factor_name: 'quality', 'lowvol', or 'composite'
        """
        self.logger.info(f"开始回测 {factor_name} 因子: {start_date} 至 {end_date}")

        dates = pd.date_range(start=start_date, end=end_date, freq=rebalance_freq)

        portfolio_value = 1.0
        equity_curve = pd.Series(index=dates, dtype=float)
        equity_curve.iloc[0] = portfolio_value
        returns_list = []
        prev_weights = None
        turnover_list = []

        for i in range(1, len(dates)):
            current_date = dates[i]
            prev_date = dates[i - 1]

            universe = self.factor_builder.data_provider.get_stock_universe(
                self.config.STOCK_UNIVERSE,
                prev_date.strftime('%Y-%m-%d')
            )

            # 构建信号
            signal = self._build_signal(factor_name, universe, prev_date)

            if signal.empty:
                equity_curve.iloc[i] = equity_curve.iloc[i - 1]
                continue

            # 构建权重
            weights = self._construct_weights(signal, top_n, bottom_n, signal_weighted)

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
            period_return = self._calc_return(
                weights, prev_date.strftime('%Y-%m-%d'), current_date.strftime('%Y-%m-%d')
            )

            portfolio_value *= (1 + period_return)
            equity_curve.iloc[i] = portfolio_value
            returns_list.append(period_return)

        returns_series = pd.Series(returns_list, index=dates[1:len(returns_list) + 1])
        result = self._calc_metrics(factor_name, start_date, end_date,
                                     equity_curve, returns_series, turnover_list)

        self.logger.info(
            f"{factor_name} 回测完成: 年化收益 {result.annualized_return * 100:.2f}%, "
            f"IR {result.information_ratio:.2f}"
        )
        return result

    def _build_signal(self, factor_name: str, universe: List[str], date) -> pd.Series:
        date_str = date.strftime('%Y-%m-%d')
        if factor_name == 'quality':
            return self.factor_builder.build_quality_signal(universe, date_str)
        elif factor_name == 'lowvol':
            return self.factor_builder.build_lowvol_signal(universe, date_str)
        elif factor_name == 'composite':
            q = self.factor_builder.build_quality_signal(universe, date_str)
            lv = self.factor_builder.build_lowvol_signal(universe, date_str)
            if q.empty or lv.empty:
                return pd.Series(dtype=float)
            return self.factor_builder.build_composite_signal(q, lv)
        else:
            raise ValueError(f"Unknown factor: {factor_name}")

    def _construct_weights(self, signal, top_n, bottom_n, signal_weighted):
        weights = pd.Series(0.0, index=signal.index)
        if signal_weighted:
            pos = signal[signal > 0]
            neg = signal[signal < 0]
            if len(pos) > 0:
                weights.loc[pos.index] = pos / pos.sum() * 0.5
            if len(neg) > 0:
                weights.loc[neg.index] = neg / neg.abs().sum() * (-0.5)
        else:
            sorted_sig = signal.sort_values(ascending=False)
            top = sorted_sig.head(top_n)
            bottom = sorted_sig.tail(bottom_n)
            weights.loc[top.index] = 0.5 / len(top)
            weights.loc[bottom.index] = -0.5 / len(bottom)
        return weights

    def _calc_return(self, weights, start_date, end_date):
        symbols = weights.index.tolist()
        prices = self.factor_builder.data_provider.get_price_data(symbols, start_date, end_date)
        if prices.empty or len(prices) < 2:
            return 0.0
        stock_returns = (prices.iloc[-1] / prices.iloc[0] - 1).fillna(0)
        return (weights * stock_returns).sum()

    def _calc_metrics(self, factor_name, start_date, end_date,
                      equity_curve, returns_series, turnover_list):
        total_return = equity_curve.dropna().iloc[-1] / equity_curve.dropna().iloc[0] - 1
        years = len(equity_curve.dropna()) / 12
        ann_ret = (1 + total_return) ** (1 / max(years, 0.01)) - 1
        vol = returns_series.std() * np.sqrt(12) if len(returns_series) > 0 else 0
        sharpe = ann_ret / vol if vol > 0 else 0
        downside = returns_series[returns_series < 0]
        ds_std = downside.std() * np.sqrt(12) if len(downside) > 0 else 0.0001
        sortino = ann_ret / ds_std if ds_std > 0 else 0
        cummax = equity_curve.dropna().cummax()
        dd = (equity_curve.dropna() - cummax) / cummax
        max_dd = dd.min()
        calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0

        return FactorBacktestResult(
            factor_name=factor_name,
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
def run_quality_lowvol_backtests(
    start_date: str = "2022-01-01",
    end_date: str = "2024-12-31",
    save_results: bool = True,
) -> Dict[str, FactorBacktestResult]:
    """
    运行 Quality+LowVol 回测

    回测三个因子:
    1. Quality (质量因子)
    2. LowVol (低波动因子)
    3. Composite (质量+低波动复合)
    """
    logger.info("=" * 70)
    logger.info("Quality + Low Volatility Backtest")
    logger.info("=" * 70)

    backtester = QualityLowVolBacktester()
    results = {}

    logger.info("\n[1/3] Running QUALITY factor backtest...")
    results['Quality'] = backtester.backtest_factor(
        'quality', start_date, end_date, rebalance_freq='ME'
    )

    logger.info("\n[2/3] Running LOW VOLATILITY factor backtest...")
    results['LowVol'] = backtester.backtest_factor(
        'lowvol', start_date, end_date, rebalance_freq='ME'
    )

    logger.info("\n[3/3] Running COMPOSITE (Quality+LowVol) backtest...")
    results['Composite'] = backtester.backtest_factor(
        'composite', start_date, end_date, rebalance_freq='ME'
    )

    # 打印汇总
    print("\n" + "=" * 90)
    print("Quality + Low Volatility Backtest Results")
    print("=" * 90)
    print(f"{'Factor':<12} {'Ann Return':<12} {'Volatility':<12} {'Sharpe':<10} {'IR':<10} {'Max DD':<10}")
    print("-" * 90)
    for name, r in results.items():
        print(f"{name:<12} {r.annualized_return*100:>10.2f}% {r.volatility*100:>10.2f}% "
              f"{r.sharpe_ratio:>9.2f} {r.information_ratio:>9.2f} {r.max_drawdown*100:>9.2f}%")
    print("=" * 90)

    if save_results:
        save_path = "backtests/quality_lowvol_results.json"
        data = {name: r.to_dict() for name, r in results.items()}
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"结果已保存: {save_path}")

        viz = ValMomVisualizer()
        viz.plot_equity_curves(results, "backtests/quality_lowvol_equity.png")
        viz.plot_drawdown(results, "backtests/quality_lowvol_drawdown.png")

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    results = run_quality_lowvol_backtests("2022-01-01", "2024-12-31")
