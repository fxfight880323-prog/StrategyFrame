"""
组合管理模块
============
整合多因子选股和CTA信号，生成完整的投资组合

功能:
1. 资产配置 (股票 vs CTA)
2. 仓位管理
3. 风险平衡
4. 周度再平衡
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
import logging

from factor_model import MultiFactorModel, FactorDataProvider
from cta_signals import CTASignalAggregator, FuturesDataProvider, SignalDirection
from config import StrategyConfig, CONFIG


class AssetClass(Enum):
    """资产类别"""
    STOCK = "stock"
    FUTURES = "futures"
    CASH = "cash"


@dataclass
class Position:
    """持仓数据类"""
    symbol: str
    asset_class: AssetClass
    quantity: float = 0
    market_value: float = 0
    weight: float = 0
    entry_price: float = 0
    current_price: float = 0
    unrealized_pnl: float = 0
    realized_pnl: float = 0
    
    def update_price(self, new_price: float):
        """更新价格"""
        self.current_price = new_price
        self.market_value = self.quantity * new_price
        self.unrealized_pnl = self.quantity * (new_price - self.entry_price)


@dataclass
class Portfolio:
    """投资组合数据类"""
    date: datetime
    total_value: float = 0
    cash: float = 0
    positions: Dict[str, Position] = field(default_factory=dict)
    
    # 分资产类别统计
    stock_value: float = 0
    futures_value: float = 0
    
    # 风险指标
    gross_exposure: float = 0
    net_exposure: float = 0
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """获取持仓"""
        return self.positions.get(symbol)
    
    def add_position(self, position: Position):
        """添加持仓"""
        self.positions[position.symbol] = position
        self._update_stats()
    
    def update_prices(self, prices: Dict[str, float]):
        """批量更新价格"""
        for symbol, price in prices.items():
            if symbol in self.positions:
                self.positions[symbol].update_price(price)
        self._update_stats()
    
    def _update_stats(self):
        """更新组合统计"""
        self.stock_value = sum(
            p.market_value for p in self.positions.values()
            if p.asset_class == AssetClass.STOCK
        )
        
        self.futures_value = sum(
            abs(p.market_value) for p in self.positions.values()
            if p.asset_class == AssetClass.FUTURES
        )
        
        long_exposure = sum(
            p.market_value for p in self.positions.values()
            if p.market_value > 0
        )
        short_exposure = sum(
            abs(p.market_value) for p in self.positions.values()
            if p.market_value < 0
        )
        
        self.gross_exposure = long_exposure + short_exposure
        self.net_exposure = long_exposure - short_exposure
        self.total_value = self.cash + self.stock_value


class AssetAllocator:
    """资产配置器"""
    
    def __init__(self, config: StrategyConfig = None):
        self.config = config or CONFIG
        self.logger = logging.getLogger(__name__)
    
    def calculate_allocation(
        self,
        market_state: Dict = None
    ) -> Dict[AssetClass, float]:
        """
        计算战略资产配置
        
        Returns:
            {AssetClass: 目标权重}
        """
        base_allocation = {
            AssetClass.STOCK: self.config.STOCK_ALLOCATION,
            AssetClass.FUTURES: self.config.CTA_ALLOCATION,
            AssetClass.CASH: 1 - self.config.STOCK_ALLOCATION - self.config.CTA_ALLOCATION
        }
        
        # 根据市场状态动态调整
        if market_state:
            volatility = market_state.get('volatility', 0.15)
            
            # 高波动环境减少风险资产
            if volatility > 0.25:
                base_allocation[AssetClass.STOCK] *= 0.8
                base_allocation[AssetClass.FUTURES] *= 0.8
                base_allocation[AssetClass.CASH] = 1 - sum([
                    base_allocation[AssetClass.STOCK],
                    base_allocation[AssetClass.FUTURES]
                ])
        
        return base_allocation
    
    def calculate_stock_weights(
        self,
        selected_stocks: List[str],
        scores: pd.DataFrame
    ) -> Dict[str, float]:
        """
        计算个股权重
        
        基于因子得分的加权方法
        """
        if not selected_stocks:
            return {}
        
        # 提取选中股票的得分
        stock_scores = scores[scores['symbol'].isin(selected_stocks)].copy()
        
        if stock_scores.empty:
            # 等权分配
            weight = 1.0 / len(selected_stocks)
            return {s: weight for s in selected_stocks}
        
        # 基于得分的权重 (得分越高，权重越大)
        # 使用softmax函数确保权重和为1
        scores_values = stock_scores['total_score'].values
        exp_scores = np.exp(scores_values - np.max(scores_values))
        weights = exp_scores / exp_scores.sum()
        
        # 应用个股权重上限
        weights = np.minimum(weights, self.config.MAX_SINGLE_STOCK_WEIGHT)
        
        # 重新归一化
        weights = weights / weights.sum()
        
        return dict(zip(stock_scores['symbol'], weights))
    
    def calculate_cta_weights(
        self,
        cta_signals: Dict
    ) -> Dict[str, float]:
        """
        计算CTA权重
        
        基于信号强度和波动率调整
        """
        if not cta_signals:
            return {}
        
        weights = {}
        total_abs_position = 0
        
        for symbol, signal in cta_signals.items():
            # 基于信号强度和波动率计算权重
            if signal.volatility > 0:
                # 波动率倒数加权 (低波动高权重)
                vol_weight = 0.10 / signal.volatility
            else:
                vol_weight = 1.0
            
            # 综合权重 = 信号方向 × 信号强度 × 波动率调整
            position = signal.target_position * signal.strength * vol_weight
            
            # 限制单个品种权重
            position = np.clip(
                position, 
                -self.config.MAX_SINGLE_CTA_WEIGHT,
                self.config.MAX_SINGLE_CTA_WEIGHT
            )
            
            weights[symbol] = position
            total_abs_position += abs(position)
        
        # 归一化到CTA总仓位
        if total_abs_position > 0:
            cta_allocation = self.config.CTA_ALLOCATION
            for symbol in weights:
                weights[symbol] = weights[symbol] / total_abs_position * cta_allocation
        
        return weights


class RiskManager:
    """风险管理器"""
    
    def __init__(self, config: StrategyConfig = None):
        self.config = config or CONFIG
        self.logger = logging.getLogger(__name__)
    
    def check_risk_limits(self, portfolio: Portfolio) -> Dict:
        """
        检查风险限制
        
        Returns:
            风险检查结果
        """
        violations = []
        warnings = []
        
        # 检查个股集中度
        for symbol, pos in portfolio.positions.items():
            if pos.asset_class == AssetClass.STOCK:
                weight = pos.market_value / portfolio.total_value if portfolio.total_value > 0 else 0
                if weight > self.config.MAX_SINGLE_STOCK_WEIGHT:
                    violations.append(f"{symbol} 权重 {weight:.2%} 超过限制 {self.config.MAX_SINGLE_STOCK_WEIGHT:.2%}")
        
        # 检查回撤
        # (需要历史数据，这里简化处理)
        
        # 检查杠杆
        leverage = portfolio.gross_exposure / portfolio.total_value if portfolio.total_value > 0 else 0
        if leverage > 1.5:
            warnings.append(f"杠杆率 {leverage:.2f}x 较高")
        
        return {
            'is_safe': len(violations) == 0,
            'violations': violations,
            'warnings': warnings
        }
    
    def calculate_position_sizes(
        self,
        target_weights: Dict[str, float],
        portfolio_value: float,
        prices: Dict[str, float],
        asset_class: AssetClass
    ) -> Dict[str, int]:
        """
        计算具体仓位数量
        """
        positions = {}
        
        for symbol, weight in target_weights.items():
            if symbol not in prices or prices[symbol] <= 0:
                continue
            
            target_value = portfolio_value * weight
            price = prices[symbol]
            
            if asset_class == AssetClass.STOCK:
                # 股票: 计算股数
                shares = int(target_value / price)
                positions[symbol] = shares
            
            elif asset_class == AssetClass.FUTURES:
                # 期货: 计算手数 (简化，假设合约乘数为1)
                lots = int(target_value / price)
                positions[symbol] = lots
        
        return positions


class PortfolioManager:
    """
    投资组合管理器
    
    整合多因子选股、CTA信号和风险管理
    """
    
    def __init__(
        self,
        config: StrategyConfig = None,
        factor_model: MultiFactorModel = None,
        cta_aggregator: CTASignalAggregator = None
    ):
        self.config = config or CONFIG
        self.factor_model = factor_model
        self.cta_aggregator = cta_aggregator
        self.allocator = AssetAllocator(config)
        self.risk_manager = RiskManager(config)
        self.logger = logging.getLogger(__name__)
        
        # 初始化数据提供器
        self.stock_provider = FactorDataProvider(self.config.RQ_API_KEY)
        self.futures_provider = FuturesDataProvider(self.config.RQ_API_KEY)
    
    def rebalance(
        self,
        current_portfolio: Portfolio,
        rebalance_date: datetime
    ) -> Tuple[Portfolio, Dict]:
        """
        组合再平衡
        
        周度换仓的核心函数
        
        Args:
            current_portfolio: 当前组合
            rebalance_date: 再平衡日期
        
        Returns:
            (新组合, 交易指令)
        """
        self.logger.info(f"开始再平衡: {rebalance_date}")
        
        # 1. 获取资产配置
        allocation = self.allocator.calculate_allocation()
        
        # 2. 多因子选股
        stock_target_weights = self._rebalance_stocks(
            rebalance_date, 
            allocation[AssetClass.STOCK]
        )
        
        # 3. CTA信号
        cta_target_weights = self._rebalance_cta(
            rebalance_date,
            allocation[AssetClass.FUTURES]
        )
        
        # 4. 合并目标权重
        target_weights = {**stock_target_weights, **cta_target_weights}
        
        # 5. 生成交易指令
        trades = self._generate_trades(current_portfolio, target_weights)
        
        # 6. 执行风险检查
        risk_check = self.risk_manager.check_risk_limits(current_portfolio)
        if not risk_check['is_safe']:
            self.logger.warning(f"风险限制警告: {risk_check['violations']}")
        
        # 7. 构建新组合 (模拟执行)
        new_portfolio = self._build_new_portfolio(
            current_portfolio,
            trades,
            rebalance_date
        )
        
        return new_portfolio, trades
    
    def _rebalance_stocks(
        self,
        date: datetime,
        target_allocation: float
    ) -> Dict[str, float]:
        """股票部分再平衡"""
        self.logger.info("选股中...")
        
        # 获取股票池
        universe = self.stock_provider.get_stock_universe(
            self.config.STOCK_UNIVERSE,
            date.strftime('%Y-%m-%d')
        )
        
        # 多因子评分
        scores = self.factor_model.score_stocks(
            universe,
            date.strftime('%Y-%m-%d')
        )
        
        # 选择Top N
        selected = scores.head(self.config.MAX_STOCK_HOLDINGS)['symbol'].tolist()
        
        # 计算权重
        weights = self.allocator.calculate_stock_weights(selected, scores)
        
        # 调整到目标配置比例
        weights = {k: v * target_allocation for k, v in weights.items()}
        
        self.logger.info(f"选中 {len(selected)} 只股票")
        
        return weights
    
    def _rebalance_cta(
        self,
        date: datetime,
        target_allocation: float
    ) -> Dict[str, float]:
        """CTA部分再平衡"""
        self.logger.info("生成CTA信号...")
        
        # 获取期货数据
        lookback_days = 120
        start_dt = date - pd.Timedelta(days=lookback_days)
        
        futures_data = {}
        for symbol in self.config.CTA_SYMBOLS:
            df = self.futures_provider.get_futures_data(
                symbol,
                start_dt.strftime('%Y-%m-%d'),
                date.strftime('%Y-%m-%d')
            )
            if not df.empty:
                futures_data[symbol] = df
        
        # 生成CTA信号
        cta_signals = self.cta_aggregator.aggregate_signals(futures_data, date)
        
        # 过滤有效信号
        active_signals = {
            k: v for k, v in cta_signals.items()
            if abs(v.target_position) > 0.1
        }
        
        # 计算权重
        weights = self.allocator.calculate_cta_weights(active_signals)
        
        self.logger.info(f"CTA有效信号: {len(active_signals)} 个")
        
        return weights
    
    def _generate_trades(
        self,
        current: Portfolio,
        target_weights: Dict[str, float]
    ) -> Dict:
        """
        生成交易指令
        
        Returns:
            {symbol: {'action': 'buy'/'sell', 'quantity': int, 'reason': str}}
        """
        trades = {}
        
        # 卖出不再持有的
        for symbol, pos in current.positions.items():
            if symbol not in target_weights or target_weights[symbol] == 0:
                trades[symbol] = {
                    'action': 'sell',
                    'quantity': pos.quantity,
                    'reason': '不再持有'
                }
        
        # 买入新持仓 / 调整现有持仓
        for symbol, weight in target_weights.items():
            target_value = current.total_value * weight
            
            if symbol in current.positions:
                current_value = current.positions[symbol].market_value
                diff_value = target_value - current_value
                
                if abs(diff_value) / current.total_value > 0.01:  # 1%阈值
                    action = 'buy' if diff_value > 0 else 'sell'
                    trades[symbol] = {
                        'action': action,
                        'quantity': abs(int(diff_value / current.positions[symbol].current_price)),
                        'reason': '权重调整'
                    }
            else:
                # 新买入
                trades[symbol] = {
                    'action': 'buy',
                    'quantity': 0,  # 需要价格数据计算
                    'reason': '新增持仓'
                }
        
        return trades
    
    def _build_new_portfolio(
        self,
        current: Portfolio,
        trades: Dict,
        date: datetime
    ) -> Portfolio:
        """构建新组合 (简化版)"""
        # 这里简化处理，实际应执行交易并更新持仓
        new_portfolio = Portfolio(
            date=date,
            total_value=current.total_value,
            cash=current.cash
        )
        
        # 复制现有持仓 (实际应应用trades)
        for symbol, pos in current.positions.items():
            if symbol not in trades or trades[symbol]['action'] != 'sell':
                new_portfolio.add_position(pos)
        
        return new_portfolio
    
    def get_portfolio_summary(self, portfolio: Portfolio) -> Dict:
        """获取组合摘要"""
        return {
            'date': portfolio.date,
            'total_value': portfolio.total_value,
            'cash': portfolio.cash,
            'stock_value': portfolio.stock_value,
            'futures_value': portfolio.futures_value,
            'num_positions': len(portfolio.positions),
            'gross_exposure': portfolio.gross_exposure,
            'net_exposure': portfolio.net_exposure,
            'leverage': portfolio.gross_exposure / portfolio.total_value if portfolio.total_value > 0 else 0
        }


# 便捷函数
def quick_rebalance(
    date: str = None,
    api_key: str = None
) -> Dict:
    """
    快速再平衡
    
    Example:
        >>> result = quick_rebalance(date="2024-03-01")
        >>> print(result['stock_weights'])
        >>> print(result['cta_weights'])
    """
    if date is None:
        date = datetime.now()
    else:
        date = datetime.strptime(date, '%Y-%m-%d')
    
    config = StrategyConfig()
    if api_key:
        config.RQ_API_KEY = api_key
    
    # 初始化组件
    from factor_model import MultiFactorModel
    from cta_signals import CTASignalAggregator
    
    factor_model = MultiFactorModel(config.FACTOR_WEIGHTS)
    cta_aggregator = CTASignalAggregator()
    
    manager = PortfolioManager(config, factor_model, cta_aggregator)
    
    # 创建空组合
    empty_portfolio = Portfolio(
        date=date,
        total_value=config.INITIAL_CAPITAL,
        cash=config.INITIAL_CAPITAL
    )
    
    # 再平衡
    new_portfolio, trades = manager.rebalance(empty_portfolio, date)
    
    # 汇总结果
    summary = manager.get_portfolio_summary(new_portfolio)
    
    return {
        'summary': summary,
        'trades': trades,
        'stock_weights': {k: v for k, v in trades.items() if not k.isupper()},
        'cta_weights': {k: v for k, v in trades.items() if k.isupper()}
    }


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("组合管理器测试")
    print("=" * 70)
    
    result = quick_rebalance(date="2024-03-01")
    
    print("\n组合摘要:")
    for key, value in result['summary'].items():
        if isinstance(value, float):
            print(f"  {key}: {value:,.2f}")
        else:
            print(f"  {key}: {value}")
    
    print(f"\n交易指令数量: {len(result['trades'])}")
