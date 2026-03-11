"""
Carry + Trend CTA策略
=====================
Carry + Trend Following Combined CTA Strategy

核心逻辑:
- Carry (期限结构收益): 利用期货升贴水获取展期收益
  - 近月 > 远月 (Backwardation): 做多获取正carry
  - 近月 < 远月 (Contango): 做空获取正carry
- Trend (趋势跟踪): 经典多时间框架趋势信号
- 组合: Carry和Trend信号低相关，组合可提升夏普

学术基础:
- Koijen, Moskowitz, Pedersen & Vrugt (2018):
  "Carry" - Journal of Financial Economics
- Moskowitz, Ooi & Pedersen (2012):
  "Time Series Momentum" - Journal of Financial Economics
- Baltas & Kosowski (2020):
  "Demystifying Time-Series Momentum Strategies"

信号构建:
- Carry Signal = Roll Yield (近月-远月)/远月 的Z-score
- Trend Signal = 加权多周期TSMOM (20/60/120日)
- Combined = 0.50 * Carry + 0.50 * Trend
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import json

from cta_signals import CTASignal, SignalDirection, FuturesDataProvider

logger = logging.getLogger(__name__)


# ============================================================
# 配置
# ============================================================
CARRY_TREND_CONFIG = {
    # Carry参数
    'carry_lookback': 60,           # carry信号计算回看期
    'roll_yield_annualize': 12,     # 展期收益年化系数

    # Trend参数
    'trend_lookback_periods': [20, 60, 120],
    'trend_weights': [0.50, 0.30, 0.20],

    # 组合参数
    'carry_weight': 0.50,
    'trend_weight': 0.50,

    # 波动率目标
    'volatility_target': 0.10,
    'max_leverage': 2.0,

    # 风控
    'stop_loss_atr': 2.5,
    'take_profit_atr': 4.0,

    # 品种
    'default_symbols': ['RB', 'CU', 'SC', 'TA', 'IF', 'IC', 'AL', 'M', 'Y', 'PP'],
}


# ============================================================
# Carry信号
# ============================================================
class CarrySignalGenerator:
    """
    Carry信号生成器

    期货市场中的Carry:
    - Backwardation (现货 > 期货): 正carry, 做多有利
    - Contango (现货 < 期货): 负carry, 做空有利

    由于真实近远月数据可能不可用，使用模拟方法:
    - 利用价格均线斜率作为carry的代理变量
    - 价格在均线上方 → 类似backwardation (做多)
    - 价格在均线下方 → 类似contango (做空)
    """

    def __init__(self, lookback: int = 60):
        self.lookback = lookback
        self.logger = logging.getLogger(__name__)

    def estimate_carry(self, prices: pd.Series) -> pd.Series:
        """
        估算Carry信号

        使用价格相对于长期均线的位置作为carry代理:
        - 高于均线 = 正carry (backwardation特征)
        - 低于均线 = 负carry (contango特征)

        额外考虑: 价格变化速度 (模拟展期收益变化)
        """
        if len(prices) < self.lookback:
            return pd.Series(dtype=float)

        # 方法1: 价格相对均线偏离
        ma = prices.rolling(self.lookback).mean()
        carry_proxy = (prices - ma) / ma

        # 方法2: 短期-长期均线差 (模拟近-远月价差)
        ma_short = prices.rolling(20).mean()
        ma_long = prices.rolling(self.lookback).mean()
        term_structure = (ma_short - ma_long) / ma_long

        # 综合 (等权)
        carry = 0.5 * carry_proxy + 0.5 * term_structure

        return carry

    def generate_signal(
        self,
        symbol: str,
        prices: pd.Series,
    ) -> Tuple[float, float]:
        """
        生成Carry信号

        Returns:
            (direction, strength)
            direction: +1 多, -1 空
            strength: 0-1
        """
        carry = self.estimate_carry(prices)
        if carry.empty or carry.isna().all():
            return 0.0, 0.0

        current_carry = carry.iloc[-1]
        if np.isnan(current_carry):
            return 0.0, 0.0

        # Z-score标准化
        carry_mean = carry.dropna().mean()
        carry_std = carry.dropna().std()
        if carry_std > 0:
            z = (current_carry - carry_mean) / carry_std
        else:
            z = 0

        # 信号方向
        direction = np.sign(z)
        strength = min(abs(z) / 2, 1.0)

        return direction, strength


# ============================================================
# Trend信号
# ============================================================
class TrendSignalGenerator:
    """
    多时间框架趋势信号

    经典TSMOM方法:
    - 多周期动量 (20/60/120日)
    - 加权平均
    - 波动率调整仓位
    """

    def __init__(
        self,
        lookback_periods: List[int] = None,
        weights: List[float] = None,
    ):
        self.lookback_periods = lookback_periods or [20, 60, 120]
        self.weights = weights or [0.50, 0.30, 0.20]

    def generate_signal(
        self,
        symbol: str,
        prices: pd.Series,
    ) -> Tuple[float, float]:
        """
        生成趋势信号

        Returns:
            (direction, strength)
        """
        if len(prices) < max(self.lookback_periods):
            return 0.0, 0.0

        # 多周期动量
        weighted_mom = 0
        for period, weight in zip(self.lookback_periods, self.weights):
            if len(prices) >= period:
                ret = prices.iloc[-1] / prices.iloc[-period] - 1
                weighted_mom += ret * weight

        # 方向和强度
        direction = np.sign(weighted_mom)
        strength = min(abs(weighted_mom) / 0.10, 1.0)

        return direction, strength


# ============================================================
# Carry + Trend组合
# ============================================================
class CarryTrendCTA:
    """
    Carry + Trend 组合CTA策略

    将Carry和Trend两类信号组合:
    - 当两者方向一致时，信号更强
    - 当两者方向矛盾时，取加权平均
    - 波动率目标化仓位管理
    """

    def __init__(self, config: dict = None):
        self.config = config or CARRY_TREND_CONFIG
        self.carry_gen = CarrySignalGenerator(self.config['carry_lookback'])
        self.trend_gen = TrendSignalGenerator(
            self.config['trend_lookback_periods'],
            self.config['trend_weights'],
        )
        self.logger = logging.getLogger(__name__)

    def generate_signal(
        self,
        symbol: str,
        prices: pd.Series,
        current_date: datetime = None,
    ) -> CTASignal:
        """生成Carry+Trend组合信号"""
        if current_date is None:
            current_date = prices.index[-1] if hasattr(prices.index[-1], 'strftime') else datetime.now()

        # 获取子信号
        carry_dir, carry_str = self.carry_gen.generate_signal(symbol, prices)
        trend_dir, trend_str = self.trend_gen.generate_signal(symbol, prices)

        # 加权组合
        carry_w = self.config['carry_weight']
        trend_w = self.config['trend_weight']

        combined_signal = (
            carry_dir * carry_str * carry_w
            + trend_dir * trend_str * trend_w
        )
        combined_strength = carry_str * carry_w + trend_str * trend_w

        # 方向
        if combined_signal > 0.10:
            direction = SignalDirection.LONG
        elif combined_signal < -0.10:
            direction = SignalDirection.SHORT
        else:
            direction = SignalDirection.FLAT

        # 波动率目标化
        returns = prices.pct_change().dropna()
        vol = returns.iloc[-20:].std() * np.sqrt(252) if len(returns) >= 20 else 0.20
        vol_scalar = self.config['volatility_target'] / max(vol, 0.05)
        vol_scalar = min(vol_scalar, self.config['max_leverage'])
        target_position = np.clip(combined_signal * vol_scalar, -1, 1)

        # 止损止盈 (基于ATR)
        current_price = prices.iloc[-1]
        atr_val = self._calc_atr(prices)
        stop_loss = None
        take_profit = None
        if direction == SignalDirection.LONG:
            stop_loss = current_price - self.config['stop_loss_atr'] * atr_val
            take_profit = current_price + self.config['take_profit_atr'] * atr_val
        elif direction == SignalDirection.SHORT:
            stop_loss = current_price + self.config['stop_loss_atr'] * atr_val
            take_profit = current_price - self.config['take_profit_atr'] * atr_val

        return CTASignal(
            symbol=symbol,
            date=current_date,
            signal=direction,
            strength=min(combined_strength, 1.0),
            target_position=target_position,
            volatility=vol,
            expected_return=abs(combined_signal) * vol * 0.4,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def generate_signals(
        self,
        data: Dict[str, pd.DataFrame],
        current_date: datetime = None,
    ) -> List[CTASignal]:
        """批量生成信号"""
        signals = []
        for symbol, df in data.items():
            prices = df['close'] if 'close' in df.columns else df.iloc[:, 0]
            if len(prices) >= max(self.config['trend_lookback_periods']):
                sig = self.generate_signal(symbol, prices, current_date)
                signals.append(sig)
        signals.sort(key=lambda x: abs(x.strength), reverse=True)
        return signals

    def _calc_atr(self, prices: pd.Series, window: int = 14) -> float:
        if len(prices) < window + 1:
            return prices.std() if len(prices) > 1 else prices.iloc[-1] * 0.02
        high = prices * 1.01
        low = prices * 0.99
        tr = pd.concat([high - low, (high - prices.shift()).abs(), (low - prices.shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(window).mean().iloc[-1]
        return atr if not np.isnan(atr) else prices.std()


# ============================================================
# 回测引擎
# ============================================================
class CarryTrendBacktester:
    """Carry+Trend CTA回测引擎"""

    def __init__(
        self,
        symbols: List[str] = None,
        config: dict = None,
    ):
        self.config = config or CARRY_TREND_CONFIG
        self.symbols = symbols or self.config['default_symbols']
        self.strategy = CarryTrendCTA(self.config)
        self.data_provider = FuturesDataProvider()
        self.logger = logging.getLogger(__name__)

    def run_backtest(
        self,
        start_date: str = "2022-01-01",
        end_date: str = "2024-12-31",
        rebalance_freq: str = 'W-MON',
    ) -> Dict:
        """运行Carry+Trend CTA回测"""
        self.logger.info(f"Carry+Trend CTA回测: {start_date} 至 {end_date}")

        # 获取数据 (带回看期)
        lookback_start = pd.to_datetime(start_date) - pd.Timedelta(days=180)
        all_data = {}
        for sym in self.symbols:
            df = self.data_provider.get_futures_data(
                sym, lookback_start.strftime('%Y-%m-%d'), end_date
            )
            if not df.empty:
                all_data[sym] = df

        if not all_data:
            return {}

        # 周度再平衡
        dates = pd.date_range(start=start_date, end=end_date, freq=rebalance_freq)
        portfolio_value = 1.0
        equity = [1.0]
        period_returns = []
        trade_count = 0
        win_count = 0
        carry_signals_history = []
        trend_signals_history = []

        for i in range(1, len(dates)):
            date = dates[i]
            prev_date = dates[i - 1]

            current_data = {}
            for sym, df in all_data.items():
                mask = df.index <= date
                if mask.any():
                    current_data[sym] = df.loc[mask]

            signals = self.strategy.generate_signals(current_data, date)
            active = [s for s in signals if s.signal != SignalDirection.FLAT]

            # 计算周期收益
            period_pnl = 0
            for sig in active:
                sym = sig.symbol
                if sym in current_data:
                    df = current_data[sym]
                    prices = df['close'] if 'close' in df.columns else df.iloc[:, 0]
                    mask_period = (prices.index > prev_date) & (prices.index <= date)
                    period_prices = prices[mask_period]
                    if len(period_prices) >= 2:
                        ret = period_prices.iloc[-1] / period_prices.iloc[0] - 1
                    elif len(period_prices) == 1 and len(prices[prices.index <= prev_date]) > 0:
                        prev_price = prices[prices.index <= prev_date].iloc[-1]
                        ret = period_prices.iloc[-1] / prev_price - 1
                    else:
                        ret = 0

                    pnl = sig.target_position * ret
                    period_pnl += pnl / max(len(active), 1)
                    trade_count += 1
                    if pnl > 0:
                        win_count += 1

            portfolio_value *= (1 + period_pnl)
            equity.append(portfolio_value)
            period_returns.append(period_pnl)

        # 计算指标
        equity_series = pd.Series(equity, index=dates[:len(equity)])
        returns_series = pd.Series(period_returns, index=dates[1:len(period_returns) + 1])

        total_return = portfolio_value - 1
        years = len(returns_series) / 52  # 周度数据
        ann_ret = (1 + total_return) ** (1 / max(years, 0.01)) - 1
        vol = returns_series.std() * np.sqrt(52)
        sharpe = ann_ret / vol if vol > 0 else 0
        cummax = equity_series.cummax()
        dd = (equity_series - cummax) / cummax
        max_dd = dd.min()
        calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0
        win_rate = win_count / max(trade_count, 1)

        return {
            'strategy': 'Carry + Trend CTA',
            'start_date': start_date,
            'end_date': end_date,
            'total_return': total_return,
            'annualized_return': ann_ret,
            'volatility': vol,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'calmar_ratio': calmar,
            'total_trades': trade_count,
            'win_rate': win_rate,
            'equity_curve': equity_series,
            'returns_series': returns_series,
        }


# ============================================================
# 便捷入口
# ============================================================
def run_carry_trend_backtest(
    start_date: str = "2022-01-01",
    end_date: str = "2024-12-31",
    symbols: List[str] = None,
    save_results: bool = True,
) -> Dict:
    """运行Carry+Trend CTA回测"""
    logger.info("=" * 70)
    logger.info("Carry + Trend CTA Backtest")
    logger.info("=" * 70)

    backtester = CarryTrendBacktester(symbols=symbols)
    result = backtester.run_backtest(start_date, end_date)

    if not result:
        return {}

    print("\n" + "=" * 70)
    print("Carry + Trend CTA Results")
    print("=" * 70)
    print(f"  年化收益率:  {result['annualized_return'] * 100:>8.2f}%")
    print(f"  年化波动率:  {result['volatility'] * 100:>8.2f}%")
    print(f"  夏普比率:    {result['sharpe_ratio']:>8.2f}")
    print(f"  最大回撤:    {result['max_drawdown'] * 100:>8.2f}%")
    print(f"  Calmar比率:  {result['calmar_ratio']:>8.2f}")
    print(f"  总交易次数:  {result['total_trades']:>8}")
    print(f"  胜率:        {result['win_rate'] * 100:>8.2f}%")
    print("=" * 70)

    if save_results:
        save_data = {k: v for k, v in result.items()
                     if not isinstance(v, (pd.Series, pd.DataFrame))}
        with open("backtests/carry_trend_cta_results.json", 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        logger.info("结果已保存: backtests/carry_trend_cta_results.json")

    return result


def get_carry_trend_signals(
    symbols: List[str] = None,
    api_key: str = None,
) -> Dict[str, CTASignal]:
    """
    获取当前Carry+Trend CTA信号

    Example:
        >>> signals = get_carry_trend_signals(['RB', 'CU', 'SC', 'IF'])
        >>> for sym, sig in signals.items():
        ...     print(f"{sym}: {sig.signal.name}, Position: {sig.target_position:.2f}")
    """
    if symbols is None:
        symbols = CARRY_TREND_CONFIG['default_symbols']

    provider = FuturesDataProvider(api_key)
    strategy = CarryTrendCTA()

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - pd.Timedelta(days=180)).strftime('%Y-%m-%d')

    data = {}
    for sym in symbols:
        df = provider.get_futures_data(sym, start_date, end_date)
        if not df.empty:
            data[sym] = df

    signals = strategy.generate_signals(data)
    return {sig.symbol: sig for sig in signals}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

    print("=" * 70)
    print("Carry + Trend CTA策略测试")
    print("=" * 70)

    result = run_carry_trend_backtest("2022-01-01", "2024-12-31")

    print("\n当前信号:")
    signals = get_carry_trend_signals()
    for sym, sig in signals.items():
        print(f"  {sym}: {sig.signal.name} | Position: {sig.target_position:.2f} | Strength: {sig.strength:.2f}")
