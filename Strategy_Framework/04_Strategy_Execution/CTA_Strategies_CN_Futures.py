"""
CTA Strategies for China Futures
=================================

Reproducing top CTA papers:
1. Time Series Momentum (Moskowitz et al. 2012)
2. Trend Following (Man Group 2025)
3. Carry Strategy (ReSolve 2024)
4. Meta-Model Dynamic Allocation (Mandatum 2025)

Markets: China Futures (Commodities + Financial)
Data Sources: AKShare (Free) / RiceQuant (Pro)
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging
from abc import ABC, abstractmethod
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# Configuration
# ============================================================

# Futures config for China market
CN_FUTURES_CONFIG = {
    # Black Metals
    'RB': {'name': 'Rebar', 'exchange': 'SHFE', 'multiplier': 10, 'category': 'Black'},
    'HC': {'name': 'Hot Coil', 'exchange': 'SHFE', 'multiplier': 10, 'category': 'Black'},
    'I':  {'name': 'Iron Ore', 'exchange': 'DCE', 'multiplier': 100, 'category': 'Black'},
    'J':  {'name': 'Coke', 'exchange': 'DCE', 'multiplier': 100, 'category': 'Black'},
    'JM': {'name': 'Coking Coal', 'exchange': 'DCE', 'multiplier': 60, 'category': 'Black'},
    
    # Non-ferrous
    'CU': {'name': 'Copper', 'exchange': 'SHFE', 'multiplier': 5, 'category': 'NonFerrous'},
    'AL': {'name': 'Aluminum', 'exchange': 'SHFE', 'multiplier': 5, 'category': 'NonFerrous'},
    'ZN': {'name': 'Zinc', 'exchange': 'SHFE', 'multiplier': 5, 'category': 'NonFerrous'},
    'NI': {'name': 'Nickel', 'exchange': 'SHFE', 'multiplier': 1, 'category': 'NonFerrous'},
    'SN': {'name': 'Tin', 'exchange': 'SHFE', 'multiplier': 1, 'category': 'NonFerrous'},
    
    # Energy
    'SC': {'name': 'Crude Oil', 'exchange': 'INE', 'multiplier': 1000, 'category': 'Energy'},
    'LU': {'name': 'Low Sulfur Fuel', 'exchange': 'INE', 'multiplier': 10, 'category': 'Energy'},
    'FU': {'name': 'Fuel Oil', 'exchange': 'SHFE', 'multiplier': 10, 'category': 'Energy'},
    
    # Chemicals
    'TA': {'name': 'PTA', 'exchange': 'CZCE', 'multiplier': 5, 'category': 'Chemicals'},
    'MA': {'name': 'Methanol', 'exchange': 'CZCE', 'multiplier': 10, 'category': 'Chemicals'},
    'PP': {'name': 'Polypropylene', 'exchange': 'DCE', 'multiplier': 5, 'category': 'Chemicals'},
    'L':  {'name': 'PE', 'exchange': 'DCE', 'multiplier': 5, 'category': 'Chemicals'},
    'EG': {'name': 'Ethylene Glycol', 'exchange': 'DCE', 'multiplier': 10, 'category': 'Chemicals'},
    
    # Agriculture
    'M':  {'name': 'Soybean Meal', 'exchange': 'DCE', 'multiplier': 10, 'category': 'Agriculture'},
    'RM': {'name': 'Rapeseed Meal', 'exchange': 'CZCE', 'multiplier': 10, 'category': 'Agriculture'},
    'OI': {'name': 'Rapeseed Oil', 'exchange': 'CZCE', 'multiplier': 10, 'category': 'Agriculture'},
    'CF': {'name': 'Cotton', 'exchange': 'CZCE', 'multiplier': 5, 'category': 'Agriculture'},
    'SR': {'name': 'Sugar', 'exchange': 'CZCE', 'multiplier': 10, 'category': 'Agriculture'},
    
    # Precious Metals
    'AU': {'name': 'Gold', 'exchange': 'SHFE', 'multiplier': 1000, 'category': 'Precious'},
    'AG': {'name': 'Silver', 'exchange': 'SHFE', 'multiplier': 15, 'category': 'Precious'},
    
    # Financial
    'IF': {'name': 'CSI 300', 'exchange': 'CFFEX', 'multiplier': 300, 'category': 'Index'},
    'IC': {'name': 'CSI 500', 'exchange': 'CFFEX', 'multiplier': 200, 'category': 'Index'},
    'IM': {'name': 'CSI 1000', 'exchange': 'CFFEX', 'multiplier': 200, 'category': 'Index'},
    'T':  {'name': '10Y Treasury', 'exchange': 'CFFEX', 'multiplier': 10000, 'category': 'Bond'},
    'TF': {'name': '5Y Treasury', 'exchange': 'CFFEX', 'multiplier': 10000, 'category': 'Bond'},
}

# Strategy parameters
STRATEGY_PARAMS = {
    'tsmom_lookback': 20,
    'tsmom_hold': 20,
    'target_volatility': 0.10,
    'trend_fast_ma': 20,
    'trend_slow_ma': 60,
    'channel_period': 20,
    'channel_width': 2.0,
    'max_position_per_symbol': 0.10,
    'max_category_exposure': 0.30,
    'target_portfolio_vol': 0.15,
}


def setup_logger(name: str = "cta_strategies") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


class Signal(Enum):
    LONG = 1
    SHORT = -1
    FLAT = 0


class MarketRegime(Enum):
    TRENDING_UP = "Trending Up"
    TRENDING_DOWN = "Trending Down"
    RANGE_BOUND = "Range Bound"
    HIGH_VOLATILITY = "High Volatility"
    CRISIS = "Crisis"


@dataclass
class FuturesData:
    symbol: str
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    open_interest: int = 0


@dataclass
class StrategySignal:
    symbol: str
    date: date
    signal: Signal
    strength: float
    target_position: float
    expected_return: float
    volatility: float
    metadata: Dict = field(default_factory=dict)


@dataclass
class PortfolioPosition:
    symbol: str
    direction: int
    quantity: int
    entry_price: float
    current_price: float
    entry_date: date
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0


class FuturesDataProvider(ABC):
    @abstractmethod
    def get_futures_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        pass
    
    @abstractmethod
    def get_all_symbols(self) -> List[str]:
        pass


class MockFuturesDataProvider(FuturesDataProvider):
    """Mock futures data provider for testing"""
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or setup_logger()
        self.cache = {}
    
    def get_futures_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        cache_key = f"{symbol}_{start_date}_{end_date}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        n = len(dates)
        
        # Different volatility for different products
        vol_map = {
            'SC': 0.025, 'AU': 0.015, 'RB': 0.018,
            'CU': 0.020, 'IF': 0.022, 'T': 0.008,
        }
        base_vol = vol_map.get(symbol[:2], 0.02)
        
        np.random.seed(hash(symbol) % 2**32)
        returns = np.random.normal(0, base_vol, n)
        
        # Add trend component
        if np.random.random() < 0.3:
            trend = np.random.choice([-1, 1]) * base_vol * 0.3
            returns += trend
        
        start_price = np.random.uniform(3000, 80000)
        prices = start_price * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'date': dates,
            'open': prices * (1 + np.random.normal(0, 0.002, n)),
            'high': prices * (1 + abs(np.random.normal(0, 0.01, n))),
            'low': prices * (1 - abs(np.random.normal(0, 0.01, n))),
            'close': prices,
            'volume': np.random.randint(10000, 1000000, n),
        })
        
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.set_index('date')
        
        self.cache[cache_key] = df
        return df
    
    def get_all_symbols(self) -> List[str]:
        return list(CN_FUTURES_CONFIG.keys())


class CTAStrategy(ABC):
    def __init__(self, name: str, params: Dict, logger: logging.Logger = None):
        self.name = name
        self.params = params
        self.logger = logger or setup_logger()
        self.signals: List[StrategySignal] = []
    
    @abstractmethod
    def generate_signals(self, data: Dict[str, pd.DataFrame], current_date: date) -> List[StrategySignal]:
        pass
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].ewm(span=60, min_periods=20).std() * np.sqrt(252)
        df['fast_ma'] = df['close'].rolling(self.params.get('trend_fast_ma', 20)).mean()
        df['slow_ma'] = df['close'].rolling(self.params.get('trend_slow_ma', 60)).mean()
        
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        df['tr'] = np.maximum(high_low, np.maximum(high_close, low_close))
        df['atr'] = df['tr'].rolling(self.params.get('channel_period', 20)).mean()
        
        df['upper_channel'] = df['fast_ma'] + self.params.get('channel_width', 2.0) * df['atr']
        df['lower_channel'] = df['fast_ma'] - self.params.get('channel_width', 2.0) * df['atr']
        
        return df


class TSMOMStrategy(CTAStrategy):
    """
    Time Series Momentum Strategy (Moskowitz et al. 2012)
    
    Long if past return > 0, Short if past return < 0
    Volatility-scaled position sizing
    """
    
    def __init__(self, params: Dict = None):
        super().__init__("TSMOM", params or STRATEGY_PARAMS)
    
    def generate_signals(self, data: Dict[str, pd.DataFrame], current_date: date) -> List[StrategySignal]:
        signals = []
        lookback = self.params['tsmom_lookback']
        target_vol = self.params['target_volatility']
        
        for symbol, df in data.items():
            try:
                df = df[df.index <= current_date]
                if len(df) < lookback + 5:
                    continue
                
                df = self.calculate_indicators(df)
                latest = df.iloc[-1]
                
                past_return = (df['close'].iloc[-1] / df['close'].iloc[-lookback] - 1)
                
                vol = latest['volatility']
                if pd.isna(vol) or vol <= 0:
                    vol = 0.20
                
                if past_return > 0:
                    signal = Signal.LONG
                    strength = min(abs(past_return) / vol, 1.0)
                elif past_return < 0:
                    signal = Signal.SHORT
                    strength = min(abs(past_return) / vol, 1.0)
                else:
                    signal = Signal.FLAT
                    strength = 0
                
                position_size = (target_vol / vol) * strength if vol > 0 else 0
                position_size = np.clip(position_size, -1.0, 1.0)
                
                signals.append(StrategySignal(
                    symbol=symbol, date=current_date, signal=signal,
                    strength=strength, target_position=position_size,
                    expected_return=past_return * 0.1, volatility=vol,
                    metadata={'past_return': past_return}
                ))
            except Exception as e:
                self.logger.debug(f"{symbol} signal generation failed: {e}")
        
        return signals


class TrendFollowingStrategy(CTAStrategy):
    """
    Trend Following Strategy (Multi-timeframe)
    
    MA Crossover + Channel Breakout confirmation
    """
    
    def __init__(self, params: Dict = None):
        super().__init__("TrendFollowing", params or STRATEGY_PARAMS)
    
    def generate_signals(self, data: Dict[str, pd.DataFrame], current_date: date) -> List[StrategySignal]:
        signals = []
        
        for symbol, df in data.items():
            try:
                df = df[df.index <= current_date]
                if len(df) < 70:
                    continue
                
                df = self.calculate_indicators(df)
                latest = df.iloc[-1]
                
                # MA signal
                ma_signal = Signal.FLAT
                if latest['fast_ma'] > latest['slow_ma']:
                    ma_signal = Signal.LONG
                elif latest['fast_ma'] < latest['slow_ma']:
                    ma_signal = Signal.SHORT
                
                # Channel signal
                channel_signal = Signal.FLAT
                if latest['close'] > latest['upper_channel']:
                    channel_signal = Signal.LONG
                elif latest['close'] < latest['lower_channel']:
                    channel_signal = Signal.SHORT
                
                # Combined signal
                if ma_signal == channel_signal and ma_signal != Signal.FLAT:
                    final_signal = ma_signal
                    trend_strength = abs(latest['fast_ma'] / latest['slow_ma'] - 1)
                    strength = min(trend_strength * 10, 1.0)
                else:
                    final_signal = Signal.FLAT
                    strength = 0
                
                vol = latest['volatility']
                if pd.isna(vol) or vol <= 0:
                    vol = 0.20
                
                position_size = (self.params['target_volatility'] / vol) * strength
                position_size = np.clip(position_size, -1.0, 1.0)
                
                signals.append(StrategySignal(
                    symbol=symbol, date=current_date, signal=final_signal,
                    strength=strength, target_position=position_size,
                    expected_return=strength * vol * np.sqrt(252),
                    volatility=vol,
                    metadata={'ma_signal': ma_signal.value, 'channel_signal': channel_signal.value}
                ))
            except Exception as e:
                self.logger.debug(f"{symbol} signal generation failed: {e}")
        
        return signals


class CarryStrategy(CTAStrategy):
    """
    Carry Strategy (Term Structure)
    
    Long Backwardation, Short Contango
    """
    
    def __init__(self, params: Dict = None):
        super().__init__("Carry", params or STRATEGY_PARAMS)
    
    def generate_signals(self, data: Dict[str, pd.DataFrame], current_date: date) -> List[StrategySignal]:
        signals = []
        
        for symbol, df in data.items():
            try:
                df = df[df.index <= current_date]
                if len(df) < 60:
                    continue
                
                df = self.calculate_indicators(df)
                latest = df.iloc[-1]
                
                # Simulate carry signal
                near_ma = df['close'].iloc[-20:].mean()
                far_ma = df['close'].iloc[-60:-20].mean()
                carry = (near_ma - far_ma) / far_ma
                
                if carry > 0.01:
                    signal = Signal.LONG
                    strength = min(carry * 10, 1.0)
                elif carry < -0.01:
                    signal = Signal.SHORT
                    strength = min(abs(carry) * 10, 1.0)
                else:
                    signal = Signal.FLAT
                    strength = 0
                
                vol = latest['volatility']
                if pd.isna(vol) or vol <= 0:
                    vol = 0.20
                
                position_size = (self.params['target_volatility'] / vol) * strength
                position_size = np.clip(position_size, -1.0, 1.0)
                
                signals.append(StrategySignal(
                    symbol=symbol, date=current_date, signal=signal,
                    strength=strength, target_position=position_size,
                    expected_return=carry * 12, volatility=vol,
                    metadata={'carry': carry}
                ))
            except Exception as e:
                self.logger.debug(f"{symbol} signal generation failed: {e}")
        
        return signals


class MetaModelAllocator:
    """
    Meta-Model Dynamic Allocator
    
    Dynamically adjust strategy weights based on market regime
    """
    
    def __init__(self, strategies: List[CTAStrategy], logger: logging.Logger = None):
        self.strategies = strategies
        self.logger = logger or setup_logger()
        self.performance_history: Dict[str, List[float]] = {s.name: [] for s in strategies}
        self.weights: Dict[str, float] = {s.name: 1.0/len(strategies) for s in strategies}
    
    def detect_regime(self, data: Dict[str, pd.DataFrame], current_date: date) -> MarketRegime:
        market_vols = []
        market_trends = []
        
        for symbol in ['IF', 'RB', 'CU', 'SC']:
            if symbol in data:
                df = data[symbol][data[symbol].index <= current_date]
                if len(df) >= 20:
                    returns = df['close'].pct_change().dropna()
                    vol = returns.iloc[-20:].std() * np.sqrt(252)
                    trend = abs(df['close'].iloc[-1] / df['close'].iloc[-20] - 1)
                    market_vols.append(vol)
                    market_trends.append(trend)
        
        avg_vol = np.mean(market_vols) if market_vols else 0.20
        avg_trend = np.mean(market_trends) if market_trends else 0
        
        if avg_vol > 0.30:
            return MarketRegime.HIGH_VOLATILITY
        elif avg_trend > 0.05:
            return MarketRegime.TRENDING_UP
        else:
            return MarketRegime.RANGE_BOUND
    
    def update_weights(self, regime: MarketRegime, recent_returns: Dict[str, float]):
        base_weights = {'TSMOM': 0.25, 'TrendFollowing': 0.35, 'Carry': 0.20}
        
        regime_adjustments = {
            MarketRegime.TRENDING_UP: {'TSMOM': 0.1, 'TrendFollowing': 0.15, 'Carry': -0.05},
            MarketRegime.TRENDING_DOWN: {'TSMOM': 0.1, 'TrendFollowing': 0.15, 'Carry': -0.1},
            MarketRegime.RANGE_BOUND: {'TSMOM': -0.1, 'TrendFollowing': -0.1, 'Carry': 0.15},
            MarketRegime.HIGH_VOLATILITY: {'TSMOM': 0.0, 'TrendFollowing': 0.05, 'Carry': -0.1},
        }
        
        adjustments = regime_adjustments.get(regime, {})
        
        for strategy_name in self.weights:
            base = base_weights.get(strategy_name, 0.2)
            adj = adjustments.get(strategy_name, 0)
            self.weights[strategy_name] = max(0.05, min(0.5, base + adj))
        
        total = sum(self.weights.values())
        self.weights = {k: v/total for k, v in self.weights.items()}
    
    def get_combined_signals(self, all_signals: Dict[str, List[StrategySignal]], 
                            current_date: date) -> List[StrategySignal]:
        combined = {}
        
        for strategy_name, signals in all_signals.items():
            weight = self.weights.get(strategy_name, 0.2)
            for signal in signals:
                if signal.symbol not in combined:
                    combined[signal.symbol] = {'weighted_position': 0, 'total_weight': 0, 'signals': []}
                combined[signal.symbol]['weighted_position'] += signal.target_position * weight
                combined[signal.symbol]['total_weight'] += weight
                combined[signal.symbol]['signals'].append(signal)
        
        result = []
        for symbol, data in combined.items():
            avg_position = data['weighted_position'] / max(data['total_weight'], 0.01)
            
            if avg_position > 0.1:
                signal = Signal.LONG
            elif avg_position < -0.1:
                signal = Signal.SHORT
            else:
                signal = Signal.FLAT
            
            result.append(StrategySignal(
                symbol=symbol, date=current_date, signal=signal,
                strength=abs(avg_position), target_position=np.clip(avg_position, -1, 1),
                expected_return=0, volatility=0.20, metadata={'weights': self.weights}
            ))
        
        return result


if __name__ == "__main__":
    logger = setup_logger()
    logger.info("="*60)
    logger.info("CTA Strategy System Initialized")
    logger.info("="*60)
    
    provider = MockFuturesDataProvider(logger)
    strategies = [TSMOMStrategy(), TrendFollowingStrategy(), CarryStrategy()]
    
    logger.info(f"Loaded strategies: {[s.name for s in strategies]}")
    logger.info(f"Available symbols: {len(provider.get_all_symbols())}")
    logger.info("="*60)
