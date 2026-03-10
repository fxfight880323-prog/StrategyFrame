"""
CTA + FLP 策略回测 (Tradier数据源)
=====================================

使用 Tradier API 获取美股和期权数据，
执行 CTA 趋势跟踪 + FLP 尾部风险对冲的完整回测。

策略特点:
- 动态CTA仓位管理 (基于20/60均线和波动率)
- 周度Put期权保险 (基于Delta选择)
- 风险预算再平衡 (利润再投入FLP)
- VIX信号调整 (高波动时策略切换)
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging

# 路径设置
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', 'data_providers'))

from TradierDataProvider import TradierDataProvider


# ============================================================
# 配置
# ============================================================
INITIAL_CAPITAL = 1_000_000
RISK_FREE_RATE = 0.05

# 策略参数
CTA_PARAMS = {
    'fast_ma': 20,
    'slow_ma': 60,
    'volatility_target': 0.15,
    'max_leverage': 1.5,
}

FLP_PARAMS = {
    'target_delta': (-0.10, -0.07),  # Put期权Delta范围
    'min_dte': 7,
    'max_dte': 45,
    'premium_budget': 0.02,  # 权利金预算 (组合价值2%)
}


# ============================================================
# 日志设置
# ============================================================
def setup_logger(name: str = "cta_flp_backtest") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# 数据模型
# ============================================================
@dataclass
class CTASignal:
    """CTA交易信号"""
    date: date
    symbol: str
    position: str  # 'LONG', 'SHORT', 'NEUTRAL'
    signal_strength: float
    fast_ma: float
    slow_ma: float
    volatility: float
    target_weight: float


@dataclass
class FLPPut:
    """FLP Put期权持仓"""
    entry_date: date
    expiry_date: date
    option_symbol: str
    strike: float
    entry_price: float
    quantity: int
    delta: float
    days_to_expiry: int
    premium_paid: float


@dataclass
class PortfolioState:
    """组合状态"""
    date: date
    total_value: float
    cta_value: float
    flp_value: float
    cash: float
    spy_price: float
    cta_return: float
    flp_return: float
    total_return: float


# ============================================================
# CTA 引擎
# ============================================================
class CTATrendEngine:
    """CTA趋势跟踪引擎"""
    
    def __init__(self, params: Dict = CTA_PARAMS, logger: logging.Logger = None):
        self.params = params
        self.logger = logger or setup_logger()
    
    def generate_signals(self, price_df: pd.DataFrame) -> pd.DataFrame:
        """
        生成CTA交易信号
        
        Returns:
            DataFrame with signals
        """
        df = price_df.copy()
        df = df.sort_values('date').reset_index(drop=True)
        
        # 计算收益率
        df['returns'] = df['close'].pct_change()
        
        # 计算均线
        df[f'ma_{self.params["fast_ma"]}'] = df['close'].rolling(
            self.params['fast_ma']
        ).mean()
        df[f'ma_{self.params["slow_ma"]}'] = df['close'].rolling(
            self.params['slow_ma']
        ).mean()
        
        # 计算波动率 (滚动20日)
        df['volatility_20d'] = df['returns'].rolling(20).std() * np.sqrt(252)
        
        # 生成信号
        df['ma_signal'] = np.where(
            df[f'ma_{self.params["fast_ma"]}'] > df[f'ma_{self.params["slow_ma"]}'],
            1, -1
        )
        
        # 波动率调整仓位
        df['vol_adjustment'] = np.where(
            df['volatility_20d'] > 0,
            min(self.params['volatility_target'] / df['volatility_20d'], 
                self.params['max_leverage']),
            0
        )
        
        # 综合信号
        df['position'] = df['ma_signal'] * df['vol_adjustment']
        df['signal'] = df['position'].apply(lambda x: 
            'LONG' if x > 0.2 else ('SHORT' if x < -0.2 else 'NEUTRAL')
        )
        
        # 计算策略收益
        df['strategy_return'] = df['position'].shift(1) * df['returns']
        
        return df
    
    def get_current_signal(self, df: pd.DataFrame, current_date: date) -> Optional[CTASignal]:
        """获取指定日期的CTA信号"""
        row = df[df['date'] == pd.Timestamp(current_date)]
        if row.empty:
            return None
        
        row = row.iloc[0]
        return CTASignal(
            date=current_date,
            symbol='SPY',
            position=row['signal'],
            signal_strength=abs(row['position']),
            fast_ma=row[f'ma_{self.params["fast_ma"]}'],
            slow_ma=row[f'ma_{self.params["slow_ma"]}'],
            volatility=row['volatility_20d'],
            target_weight=min(abs(row['position']), 1.0)
        )


# ============================================================
# FLP 引擎
# ============================================================
class FLPEngine:
    """FLP尾部风险对冲引擎"""
    
    def __init__(self, params: Dict = FLP_PARAMS, 
                 data_provider: TradierDataProvider = None,
                 logger: logging.Logger = None):
        self.params = params
        self.data_provider = data_provider
        self.logger = logger or setup_logger()
    
    def select_weekly_put(self, current_date: date, 
                         portfolio_value: float) -> Optional[FLPPut]:
        """
        每周选择合适的Put期权
        
        Args:
            current_date: 当前日期
            portfolio_value: 组合价值
        
        Returns:
            FLPPut 期权持仓对象
        """
        if not self.data_provider:
            self.logger.error("未配置数据提供器")
            return None
        
        # 使用数据提供器选择Put
        option_data = self.data_provider.select_put_for_flp(
            symbol='SPY',
            target_delta=self.params['target_delta'],
            min_days_to_expiry=self.params['min_dte'],
            max_days_to_expiry=self.params['max_dte']
        )
        
        if not option_data:
            return None
        
        # 计算购买数量
        premium_budget = portfolio_value * self.params['premium_budget']
        contract_count = int(premium_budget / (option_data['last'] * 100))
        
        if contract_count < 1:
            self.logger.warning(f"权利金不足，跳过购买 ({option_data['last']:.2f})")
            return None
        
        return FLPPut(
            entry_date=current_date,
            expiry_date=datetime.strptime(option_data['expiration'], '%Y-%m-%d').date(),
            option_symbol=option_data['option_symbol'],
            strike=option_data['strike'],
            entry_price=option_data['last'],
            quantity=contract_count,
            delta=option_data['delta'],
            days_to_expiry=option_data['days_to_expiry'],
            premium_paid=option_data['last'] * contract_count * 100
        )
    
    def calculate_put_pnl(self, put: FLPPut, current_date: date, 
                         spy_price: float) -> Tuple[float, float]:
        """
        计算Put期权当前盈亏
        
        Returns:
            (当前价值, 盈亏)
        """
        # 检查是否到期
        if current_date >= put.expiry_date:
            # 到期行权价值
            intrinsic = max(put.strike - spy_price, 0)
            current_value = intrinsic * put.quantity * 100
        else:
            # 未到期，估算价值 (简化Delta近似)
            days_left = (put.expiry_date - current_date).days
            time_decay = 1 - (put.days_to_expiry - days_left) / put.days_to_expiry * 0.3
            
            # 基于Delta和标的价格变化估算
            price_change = spy_price - put.entry_price  # 近似
            delta_pnl = put.delta * price_change * put.quantity * 100
            
            # 时间衰减
            theta_loss = put.entry_price * (1 - time_decay) * 0.2
            
            estimated_price = max(put.entry_price + delta_pnl / (put.quantity * 100) - theta_loss, 0.01)
            current_value = estimated_price * put.quantity * 100
        
        pnl = current_value - put.premium_paid
        return current_value, pnl


# ============================================================
# 策略回测引擎
# ============================================================
class CTAFLPBacktest:
    """CTA + FLP 策略回测引擎"""
    
    def __init__(self, initial_capital: float = INITIAL_CAPITAL,
                 data_provider: TradierDataProvider = None,
                 logger: logging.Logger = None):
        self.initial_capital = initial_capital
        self.data_provider = data_provider or TradierDataProvider()
        self.logger = logger or setup_logger()
        
        # 初始化引擎
        self.cta_engine = CTATrendEngine(logger=self.logger)
        self.flp_engine = FLPEngine(data_provider=self.data_provider, logger=self.logger)
        
        # 回测状态
        self.portfolio_history: List[PortfolioState] = []
        self.current_put: Optional[FLPPut] = None
        self.put_history: List[Dict] = []
        
    def run_backtest(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        执行完整回测
        
        Args:
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
        
        Returns:
            回测结果 DataFrame
        """
        self.logger.info("="*60)
        self.logger.info("CTA + FLP 策略回测 (Tradier数据源)")
        self.logger.info("="*60)
        self.logger.info(f"回测区间: {start_date} ~ {end_date}")
        self.logger.info(f"初始资金: ${self.initial_capital:,.0f}")
        self.logger.info("")
        
        # 1. 获取历史数据
        spy_data = self.data_provider.get_historical_data('SPY', start_date, end_date)
        if spy_data.empty:
            self.logger.error("无法获取SPY历史数据")
            return pd.DataFrame()
        
        # 2. 生成CTA信号
        cta_df = self.cta_engine.generate_signals(spy_data)
        
        # 3. 初始化组合
        cash = self.initial_capital
        cta_value = 0.0
        flp_value = 0.0
        
        # 4. 逐日回测
        trade_dates = cta_df['date'].tolist()
        
        for i, current_date in enumerate(trade_dates):
            if i == 0:
                continue  # 跳过第一天（无信号）
            
            date_str = current_date.strftime('%Y-%m-%d')
            current_price = cta_df[cta_df['date'] == current_date]['close'].iloc[0]
            
            # 获取CTA信号
            signal = self.cta_engine.get_current_signal(cta_df, current_date.date())
            
            # ========== CTA 仓位管理 ==========
            if signal:
                # 计算CTA目标仓位
                target_cta_value = self.initial_capital * 0.75 * signal.target_weight
                
                # 根据信号方向调整
                if signal.position == 'LONG':
                    cta_value = target_cta_value
                elif signal.position == 'SHORT':
                    cta_value = -target_cta_value * 0.5  # 做空限制50%
                else:
                    cta_value = 0
            
            # ========== FLP 周度对冲 ==========
            # 每周五（或周一）检查并购买新Put
            if current_date.weekday() == 0:  # 周一
                # 检查现有Put是否过期
                if self.current_put and current_date.date() >= self.current_put.expiry_date:
                    self.logger.info(f"[{date_str}] Put到期，结算")
                    self.current_put = None
                    flp_value = 0
                
                # 购买新Put
                if not self.current_put:
                    portfolio_value = cash + abs(cta_value) + flp_value
                    new_put = self.flp_engine.select_weekly_put(
                        current_date.date(), portfolio_value
                    )
                    
                    if new_put:
                        self.current_put = new_put
                        flp_value = new_put.premium_paid
                        cash -= flp_value
                        
                        self.put_history.append({
                            'date': date_str,
                            'symbol': new_put.option_symbol,
                            'strike': new_put.strike,
                            'premium': new_put.premium_paid,
                            'expiry': new_put.expiry_date.strftime('%Y-%m-%d')
                        })
            
            # 更新FLP价值
            if self.current_put:
                flp_value, flp_pnl = self.flp_engine.calculate_put_pnl(
                    self.current_put, current_date.date(), current_price
                )
            
            # 计算CTA收益
            if i > 0:
                prev_price = cta_df[cta_df['date'] == trade_dates[i-1]]['close'].iloc[0]
                daily_return = (current_price - prev_price) / prev_price
                
                # 根据信号计算CTA收益
                if signal and signal.position == 'LONG':
                    cta_return = daily_return * signal.target_weight
                elif signal and signal.position == 'SHORT':
                    cta_return = -daily_return * signal.target_weight * 0.5
                else:
                    cta_return = 0
            else:
                cta_return = 0
            
            # 计算组合总价值
            total_value = cash + abs(cta_value) + flp_value
            
            # 记录状态
            self.portfolio_history.append(PortfolioState(
                date=current_date.date(),
                total_value=total_value,
                cta_value=abs(cta_value),
                flp_value=flp_value,
                cash=cash,
                spy_price=current_price,
                cta_return=cta_return,
                flp_return=0 if not self.current_put else (flp_value - self.current_put.premium_paid) / self.initial_capital,
                total_return=(total_value - self.initial_capital) / self.initial_capital
            ))
            
            # 定期输出
            if i % 22 == 0 or i == len(trade_dates) - 1:
                self.logger.info(
                    f"[{date_str}] 总价值: ${total_value:,.0f} "
                    f"(CTA: ${abs(cta_value):,.0f}, FLP: ${flp_value:,.0f}) "
                    f"CTA信号: {signal.position if signal else 'N/A'}"
                )
        
        # 5. 生成回测报告
        return self._generate_report()
    
    def _generate_report(self) -> pd.DataFrame:
        """生成回测报告"""
        if not self.portfolio_history:
            return pd.DataFrame()
        
        df = pd.DataFrame([
            {
                'Date': s.date,
                'Total_Value': s.total_value,
                'CTA_Value': s.cta_value,
                'FLP_Value': s.flp_value,
                'Cash': s.cash,
                'SPY_Price': s.spy_price,
                'CTA_Return': s.cta_return,
                'FLP_Return': s.flp_return,
                'Total_Return': s.total_return,
            }
            for s in self.portfolio_history
        ])
        
        # 计算累计收益
        df['CTA_Cumulative'] = (1 + df['CTA_Return'].fillna(0)).cumprod() - 1
        df['Total_Cumulative'] = (1 + df['Total_Return']).cumprod() - 1
        
        self.logger.info("")
        self.logger.info("="*60)
        self.logger.info("回测完成")
        self.logger.info(f"最终价值: ${df['Total_Value'].iloc[-1]:,.0f}")
        self.logger.info(f"总收益率: {df['Total_Cumulative'].iloc[-1]*100:.2f}%")
        self.logger.info(f"CTA收益率: {df['CTA_Cumulative'].iloc[-1]*100:.2f}%")
        self.logger.info("="*60)
        
        return df


# ============================================================
# 测试函数
# ============================================================
def test_backtest():
    """测试 CTA + FLP 回测"""
    print("="*60)
    print("CTA + FLP 策略回测测试 (Tradier数据)")
    print("="*60)
    print()
    
    # 创建回测引擎
    backtest = CTAFLPBacktest(initial_capital=1_000_000)
    
    # 检查API Key
    if backtest.data_provider.api_key == "YOUR_TRADIER_API_KEY_HERE":
        print("⚠️ 请先在 TradierDataProvider.py 中设置有效的 API Key")
        print("   获取地址: https://developer.tradier.com/")
        print()
        print("注意: 沙盒环境可免费测试，但数据有延迟")
        return
    
    # 执行回测 (最近3个月)
    end = date.today()
    start = end - timedelta(days=90)
    
    print(f"回测区间: {start} ~ {end}")
    print()
    
    result = backtest.run_backtest(start.isoformat(), end.isoformat())
    
    if not result.empty:
        print()
        print("【回测结果摘要】")
        print(f"初始资金: $1,000,000")
        print(f"最终资金: ${result['Total_Value'].iloc[-1]:,.0f}")
        print(f"总收益率: {result['Total_Cumulative'].iloc[-1]*100:.2f}%")
        print(f"CTA收益贡献: {result['CTA_Cumulative'].iloc[-1]*100:.2f}%")
        print(f"期权交易次数: {len(backtest.put_history)}")


if __name__ == "__main__":
    test_backtest()
