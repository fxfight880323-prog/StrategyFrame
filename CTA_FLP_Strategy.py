"""
CTA + FLP 尾部风险对冲策略系统
================================

策略架构:
1. CTA趋势引擎: 20/60日MA交叉 + 通道突破
2. FLP动态保护: 每周滚动买入SPY Put (Delta -0.07~-0.10)
3. 风险预算平衡: 盈利回哺保护机制

参考:
- Goldman Sachs Research (2026): Dynamic Hedging in 2026
- Journal of Derivatives (2025): Fixed Leverage Puts vs Rolling OTM Puts

作者: Quant Strategy Team
日期: 2026-02-26
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging


# ============================================================
# 配置参数
# ============================================================

# CTA策略配置
CTA_CONFIG = {
    'fast_ma': 20,           # 快速均线
    'slow_ma': 60,           # 慢速均线
    'channel_period': 20,    # 通道周期
    'channel_width': 2.0,    # 通道宽度 (ATR倍数)
    'vol_lookback': 60,      # 波动率回看周期
}

# FLP保护配置
FLP_CONFIG = {
    'underlying': 'SPY',
    'delta_target': (-0.10, -0.07),  # Delta目标范围
    'dte_target': 7,                 # 到期日(每周五)
    'vix_low_threshold': 15,         # VIX低位阈值
    'vix_high_threshold': 30,        # VIX高位阈值
    'budget_increase_pct': 0.20,     # VIX<15时增加20%预算
    'spread_width': 0.05,            # Put Spread宽度(5%)
}

# 风险预算配置
RISK_CONFIG = {
    'cta_base_weight': 0.80,         # CTA基础权重
    'flp_base_weight': 0.05,         # FLP基础权重
    'cash_weight': 0.15,             # 现金权重
    'profit_reinvest_pct': 0.15,     # 利润回哺比例
    'max_flp_weight': 0.10,          # FLP最大权重
    'min_flp_weight': 0.02,          # FLP最小权重
}

# 标的配置
UNIVERSE = {
    'ES': {'name': 'S&P 500 E-mini', 'multiplier': 50, 'tick': 0.25},
    'GC': {'name': 'Gold', 'multiplier': 100, 'tick': 0.10},
    'ZN': {'name': '10Y Treasury Note', 'multiplier': 1000, 'tick': 1/64},
}


# ============================================================
# 数据模型
# ============================================================

class Signal(Enum):
    LONG = 1
    SHORT = -1
    FLAT = 0

class FLPMode(Enum):
    LONG_PUT = "Long Put"           # 单纯买入Put
    PUT_SPREAD = "Put Spread"       # Put Spread降低成本
    NO_HEDGE = "No Hedge"           # 不保护

@dataclass
class CTASignal:
    """CTA信号"""
    symbol: str
    date: date
    signal: Signal
    fast_ma: float
    slow_ma: float
    price: float
    atr: float
    volatility: float
    position_size: float = 0.0

@dataclass
class FLPSignal:
    """FLP保护信号"""
    date: date
    underlying_price: float
    vix: float
    mode: FLPMode
    put_strike: Optional[float] = None
    put_delta: Optional[float] = None
    put_premium: Optional[float] = None
    spread_short_strike: Optional[float] = None
    budget: float = 0.0

@dataclass
class PortfolioState:
    """组合状态"""
    date: date
    cta_positions: Dict[str, float] = field(default_factory=dict)
    flp_position: Optional[FLPSignal] = None
    cta_pnl: float = 0.0
    flp_pnl: float = 0.0
    total_value: float = 1_000_000.0
    risk_budget: Dict[str, float] = field(default_factory=dict)


# ============================================================
# CTA多周期趋势引擎
# ============================================================

class CTATrendEngine:
    """
    CTA多周期趋势引擎
    
    逻辑:
    1. 20日(快速)和60日(慢速)MA交叉
    2. 通道突破确认
    3. 波动率倒数分配仓位
    """
    
    def __init__(self, config: Dict = CTA_CONFIG):
        self.config = config
        self.signals: List[CTASignal] = []
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()
        
        # 移动平均线
        df['fast_ma'] = df['close'].rolling(self.config['fast_ma']).mean()
        df['slow_ma'] = df['close'].rolling(self.config['slow_ma']).mean()
        
        # ATR (Average True Range)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        df['tr'] = np.maximum(high_low, np.maximum(high_close, low_close))
        df['atr'] = df['tr'].rolling(self.config['channel_period']).mean()
        
        # 通道
        df['upper_channel'] = df['fast_ma'] + self.config['channel_width'] * df['atr']
        df['lower_channel'] = df['fast_ma'] - self.config['channel_width'] * df['atr']
        
        # 波动率
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(self.config['vol_lookback']).std() * np.sqrt(252)
        
        return df
    
    def generate_signal(self, df: pd.DataFrame, symbol: str) -> List[CTASignal]:
        """生成CTA信号"""
        df = self.calculate_indicators(df)
        signals = []
        
        for i in range(self.config['slow_ma'] + 10, len(df)):
            row = df.iloc[i]
            row_date = row.name if isinstance(row.name, date) else pd.to_datetime(row.name).date()
            
            # MA交叉信号
            ma_signal = Signal.FLAT
            if row['fast_ma'] > row['slow_ma']:
                ma_signal = Signal.LONG
            elif row['fast_ma'] < row['slow_ma']:
                ma_signal = Signal.SHORT
            
            # 通道突破确认
            channel_signal = Signal.FLAT
            if row['close'] > row['upper_channel']:
                channel_signal = Signal.LONG
            elif row['close'] < row['lower_channel']:
                channel_signal = Signal.SHORT
            
            # 综合信号 (需要MA和通道同向)
            final_signal = Signal.FLAT
            if ma_signal == channel_signal and ma_signal != Signal.FLAT:
                final_signal = ma_signal
            
            signal = CTASignal(
                symbol=symbol,
                date=row_date,
                signal=final_signal,
                fast_ma=row['fast_ma'],
                slow_ma=row['slow_ma'],
                price=row['close'],
                atr=row['atr'],
                volatility=row['volatility']
            )
            signals.append(signal)
        
        return signals
    
    def calculate_position_sizes(self, signals: List[CTASignal], 
                                 target_vol: float = 0.15) -> List[CTASignal]:
        """
        波动率倒数分配仓位
        
        公式: Position Size ∝ 1 / Volatility
        """
        # 计算平均波动率
        vols = [s.volatility for s in signals if s.volatility > 0]
        if not vols:
            return signals
        
        avg_vol = np.mean(vols)
        
        for signal in signals:
            if signal.volatility > 0:
                # 波动率倒数权重
                vol_weight = avg_vol / signal.volatility
                # 限制最大仓位
                signal.position_size = min(vol_weight * 0.33, 1.0)
            else:
                signal.position_size = 0.0
        
        return signals


# ============================================================
# FLP动态保护引擎
# ============================================================

class FLPEngine:
    """
    Fixed Leverage Puts 动态保护引擎
    
    执行规则:
    1. 每周五买入下周五到期的SPY Put (Delta -0.07~-0.10)
    2. VIX<15时增加20%预算; VIX>30时改用Put Spread
    3. 滚动持有
    """
    
    def __init__(self, config: Dict = FLP_CONFIG):
        self.config = config
        self.signals: List[FLPSignal] = []
    
    def get_next_friday(self, current_date: date) -> date:
        """获取下周五日期"""
        days_ahead = 4 - current_date.weekday()  # Friday is 4
        if days_ahead <= 0:
            days_ahead += 7
        return current_date + timedelta(days=days_ahead)
    
    def calculate_put_strike(self, price: float, delta: float, 
                            volatility: float, dte: int) -> float:
        """
        根据Delta计算Put行权价 (简化Black-Scholes)
        
        Delta ≈ N(-d1) for Put
        d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T)
        """
        # 简化计算: Delta与价外程度近似线性
        # Delta -0.10 ≈ 2% OTM
        otm_pct = abs(delta) * 0.20  # 约20倍关系
        strike = price * (1 - otm_pct)
        return round(strike, 2)
    
    def estimate_put_premium(self, strike: float, underlying: float, 
                            volatility: float, dte: int) -> float:
        """估算Put期权费 (简化)"""
        # 简化模型: Premium ≈ Intrinsic + Time Value
        intrinsic = max(0, strike - underlying)
        time_value = underlying * volatility * np.sqrt(dte / 365) * 0.4
        return intrinsic + time_value
    
    def determine_mode(self, vix: float) -> FLPMode:
        """根据VIX确定保护模式"""
        if vix < self.config['vix_low_threshold']:
            return FLPMode.LONG_PUT  # 保护便宜，直接买入
        elif vix > self.config['vix_high_threshold']:
            return FLPMode.PUT_SPREAD  # 保护昂贵，用Spread降成本
        else:
            return FLPMode.LONG_PUT
    
    def calculate_budget(self, base_budget: float, vix: float) -> float:
        """计算保护预算"""
        if vix < self.config['vix_low_threshold']:
            return base_budget * (1 + self.config['budget_increase_pct'])
        elif vix > self.config['vix_high_threshold']:
            return base_budget * 0.7  # 减少预算
        else:
            return base_budget
    
    def generate_signal(self, date: date, underlying_price: float, 
                       vix: float, base_budget: float) -> Optional[FLPSignal]:
        """生成FLP信号"""
        # 只在每周五生成信号
        if date.weekday() != 4:  # Friday
            return None
        
        mode = self.determine_mode(vix)
        budget = self.calculate_budget(base_budget, vix)
        
        if mode == FLPMode.NO_HEDGE:
            return FLPSignal(date=date, underlying_price=underlying_price, 
                           vix=vix, mode=mode, budget=0)
        
        # 计算Put行权价 (Delta -0.10 ~ -0.07)
        target_delta = np.mean(self.config['delta_target'])
        volatility = vix / 100
        dte = self.config['dte_target']
        
        put_strike = self.calculate_put_strike(underlying_price, target_delta, volatility, dte)
        put_premium = self.estimate_put_premium(put_strike, underlying_price, volatility, dte)
        
        # Put Spread设置
        spread_short_strike = None
        if mode == FLPMode.PUT_SPREAD:
            spread_short_strike = put_strike * (1 - self.config['spread_width'])
        
        return FLPSignal(
            date=date,
            underlying_price=underlying_price,
            vix=vix,
            mode=mode,
            put_strike=put_strike,
            put_delta=target_delta,
            put_premium=put_premium,
            spread_short_strike=spread_short_strike,
            budget=budget
        )


# ============================================================
# 风险预算动态平衡
# ============================================================

class RiskBudgetBalancer:
    """
    风险预算动态平衡器
    
    逻辑:
    1. CTA盈利时提取10-20%增持FLP保护
    2. 牛市收缩CTA仓位，保留FLP基础防守
    3. 动态调整权重
    """
    
    def __init__(self, config: Dict = RISK_CONFIG):
        self.config = config
        self.cta_cum_pnl = 0.0
        self.flp_cum_cost = 0.0
    
    def calculate_weights(self, portfolio: PortfolioState, 
                         market_regime: str = "normal") -> Dict[str, float]:
        """
        计算动态权重
        
        Args:
            portfolio: 当前组合状态
            market_regime: 市场环境 (bull/normal/bear)
        """
        base_cta = self.config['cta_base_weight']
        base_flp = self.config['flp_base_weight']
        base_cash = self.config['cash_weight']
        
        # 1. 盈利回哺保护
        profit_boost = 0.0
        if portfolio.cta_pnl > 0:
            profit_boost = portfolio.cta_pnl * self.config['profit_reinvest_pct']
            profit_boost = min(profit_boost, base_cta * 0.2)  # 限制最大转移
        
        cta_weight = base_cta - profit_boost
        flp_weight = base_flp + profit_boost
        
        # 2. 市场环境调整
        if market_regime == "bull":
            # 牛市收缩CTA，保留FLP防守
            cta_weight *= 0.7
            cash_weight = base_cash + (base_cta * 0.3)
        elif market_regime == "bear":
            # 熊市增加保护
            flp_weight = min(flp_weight * 1.5, self.config['max_flp_weight'])
            cta_weight = max(cta_weight * 0.8, 0.5)
            cash_weight = 1 - cta_weight - flp_weight
        else:
            cash_weight = base_cash
        
        # 3. 边界检查
        flp_weight = max(min(flp_weight, self.config['max_flp_weight']), 
                        self.config['min_flp_weight'])
        cta_weight = max(min(cta_weight, 0.9), 0.3)
        cash_weight = 1 - cta_weight - flp_weight
        
        return {
            'cta': cta_weight,
            'flp': flp_weight,
            'cash': cash_weight
        }
    
    def update_pnl(self, cta_daily_pnl: float, flp_daily_pnl: float):
        """更新累计盈亏"""
        self.cta_cum_pnl += cta_daily_pnl
        # FLP成本是负的PNL (权利金支出)
        if flp_daily_pnl < 0:
            self.flp_cum_cost += abs(flp_daily_pnl)


# ============================================================
# 回测引擎
# ============================================================

class CTAFLPBacktester:
    """
    CTA + FLP 策略回测引擎
    """
    
    def __init__(self, initial_capital: float = 1_000_000):
        self.initial_capital = initial_capital
        self.cta_engine = CTATrendEngine()
        self.flp_engine = FLPEngine()
        self.risk_balancer = RiskBudgetBalancer()
        self.logger = self._setup_logger()
    
    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("cta_flp_backtest")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
            sh = logging.StreamHandler(sys.stdout)
            sh.setFormatter(fmt)
            logger.addHandler(sh)
        return logger
    
    def run_backtest(self, price_data: Dict[str, pd.DataFrame], 
                    vix_data: pd.DataFrame,
                    start_date: date, end_date: date) -> pd.DataFrame:
        """
        运行回测
        
        Args:
            price_data: {symbol: price_df} 价格数据
            vix_data: VIX数据
            start_date: 开始日期
            end_date: 结束日期
        """
        self.logger.info("="*60)
        self.logger.info("CTA + FLP 策略回测")
        self.logger.info("="*60)
        
        # 1. 生成CTA信号
        all_cta_signals = {}
        for symbol, df in price_data.items():
            signals = self.cta_engine.generate_signal(df, symbol)
            signals = self.cta_engine.calculate_position_sizes(signals)
            all_cta_signals[symbol] = signals
            self.logger.info(f"{symbol}: 生成 {len(signals)} 个CTA信号")
        
        # 2. 回测循环
        results = []
        current_date = start_date
        portfolio = PortfolioState(date=current_date)
        
        while current_date <= end_date:
            # 获取当日VIX
            vix_row = vix_data[vix_data.index.date == current_date]
            vix = vix_row['close'].iloc[0] if not vix_row.empty else 20.0
            
            # 获取SPY价格
            spy_price = 400.0  # 简化，实际应从数据获取
            
            # 生成FLP信号 (每周五)
            flp_signal = self.flp_engine.generate_signal(
                current_date, spy_price, vix, 
                base_budget=portfolio.total_value * 0.05
            )
            
            # 计算权重
            weights = self.risk_balancer.calculate_weights(portfolio, "normal")
            
            # 记录状态
            results.append({
                'date': current_date,
                'total_value': portfolio.total_value,
                'cta_weight': weights['cta'],
                'flp_weight': weights['flp'],
                'cash_weight': weights['cash'],
                'vix': vix,
                'flp_mode': flp_signal.mode.value if flp_signal else "None",
            })
            
            current_date += timedelta(days=1)
        
        return pd.DataFrame(results)
    
    def calculate_metrics(self, results_df: pd.DataFrame) -> Dict:
        """计算绩效指标"""
        if results_df.empty:
            return {}
        
        final_value = results_df['total_value'].iloc[-1]
        initial_value = self.initial_capital
        total_return = (final_value / initial_value - 1) * 100
        
        results_df['daily_return'] = results_df['total_value'].pct_change()
        volatility = results_df['daily_return'].std() * np.sqrt(252) * 100
        
        # 最大回撤
        results_df['cummax'] = results_df['total_value'].cummax()
        results_df['drawdown'] = (results_df['total_value'] - results_df['cummax']) / results_df['cummax']
        max_drawdown = results_df['drawdown'].min() * 100
        
        # 夏普比率
        risk_free = 5.0
        sharpe = (total_return - risk_free) / volatility if volatility > 0 else 0
        
        return {
            'total_return_pct': total_return,
            'annual_volatility_pct': volatility,
            'max_drawdown_pct': max_drawdown,
            'sharpe_ratio': sharpe,
            'final_value': final_value,
        }


# ============================================================
# 主函数
# ============================================================

def demo_strategy():
    """策略演示"""
    print("="*60)
    print("CTA + FLP 尾部风险对冲策略")
    print("="*60)
    print()
    
    # 策略说明
    print("【策略架构】")
    print("1. CTA趋势引擎: 20/60日MA交叉 + 波动率倒数加权")
    print("2. FLP保护: 每周买入Delta -0.07~-0.10的SPY Put")
    print("3. 风险平衡: CTA盈利15%回哺FLP保护")
    print()
    
    print("【配置参数】")
    print(f"CTA Fast MA: {CTA_CONFIG['fast_ma']}日")
    print(f"CTA Slow MA: {CTA_CONFIG['slow_ma']}日")
    print(f"FLP Delta Range: {FLP_CONFIG['delta_target']}")
    print(f"Profit Reinvest: {RISK_CONFIG['profit_reinvest_pct']*100}%")
    print()
    
    # 模拟权重变化
    print("【风险预算动态调整示例】")
    print()
    
    balancer = RiskBudgetBalancer()
    
    scenarios = [
        ("初始状态", 0, 0, "normal"),
        ("CTA盈利", 100000, 0, "normal"),
        ("牛市环境", 100000, 0, "bull"),
        ("熊市环境", -50000, 0, "bear"),
    ]
    
    for name, cta_pnl, flp_pnl, regime in scenarios:
        portfolio = PortfolioState(date=date.today())
        portfolio.cta_pnl = cta_pnl
        portfolio.flp_pnl = flp_pnl
        
        weights = balancer.calculate_weights(portfolio, regime)
        
        print(f"{name:12s} (CTA盈亏: ${cta_pnl:+,}, 环境: {regime})")
        print(f"  CTA权重:  {weights['cta']*100:5.1f}%")
        print(f"  FLP权重:  {weights['flp']*100:5.1f}%")
        print(f"  现金权重: {weights['cash']*100:5.1f}%")
        print()
    
    print("【FLP保护模式】")
    print()
    
    flp = FLPEngine()
    vix_levels = [12, 20, 35]
    
    for vix in vix_levels:
        mode = flp.determine_mode(vix)
        budget_adj = flp.calculate_budget(10000, vix)
        
        print(f"VIX = {vix:2d}")
        print(f"  模式: {mode.value}")
        print(f"  预算调整: ${budget_adj:,.0f}")
        print()
    
    print("="*60)


if __name__ == "__main__":
    demo_strategy()
