"""
CTA + FLP 整合策略 - FMP 数据版本
=================================

使用 Financial Modeling Prep API 获取实时数据
- CTA: 20/60日MA交叉趋势跟踪
- FLP: 每周买入 Delta -0.07~-0.10 的 SPY Put
- 风险平衡: CTA盈利时回哺FLP保护

API Key: Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field

# 路径设置
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', 'data_providers'))

# 导入 FMP 数据提供器和策略模块
from FMPDataProvider import FMPDataProvider, CTADataAdapter, FLPDataAdapter
from CTA_FMP_Strategy import CTAEngineFMP
from FLP_FMP_Strategy import FLPEngineFMP, FLPMode


# ============================================================
# 配置
# ============================================================
INTEGRATED_CONFIG = {
    # CTA配置
    'cta_symbols': ['AAPL', 'MSFT', 'NVDA', 'SPY', 'QQQ'],
    'cta_weight': 0.75,
    
    # FLP配置
    'flp_weight': 0.05,
    
    # 风险平衡
    'cash_weight': 0.20,
    'profit_reinvest_pct': 0.15,
    'max_flp_weight': 0.10,
    'min_flp_weight': 0.02,
    
    # 初始资金
    'initial_capital': 1_000_000,
}


@dataclass
class PortfolioState:
    """组合状态"""
    date: date
    total_value: float = 1_000_000.0
    cta_allocation: float = 750_000.0  # 75%
    flp_allocation: float = 50_000.0   # 5%
    cash_allocation: float = 200_000.0 # 20%
    
    cta_pnl: float = 0.0
    flp_cost: float = 0.0
    
    cta_positions: Dict[str, Dict] = field(default_factory=dict)
    flp_position: Optional[Dict] = None


# ============================================================
# 整合策略引擎
# ============================================================
class IntegratedStrategyFMP:
    """
    CTA + FLP 整合策略引擎
    
    1. 每日更新 CTA 信号
    2. 每周五执行 FLP 保护
    3. 动态调整风险预算
    """
    
    def __init__(self, config: Dict = INTEGRATED_CONFIG):
        self.config = config
        self.cta_engine = CTAEngineFMP()
        self.flp_engine = FLPEngineFMP()
        self.fmp = FMPDataProvider()
        self.logger = self.fmp.logger
        
        self.portfolio = PortfolioState(date=date.today())
        self.history: List[PortfolioState] = []
    
    def calculate_dynamic_allocation(self, market_regime: str = 'normal') -> Dict[str, float]:
        """
        计算动态资金分配
        
        Args:
            market_regime: 市场环境 (bull/normal/bear)
        
        Returns:
            Dict with allocation weights
        """
        base_cta = self.config['cta_weight']
        base_flp = self.config['flp_weight']
        base_cash = self.config['cash_weight']
        
        # 1. 盈利回哺机制
        profit_boost = 0.0
        if self.portfolio.cta_pnl > 0:
            # CTA盈利时，提取15%增持FLP
            profit_boost = min(
                self.portfolio.cta_pnl * self.config['profit_reinvest_pct'],
                self.portfolio.total_value * 0.05  # 限制最大转移5%
            )
        
        cta_weight = base_cta - (profit_boost / self.portfolio.total_value)
        flp_weight = base_flp + (profit_boost / self.portfolio.total_value)
        
        # 2. 市场环境调整
        if market_regime == 'bull':
            # 牛市收缩CTA，保留FLP防守
            cta_weight *= 0.8
            cash_weight = 1 - cta_weight - flp_weight + (base_cta * 0.2)
        elif market_regime == 'bear':
            # 熊市增加保护
            flp_weight = min(flp_weight * 1.5, self.config['max_flp_weight'])
            cta_weight = max(cta_weight * 0.7, 0.4)
            cash_weight = 1 - cta_weight - flp_weight
        else:
            cash_weight = base_cash
        
        # 3. 边界检查
        flp_weight = max(min(flp_weight, self.config['max_flp_weight']), 
                        self.config['min_flp_weight'])
        cta_weight = max(min(cta_weight, 0.85), 0.40)
        cash_weight = max(0, 1 - cta_weight - flp_weight)
        
        return {
            'cta': cta_weight,
            'flp': flp_weight,
            'cash': cash_weight
        }
    
    def update_cta_positions(self):
        """更新 CTA 持仓信号"""
        self.logger.info("\n更新 CTA 信号...")
        
        # 获取最新信号
        signals = self.cta_engine.analyze_symbols(
            symbols=self.config['cta_symbols'],
            lookback_days=120
        )
        
        if signals.empty:
            self.logger.warning("无法获取CTA信号")
            return
        
        # 转换为持仓
        self.portfolio.cta_positions = {}
        for _, row in signals.iterrows():
            symbol = row['symbol']
            signal = row['signal']
            score = row['score']
            
            # 只保留多头信号且评分>60的
            if signal == 'LONG' and score > 60:
                self.portfolio.cta_positions[symbol] = {
                    'signal': signal,
                    'score': score,
                    'price': row['price'],
                    'weight': score / 100 * 0.2,  # 按评分分配权重，最大20%
                }
        
        self.logger.info(f"CTA持仓: {len(self.portfolio.cta_positions)} 只")
        for symbol, pos in self.portfolio.cta_positions.items():
            self.logger.info(f"  {symbol}: Score={pos['score']:.1f}, Weight={pos['weight']*100:.1f}%")
    
    def execute_flp_hedge(self, trade_date: date = None):
        """执行 FLP 对冲"""
        if trade_date is None:
            trade_date = date.today()
        
        # 只在周五执行
        if trade_date.weekday() != 4:
            return None
        
        self.logger.info("\n执行 FLP 周度对冲...")
        
        # 计算当前FLP分配
        weights = self.calculate_dynamic_allocation()
        flp_budget = self.portfolio.total_value * weights['flp']
        
        # 执行交易
        trade = self.flp_engine.execute_weekly_hedge(
            portfolio_value=self.portfolio.total_value,
            trade_date=trade_date
        )
        
        if trade:
            self.portfolio.flp_position = {
                'date': trade.date,
                'strike': trade.long_put_strike,
                'delta': trade.long_put_delta,
                'cost': trade.total_cost,
                'mode': trade.mode.value,
            }
            self.portfolio.flp_cost += trade.total_cost
            
            self.logger.info(f"FLP交易成功: Cost=${trade.total_cost:.2f}")
        
        return trade
    
    def run_daily_update(self, current_date: date = None):
        """每日更新"""
        if current_date is None:
            current_date = date.today()
        
        self.logger.info("="*70)
        self.logger.info(f"每日更新 - {current_date}")
        self.logger.info("="*70)
        
        # 1. 更新CTA信号
        self.update_cta_positions()
        
        # 2. 执行FLP对冲（如果是周五）
        if current_date.weekday() == 4:
            self.execute_flp_hedge(current_date)
        
        # 3. 计算当前分配
        weights = self.calculate_dynamic_allocation()
        
        self.logger.info("\n当前资金分配:")
        self.logger.info(f"  CTA:  {weights['cta']*100:.1f}%  "
                        f"(${self.portfolio.total_value * weights['cta']:,.0f})")
        self.logger.info(f"  FLP:  {weights['flp']*100:.1f}%  "
                        f"(${self.portfolio.total_value * weights['flp']:,.0f})")
        self.logger.info(f"  现金: {weights['cash']*100:.1f}%  "
                        f"(${self.portfolio.total_value * weights['cash']:,.0f})")
        
        # 4. 保存历史
        self.history.append(PortfolioState(
            date=current_date,
            total_value=self.portfolio.total_value,
            cta_allocation=self.portfolio.total_value * weights['cta'],
            flp_allocation=self.portfolio.total_value * weights['flp'],
            cash_allocation=self.portfolio.total_value * weights['cash'],
            cta_pnl=self.portfolio.cta_pnl,
            flp_cost=self.portfolio.flp_cost,
            cta_positions=self.portfolio.cta_positions.copy(),
            flp_position=self.portfolio.flp_position.copy() if self.portfolio.flp_position else None
        ))
        
        self.logger.info("="*70)
    
    def generate_report(self) -> pd.DataFrame:
        """生成策略报告"""
        if not self.history:
            return pd.DataFrame()
        
        records = []
        for state in self.history:
            records.append({
                'date': state.date,
                'total_value': state.total_value,
                'cta_allocation': state.cta_allocation,
                'flp_allocation': state.flp_allocation,
                'cash_allocation': state.cash_allocation,
                'cta_pnl': state.cta_pnl,
                'flp_cost': state.flp_cost,
                'cta_positions': len(state.cta_positions),
            })
        
        return pd.DataFrame(records)


# ============================================================
# 主函数
# ============================================================
def main():
    """主程序"""
    print("\n" + "="*70)
    print("CTA + FLP 整合策略 - FMP 实时数据版本")
    print("="*70)
    print()
    
    # 创建策略引擎
    strategy = IntegratedStrategyFMP()
    
    # 运行今日更新
    strategy.run_daily_update()
    
    print()
    print("="*70)
    print("策略摘要")
    print("="*70)
    print()
    
    # CTA持仓
    print("【CTA趋势持仓】")
    if strategy.portfolio.cta_positions:
        for symbol, pos in strategy.portfolio.cta_positions.items():
            print(f"  {symbol}: 信号={pos['signal']}, 评分={pos['score']:.1f}, "
                  f"权重={pos['weight']*100:.1f}%")
    else:
        print("  无活跃持仓")
    print()
    
    # FLP保护
    print("【FLP保护状态】")
    if strategy.portfolio.flp_position:
        flp = strategy.portfolio.flp_position
        print(f"  持仓: SPY Put")
        print(f"  行权价: ${flp['strike']:.2f}")
        print(f"  Delta: {flp['delta']:.3f}")
        print(f"  成本: ${flp['cost']:.2f}")
        print(f"  模式: {flp['mode']}")
    else:
        print("  今日无FLP交易")
    print()
    
    # 资金分配
    print("【资金分配】")
    weights = strategy.calculate_dynamic_allocation()
    print(f"  CTA策略:  {weights['cta']*100:5.1f}%")
    print(f"  FLP保护:  {weights['flp']*100:5.1f}%")
    print(f"  现金:     {weights['cash']*100:5.1f}%")
    print()
    
    # 运行模拟（最近30天）
    print("="*70)
    print("模拟最近30天运行...")
    print("="*70)
    
    end = date.today()
    start = end - timedelta(days=30)
    current = start
    
    while current <= end:
        strategy.run_daily_update(current)
        current += timedelta(days=1)
    
    # 生成报告
    report = strategy.generate_report()
    if not report.empty:
        print()
        print("策略运行历史 (最近10天):")
        print(report.tail(10).to_string(index=False))
    
    print()
    print("="*70)
    print("完成")
    print("="*70)
    print()


if __name__ == "__main__":
    main()
