"""
技术形态策略回测系统
====================

基于TechnicalPatternAnalyzer生成的信号进行回测
支持多种仓位管理和风险控制策略

功能:
- 信号驱动回测
- 动态仓位管理
- 止损止盈执行
- 详细绩效报告
"""

import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

from TechnicalPatternAnalyzer import (
    TechnicalPatternAnalyzer, PatternBatchAnalyzer, 
    SignalStrength, PatternType, PriceActionSignal
)


# ============================================================
# 配置
# ============================================================
INITIAL_CAPITAL = 1_000_000
MAX_POSITIONS = 10  # 最大持仓数
POSITION_SIZE = 0.1  # 单只股票仓位10%

# 信号映射到仓位方向
SIGNAL_DIRECTION = {
    '强烈买入': 1,
    '买入': 1,
    '偏买入': 0.5,
    '中性': 0,
    '偏卖出': -0.5,
    '卖出': -1,
    '强烈卖出': -1,
}


# ============================================================
# 日志
# ============================================================
def setup_logger(name: str = "pattern_backtest") -> logging.Logger:
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
class Position:
    """持仓"""
    symbol: str
    entry_date: date
    entry_price: float
    quantity: int
    direction: int  # 1=多头, -1=空头
    target_price: float
    stop_loss: float
    signal_strength: str
    
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    
    def market_value(self) -> float:
        return abs(self.quantity) * self.current_price
    
    def cost_basis(self) -> float:
        return abs(self.quantity) * self.entry_price


@dataclass
class Trade:
    """交易记录"""
    symbol: str
    entry_date: date
    exit_date: date
    entry_price: float
    exit_price: float
    quantity: int
    direction: int
    pnl: float
    pnl_pct: float
    exit_reason: str  # 'target', 'stop_loss', 'signal_reversal', 'max_hold'


@dataclass
class DailyPortfolio:
    """每日组合状态"""
    date: date
    cash: float
    positions_value: float
    total_value: float
    daily_return: float
    cumulative_return: float
    num_positions: int


# ============================================================
# 技术形态策略回测引擎
# ============================================================
class PatternStrategyBacktest:
    """
    技术形态策略回测引擎
    
    基于TechnicalPatternAnalyzer的信号进行回测
    """
    
    def __init__(self, initial_capital: float = INITIAL_CAPITAL,
                 max_positions: int = MAX_POSITIONS,
                 position_size: float = POSITION_SIZE,
                 logger: logging.Logger = None):
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.position_size = position_size
        self.logger = logger or setup_logger()
        
        # 分析器
        self.analyzer = TechnicalPatternAnalyzer(logger)
        
        # 回测状态
        self.cash: float = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.portfolio_history: List[DailyPortfolio] = []
        self.signal_history: List[Dict] = []
        
        # 参数
        self.max_hold_days = 30  # 最大持仓天数
        self.trailing_stop = 0.05  # 移动止损5%
    
    def run_backtest(self, symbols: List[str], start_date: str, 
                    end_date: str, rebalance_freq: int = 5) -> pd.DataFrame:
        """
        执行回测
        
        Args:
            symbols: 股票列表
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
            rebalance_freq: 再平衡频率(交易日)
        """
        self.logger.info("="*60)
        self.logger.info("技术形态策略回测")
        self.logger.info("="*60)
        self.logger.info(f"回测区间: {start_date} ~ {end_date}")
        self.logger.info(f"标的数量: {len(symbols)}")
        self.logger.info(f"初始资金: ${self.initial_capital:,.0f}")
        self.logger.info(f"最大持仓: {self.max_positions}")
        self.logger.info(f"单仓仓位: {self.position_size*100:.0f}%")
        self.logger.info("")
        
        # 生成日期序列
        dates = pd.date_range(start=start_date, end=end_date, freq='B')  # 工作日
        
        for i, current_date in enumerate(dates):
            date_str = current_date.strftime('%Y-%m-%d')
            
            # 每N天或每日重新分析信号
            if i % rebalance_freq == 0 or i == len(dates) - 1:
                self.logger.info(f"[{date_str}] 分析信号...")
                signals = self._generate_signals_for_date(symbols, date_str)
            else:
                # 更新持仓价格
                self._update_positions_price(date_str)
                signals = []
            
            # 处理信号 - 开平仓
            self._process_signals(signals, date_str)
            
            # 检查止损止盈
            self._check_exits(date_str)
            
            # 记录组合状态
            self._record_portfolio(date_str)
            
            # 定期输出
            if i % 22 == 0 or i == len(dates) - 1:
                portfolio = self.portfolio_history[-1] if self.portfolio_history else None
                if portfolio:
                    self.logger.info(
                        f"  总资产: ${portfolio.total_value:,.0f} "
                        f"({portfolio.cumulative_return*100:+.2f}%) "
                        f"持仓: {portfolio.num_positions}"
                    )
        
        # 平掉所有持仓
        final_date = dates[-1].strftime('%Y-%m-%d')
        self._close_all_positions(final_date)
        
        # 生成报告
        return self._generate_report()
    
    def _generate_signals_for_date(self, symbols: List[str], 
                                   current_date: str) -> List[Dict]:
        """生成指定日期的信号"""
        signals = []
        
        for symbol in symbols:
            try:
                # 获取历史数据到当前日期
                df = self.analyzer.get_stock_data(symbol, period="3mo")
                if df.empty or len(df) < 30:
                    continue
                
                # 过滤到当前日期之前的数据
                df['Date'] = pd.to_datetime(df['Date'])
                df = df[df['Date'] <= current_date]
                
                if len(df) < 30:
                    continue
                
                # 使用最新数据生成信号
                df = self.analyzer.calculate_indicators(df)
                
                # 手动构建信号
                latest = df.iloc[-1]
                trend = self.analyzer.analyze_trend(df)
                price_action = self.analyzer.analyze_price_action(df)
                pattern = self.analyzer.detect_head_shoulders(df)
                if not pattern:
                    pattern = self.analyzer.detect_double_top_bottom(df)
                if not pattern:
                    pattern = self.analyzer.detect_triangle(df)
                if not pattern:
                    pattern = PatternType.UNKNOWN
                
                signal_strength = self.analyzer._calculate_signal_strength(
                    trend, price_action, pattern, latest
                )
                
                # 只记录有意义的信号
                if signal_strength not in [SignalStrength.NEUTRAL]:
                    signals.append({
                        'symbol': symbol,
                        'date': current_date,
                        'signal': signal_strength.value,
                        'pattern': pattern.value,
                        'trend': trend.value,
                        'price': latest['Close'],
                        'target': latest['Close'] * 1.05,
                        'stop_loss': latest['Close'] * 0.95,
                    })
                    
            except Exception as e:
                self.logger.debug(f"  {symbol} 信号生成失败: {e}")
        
        self.signal_history.extend(signals)
        return signals
    
    def _process_signals(self, signals: List[Dict], current_date: str):
        """处理交易信号"""
        for signal in signals:
            symbol = signal['symbol']
            signal_type = signal['signal']
            direction = SIGNAL_DIRECTION.get(signal_type, 0)
            
            # 买入信号
            if direction > 0 and symbol not in self.positions:
                if len(self.positions) >= self.max_positions:
                    continue  # 已达最大持仓
                
                self._open_position(symbol, signal, current_date, direction)
            
            # 卖出信号
            elif direction < 0 and symbol in self.positions:
                position = self.positions[symbol]
                if position.direction > 0:  # 当前是多头，平仓
                    self._close_position(symbol, signal['price'], current_date, 'signal_reversal')
            
            # 信号变化 - 从买入变中性/卖出
            elif direction == 0 and symbol in self.positions:
                position = self.positions[symbol]
                if position.direction > 0:
                    self._close_position(symbol, signal['price'], current_date, 'signal_reversal')
    
    def _open_position(self, symbol: str, signal: Dict, 
                       current_date: str, direction: int):
        """开仓"""
        price = signal['price']
        
        # 计算购买数量
        position_value = self.cash * self.position_size
        quantity = int(position_value / price)
        
        if quantity < 1:
            return
        
        cost = quantity * price
        if cost > self.cash * 0.95:
            return
        
        # 扣除资金
        self.cash -= cost
        
        # 创建持仓
        position = Position(
            symbol=symbol,
            entry_date=datetime.strptime(current_date, '%Y-%m-%d').date(),
            entry_price=price,
            quantity=quantity * direction,
            direction=direction,
            target_price=signal['target'],
            stop_loss=signal['stop_loss'],
            signal_strength=signal['signal'],
            current_price=price
        )
        
        self.positions[symbol] = position
        self.logger.info(f"  买入 {symbol}: {quantity}股 @ ${price:.2f}")
    
    def _close_position(self, symbol: str, price: float, 
                       current_date: str, reason: str):
        """平仓"""
        if symbol not in self.positions:
            return
        
        position = self.positions[symbol]
        
        # 计算盈亏
        exit_price = price
        pnl = (exit_price - position.entry_price) * position.quantity
        pnl_pct = (exit_price / position.entry_price - 1) * 100 * position.direction
        
        # 回收资金
        self.cash += position.quantity * exit_price
        
        # 记录交易
        trade = Trade(
            symbol=symbol,
            entry_date=position.entry_date,
            exit_date=datetime.strptime(current_date, '%Y-%m-%d').date(),
            entry_price=position.entry_price,
            exit_price=exit_price,
            quantity=abs(position.quantity),
            direction=position.direction,
            pnl=pnl,
            pnl_pct=pnl_pct,
            exit_reason=reason
        )
        self.trades.append(trade)
        
        self.logger.info(
            f"  卖出 {symbol}: {abs(position.quantity)}股 @ ${exit_price:.2f} "
            f"盈亏: {pnl_pct:+.2f}% ({reason})"
        )
        
        # 移除持仓
        del self.positions[symbol]
    
    def _update_positions_price(self, current_date: str):
        """更新持仓价格"""
        for symbol, position in self.positions.items():
            try:
                df = self.analyzer.get_stock_data(symbol, period="1mo")
                if df.empty:
                    continue
                
                df['Date'] = pd.to_datetime(df['Date'])
                row = df[df['Date'] <= current_date].tail(1)
                
                if not row.empty:
                    position.current_price = row['Close'].iloc[0]
                    position.unrealized_pnl = (
                        position.current_price - position.entry_price
                    ) * position.quantity
                    position.unrealized_pnl_pct = (
                        position.current_price / position.entry_price - 1
                    ) * 100 * position.direction
                    
            except Exception as e:
                pass
    
    def _check_exits(self, current_date: str):
        """检查止损止盈"""
        current = datetime.strptime(current_date, '%Y-%m-%d').date()
        
        for symbol, position in list(self.positions.items()):
            # 止损检查
            if position.direction > 0:  # 多头
                if position.current_price <= position.stop_loss:
                    self._close_position(symbol, position.current_price, current_date, 'stop_loss')
                    continue
                
                if position.current_price >= position.target_price:
                    self._close_position(symbol, position.current_price, current_date, 'target')
                    continue
            
            # 最大持仓时间检查
            hold_days = (current - position.entry_date).days
            if hold_days >= self.max_hold_days:
                self._close_position(symbol, position.current_price, current_date, 'max_hold')
                continue
    
    def _close_all_positions(self, current_date: str):
        """平掉所有持仓"""
        for symbol in list(self.positions.keys()):
            position = self.positions[symbol]
            self._close_position(symbol, position.current_price, current_date, 'backtest_end')
    
    def _record_portfolio(self, current_date: str):
        """记录组合状态"""
        current = datetime.strptime(current_date, '%Y-%m-%d').date()
        
        # 计算持仓市值
        positions_value = sum(p.market_value() for p in self.positions.values())
        total_value = self.cash + positions_value
        
        # 计算收益
        prev_value = self.portfolio_history[-1].total_value if self.portfolio_history else self.initial_capital
        daily_return = (total_value - prev_value) / prev_value if prev_value > 0 else 0
        cumulative_return = (total_value - self.initial_capital) / self.initial_capital
        
        self.portfolio_history.append(DailyPortfolio(
            date=current,
            cash=self.cash,
            positions_value=positions_value,
            total_value=total_value,
            daily_return=daily_return,
            cumulative_return=cumulative_return,
            num_positions=len(self.positions)
        ))
    
    def _generate_report(self) -> pd.DataFrame:
        """生成回测报告"""
        if not self.portfolio_history:
            return pd.DataFrame()
        
        # 组合历史
        portfolio_df = pd.DataFrame([
            {
                'Date': p.date,
                'Cash': p.cash,
                'Positions_Value': p.positions_value,
                'Total_Value': p.total_value,
                'Daily_Return': p.daily_return,
                'Cumulative_Return': p.cumulative_return,
                'Num_Positions': p.num_positions
            }
            for p in self.portfolio_history
        ])
        
        # 交易记录
        trades_df = pd.DataFrame([
            {
                'Symbol': t.symbol,
                'Entry_Date': t.entry_date,
                'Exit_Date': t.exit_date,
                'Entry_Price': t.entry_price,
                'Exit_Price': t.exit_price,
                'Quantity': t.quantity,
                'PnL': t.pnl,
                'PnL_Pct': t.pnl_pct,
                'Exit_Reason': t.exit_reason,
                'Hold_Days': (t.exit_date - t.entry_date).days
            }
            for t in self.trades
        ])
        
        # 绩效统计
        self.logger.info("")
        self.logger.info("="*60)
        self.logger.info("回测绩效报告")
        self.logger.info("="*60)
        
        final_value = portfolio_df['Total_Value'].iloc[-1]
        total_return = (final_value - self.initial_capital) / self.initial_capital
        
        # 计算夏普比率
        daily_returns = portfolio_df['Daily_Return'].dropna()
        sharpe = 0
        if len(daily_returns) > 1 and daily_returns.std() > 0:
            sharpe = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
        
        # 最大回撤
        cumulative = portfolio_df['Cumulative_Return']
        running_max = cumulative.cummax()
        drawdown = (cumulative - running_max) / (1 + running_max)
        max_drawdown = drawdown.min()
        
        # 交易统计
        if not trades_df.empty:
            win_trades = trades_df[trades_df['PnL'] > 0]
            loss_trades = trades_df[trades_df['PnL'] <= 0]
            
            win_rate = len(win_trades) / len(trades_df) * 100 if len(trades_df) > 0 else 0
            avg_win = win_trades['PnL_Pct'].mean() if not win_trades.empty else 0
            avg_loss = loss_trades['PnL_Pct'].mean() if not loss_trades.empty else 0
            
            self.logger.info(f"总交易次数: {len(trades_df)}")
            self.logger.info(f"盈利次数: {len(win_trades)} ({win_rate:.1f}%)")
            self.logger.info(f"平均盈利: {avg_win:.2f}%")
            self.logger.info(f"平均亏损: {avg_loss:.2f}%")
        
        self.logger.info(f"最终资产: ${final_value:,.0f}")
        self.logger.info(f"总收益率: {total_return*100:.2f}%")
        self.logger.info(f"夏普比率: {sharpe:.2f}")
        self.logger.info(f"最大回撤: {max_drawdown*100:.2f}%")
        self.logger.info("="*60)
        
        return portfolio_df
    
    def get_trade_summary(self) -> pd.DataFrame:
        """获取交易汇总"""
        if not self.trades:
            return pd.DataFrame()
        
        return pd.DataFrame([
            {
                'Symbol': t.symbol,
                'Entry': t.entry_date,
                'Exit': t.exit_date,
                'Entry_Price': t.entry_price,
                'Exit_Price': t.exit_price,
                'PnL_$': t.pnl,
                'PnL_%': t.pnl_pct,
                'Reason': t.exit_reason,
                'Days': (t.exit_date - t.entry_date).days
            }
            for t in self.trades
        ])


# ============================================================
# 测试函数
# ============================================================
def test_backtest():
    """测试回测系统"""
    print("="*60)
    print("技术形态策略回测测试")
    print("="*60)
    print()
    
    # 创建回测引擎
    backtest = PatternStrategyBacktest(
        initial_capital=100000,
        max_positions=5,
        position_size=0.15
    )
    
    # 回测参数
    end = date.today()
    start = end - timedelta(days=90)
    
    symbols = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META', 'SPY', 'QQQ']
    
    print(f"回测区间: {start} ~ {end}")
    print(f"测试标的: {symbols}")
    print()
    
    # 执行回测
    result = backtest.run_backtest(
        symbols=symbols,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        rebalance_freq=5
    )
    
    if not result.empty:
        print("\n【回测结果】")
        print(result.tail(10)[['Date', 'Total_Value', 'Cumulative_Return', 'Num_Positions']].to_string(index=False))
        
        trades = backtest.get_trade_summary()
        if not trades.empty:
            print("\n【交易记录】")
            print(trades.to_string(index=False))


if __name__ == "__main__":
    test_backtest()
