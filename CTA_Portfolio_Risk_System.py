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
- 多策略组�?
- 多品种期货组�?
- 动态风险管�?
"""

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import logging
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# 配置参数
# ============================================================
RISK_LIMITS = {
    # 单一限制
    'max_position_per_symbol': 0.10,      # 单品种最�?0%
    'max_position_per_category': 0.30,    # 单板块最�?0%
    'max_leverage': 2.0,                   # 最大杠�?�?
    'max_margin_usage': 0.70,             # 保证金使用率最�?0%
    
    # 组合限制
    'max_portfolio_volatility': 0.15,     # 组合年化波动率目�?5%
    'max_drawdown_limit': 0.15,           # 最大回撤限�?5%
    'daily_var_limit': 0.02,              # 单日VaR限制2%
    
    # 流动性限�?
    'max_position_pct_of_volume': 0.05,   # 仓位不超过日成交量的5%
    'max_illiquid_allocation': 0.20,      # 非流动性品种最�?0%
}

CATEGORY_MAP = {
    '黑色': ['RB', 'HC', 'I', 'J', 'JM'],
    '有色': ['CU', 'AL', 'ZN', 'NI', 'SN', 'AU', 'AG'],
    '能源': ['SC', 'LU', 'FU'],
    '化工': ['TA', 'MA', 'PP', 'L', 'EG', 'PVC'],
    '农产�?: ['M', 'RM', 'OI', 'CF', 'SR', 'C', 'CS'],
    '股指': ['IF', 'IC', 'IM'],
    '国�?: ['T', 'TF', 'TS'],
}


# ============================================================
# 数据模型
# ============================================================
class RiskLevel(Enum):
    GREEN = "正常"
    YELLOW = "警告"
    ORANGE = "风险"
    RED = "危险"

@dataclass
class RiskCheckResult:
    """风险检查结�?""
    passed: bool
    risk_level: RiskLevel
    check_name: str
    message: str
    current_value: float
    limit_value: float
    action_required: Optional[str] = None

@dataclass
class Position:
    """持仓"""
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    entry_date: date
    direction: int  # 1=�? -1=�?
    stop_loss: float
    take_profit: float
    
    @property
    def market_value(self) -> float:
        return abs(self.quantity) * self.current_price
    
    @property
    def unrealized_pnl(self) -> float:
        return self.quantity * (self.current_price - self.entry_price)
    
    @property
    def unrealized_pnl_pct(self) -> float:
        return (self.current_price / self.entry_price - 1) * self.direction

@dataclass
class PortfolioRiskState:
    """组合风险状�?""
    date: date
    total_value: float
    positions: Dict[str, Position]
    gross_exposure: float
    net_exposure: float
    portfolio_volatility: float
    var_95: float
    stress_loss: float
    margin_used: float
    risk_level: RiskLevel
    

# ============================================================
# 事前风控 (Pre-trade Risk)
# ============================================================
class PreTradeRiskManager:
    """事前风险管控"""
    
    def __init__(self, limits: Dict = RISK_LIMITS, logger: logging.Logger = None):
        self.limits = limits
        self.logger = logger or logging.getLogger(__name__)
        self.recent_trades: List[Dict] = []
        self.daily_volume_estimate: Dict[str, float] = {}
    
    def check_order(self, 
                   symbol: str,
                   order_quantity: int,
                   order_price: float,
                   direction: int,
                   current_portfolio: Dict[str, Position],
                   total_capital: float) -> List[RiskCheckResult]:
        """
        订单风险检�?
        
        Returns:
            风险检查结果列�?
        """
        results = []
        
        # 1. 单品种仓位限制检�?
        result = self._check_symbol_limit(symbol, order_quantity, order_price, 
                                         current_portfolio, total_capital)
        results.append(result)
        
        # 2. 板块集中度检�?
        result = self._check_category_limit(symbol, order_quantity, order_price,
                                           current_portfolio, total_capital)
        results.append(result)
        
        # 3. 总仓位限制检�?
        result = self._check_total_exposure(order_quantity, order_price, 
                                           current_portfolio, total_capital)
        results.append(result)
        
        # 4. 流动性检�?
        result = self._check_liquidity(symbol, order_quantity, order_price)
        results.append(result)
        
        # 5. 单日交易频率检�?
        result = self._check_trade_frequency(symbol)
        results.append(result)
        
        return results
    
    def _check_symbol_limit(self, symbol: str, quantity: int, price: float,
                           portfolio: Dict[str, Position], 
                           total_capital: float) -> RiskCheckResult:
        """检查单品种仓位限制"""
        limit = self.limits['max_position_per_symbol']
        
        # 计算当前仓位
        current_pos = portfolio.get(symbol)
        current_value = current_pos.market_value if current_pos else 0
        
        # 计算新仓�?
        new_value = abs(quantity) * price
        new_total = sum(p.market_value for p in portfolio.values()) + new_value - current_value
        
        ratio = new_value / total_capital if total_capital > 0 else 0
        
        if ratio > limit:
            return RiskCheckResult(
                passed=False,
                risk_level=RiskLevel.RED,
                check_name="单品种仓位限�?,
                message=f"{symbol} 仓位 {ratio*100:.1f}% 超过限制 {limit*100:.1f}%",
                current_value=ratio,
                limit_value=limit,
                action_required=f"减少订单量至 {int(limit * total_capital / price)} �?
            )
        elif ratio > limit * 0.8:
            return RiskCheckResult(
                passed=True,
                risk_level=RiskLevel.YELLOW,
                check_name="单品种仓位限�?,
                message=f"{symbol} 仓位接近限制",
                current_value=ratio,
                limit_value=limit
            )
        
        return RiskCheckResult(
            passed=True,
            risk_level=RiskLevel.GREEN,
            check_name="单品种仓位限�?,
            message=f"{symbol} 仓位正常",
            current_value=ratio,
            limit_value=limit
        )
    
    def _check_category_limit(self, symbol: str, quantity: int, price: float,
                             portfolio: Dict[str, Position],
                             total_capital: float) -> RiskCheckResult:
        """检查板块集中度"""
        limit = self.limits['max_position_per_category']
        
        # 找到所属板�?
        category = None
        for cat, symbols in CATEGORY_MAP.items():
            if symbol in symbols:
                category = cat
                break
        
        if category is None:
            return RiskCheckResult(True, RiskLevel.GREEN, "板块集中�?, "未知板块", 0, limit)
        
        # 计算板块当前仓位
        category_value = 0
        for sym, pos in portfolio.items():
            if sym in CATEGORY_MAP.get(category, []):
                category_value += pos.market_value
        
        # 添加新订�?
        new_order_value = abs(quantity) * price
        # 减去当前品种已有仓位 (避免重复计算)
        current_pos = portfolio.get(symbol)
        if current_pos:
            category_value -= current_pos.market_value
        category_value += new_order_value
        
        ratio = category_value / total_capital if total_capital > 0 else 0
        
        if ratio > limit:
            return RiskCheckResult(
                passed=False,
                risk_level=RiskLevel.RED,
                check_name="板块集中度限�?,
                message=f"{category}板块 集中�?{ratio*100:.1f}% 超过限制",
                current_value=ratio,
                limit_value=limit
            )
        
        return RiskCheckResult(
            passed=True,
            risk_level=RiskLevel.GREEN if ratio < limit * 0.7 else RiskLevel.YELLOW,
            check_name="板块集中度限�?,
            message=f"{category}板块 集中�?{ratio*100:.1f}%",
            current_value=ratio,
            limit_value=limit
        )
    
    def _check_total_exposure(self, quantity: int, price: float,
                             portfolio: Dict[str, Position],
                             total_capital: float) -> RiskCheckResult:
        """检查总仓�?""
        current_exposure = sum(p.market_value for p in portfolio.values())
        new_exposure = current_exposure + abs(quantity) * price
        
        # 扣除已有仓位 (假设是调�?
        # 简化处�?实际需根据具体情况
        
        ratio = new_exposure / total_capital if total_capital > 0 else 0
        limit = self.limits['max_leverage']
        
        if ratio > limit:
            return RiskCheckResult(
                passed=False,
                risk_level=RiskLevel.RED,
                check_name="总仓位限�?,
                message=f"总仓�?{ratio*100:.1f}% 超过杠杆限制 {limit*100:.1f}%",
                current_value=ratio,
                limit_value=limit
            )
        
        return RiskCheckResult(
            passed=True,
            risk_level=RiskLevel.GREEN if ratio < limit * 0.8 else RiskLevel.YELLOW,
            check_name="总仓位限�?,
            message=f"总仓�?{ratio*100:.1f}%",
            current_value=ratio,
            limit_value=limit
        )
    
    def _check_liquidity(self, symbol: str, quantity: int, price: float) -> RiskCheckResult:
        """检查流动�?""
        limit = self.limits['max_position_pct_of_volume']
        
        # 获取估算成交�?(实际应从市场数据获取)
        estimated_volume = self.daily_volume_estimate.get(symbol, 100000)
        
        ratio = abs(quantity) / estimated_volume if estimated_volume > 0 else 0
        
        if ratio > limit:
            return RiskCheckResult(
                passed=False,
                risk_level=RiskLevel.ORANGE,
                check_name="流动性限�?,
                message=f"订单量占成交�?{ratio*100:.1f}% 过高",
                current_value=ratio,
                limit_value=limit,
                action_required="分批下单或选择其他时间"
            )
        
        return RiskCheckResult(
            passed=True,
            risk_level=RiskLevel.GREEN,
            check_name="流动性限�?,
            message=f"流动性充�?,
            current_value=ratio,
            limit_value=limit
        )
    
    def _check_trade_frequency(self, symbol: str) -> RiskCheckResult:
        """检查交易频�?""
        # 简化实�? 检查当日是否已有交�?
        today = date.today()
        today_trades = [t for t in self.recent_trades 
                       if t['symbol'] == symbol and t['date'] == today]
        
        if len(today_trades) > 5:
            return RiskCheckResult(
                passed=True,
                risk_level=RiskLevel.YELLOW,
                check_name="交易频率",
                message=f"{symbol} 今日已交易{len(today_trades)}�?,
                current_value=len(today_trades),
                limit_value=5
            )
        
        return RiskCheckResult(
            passed=True,
            risk_level=RiskLevel.GREEN,
            check_name="交易频率",
            message="交易频率正常",
            current_value=len(today_trades),
            limit_value=5
        )
    
    def can_execute(self, results: List[RiskCheckResult]) -> Tuple[bool, List[str]]:
        """
        判断是否可以执行订单
        
        Returns:
            (是否可执�? 需要采取的行动列表)
        """
        critical_violations = [r for r in results 
                              if not r.passed and r.risk_level == RiskLevel.RED]
        
        if critical_violations:
            actions = [r.action_required for r in critical_violations if r.action_required]
            return False, actions
        
        return True, []


# ============================================================
# 仓位管理 (Position Sizing)
# ============================================================
class PositionSizer:
    """仓位管理�?""
    
    def __init__(self, target_volatility: float = 0.15):
        self.target_vol = target_volatility
    
    def volatility_targeting(self,
                            expected_return: float,
                            volatility: float,
                            correlation: float = 0.5) -> float:
        """
        波动率目标法
        
        Position Size = Target Vol / (Volatility × sqrt(Correlation))
        """
        if volatility <= 0:
            return 0
        
        # Kelly Criterion 变体
        kelly = expected_return / (volatility ** 2) if volatility > 0 else 0
        
        # 调整至目标波动率
        position = self.target_vol / volatility * 0.5  # 半Kelly
        
        return np.clip(position, -1.0, 1.0)
    
    def risk_parity(self,
                   volatilities: Dict[str, float],
                   correlations: pd.DataFrame) -> Dict[str, float]:
        """
        风险平价分配
        
        使每个品种对组合风险的贡献相�?
        """
        n = len(volatilities)
        if n == 0:
            return {}
        
        # 简�? 逆波动率加权
        inv_vols = {s: 1/v if v > 0 else 0 for s, v in volatilities.items()}
        total = sum(inv_vols.values())
        
        if total == 0:
            return {s: 1/n for s in volatilities}
        
        weights = {s: v/total for s, v in inv_vols.items()}
        
        return weights
    
    def dynamic_position(self,
                        signal_strength: float,
                        current_volatility: float,
                        market_regime: str = 'normal') -> float:
        """
        动态仓位调�?
        
        Args:
            signal_strength: 信号强度 0-1
            current_volatility: 当前波动�?
            market_regime: 市场状�?
        """
        # 基础仓位
        base_position = signal_strength
        
        # 波动率调�?
        vol_adj = self.target_vol / current_volatility if current_volatility > 0 else 1
        
        # 市场环境调整
        regime_adj = {
            'normal': 1.0,
            'high_vol': 0.5,      # 高波动减�?
            'crisis': 0.3,        # 危机时大幅减�?
            'trending': 1.2,      # 趋势时增�?
        }.get(market_regime, 1.0)
        
        position = base_position * vol_adj * regime_adj
        
        return np.clip(position, 0, 1.0)


# ============================================================
# 止损止盈管理
# ============================================================
class StopLossManager:
    """止损止盈管理�?""
    
    def __init__(self, default_stop_pct: float = 0.03):
        self.default_stop = default_stop_pct
        self.positions_trailing_stop: Dict[str, float] = {}
    
    def calculate_stop_levels(self,
                            entry_price: float,
                            direction: int,
                            atr: float = None,
                            method: str = 'fixed') -> Tuple[float, float]:
        """
        计算止损止盈价位
        
        Args:
            entry_price: 入场�?
            direction: 方向 (1=�? -1=�?
            atr: ATR�?
            method: 'fixed', 'atr', 'volatility'
        
        Returns:
            (止损�? 止盈�?
        """
        if method == 'fixed':
            stop_dist = entry_price * self.default_stop
            tp_dist = stop_dist * 2  # 1:2 盈亏�?
        elif method == 'atr':
            stop_dist = (atr or entry_price * 0.02) * 2
            tp_dist = stop_dist * 3
        else:
            stop_dist = entry_price * self.default_stop
            tp_dist = stop_dist * 2
        
        if direction == 1:  # 多头
            stop_price = entry_price - stop_dist
            tp_price = entry_price + tp_dist
        else:  # 空头
            stop_price = entry_price + stop_dist
            tp_price = entry_price - tp_dist
        
        return stop_price, tp_price
    
    def update_trailing_stop(self,
                           symbol: str,
                           current_price: float,
                           highest_price: float,
                           lowest_price: float,
                           direction: int,
                           trail_pct: float = 0.05) -> Optional[float]:
        """
        更新移动止损
        
        Returns:
            新的止损�?(如有更新)
        """
        if direction == 1:  # 多头
            # 以最高价回撤一定比例作为止�?
            new_stop = highest_price * (1 - trail_pct)
            current_stop = self.positions_trailing_stop.get(symbol)
            
            if current_stop is None or new_stop > current_stop:
                self.positions_trailing_stop[symbol] = new_stop
                return new_stop
        else:  # 空头
            new_stop = lowest_price * (1 + trail_pct)
            current_stop = self.positions_trailing_stop.get(symbol)
            
            if current_stop is None or new_stop < current_stop:
                self.positions_trailing_stop[symbol] = new_stop
                return new_stop
        
        return None
    
    def check_exit(self,
                  position: Position,
                  current_price: float,
                  current_date: date) -> Optional[str]:
        """
        检查是否需要平�?
        
        Returns:
            平仓原因 (如需�?
        """
        # 止损检�?
        if position.direction == 1:  # 多头
            if current_price <= position.stop_loss:
                return 'stop_loss'
            if current_price >= position.take_profit:
                return 'take_profit'
        else:  # 空头
            if current_price >= position.stop_loss:
                return 'stop_loss'
            if current_price <= position.take_profit:
                return 'take_profit'
        
        # 时间止损 (持仓超过20�?
        if (current_date - position.entry_date).days > 20:
            return 'time_stop'
        
        return None


# ============================================================
# 组合风险监控
# ============================================================
class PortfolioRiskMonitor:
    """组合风险监控�?""
    
    def __init__(self, limits: Dict = RISK_LIMITS):
        self.limits = limits
        self.risk_history: List[PortfolioRiskState] = []
    
    def calculate_portfolio_risk(self,
                                positions: Dict[str, Position],
                                returns_history: Dict[str, pd.Series],
                                current_date: date,
                                total_capital: float) -> PortfolioRiskState:
        """计算组合风险指标"""
        
        # 基础指标
        total_value = sum(p.market_value for p in positions.values())
        gross_exposure = total_value / total_capital if total_capital > 0 else 0
        
        net_exposure = sum(p.market_value * np.sign(p.quantity) for p in positions.values())
        net_exposure = net_exposure / total_capital if total_capital > 0 else 0
        
        # 计算组合波动�?(简�?
        portfolio_returns = self._estimate_portfolio_returns(positions, returns_history)
        portfolio_vol = portfolio_returns.std() * np.sqrt(252) if len(portfolio_returns) > 0 else 0
        
        # VaR计算
        var_95 = np.percentile(portfolio_returns, 5) if len(portfolio_returns) > 0 else 0
        
        # 压力测试 (简�?
        stress_loss = var_95 * 2  # 简化假�?
        
        # 保证金估�?(简�?0%)
        margin_used = gross_exposure * 0.10
        
        # 风险等级判断
        risk_level = self._determine_risk_level(
            portfolio_vol, 
            gross_exposure, 
            margin_used
        )
        
        state = PortfolioRiskState(
            date=current_date,
            total_value=total_value,
            positions=positions.copy(),
            gross_exposure=gross_exposure,
            net_exposure=net_exposure,
            portfolio_volatility=portfolio_vol,
            var_95=var_95,
            stress_loss=stress_loss,
            margin_used=margin_used,
            risk_level=risk_level
        )
        
        self.risk_history.append(state)
        return state
    
    def _estimate_portfolio_returns(self,
                                   positions: Dict[str, Position],
                                   returns_history: Dict[str, pd.Series]) -> pd.Series:
        """估算组合历史收益"""
        if not positions:
            return pd.Series()
        
        # 简�? 等权组合收益
        returns_list = []
        weights = []
        
        for symbol, pos in positions.items():
            if symbol in returns_history:
                returns_list.append(returns_history[symbol])
                weights.append(pos.market_value)
        
        if not returns_list:
            return pd.Series()
        
        # 对齐并加�?
        df = pd.concat(returns_list, axis=1).fillna(0)
        total = sum(weights)
        weights = [w/total for w in weights]
        
        portfolio_returns = (df * weights).sum(axis=1)
        return portfolio_returns
    
    def _determine_risk_level(self,
                             portfolio_vol: float,
                             gross_exposure: float,
                             margin_used: float) -> RiskLevel:
        """确定风险等级"""
        
        if (portfolio_vol > self.limits['max_portfolio_volatility'] or
            gross_exposure > self.limits['max_leverage'] * 0.9 or
            margin_used > self.limits['max_margin_usage']):
            return RiskLevel.RED
        
        if (portfolio_vol > self.limits['max_portfolio_volatility'] * 0.8 or
            gross_exposure > self.limits['max_leverage'] * 0.75 or
            margin_used > self.limits['max_margin_usage'] * 0.8):
            return RiskLevel.ORANGE
        
        if (portfolio_vol > self.limits['max_portfolio_volatility'] * 0.6 or
            gross_exposure > self.limits['max_leverage'] * 0.6):
            return RiskLevel.YELLOW
        
        return RiskLevel.GREEN
    
    def generate_risk_report(self, state: PortfolioRiskState) -> str:
        """生成风险报告"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"组合风险监控报告 - {state.date}")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"风险等级: {state.risk_level.value}")
        lines.append("")
        lines.append("【组合概况�?)
        lines.append(f"  总资�?      ${state.total_value:,.0f}")
        lines.append(f"  毛敞�?      {state.gross_exposure*100:.1f}%")
        lines.append(f"  净敞口:      {state.net_exposure*100:+.1f}%")
        lines.append("")
        lines.append("【风险指标�?)
        lines.append(f"  组合波动�?  {state.portfolio_volatility*100:.2f}% (目标: {self.limits['max_portfolio_volatility']*100:.0f}%)")
        lines.append(f"  单日VaR(95%): {state.var_95*100:.2f}%")
        lines.append(f"  压力测试损失: {state.stress_loss*100:.2f}%")
        lines.append(f"  保证金使�?  {state.margin_used*100:.1f}%")
        lines.append("")
        lines.append("【持仓分布�?)
        for symbol, pos in state.positions.items():
            lines.append(f"  {symbol}: {pos.unrealized_pnl_pct*100:+.2f}% (${pos.market_value:,.0f})")
        lines.append("=" * 60)
        
        return "\n".join(lines)


# ============================================================
# 主风控系�?
# ============================================================
class CTARiskManagementSystem:
    """
    CTA组合风控系统主类
    
    整合所有风控模�?
    """
    
    def __init__(self, limits: Dict = RISK_LIMITS):
        self.limits = limits
        self.pre_trade_manager = PreTradeRiskManager(limits)
        self.position_sizer = PositionSizer()
        self.stop_loss_manager = StopLossManager()
        self.risk_monitor = PortfolioRiskMonitor(limits)
        self.logger = logging.getLogger(__name__)
    
    def check_and_size_order(self,
                            symbol: str,
                            signal_strength: float,
                            expected_return: float,
                            volatility: float,
                            current_portfolio: Dict[str, Position],
                            total_capital: float) -> Dict:
        """
        综合风控检查与仓位计算
        
        Returns:
            {
                'can_trade': bool,
                'recommended_position': float,  # 目标仓位比例
                'max_position': float,          # 最大允许仓�?
                'stop_loss': float,
                'take_profit': float,
                'risk_checks': List[RiskCheckResult]
            }
        """
        # 1. 计算推荐仓位
        recommended = self.position_sizer.volatility_targeting(
            expected_return, volatility
        )
        
        # 2. 事前风控检�?
        test_quantity = int(recommended * total_capital / 100)  # 假设价格100
        risk_checks = self.pre_trade_manager.check_order(
            symbol, test_quantity, 100, 1, 
            current_portfolio, total_capital
        )
        
        can_trade, actions = self.pre_trade_manager.can_execute(risk_checks)
        
        # 3. 根据风控结果调整仓位
        if not can_trade:
            max_position = 0
        else:
            # 找到最严格的限�?
            max_position = recommended
            for check in risk_checks:
                if check.risk_level in [RiskLevel.ORANGE, RiskLevel.RED]:
                    max_position *= 0.7  # 降低30%
        
        # 4. 计算止损止盈
        stop_loss, take_profit = self.stop_loss_manager.calculate_stop_levels(
            100, 1, volatility * 100, 'atr'
        )
        
        return {
            'can_trade': can_trade,
            'recommended_position': recommended,
            'max_position': max_position,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'risk_checks': risk_checks,
            'actions_required': actions
        }


# ============================================================
# 测试代码
# ============================================================
if __name__ == "__main__":
    print("=" * 70)
    print("CTA组合风控系统")
    print("=" * 70)
    print()
    
    # 初始化系�?
    risk_system = CTARiskManagementSystem()
    
    # 模拟当前组合
    current_portfolio = {
        'RB': Position('RB', 10, 3500, 3600, date.today() - timedelta(days=5), 1, 3400, 3800),
        'CU': Position('CU', 5, 68000, 70000, date.today() - timedelta(days=3), 1, 66000, 72000),
    }
    
    total_capital = 1_000_000
    
    # 测试新订单风�?
    print("【测试新订单风控�?)
    print()
    
    test_cases = [
        ('RB', 0.8, 0.10, 0.20),   # 加仓已有品种
        ('I', 0.6, 0.08, 0.25),    # 新品�?
        ('SC', 1.0, 0.12, 0.30),   # 高波动品�?
    ]
    
    for symbol, strength, exp_ret, vol in test_cases:
        print(f"品种: {symbol}, 信号强度: {strength}, 预期收益: {exp_ret*100:.1f}%, 波动�? {vol*100:.1f}%")
        
        result = risk_system.check_and_size_order(
            symbol, strength, exp_ret, vol,
            current_portfolio, total_capital
        )
        
        print(f"  是否可交�? {result['can_trade']}")
        print(f"  推荐仓位: {result['recommended_position']*100:.1f}%")
        print(f"  最大允�? {result['max_position']*100:.1f}%")
        print(f"  止损: {result['stop_loss']:.2f}, 止盈: {result['take_profit']:.2f}")
        
        for check in result['risk_checks']:
            status = "�? if check.passed else "�?
            print(f"  [{status}] {check.check_name}: {check.message}")
        print()
    
    # 组合风险监控
    print("=" * 70)
    print("【组合风险监控�?)
    print()
    
    # 模拟历史收益
    np.random.seed(42)
    returns_history = {
        'RB': pd.Series(np.random.normal(0.001, 0.018, 252)),
        'CU': pd.Series(np.random.normal(0.001, 0.020, 252)),
    }
    
    risk_state = risk_system.risk_monitor.calculate_portfolio_risk(
        current_portfolio, returns_history, date.today(), total_capital
    )
    
    print(risk_system.risk_monitor.generate_risk_report(risk_state))
    
    print()
    print("=" * 70)
    print("风控系统测试完成!")
    print("=" * 70)
