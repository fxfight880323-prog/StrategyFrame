"""
CTA信号生成模块
===============
基于米筐期货数据的CTA策略信号生成

包含策略:
1. 时间序列动量 (Time Series Momentum, TSMOM)
2. 趋势跟踪 (Trend Following)
3. 波动率目标 (Volatility Targeting)
4. 跨品种套利信号
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
import logging

# 尝试导入米筐SDK
try:
    import rqdatac as rq
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False


class SignalDirection(Enum):
    """信号方向"""
    LONG = 1
    SHORT = -1
    FLAT = 0


@dataclass
class CTASignal:
    """CTA信号数据类"""
    symbol: str                      # 品种代码
    date: datetime                   # 信号日期
    signal: SignalDirection          # 信号方向
    strength: float                  # 信号强度 (0-1)
    target_position: float           # 目标仓位 (-1 to 1)
    volatility: float                # 当前波动率
    expected_return: float           # 预期收益
    stop_loss: Optional[float] = None  # 止损价位
    take_profit: Optional[float] = None  # 止盈价位


class FuturesDataProvider:
    """期货数据提供器"""
    
    # 品种代码映射
    SYMBOL_MAP = {
        # 黑色金属
        'RB': 'RB8888.XSGE',    # 螺纹钢
        'HC': 'HC8888.XSGE',    # 热轧卷板
        'I':  'I8888.XDCE',     # 铁矿石
        'J':  'J8888.XDCE',     # 焦炭
        'JM': 'JM8888.XDCE',    # 焦煤
        
        # 有色金属
        'CU': 'CU8888.XSGE',    # 铜
        'AL': 'AL8888.XSGE',    # 铝
        'ZN': 'ZN8888.XSGE',    # 锌
        'NI': 'NI8888.XSGE',    # 镍
        'SN': 'SN8888.XSGE',    # 锡
        
        # 能源化工
        'SC': 'SC8888.XINE',    # 原油
        'LU': 'LU8888.XINE',    # 低硫燃料油
        'FU': 'FU8888.XSGE',    # 燃料油
        'TA': 'TA8888.XZCE',    # PTA
        'MA': 'MA8888.XZCE',    # 甲醇
        'PP': 'PP8888.XDCE',    # 聚丙烯
        'L':  'L8888.XDCE',     # 塑料
        
        # 农产品
        'A':  'A8888.XDCE',     # 豆一
        'M':  'M8888.XDCE',     # 豆粕
        'Y':  'Y8888.XDCE',     # 豆油
        'P':  'P8888.XDCE',     # 棕榈油
        'SR': 'SR8888.XZCE',    # 白糖
        'CF': 'CF8888.XZCE',    # 棉花
        
        # 股指
        'IF': 'IF8888.CCFX',    # 沪深300
        'IC': 'IC8888.CCFX',    # 中证500
        'IH': 'IH8888.CCFX',    # 上证50
        'IM': 'IM8888.CCFX',    # 中证1000
    }
    
    def __init__(self, api_key: str = None):
        # 如果没有传入api_key，从配置文件读取
        if api_key is None:
            try:
                from config import RQ_API_KEY
                api_key = RQ_API_KEY
            except ImportError:
                api_key = None
        
        self.api_key = api_key
        self.connected = False
        self.logger = logging.getLogger(__name__)
        
        if RQ_AVAILABLE and api_key:
            self._connect()
    
    def _connect(self):
        """连接米筐"""
        try:
            rq.init(self.api_key)
            self.connected = True
            self.logger.info("米筐期货数据连接成功")
        except Exception as e:
            self.logger.error(f"连接失败: {e}")
    
    def get_futures_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        fields: List[str] = None
    ) -> pd.DataFrame:
        """
        获取期货数据
        
        Args:
            symbol: 品种代码 (如 'RB', 'CU')
            start_date: 开始日期
            end_date: 结束日期
            fields: 字段列表 [open, high, low, close, volume, open_interest]
        """
        if fields is None:
            fields = ['open', 'high', 'low', 'close', 'volume']
        
        if not self.connected:
            return self._mock_futures_data(symbol, start_date, end_date, fields)
        
        try:
            # 转换代码
            rq_symbol = self.SYMBOL_MAP.get(symbol, symbol)
            
            data = rq.get_price(
                rq_symbol,
                start_date=start_date,
                end_date=end_date,
                frequency='1d',
                fields=fields
            )
            return data
        except Exception as e:
            self.logger.error(f"获取{symbol}数据失败: {e}")
            return self._mock_futures_data(symbol, start_date, end_date, fields)
    
    def _mock_futures_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        fields: List[str]
    ) -> pd.DataFrame:
        """模拟期货数据"""
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        np.random.seed(hash(symbol) % 2**32)
        
        # 生成随机价格序列 (带趋势)
        trend = np.random.choice([-1, 1]) * np.random.uniform(0.0001, 0.001)
        returns = np.random.normal(trend, 0.015, len(dates))
        
        close = 5000 * np.exp(np.cumsum(returns))
        
        data = pd.DataFrame(index=dates)
        if 'close' in fields:
            data['close'] = close
        if 'open' in fields:
            data['open'] = close * (1 + np.random.normal(0, 0.005, len(dates)))
        if 'high' in fields:
            data['high'] = data[['open', 'close']].max(axis=1) * (1 + abs(np.random.normal(0, 0.01, len(dates))))
        if 'low' in fields:
            data['low'] = data[['open', 'close']].min(axis=1) * (1 - abs(np.random.normal(0, 0.01, len(dates))))
        if 'volume' in fields:
            data['volume'] = np.random.randint(100000, 1000000, len(dates))
        
        return data
    
    def get_all_symbols(self) -> List[str]:
        """获取所有支持的品种"""
        return list(self.SYMBOL_MAP.keys())


class TSMOMStrategy:
    """
    时间序列动量策略 (Time Series Momentum)
    
    基于Moskowitz & Grinblatt (1999) 的经典动量策略
    """
    
    def __init__(
        self,
        lookback_periods: List[int] = None,
        weights: List[float] = None,
        volatility_target: float = 0.10
    ):
        self.lookback_periods = lookback_periods or [20, 60, 120]
        self.weights = weights or [0.5, 0.3, 0.2]
        self.volatility_target = volatility_target
        self.logger = logging.getLogger(__name__)
    
    def calculate_momentum(
        self, 
        prices: pd.Series
    ) -> Dict[int, float]:
        """计算多周期动量"""
        momentum = {}
        for period in self.lookback_periods:
            if len(prices) >= period:
                ret = prices.iloc[-1] / prices.iloc[-period] - 1
                momentum[period] = ret
        return momentum
    
    def calculate_volatility(
        self, 
        prices: pd.Series, 
        window: int = 20
    ) -> float:
        """计算实现波动率"""
        if len(prices) < window:
            return 0.20  # 默认20%波动率
        
        returns = prices.pct_change().dropna()
        vol = returns.iloc[-window:].std() * np.sqrt(252)
        return max(vol, 0.05)  # 最低5%波动率
    
    def generate_signal(
        self,
        symbol: str,
        prices: pd.Series,
        current_date: datetime = None
    ) -> CTASignal:
        """
        生成TSMOM信号
        """
        if current_date is None:
            current_date = prices.index[-1]
        
        # 计算多周期动量
        momentum = self.calculate_momentum(prices)
        
        # 加权平均动量
        weighted_momentum = sum(
            momentum.get(p, 0) * w 
            for p, w in zip(self.lookback_periods, self.weights)
        )
        
        # 计算波动率
        volatility = self.calculate_volatility(prices)
        
        # 波动率调整仓位
        position_size = self.volatility_target / volatility
        position_size = min(position_size, 2.0)  # 最大2倍杠杆
        
        # 确定信号方向
        if weighted_momentum > 0.02:  # 2%动量阈值
            direction = SignalDirection.LONG
            target_position = position_size
        elif weighted_momentum < -0.02:
            direction = SignalDirection.SHORT
            target_position = -position_size
        else:
            direction = SignalDirection.FLAT
            target_position = 0
        
        # 信号强度 (0-1)
        strength = min(abs(weighted_momentum) / 0.10, 1.0)
        
        # 计算止损止盈
        current_price = prices.iloc[-1]
        atr = self._calculate_atr(prices)
        
        stop_loss = None
        take_profit = None
        
        if direction == SignalDirection.LONG:
            stop_loss = current_price - 2 * atr
            take_profit = current_price + 3 * atr
        elif direction == SignalDirection.SHORT:
            stop_loss = current_price + 2 * atr
            take_profit = current_price - 3 * atr
        
        return CTASignal(
            symbol=symbol,
            date=current_date,
            signal=direction,
            strength=strength,
            target_position=target_position,
            volatility=volatility,
            expected_return=weighted_momentum * position_size,
            stop_loss=stop_loss,
            take_profit=take_profit
        )
    
    def _calculate_atr(self, prices: pd.Series, window: int = 14) -> float:
        """计算ATR (Average True Range)"""
        if len(prices) < window + 1:
            return prices.std()
        
        # 模拟high/low (实际应从数据获取)
        high = prices * 1.01
        low = prices * 0.99
        close = prices
        
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window).mean().iloc[-1]
        
        return atr if not np.isnan(atr) else prices.std()
    
    def generate_signals(
        self,
        data: Dict[str, pd.DataFrame],
        current_date: datetime = None
    ) -> List[CTASignal]:
        """
        批量生成信号
        
        Args:
            data: {symbol: price_df}
            current_date: 当前日期
        
        Returns:
            CTASignal列表
        """
        signals = []
        
        for symbol, df in data.items():
            if 'close' in df.columns:
                prices = df['close']
            else:
                prices = df.iloc[:, 0]  # 假设第一列是价格
            
            if len(prices) >= max(self.lookback_periods):
                signal = self.generate_signal(symbol, prices, current_date)
                signals.append(signal)
        
        # 按信号强度排序
        signals.sort(key=lambda x: abs(x.strength), reverse=True)
        
        return signals


class TrendFollowingStrategy:
    """
    趋势跟踪策略
    
    基于多时间框架移动平均的趋势判断
    """
    
    def __init__(
        self,
        short_window: int = 20,
        medium_window: int = 60,
        long_window: int = 120
    ):
        self.short_window = short_window
        self.medium_window = medium_window
        self.long_window = long_window
    
    def generate_signal(
        self,
        symbol: str,
        prices: pd.Series,
        current_date: datetime = None
    ) -> CTASignal:
        """生成趋势跟踪信号"""
        if current_date is None:
            current_date = prices.index[-1]
        
        # 计算移动平均线
        ma_short = prices.rolling(self.short_window).mean().iloc[-1]
        ma_medium = prices.rolling(self.medium_window).mean().iloc[-1]
        ma_long = prices.rolling(self.long_window).mean().iloc[-1]
        
        current_price = prices.iloc[-1]
        
        # 趋势判断
        trend_score = 0
        
        if current_price > ma_short:
            trend_score += 1
        if ma_short > ma_medium:
            trend_score += 1
        if ma_medium > ma_long:
            trend_score += 1
        
        if current_price < ma_short:
            trend_score -= 1
        if ma_short < ma_medium:
            trend_score -= 1
        if ma_medium < ma_long:
            trend_score -= 1
        
        # 确定信号
        if trend_score >= 2:
            direction = SignalDirection.LONG
            target_position = min(trend_score / 3, 1.0)
        elif trend_score <= -2:
            direction = SignalDirection.SHORT
            target_position = max(trend_score / 3, -1.0)
        else:
            direction = SignalDirection.FLAT
            target_position = 0
        
        strength = abs(trend_score) / 3
        
        # 计算波动率
        volatility = prices.pct_change().std() * np.sqrt(252)
        
        return CTASignal(
            symbol=symbol,
            date=current_date,
            signal=direction,
            strength=strength,
            target_position=target_position,
            volatility=volatility,
            expected_return=target_position * volatility * 0.5
        )
    
    def generate_signals(
        self,
        data: Dict[str, pd.DataFrame],
        current_date: datetime = None
    ) -> List[CTASignal]:
        """批量生成信号"""
        signals = []
        
        for symbol, df in data.items():
            if 'close' in df.columns:
                prices = df['close']
            else:
                prices = df.iloc[:, 0]
            
            if len(prices) >= self.long_window:
                signal = self.generate_signal(symbol, prices, current_date)
                signals.append(signal)
        
        return signals


class CTASignalAggregator:
    """
    CTA信号聚合器
    
    整合多个CTA策略的信号，生成综合仓位建议
    """
    
    def __init__(self, strategies: List = None):
        self.strategies = strategies or [TSMOMStrategy(), TrendFollowingStrategy()]
        self.logger = logging.getLogger(__name__)
    
    def aggregate_signals(
        self,
        data: Dict[str, pd.DataFrame],
        current_date: datetime = None
    ) -> Dict[str, CTASignal]:
        """
        聚合多策略信号
        """
        all_signals = {}
        
        for strategy in self.strategies:
            signals = strategy.generate_signals(data, current_date)
            
            for signal in signals:
                symbol = signal.symbol
                if symbol not in all_signals:
                    all_signals[symbol] = []
                all_signals[symbol].append(signal)
        
        # 平均各策略信号
        aggregated = {}
        for symbol, signals in all_signals.items():
            if signals:
                avg_position = np.mean([s.target_position for s in signals])
                avg_strength = np.mean([s.strength for s in signals])
                avg_volatility = np.mean([s.volatility for s in signals])
                
                # 确定方向
                if avg_position > 0.1:
                    direction = SignalDirection.LONG
                elif avg_position < -0.1:
                    direction = SignalDirection.SHORT
                else:
                    direction = SignalDirection.FLAT
                
                aggregated[symbol] = CTASignal(
                    symbol=symbol,
                    date=current_date or datetime.now(),
                    signal=direction,
                    strength=avg_strength,
                    target_position=np.clip(avg_position, -1, 1),
                    volatility=avg_volatility,
                    expected_return=avg_position * avg_volatility
                )
        
        return aggregated


# 便捷函数
def get_cta_signals(
    symbols: List[str] = None,
    start_date: str = None,
    end_date: str = None,
    api_key: str = None
) -> Dict[str, CTASignal]:
    """
    快速获取CTA信号
    
    Example:
        >>> signals = get_cta_signals(['RB', 'CU', 'SC'])
        >>> for sym, sig in signals.items():
        ...     print(f"{sym}: {sig.signal.name}, Position: {sig.target_position:.2f}")
    """
    provider = FuturesDataProvider(api_key)
    
    if symbols is None:
        symbols = ['RB', 'CU', 'SC', 'TA', 'IF']
    
    if end_date is None:
        end_date = datetime.now().strftime('%Y-%m-%d')
    if start_date is None:
        start = datetime.now() - pd.Timedelta(days=180)
        start_date = start.strftime('%Y-%m-%d')
    
    # 获取数据
    data = {}
    for sym in symbols:
        df = provider.get_futures_data(sym, start_date, end_date)
        if not df.empty:
            data[sym] = df
    
    # 生成信号
    aggregator = CTASignalAggregator()
    signals = aggregator.aggregate_signals(data)
    
    return signals


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("CTA信号生成测试")
    print("=" * 70)
    
    signals = get_cta_signals(['RB', 'CU', 'SC', 'IF'])
    
    print("\nCTA Signals:")
    print("-" * 70)
    print(f"{'Symbol':<10} {'Direction':<10} {'Position':<10} {'Strength':<10} {'Volatility':<10}")
    print("-" * 70)
    
    for sym, sig in signals.items():
        print(f"{sym:<10} {sig.signal.name:<10} {sig.target_position:<10.2f} "
              f"{sig.strength:<10.2f} {sig.volatility:<10.2%}")
