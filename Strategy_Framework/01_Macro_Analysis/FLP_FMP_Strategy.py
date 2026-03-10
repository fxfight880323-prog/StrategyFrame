"""
FLP (Fixed Leverage Puts) 尾部风险对冲策略 - FMP 版本
======================================================

使用 Financial Modeling Prep API 获取实时 VIX 和期权数据
API Key: Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq

执行规则:
- 每周五买入下周五到期、Delta -0.07至-0.10的 SPY Put
- VIX < 15 时增加20%预算
- VIX > 30 时改用 Put Spread
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# 路径设置
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', 'data_providers'))

# 导入 FMP 数据提供器
from FMPDataProvider import FMPDataProvider, FLPDataAdapter


# ============================================================
# 配置
# ============================================================
FLP_CONFIG = {
    'underlying': 'SPY',
    'delta_target': (-0.10, -0.07),
    'dte_target': 7,
    'vix_low_threshold': 15,
    'vix_high_threshold': 30,
    'budget_increase_pct': 0.20,
    'spread_width': 0.05,
    'base_budget_pct': 0.05,  # 组合价值的5%
}


class FLPMode(Enum):
    """FLP 保护模式"""
    LONG_PUT = "Long Put"
    PUT_SPREAD = "Put Spread"
    NO_HEDGE = "No Hedge"


@dataclass
class FLPTrade:
    """FLP 交易记录"""
    date: date
    underlying_price: float
    vix: float
    mode: FLPMode
    long_put_strike: float
    long_put_delta: float
    long_put_premium: float
    short_put_strike: Optional[float] = None  # 用于 Put Spread
    total_cost: float = 0.0
    budget: float = 0.0


# ============================================================
# FLP 引擎 (FMP 版本)
# ============================================================
class FLPEngineFMP:
    """
    FLP 动态保护引擎 - 使用 FMP 实时数据
    """
    
    def __init__(self, config: Dict = FLP_CONFIG):
        self.config = config
        self.fmp = FMPDataProvider()
        self.adapter = FLPDataAdapter(self.fmp)
        self.logger = self.fmp.logger
        self.trades: List[FLPTrade] = []
    
    def get_next_friday(self, from_date: date = None) -> date:
        """获取下一个周五"""
        if from_date is None:
            from_date = date.today()
        
        days_ahead = 4 - from_date.weekday()  # Friday is 4
        if days_ahead <= 0:
            days_ahead += 7
        return from_date + timedelta(days=days_ahead)
    
    def determine_mode(self, vix: float) -> FLPMode:
        """根据 VIX 确定保护模式"""
        if vix < self.config['vix_low_threshold']:
            return FLPMode.LONG_PUT
        elif vix > self.config['vix_high_threshold']:
            return FLPMode.PUT_SPREAD
        else:
            return FLPMode.LONG_PUT
    
    def calculate_budget(self, portfolio_value: float, vix: float) -> float:
        """计算保护预算"""
        base_budget = portfolio_value * self.config['base_budget_pct']
        
        if vix < self.config['vix_low_threshold']:
            # VIX 低时增加预算
            return base_budget * (1 + self.config['budget_increase_pct'])
        elif vix > self.config['vix_high_threshold']:
            # VIX 高时减少预算
            return base_budget * 0.7
        else:
            return base_budget
    
    def execute_weekly_hedge(self, portfolio_value: float = 1_000_000,
                            trade_date: date = None) -> Optional[FLPTrade]:
        """
        执行每周对冲
        
        Args:
            portfolio_value: 组合价值
            trade_date: 交易日期 (默认今天)
        
        Returns:
            FLPTrade 交易记录
        """
        if trade_date is None:
            trade_date = date.today()
        
        # 只在周五执行
        if trade_date.weekday() != 4:  # Friday
            self.logger.info(f"{trade_date} 不是周五，跳过")
            return None
        
        self.logger.info("="*60)
        self.logger.info(f"执行 FLP 周度对冲 - {trade_date}")
        self.logger.info("="*60)
        
        # 1. 获取 SPY 当前价格
        spy_quote = self.fmp.get_stock_quote('SPY')
        if not spy_quote:
            self.logger.error("无法获取 SPY 报价")
            return None
        
        spy_price = spy_quote.get('price', 0)
        self.logger.info(f"SPY 当前价格: ${spy_price:.2f}")
        
        # 2. 获取 VIX
        # 尝试获取实时 VIX，如果没有则使用模拟
        vix_data = self.adapter.get_vix_series(
            (trade_date - timedelta(days=5)).isoformat(),
            trade_date.isoformat()
        )
        
        if not vix_data.empty:
            vix = vix_data['close'].iloc[-1]
        else:
            vix = 20.0  # 默认值
        
        self.logger.info(f"VIX 指数: {vix:.2f}")
        
        # 3. 确定保护模式
        mode = self.determine_mode(vix)
        self.logger.info(f"保护模式: {mode.value}")
        
        # 4. 计算预算
        budget = self.calculate_budget(portfolio_value, vix)
        self.logger.info(f"保护预算: ${budget:,.2f}")
        
        # 5. 选择期权
        put_info = self.adapter.select_put_for_flp(
            spy_price, 
            self.config['delta_target']
        )
        
        if not put_info:
            self.logger.warning("无法选择合适的 Put 期权")
            return None
        
        long_put_strike = put_info.get('strike', spy_price * 0.95)
        long_put_delta = put_info.get('delta', -0.085)
        long_put_premium = put_info.get('premium', spy_price * 0.02)
        
        self.logger.info(f"买入 Put: Strike=${long_put_strike:.2f}, "
                        f"Delta={long_put_delta:.3f}, "
                        f"Premium=${long_put_premium:.2f}")
        
        # 6. Put Spread 处理
        short_put_strike = None
        if mode == FLPMode.PUT_SPREAD:
            short_put_strike = long_put_strike * (1 - self.config['spread_width'])
            self.logger.info(f"卖出 Put (Spread): Strike=${short_put_strike:.2f}")
        
        # 7. 计算成本
        if mode == FLPMode.LONG_PUT:
            total_cost = long_put_premium * 100  # 每手100股
        else:  # Put Spread
            short_premium = long_put_premium * 0.3  # 估算
            total_cost = (long_put_premium - short_premium) * 100
        
        self.logger.info(f"总成本: ${total_cost:.2f}")
        
        # 8. 创建交易记录
        trade = FLPTrade(
            date=trade_date,
            underlying_price=spy_price,
            vix=vix,
            mode=mode,
            long_put_strike=long_put_strike,
            long_put_delta=long_put_delta,
            long_put_premium=long_put_premium,
            short_put_strike=short_put_strike,
            total_cost=total_cost,
            budget=budget
        )
        
        self.trades.append(trade)
        
        self.logger.info("="*60)
        
        return trade
    
    def simulate_weekly_trades(self, start_date: date, end_date: date,
                               portfolio_value: float = 1_000_000) -> pd.DataFrame:
        """
        模拟历史每周交易
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            portfolio_value: 组合价值
        
        Returns:
            DataFrame with all simulated trades
        """
        self.logger.info("="*60)
        self.logger.info("模拟 FLP 历史交易")
        self.logger.info("="*60)
        
        current = start_date
        trades = []
        
        while current <= end_date:
            if current.weekday() == 4:  # Friday
                trade = self.execute_weekly_hedge(portfolio_value, current)
                if trade:
                    trades.append({
                        'date': trade.date,
                        'spy_price': trade.underlying_price,
                        'vix': trade.vix,
                        'mode': trade.mode.value,
                        'strike': trade.long_put_strike,
                        'delta': trade.long_put_delta,
                        'premium': trade.long_put_premium,
                        'cost': trade.total_cost,
                        'budget': trade.budget,
                    })
            current += timedelta(days=1)
        
        df = pd.DataFrame(trades)
        
        self.logger.info(f"\n模拟完成: {len(df)} 笔交易")
        
        if not df.empty:
            self.logger.info(f"总成本: ${df['cost'].sum():,.2f}")
            self.logger.info(f"平均成本: ${df['cost'].mean():,.2f}")
            self.logger.info(f"VIX 范围: {df['vix'].min():.1f} - {df['vix'].max():.1f}")
        
        return df
    
    def analyze_cost_vs_protection(self, trades_df: pd.DataFrame) -> Dict:
        """分析成本与保护效果"""
        if trades_df.empty:
            return {}
        
        # 按 VIX 水平分组统计
        trades_df['vix_bucket'] = pd.cut(
            trades_df['vix'], 
            bins=[0, 15, 30, 100], 
            labels=['Low (<15)', 'Normal (15-30)', 'High (>30)']
        )
        
        analysis = trades_df.groupby('vix_bucket').agg({
            'cost': ['mean', 'sum', 'count'],
            'premium': 'mean',
            'delta': 'mean'
        }).round(2)
        
        return analysis.to_dict()


# ============================================================
# 主函数
# ============================================================
def main():
    """主程序"""
    print("\n" + "="*70)
    print("FLP 尾部风险对冲策略 - FMP 版本")
    print("="*70)
    print()
    
    engine = FLPEngineFMP()
    
    # 检查今天是否需要交易
    today = date.today()
    
    print(f"今天: {today} ({today.strftime('%A')})")
    print()
    
    if today.weekday() == 4:  # Friday
        print("今天是周五，执行对冲交易...")
        trade = engine.execute_weekly_hedge(portfolio_value=1_000_000)
        
        if trade:
            print()
            print("="*70)
            print("交易执行成功")
            print("="*70)
            print(f"标的: SPY @ ${trade.underlying_price:.2f}")
            print(f"VIX: {trade.vix:.2f}")
            print(f"模式: {trade.mode.value}")
            print(f"买入 Put: Strike=${trade.long_put_strike:.2f}, Delta={trade.long_put_delta:.3f}")
            print(f"权利金: ${trade.long_put_premium:.2f}")
            print(f"总成本: ${trade.total_cost:.2f}")
    else:
        print("今天不是周五，不执行交易")
        print()
        print("模拟本周五的交易...")
        next_friday = engine.get_next_friday()
        print(f"下一个周五: {next_friday}")
    
    print()
    print("="*70)
    print("模拟历史3个月交易...")
    print("="*70)
    
    # 模拟最近3个月
    end = date.today()
    start = end - timedelta(days=90)
    
    trades_df = engine.simulate_weekly_trades(start, end)
    
    if not trades_df.empty:
        print()
        print("最近5笔交易:")
        print(trades_df.tail().to_string(index=False))
        print()
        
        # 分析成本
        analysis = engine.analyze_cost_vs_protection(trades_df)
        if analysis:
            print("成本分析 (按 VIX 水平):")
            print(analysis)
    
    print()
    print("="*70)
    print("完成")
    print("="*70)
    print()


if __name__ == "__main__":
    main()
