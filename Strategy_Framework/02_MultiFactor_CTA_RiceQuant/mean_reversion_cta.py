"""
均值回归CTA策略
===============
Mean Reversion CTA Strategy

核心逻辑:
- 短周期反转: 当价格偏离短期均值过远时，预期回归
- 布林带突破回归: 价格触及布林带外轨后回归中轨
- RSI超买超卖: RSI极端值后的回归
- 跨品种价差回归: 相关品种价差偏离均值后回归

与趋势跟踪CTA形成互补:
- 趋势策略在趋势市中盈利，震荡市中亏损
- 均值回归在震荡市中盈利，趋势市中亏损
- 两者组合可以平滑收益曲线

学术基础:
- Poterba & Summers (1988): "Mean Reversion in Stock Prices"
- Baltas & Kosowski (2013): "Momentum and Mean Reversion in Strategic Asset Allocation"
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import logging

from cta_signals import CTASignal, SignalDirection, FuturesDataProvider

logger = logging.getLogger(__name__)


# ============================================================
# 配置
# ============================================================
MEAN_REVERSION_CONFIG = {
    # 布林带参数
    'bb_window': 20,
    'bb_std': 2.0,

    # RSI参数
    'rsi_window': 14,
    'rsi_overbought': 70,
    'rsi_oversold': 30,

    # Z-score参数
    'zscore_window': 20,
    'zscore_entry': 2.0,      # 入场阈值
    'zscore_exit': 0.5,       # 出场阈值

    # 持仓限制
    'max_holding_days': 10,    # 最大持仓天数 (均值回归是短周期)
    'stop_loss_atr': 1.5,     # ATR止损倍数
    'take_profit_atr': 2.0,   # ATR止盈倍数

    # 信号权重
    'signal_weights': {
        'bollinger': 0.35,
        'rsi': 0.30,
        'zscore': 0.35,
    },

    # 波动率目标
    'volatility_target': 0.10,
}


# ============================================================
# 技术指标计算
# ============================================================
class TechnicalIndicators:
    """技术指标计算工具"""

    @staticmethod
    def bollinger_bands(
        prices: pd.Series,
        window: int = 20,
        num_std: float = 2.0,
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        布林带

        Returns:
            (upper_band, middle_band, lower_band)
        """
        middle = prices.rolling(window).mean()
        std = prices.rolling(window).std()
        upper = middle + num_std * std
        lower = middle - num_std * std
        return upper, middle, lower

    @staticmethod
    def rsi(prices: pd.Series, window: int = 14) -> pd.Series:
        """
        RSI (Relative Strength Index)
        """
        delta = prices.diff()
        gain = delta.where(delta > 0, 0)
        loss = (-delta).where(delta < 0, 0)

        avg_gain = gain.rolling(window).mean()
        avg_loss = loss.rolling(window).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def zscore(prices: pd.Series, window: int = 20) -> pd.Series:
        """
        价格Z-score (价格偏离均值的标准差倍数)
        """
        mean = prices.rolling(window).mean()
        std = prices.rolling(window).std()
        return (prices - mean) / std.replace(0, np.nan)

    @staticmethod
    def atr(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        window: int = 14,
    ) -> pd.Series:
        """ATR (Average True Range)"""
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window).mean()


# ============================================================
# 均值回归信号生成器
# ============================================================
class BollingerReversionSignal:
    """
    布林带均值回归信号

    当价格触及布林带外轨时，预期回归中轨:
    - 价格 > 上轨: 做空 (预期回落)
    - 价格 < 下轨: 做多 (预期反弹)
    - 信号强度与偏离程度成正比
    """

    def __init__(self, window: int = 20, num_std: float = 2.0):
        self.window = window
        self.num_std = num_std
        self.indicators = TechnicalIndicators()

    def generate(self, prices: pd.Series) -> Tuple[float, float]:
        """
        Returns:
            (signal_direction, signal_strength)
            direction: +1 多, -1 空, 0 平
            strength: 0-1
        """
        if len(prices) < self.window + 5:
            return 0.0, 0.0

        upper, middle, lower = self.indicators.bollinger_bands(
            prices, self.window, self.num_std
        )

        current = prices.iloc[-1]
        up = upper.iloc[-1]
        mid = middle.iloc[-1]
        low = lower.iloc[-1]

        if np.isnan(up) or np.isnan(low):
            return 0.0, 0.0

        band_width = up - low
        if band_width <= 0:
            return 0.0, 0.0

        if current > up:
            # 超买 -> 做空
            deviation = (current - up) / band_width
            strength = min(deviation * 2, 1.0)
            return -1.0, strength
        elif current < low:
            # 超卖 -> 做多
            deviation = (low - current) / band_width
            strength = min(deviation * 2, 1.0)
            return 1.0, strength
        else:
            # 在通道内 -> 平仓信号
            return 0.0, 0.0


class RSIReversionSignal:
    """
    RSI均值回归信号

    RSI极端值预示均值回归:
    - RSI > 70: 超买，预期回落
    - RSI < 30: 超卖，预期反弹
    """

    def __init__(self, window: int = 14, overbought: float = 70, oversold: float = 30):
        self.window = window
        self.overbought = overbought
        self.oversold = oversold
        self.indicators = TechnicalIndicators()

    def generate(self, prices: pd.Series) -> Tuple[float, float]:
        if len(prices) < self.window + 5:
            return 0.0, 0.0

        rsi = self.indicators.rsi(prices, self.window)
        current_rsi = rsi.iloc[-1]

        if np.isnan(current_rsi):
            return 0.0, 0.0

        if current_rsi > self.overbought:
            strength = min((current_rsi - self.overbought) / 30, 1.0)
            return -1.0, strength
        elif current_rsi < self.oversold:
            strength = min((self.oversold - current_rsi) / 30, 1.0)
            return 1.0, strength
        else:
            return 0.0, 0.0


class ZScoreReversionSignal:
    """
    Z-Score均值回归信号

    价格偏离短期均值超过N个标准差时，预期回归:
    - Z > +2: 做空
    - Z < -2: 做多
    - |Z| < 0.5: 平仓
    """

    def __init__(self, window: int = 20, entry_threshold: float = 2.0, exit_threshold: float = 0.5):
        self.window = window
        self.entry_threshold = entry_threshold
        self.exit_threshold = exit_threshold
        self.indicators = TechnicalIndicators()

    def generate(self, prices: pd.Series) -> Tuple[float, float]:
        if len(prices) < self.window + 5:
            return 0.0, 0.0

        z = self.indicators.zscore(prices, self.window)
        current_z = z.iloc[-1]

        if np.isnan(current_z):
            return 0.0, 0.0

        if current_z > self.entry_threshold:
            strength = min((current_z - self.entry_threshold) / 2, 1.0)
            return -1.0, strength
        elif current_z < -self.entry_threshold:
            strength = min((-current_z - self.entry_threshold) / 2, 1.0)
            return 1.0, strength
        else:
            return 0.0, 0.0


# ============================================================
# 均值回归CTA聚合器
# ============================================================
class MeanReversionCTA:
    """
    均值回归CTA策略

    聚合多个均值回归信号，生成综合CTA交易建议
    """

    def __init__(self, config: dict = None):
        self.config = config or MEAN_REVERSION_CONFIG
        self.bb_signal = BollingerReversionSignal(
            self.config['bb_window'], self.config['bb_std']
        )
        self.rsi_signal = RSIReversionSignal(
            self.config['rsi_window'],
            self.config['rsi_overbought'],
            self.config['rsi_oversold'],
        )
        self.zscore_signal = ZScoreReversionSignal(
            self.config['zscore_window'],
            self.config['zscore_entry'],
            self.config['zscore_exit'],
        )
        self.indicators = TechnicalIndicators()
        self.logger = logging.getLogger(__name__)

    def generate_signal(
        self,
        symbol: str,
        prices: pd.Series,
        current_date: datetime = None,
    ) -> CTASignal:
        """
        生成单品种均值回归信号
        """
        if current_date is None:
            current_date = prices.index[-1]

        # 获取各子信号
        bb_dir, bb_str = self.bb_signal.generate(prices)
        rsi_dir, rsi_str = self.rsi_signal.generate(prices)
        z_dir, z_str = self.zscore_signal.generate(prices)

        # 加权聚合
        weights = self.config['signal_weights']
        weighted_signal = (
            bb_dir * bb_str * weights['bollinger']
            + rsi_dir * rsi_str * weights['rsi']
            + z_dir * z_str * weights['zscore']
        )
        total_strength = (
            bb_str * weights['bollinger']
            + rsi_str * weights['rsi']
            + z_str * weights['zscore']
        )

        # 信号方向
        if weighted_signal > 0.15:
            direction = SignalDirection.LONG
        elif weighted_signal < -0.15:
            direction = SignalDirection.SHORT
        else:
            direction = SignalDirection.FLAT

        # 波动率调整仓位
        vol = prices.pct_change().dropna().iloc[-20:].std() * np.sqrt(252) if len(prices) > 20 else 0.20
        vol_scalar = self.config['volatility_target'] / max(vol, 0.05)
        target_position = np.clip(weighted_signal * vol_scalar, -1, 1)

        # 止损止盈 (基于ATR)
        current_price = prices.iloc[-1]
        # 模拟ATR
        atr_val = prices.rolling(14).apply(
            lambda x: (x.max() - x.min()) if len(x) >= 2 else 0
        ).iloc[-1] if len(prices) > 14 else current_price * 0.02

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
            strength=min(total_strength, 1.0),
            target_position=target_position,
            volatility=vol,
            expected_return=abs(weighted_signal) * vol * 0.3,
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
            if len(prices) >= 30:
                sig = self.generate_signal(symbol, prices, current_date)
                signals.append(sig)
        signals.sort(key=lambda x: abs(x.strength), reverse=True)
        return signals


# ============================================================
# 回测引擎
# ============================================================
class MeanReversionBacktester:
    """均值回归CTA回测引擎"""

    def __init__(
        self,
        symbols: List[str] = None,
        config: dict = None,
    ):
        self.symbols = symbols or ['RB', 'CU', 'SC', 'TA', 'IF', 'IC', 'AL', 'M']
        self.config = config or MEAN_REVERSION_CONFIG
        self.strategy = MeanReversionCTA(self.config)
        self.data_provider = FuturesDataProvider()
        self.logger = logging.getLogger(__name__)

    def run_backtest(
        self,
        start_date: str = "2022-01-01",
        end_date: str = "2024-12-31",
    ) -> Dict:
        """
        运行均值回归CTA回测
        """
        self.logger.info(f"均值回归CTA回测: {start_date} 至 {end_date}")

        # 获取数据
        all_data = {}
        for sym in self.symbols:
            # 获取更长历史 (回看期需要)
            lookback_start = pd.to_datetime(start_date) - pd.Timedelta(days=60)
            df = self.data_provider.get_futures_data(
                sym, lookback_start.strftime('%Y-%m-%d'), end_date
            )
            if not df.empty:
                all_data[sym] = df

        if not all_data:
            self.logger.error("无可用数据")
            return {}

        # 生成每日信号并模拟交易
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        portfolio_value = 1.0
        equity = [1.0]
        daily_returns = []
        trade_count = 0
        win_count = 0

        for i in range(1, len(dates)):
            date = dates[i]

            # 截取到当前日期的数据
            current_data = {}
            for sym, df in all_data.items():
                mask = df.index <= date
                if mask.any():
                    current_data[sym] = df.loc[mask]

            # 生成信号
            signals = self.strategy.generate_signals(current_data, date)

            # 计算组合日收益 (基于信号的模拟)
            daily_pnl = 0
            active_signals = [s for s in signals if s.signal != SignalDirection.FLAT]

            for sig in active_signals:
                sym = sig.symbol
                if sym in current_data and len(current_data[sym]) >= 2:
                    df = current_data[sym]
                    prices = df['close'] if 'close' in df.columns else df.iloc[:, 0]
                    if len(prices) >= 2:
                        ret = prices.iloc[-1] / prices.iloc[-2] - 1
                        # 均值回归: 做反向
                        pnl = sig.target_position * ret
                        daily_pnl += pnl / max(len(active_signals), 1)
                        trade_count += 1
                        if pnl > 0:
                            win_count += 1

            portfolio_value *= (1 + daily_pnl)
            equity.append(portfolio_value)
            daily_returns.append(daily_pnl)

        # 计算指标
        equity_series = pd.Series(equity, index=dates[:len(equity)])
        returns_series = pd.Series(daily_returns, index=dates[1:len(daily_returns) + 1])

        total_return = portfolio_value - 1
        years = len(dates) / 252
        ann_ret = (1 + total_return) ** (1 / max(years, 0.01)) - 1
        vol = returns_series.std() * np.sqrt(252) if len(returns_series) > 0 else 0
        sharpe = ann_ret / vol if vol > 0 else 0
        cummax = equity_series.cummax()
        dd = (equity_series - cummax) / cummax
        max_dd = dd.min()
        win_rate = win_count / max(trade_count, 1)

        result = {
            'strategy': 'Mean Reversion CTA',
            'start_date': start_date,
            'end_date': end_date,
            'total_return': total_return,
            'annualized_return': ann_ret,
            'volatility': vol,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'total_trades': trade_count,
            'win_rate': win_rate,
            'equity_curve': equity_series,
            'returns_series': returns_series,
        }

        return result


# ============================================================
# 便捷入口
# ============================================================
def run_mean_reversion_backtest(
    start_date: str = "2022-01-01",
    end_date: str = "2024-12-31",
    symbols: List[str] = None,
    save_results: bool = True,
) -> Dict:
    """运行均值回归CTA回测"""
    logger.info("=" * 70)
    logger.info("Mean Reversion CTA Backtest")
    logger.info("=" * 70)

    backtester = MeanReversionBacktester(symbols=symbols)
    result = backtester.run_backtest(start_date, end_date)

    if not result:
        return {}

    # 打印结果
    print("\n" + "=" * 70)
    print("Mean Reversion CTA Results")
    print("=" * 70)
    print(f"  年化收益率:  {result['annualized_return'] * 100:>8.2f}%")
    print(f"  年化波动率:  {result['volatility'] * 100:>8.2f}%")
    print(f"  夏普比率:    {result['sharpe_ratio']:>8.2f}")
    print(f"  最大回撤:    {result['max_drawdown'] * 100:>8.2f}%")
    print(f"  总交易次数:  {result['total_trades']:>8}")
    print(f"  胜率:        {result['win_rate'] * 100:>8.2f}%")
    print("=" * 70)

    if save_results:
        import json
        save_data = {k: v for k, v in result.items()
                     if not isinstance(v, (pd.Series, pd.DataFrame))}
        with open("backtests/mean_reversion_cta_results.json", 'w', encoding='utf-8') as f:
            json.dump(save_data, f, indent=2, ensure_ascii=False)
        logger.info("结果已保存: backtests/mean_reversion_cta_results.json")

    return result


def get_mean_reversion_signals(
    symbols: List[str] = None,
    api_key: str = None,
) -> Dict[str, CTASignal]:
    """
    获取当前均值回归CTA信号

    Example:
        >>> signals = get_mean_reversion_signals(['RB', 'CU', 'SC'])
        >>> for sym, sig in signals.items():
        ...     print(f"{sym}: {sig.signal.name}, Strength: {sig.strength:.2f}")
    """
    if symbols is None:
        symbols = ['RB', 'CU', 'SC', 'TA', 'IF', 'IC']

    provider = FuturesDataProvider(api_key)
    strategy = MeanReversionCTA()

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - pd.Timedelta(days=90)).strftime('%Y-%m-%d')

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
    print("均值回归CTA策略测试")
    print("=" * 70)

    # 回测
    result = run_mean_reversion_backtest("2022-01-01", "2024-12-31")

    # 当前信号
    print("\n当前信号:")
    signals = get_mean_reversion_signals()
    for sym, sig in signals.items():
        print(f"  {sym}: {sig.signal.name} | Position: {sig.target_position:.2f} | Strength: {sig.strength:.2f}")
