"""
期权策略回测模块 (Tradier数据源)
==================================

基于Tradier API提供的专业期权数据(希腊字母、IV等)，
实现多种期权策略的回测:
1. Put保险策略 (Protective Put)
2. Put价差策略 (Bear Put Spread)
3. 动态Delta对冲
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

# 路径设置
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', 'data_providers'))

from TradierDataProvider import TradierDataProvider


# ============================================================
# 日志设置
# ============================================================
def setup_logger(name: str = "options_backtest") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# 期权策略枚举
# ============================================================
class OptionsStrategy(Enum):
    PROTECTIVE_PUT = "protective_put"      # 保护性Put
    BEAR_PUT_SPREAD = "bear_put_spread"    # 熊市Put价差
    COLLAR = "collar"                       # 领式组合


# ============================================================
# 期权持仓
# ============================================================
@dataclass
class OptionPosition:
    """期权持仓"""
    entry_date: date
    symbol: str                    # 期权代码
    underlying: str                # 标的代码
    option_type: str               # 'call' or 'put'
    strike: float
    expiry: date
    entry_price: float
    quantity: int                  # 正数=买入，负数=卖出
    delta: float
    gamma: Optional[float] = None
    theta: Optional[float] = None
    vega: Optional[float] = None
    iv: Optional[float] = None
    
    # 持仓状态
    current_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    
    def market_value(self) -> float:
        return self.current_price * abs(self.quantity) * 100
    
    def cost_basis(self) -> float:
        return self.entry_price * abs(self.quantity) * 100


# ============================================================
# 期权策略回测引擎
# ============================================================
class OptionsStrategyBacktest:
    """期权策略回测引擎"""
    
    def __init__(self, initial_capital: float = 1_000_000,
                 strategy: OptionsStrategy = OptionsStrategy.PROTECTIVE_PUT,
                 data_provider: TradierDataProvider = None,
                 logger: logging.Logger = None):
        self.initial_capital = initial_capital
        self.strategy = strategy
        self.data_provider = data_provider or TradierDataProvider()
        self.logger = logger or setup_logger()
        
        # 回测状态
        self.underlying_position: Dict[str, float] = {}  # 标的持仓
        self.option_positions: List[OptionPosition] = []
        self.cash: float = initial_capital
        self.history: List[Dict] = []
        
    def initialize_hedge(self, underlying: str, shares: int, 
                         hedge_date: date, hedge_ratio: float = 1.0):
        """
        初始化对冲仓位
        
        Args:
            underlying: 标的代码 (如 'SPY')
            shares: 标的股票数量
            hedge_date: 对冲开始日期
            hedge_ratio: 对冲比例 (1.0 = 完全对冲)
        """
        self.logger.info(f"初始化对冲: {underlying} x{shares} 股")
        self.logger.info(f"对冲日期: {hedge_date}")
        self.logger.info(f"对冲比例: {hedge_ratio*100:.0f}%")
        
        # 记录标的持仓
        self.underlying_position[underlying] = shares
        
        # 根据策略建立期权对冲
        if self.strategy == OptionsStrategy.PROTECTIVE_PUT:
            self._setup_protective_put(underlying, shares, hedge_date, hedge_ratio)
        elif self.strategy == OptionsStrategy.BEAR_PUT_SPREAD:
            self._setup_put_spread(underlying, shares, hedge_date, hedge_ratio)
        
        self.logger.info(f"现金余额: ${self.cash:,.0f}")
    
    def _setup_protective_put(self, underlying: str, shares: int, 
                             hedge_date: date, hedge_ratio: float):
        """建立保护性Put仓位"""
        self.logger.info("【策略】保护性Put (Protective Put)")
        
        # 获取标的当前价格
        quote = self.data_provider.get_stock_quote(underlying)
        if not quote:
            self.logger.error("无法获取标的报价")
            return
        
        spot_price = quote['price']
        self.logger.info(f"  {underlying} 当前价格: ${spot_price:.2f}")
        
        # 计算需要对冲的Delta
        target_delta = -shares * hedge_ratio
        self.logger.info(f"  目标对冲Delta: {target_delta:.0f}")
        
        # 获取期权数据
        option_data = self.data_provider.select_put_for_flp(
            symbol=underlying,
            target_delta=(-0.10, -0.07),
            min_days_to_expiry=20,
            max_days_to_expiry=60
        )
        
        if not option_data:
            self.logger.error("无法找到合适的Put期权")
            return
        
        # 计算需要的合约数量
        contract_size = 100  # 每份合约100股
        contracts_needed = int(abs(target_delta) / (abs(option_data['delta']) * contract_size))
        
        # 限制最大合约数
        max_budget = self.cash * 0.03  # 最多3%资金用于权利金
        affordable_contracts = int(max_budget / (option_data['last'] * contract_size))
        
        contracts = min(contracts_needed, max(affordable_contracts, 1))
        
        self.logger.info(f"  需要合约数: {contracts_needed}, 预算可购买: {affordable_contracts}")
        self.logger.info(f"  实际购买: {contracts}")
        
        # 创建期权持仓
        position = OptionPosition(
            entry_date=hedge_date,
            symbol=option_data['option_symbol'],
            underlying=underlying,
            option_type='put',
            strike=option_data['strike'],
            expiry=datetime.strptime(option_data['expiration'], '%Y-%m-%d').date(),
            entry_price=option_data['last'],
            quantity=contracts,
            delta=option_data['delta'],
            gamma=option_data.get('gamma'),
            theta=option_data.get('theta'),
            vega=option_data.get('vega'),
            iv=option_data.get('iv'),
            current_price=option_data['last']
        )
        
        # 扣除权利金
        premium_paid = position.cost_basis()
        self.cash -= premium_paid
        
        self.option_positions.append(position)
        
        self.logger.info(f"  购买 {contracts} 张 Put")
        self.logger.info(f"    代码: {position.symbol}")
        self.logger.info(f"    行权价: ${position.strike:.2f}")
        self.logger.info(f"    到期日: {position.expiry}")
        self.logger.info(f"    权利金: ${premium_paid:,.0f}")
        self.logger.info(f"    Delta: {position.delta:.3f}")
        
        # 对冲效果
        hedge_coverage = abs(position.delta) * contracts * contract_size / shares * 100
        self.logger.info(f"  对冲覆盖率: {hedge_coverage:.1f}%")
    
    def _setup_put_spread(self, underlying: str, shares: int, 
                         hedge_date: date, hedge_ratio: float):
        """建立Put价差仓位"""
        self.logger.info("【策略】熊市Put价差 (Bear Put Spread)")
        
        # 获取期权到期日
        expirations = self.data_provider.get_option_expirations(underlying)
        if not expirations:
            self.logger.error("无法获取期权到期日")
            return
        
        # 选择到期日
        expiry = expirations[min(2, len(expirations)-1)]  # 选择第三个到期日
        self.logger.info(f"  选择到期日: {expiry}")
        
        # 获取期权链
        chain = self.data_provider.get_option_chain(underlying, expiry, greeks=True)
        if chain.empty:
            self.logger.error("无法获取期权链")
            return
        
        puts = chain[chain['option_type'] == 'put'].copy()
        if puts.empty:
            self.logger.error("无Put期权数据")
            return
        
        # 选择价外和价内Put构建价差
        quote = self.data_provider.get_stock_quote(underlying)
        spot_price = quote['price']
        
        # 买入价内Put (Delta ~ -0.6)
        puts['delta_num'] = pd.to_numeric(puts.get('delta', 0), errors='coerce').abs()
        itm_put = puts.nlargest(3, 'delta_num').iloc[0]  # 最价内的
        
        # 卖出价外Put (Delta ~ -0.3)
        otm_put = puts.nsmallest(10, 'strike').iloc[-1]  # 价外的
        
        # 计算合约数量
        contracts = max(1, int(shares * hedge_ratio / 100))
        
        self.logger.info(f"  买入Put: {itm_put.get('symbol')} @ ${float(itm_put.get('strike', 0)):.2f}")
        self.logger.info(f"  卖出Put: {otm_put.get('symbol')} @ ${float(otm_put.get('strike', 0)):.2f}")
        
        # 净权利金
        buy_premium = float(itm_put.get('last', 0)) * contracts * 100
        sell_premium = float(otm_put.get('last', 0)) * contracts * 100
        net_premium = buy_premium - sell_premium
        
        self.cash -= net_premium
        
        self.logger.info(f"  净权利金支出: ${net_premium:,.0f}")
        self.logger.info(f"  最大盈利: ${(float(itm_put.get('strike', 0)) - float(otm_put.get('strike', 0))) * contracts * 100 - net_premium:,.0f}")
        self.logger.info(f"  最大亏损: ${net_premium:,.0f}")
    
    def update_portfolio(self, current_date: date, underlying_prices: Dict[str, float]):
        """
        更新组合价值
        
        Args:
            current_date: 当前日期
            underlying_prices: {symbol: price} 标的当前价格
        """
        # 更新标的价值
        underlying_value = 0
        for sym, shares in self.underlying_position.items():
            if sym in underlying_prices:
                underlying_value += shares * underlying_prices[sym]
        
        # 更新期权价值 (简化: 使用Delta估算)
        option_value = 0
        for pos in self.option_positions:
            if current_date >= pos.expiry:
                # 到期结算
                if pos.underlying in underlying_prices:
                    spot = underlying_prices[pos.underlying]
                    intrinsic = max(pos.strike - spot, 0) if pos.option_type == 'put' else max(spot - pos.strike, 0)
                    pos.current_price = intrinsic
            else:
                # 未到期，Delta估算
                if pos.underlying in underlying_prices:
                    price_change = underlying_prices[pos.underlying] - pos.entry_price
                    price_change_pct = price_change / pos.entry_price if pos.entry_price > 0 else 0
                    
                    # Delta收益 + Gamma效应
                    delta_effect = pos.delta * price_change
                    gamma_effect = (pos.gamma or 0) * price_change ** 2 / 2 if pos.gamma else 0
                    
                    # Theta衰减
                    days_passed = (current_date - pos.entry_date).days
                    theta_effect = (pos.theta or 0) * days_passed if pos.theta else 0
                    
                    new_price = pos.entry_price + delta_effect + gamma_effect + theta_effect
                    pos.current_price = max(new_price, 0.01)
            
            pos.unrealized_pnl = (pos.current_price - pos.entry_price) * pos.quantity * 100
            option_value += pos.market_value() * (1 if pos.quantity > 0 else -1)
        
        # 总资产
        total_value = self.cash + underlying_value + option_value
        
        # 记录
        self.history.append({
            'date': current_date,
            'cash': self.cash,
            'underlying_value': underlying_value,
            'option_value': option_value,
            'total_value': total_value,
            'unrealized_pnl': sum(p.unrealized_pnl for p in self.option_positions)
        })
        
        return total_value
    
    def run_backtest(self, underlying: str, start_date: str, end_date: str,
                    rebalance_freq: int = 30) -> pd.DataFrame:
        """
        执行期权策略回测
        
        Args:
            underlying: 标的代码
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
            rebalance_freq: 再平衡频率(天)
        
        Returns:
            回测结果 DataFrame
        """
        self.logger.info("="*60)
        self.logger.info(f"期权策略回测: {self.strategy.value}")
        self.logger.info(f"标的: {underlying}")
        self.logger.info(f"回测区间: {start_date} ~ {end_date}")
        self.logger.info("="*60)
        
        # 获取历史数据
        hist_data = self.data_provider.get_historical_data(underlying, start_date, end_date)
        if hist_data.empty:
            self.logger.error("无法获取历史数据")
            return pd.DataFrame()
        
        # 初始化 - 全仓持有标的
        first_price = hist_data['close'].iloc[0]
        shares = int(self.initial_capital * 0.95 / first_price)  # 95%资金用于标的
        self.underlying_position[underlying] = shares
        self.cash = self.initial_capital - shares * first_price
        
        self.logger.info(f"初始持仓: {shares} 股 {underlying} @ ${first_price:.2f}")
        self.logger.info(f"现金: ${self.cash:,.0f}")
        
        # 初始对冲
        self.initialize_hedge(underlying, shares, hist_data['date'].iloc[0].date(), hedge_ratio=0.8)
        
        # 逐日回测
        last_rebalance = hist_data['date'].iloc[0].date()
        
        for idx, row in hist_data.iterrows():
            current_date = row['date'].date() if hasattr(row['date'], 'date') else row['date']
            current_price = row['close']
            
            # 检查再平衡
            days_since_rebalance = (current_date - last_rebalance).days
            
            if days_since_rebalance >= rebalance_freq:
                self.logger.info(f"[{current_date}] 再平衡...")
                # 平仓旧期权
                self.option_positions = []
                # 建立新对冲
                self.initialize_hedge(underlying, shares, current_date, hedge_ratio=0.8)
                last_rebalance = current_date
            
            # 更新组合价值
            self.update_portfolio(current_date, {underlying: current_price})
        
        # 生成报告
        df = pd.DataFrame(self.history)
        if not df.empty:
            df['return'] = df['total_value'].pct_change()
            df['cumulative_return'] = (1 + df['return'].fillna(0)).cumprod() - 1
            
            # 对比买入持有
            buy_hold_return = (hist_data['close'].iloc[-1] - hist_data['close'].iloc[0]) / hist_data['close'].iloc[0]
            
            self.logger.info("")
            self.logger.info("="*60)
            self.logger.info("回测结果")
            self.logger.info(f"策略收益: {df['cumulative_return'].iloc[-1]*100:.2f}%")
            self.logger.info(f"买入持有收益: {buy_hold_return*100:.2f}%")
            self.logger.info(f"超额收益: {(df['cumulative_return'].iloc[-1] - buy_hold_return)*100:.2f}%")
            self.logger.info("="*60)
        
        return df


# ============================================================
# 测试函数
# ============================================================
def test_options_backtest():
    """测试期权策略回测"""
    print("="*60)
    print("期权策略回测测试 (Tradier数据)")
    print("="*60)
    print()
    
    # 创建回测引擎
    backtest = OptionsStrategyBacktest(
        initial_capital=1_000_000,
        strategy=OptionsStrategy.PROTECTIVE_PUT
    )
    
    # 检查API Key
    if backtest.data_provider.api_key == "YOUR_TRADIER_API_KEY_HERE":
        print("⚠️ 请先在 TradierDataProvider.py 中设置有效的 API Key")
        print("   获取地址: https://developer.tradier.com/")
        return
    
    # 执行回测
    end = date.today()
    start = end - timedelta(days=60)
    
    result = backtest.run_backtest('SPY', start.isoformat(), end.isoformat())
    
    if not result.empty:
        print("\n【回测数据预览】")
        print(result.tail())


if __name__ == "__main__":
    test_options_backtest()
