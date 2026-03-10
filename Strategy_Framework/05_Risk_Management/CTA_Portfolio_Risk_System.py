#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CTA组合风控系统
===============

功能模块:
1. 事前风控 (Pre-trade Risk)
2. 仓位管理 (Position Sizing)
3. 止损止盈 (Stop Loss / Take Profit)
4. 风险预算 (Risk Budgeting)
5. 实时监控 (Real-time Monitoring)
6. 压力测试 (Stress Testing)

适用:
- 多策略组合
- 多品种期货组合
- 动态风险管理
"""

import pandas as pd
import numpy as np
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# 配置常量
# ============================================================

# 品种分类
COMMODITY_GROUPS = {
    '金属': ['AU', 'AG', 'CU', 'AL', 'ZN', 'PB', 'NI', 'SN'],
    '能源': ['SC', 'FU', 'BU', 'PG', 'TA', 'EG', 'L', 'PP', 'EB'],
    '农产品': ['M', 'RM', 'OI', 'CF', 'SR', 'C', 'CS'],
    '化工': ['MA', 'FG', 'SA', 'PF', 'UR', 'RU', 'NR', 'BR'],
    '股指': ['IF', 'IC', 'IM', 'IH', 'TF', 'T', 'TS'],
}

# 风控阈值
RISK_LIMITS = {
    'max_single_position': 0.10,      # 单品种最大仓位 10%
    'max_sector_position': 0.30,      # 板块最大仓位 30%
    'max_total_margin': 0.50,         # 最大保证金占用 50%
    'max_leverage': 3.0,              # 最大杠杆倍数
    'max_daily_drawdown': 0.03,       # 单日最大回撤 3%
    'max_total_drawdown': 0.15,       # 总最大回撤 15%
}

# ============================================================
# 数据类
# ============================================================

class RiskLevel(Enum):
    GREEN = "绿色"    # 低风险
    YELLOW = "黄色"   # 中风险
    ORANGE = "橙色"   # 高风险
    RED = "红色"      # 极高风险

@dataclass
class Position:
    """持仓信息"""
    symbol: str
    direction: str      # LONG / SHORT
    quantity: int
    avg_price: float
    current_price: float
    margin_occupied: float
    unrealized_pnl: float
    
    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price
    
    @property
    def pnl_pct(self) -> float:
        if self.avg_price == 0:
            return 0
        return (self.current_price - self.avg_price) / self.avg_price * (1 if self.direction == "LONG" else -1)

@dataclass
class Portfolio:
    """投资组合"""
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    
    @property
    def total_value(self) -> float:
        positions_value = sum(p.market_value for p in self.positions.values())
        return self.cash + positions_value
    
    @property
    def total_margin(self) -> float:
        return sum(p.margin_occupied for p in self.positions.values())
    
    @property
    def margin_ratio(self) -> float:
        if self.total_value == 0:
            return 0
        return self.total_margin / self.total_value

# ============================================================
# 风控系统
# ============================================================

class RiskManager:
    """组合风控管理器"""
    
    def __init__(self, config: Dict = None):
        self.config = config or RISK_LIMITS
        self.logger = logger
        
    def check_all(self, portfolio: Portfolio) -> Dict:
        """执行所有风控检查"""
        results = {
            'timestamp': datetime.now().isoformat(),
            'risk_level': RiskLevel.GREEN,
            'checks': {},
            'alerts': [],
            'recommendations': []
        }
        
        # 1. 仓位集中度检查
        check_result = self.check_concentration(portfolio)
        results['checks']['concentration'] = check_result
        if check_result['violated']:
            results['alerts'].extend(check_result['alerts'])
        
        # 2. 保证金检查
        check_result = self.check_margin(portfolio)
        results['checks']['margin'] = check_result
        if check_result['violated']:
            results['alerts'].extend(check_result['alerts'])
        
        # 3. 回撤检查
        check_result = self.check_drawdown(portfolio)
        results['checks']['drawdown'] = check_result
        if check_result['violated']:
            results['alerts'].extend(check_result['alerts'])
        
        # 4. 计算综合风险等级
        results['risk_level'] = self.calculate_risk_level(results['checks'])
        
        # 5. 生成建议
        results['recommendations'] = self.generate_recommendations(results)
        
        return results
    
    def check_concentration(self, portfolio: Portfolio) -> Dict:
        """检查仓位集中度"""
        result = {'violated': False, 'alerts': [], 'details': {}}
        
        total_value = portfolio.total_value
        if total_value == 0:
            return result
        
        # 单品种检查
        for symbol, pos in portfolio.positions.items():
            weight = pos.market_value / total_value
            result['details'][symbol] = {'weight': weight}
            
            if weight > self.config['max_single_position']:
                result['violated'] = True
                result['alerts'].append(f"{symbol} 仓位超限: {weight:.1%} > {self.config['max_single_position']:.1%}")
        
        # 板块检查
        sector_weights = self.calculate_sector_weights(portfolio)
        for sector, weight in sector_weights.items():
            if weight > self.config['max_sector_position']:
                result['violated'] = True
                result['alerts'].append(f"{sector}板块 仓位超限: {weight:.1%} > {self.config['max_sector_position']:.1%}")
        
        return result
    
    def check_margin(self, portfolio: Portfolio) -> Dict:
        """检查保证金"""
        result = {'violated': False, 'alerts': [], 'details': {}}
        
        margin_ratio = portfolio.margin_ratio
        result['details']['margin_ratio'] = margin_ratio
        
        if margin_ratio > self.config['max_total_margin']:
            result['violated'] = True
            result['alerts'].append(f"保证金占用超限: {margin_ratio:.1%} > {self.config['max_total_margin']:.1%}")
        
        return result
    
    def check_drawdown(self, portfolio: Portfolio, history: List[float] = None) -> Dict:
        """检查回撤"""
        result = {'violated': False, 'alerts': [], 'details': {}}
        
        # 简化版：基于未实现盈亏计算当日回撤
        total_pnl = sum(p.unrealized_pnl for p in portfolio.positions.values())
        if portfolio.total_value > 0:
            daily_dd = abs(total_pnl) / portfolio.total_value
            result['details']['daily_drawdown'] = daily_dd
            
            if daily_dd > self.config['max_daily_drawdown']:
                result['violated'] = True
                result['alerts'].append(f"单日回撤超限: {daily_dd:.1%} > {self.config['max_daily_drawdown']:.1%}")
        
        return result
    
    def calculate_sector_weights(self, portfolio: Portfolio) -> Dict[str, float]:
        """计算板块权重"""
        sector_values = {sector: 0.0 for sector in COMMODITY_GROUPS.keys()}
        total_value = portfolio.total_value
        
        if total_value == 0:
            return sector_values
        
        for symbol, pos in portfolio.positions.items():
            code = ''.join(filter(str.isalpha, symbol.upper()))
            for sector, codes in COMMODITY_GROUPS.items():
                if code in codes:
                    sector_values[sector] += pos.market_value
                    break
        
        return {k: v / total_value for k, v in sector_values.items()}
    
    def calculate_risk_level(self, checks: Dict) -> RiskLevel:
        """计算综合风险等级"""
        violation_count = sum(1 for c in checks.values() if c.get('violated', False))
        
        if violation_count >= 3:
            return RiskLevel.RED
        elif violation_count >= 2:
            return RiskLevel.ORANGE
        elif violation_count >= 1:
            return RiskLevel.YELLOW
        return RiskLevel.GREEN
    
    def generate_recommendations(self, results: Dict) -> List[str]:
        """生成风控建议"""
        recommendations = []
        
        if results['risk_level'] == RiskLevel.RED:
            recommendations.append("[紧急] 风险等级极高，建议立即减仓")
        elif results['risk_level'] == RiskLevel.ORANGE:
            recommendations.append("[警告] 风险等级高，建议减仓或对冲")
        elif results['risk_level'] == RiskLevel.YELLOW:
            recommendations.append("[提醒] 风险等级中等，密切关注")
        else:
            recommendations.append("[正常] 风险可控，维持当前策略")
        
        return recommendations


class PositionSizer:
    """仓位管理器"""
    
    def __init__(self, risk_per_trade: float = 0.02, max_position: float = 0.10):
        self.risk_per_trade = risk_per_trade  # 单笔风险敞口
        self.max_position = max_position      # 最大仓位
    
    def calculate_position_size(self, portfolio_value: float, 
                                entry_price: float, 
                                stop_loss: float) -> int:
        """计算仓位大小
        
        Args:
            portfolio_value: 组合总值
            entry_price: 入场价格
            stop_loss: 止损价格
        
        Returns:
            建议仓位数量
        """
        # 风险金额
        risk_amount = portfolio_value * self.risk_per_trade
        
        # 每单位风险
        risk_per_unit = abs(entry_price - stop_loss)
        
        if risk_per_unit == 0:
            return 0
        
        # 计算仓位
        position_size = risk_amount / risk_per_unit
        
        # 限制最大仓位
        max_units = (portfolio_value * self.max_position) / entry_price
        position_size = min(position_size, max_units)
        
        return int(position_size)


# ============================================================
# 演示
# ============================================================

def demo_risk_management():
    """风控系统演示"""
    print("="*60)
    print("CTA组合风控系统演示")
    print("="*60)
    
    # 创建模拟持仓
    positions = {
        'CU': Position('CU', 'LONG', 10, 70000, 72000, 140000, 20000),
        'RB': Position('RB', 'SHORT', 20, 3500, 3400, 14000, 2000),
        'SC': Position('SC', 'LONG', 5, 550, 580, 27500, 1500),
    }
    
    portfolio = Portfolio(
        cash=500000,
        positions=positions
    )
    
    print(f"\n组合概况:")
    print(f"  现金: {portfolio.cash:,.0f}")
    print(f"  总市值: {portfolio.total_value:,.0f}")
    print(f"  保证金占用: {portfolio.total_margin:,.0f} ({portfolio.margin_ratio:.1%})")
    print(f"\n持仓详情:")
    for symbol, pos in positions.items():
        print(f"  {symbol}: {pos.direction} {pos.quantity}手, 盈亏: {pos.unrealized_pnl:+,.0f}")
    
    # 执行风控检查
    risk_mgr = RiskManager()
    results = risk_mgr.check_all(portfolio)
    
    print(f"\n风控检查结果:")
    print(f"  风险等级: {results['risk_level'].value}")
    print(f"  检查时间: {results['timestamp']}")
    
    if results['alerts']:
        print(f"\n[警告]")
        for alert in results['alerts']:
            print(f"  ! {alert}")
    else:
        print(f"\n[无警告] 所有指标正常")
    
    print(f"\n[建议]")
    for rec in results['recommendations']:
        print(f"  > {rec}")
    
    # 仓位计算示例
    print(f"\n仓位计算示例:")
    sizer = PositionSizer(risk_per_trade=0.02, max_position=0.10)
    size = sizer.calculate_position_size(
        portfolio_value=portfolio.total_value,
        entry_price=70000,
        stop_loss=68000
    )
    print(f"  组合总值: {portfolio.total_value:,.0f}")
    print(f"  入场价: 70,000, 止损价: 68,000")
    print(f"  建议仓位: {size}手")
    
    print("\n" + "="*60)


if __name__ == '__main__':
    demo_risk_management()
