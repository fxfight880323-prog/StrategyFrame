"""
CTA 策略回测校验系统
=====================
验证交易信号的有效性和选股排名的准确性

回测逻辑：
1. 基于CTA信号生成交易指令 (BUY/HOLD/SELL)
2. 模拟交易执行和仓位管理
3. 计算绩效指标和风险指标
4. 对比不同策略的表现
"""

import sys
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

import pandas as pd
import numpy as np
import akshare as ak


# ============================================================
# CONFIG
# ============================================================
INITIAL_CAPITAL = 1000000  # 初始资金 100万美元
POSITION_SIZE = 0.15       # 单只股票最大仓位 15%
COMMISSION = 0.001         # 手续费 0.1%
SLIPPAGE = 0.001           # 滑点 0.1%
STOP_LOSS = 0.08           # 止损线 8%
TAKE_PROFIT = 0.20         # 止盈线 20%


# ============================================================
# Logging
# ============================================================
def setup_logger(name: str = "cta_backtest", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# Data Loader
# ============================================================
class DataLoader:
    """数据加载器"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.cache = {}
    
    def load_stock_data(self, ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
        """加载股票数据"""
        import time
        import random
        
        cache_key = f"{ticker}_{start_date}_{end_date}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                time.sleep(0.3 + random.uniform(0, 0.3))
                df = ak.stock_us_daily(symbol=ticker, adjust="")
                break
            except:
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    return pd.DataFrame()
        
        if df is None or df.empty:
            return pd.DataFrame()
        
        df = df.reset_index()
        df['Date'] = pd.to_datetime(df['Date'] if 'Date' in df.columns else df['date']).dt.date
        df = df[(df['Date'] >= pd.to_datetime(start_date).date()) & 
                (df['Date'] <= pd.to_datetime(end_date).date())].copy()
        
        if df.empty:
            return pd.DataFrame()
        
        df['Ticker'] = ticker
        df['Return'] = df['close'].pct_change()
        df['Cumulative_Return'] = (1 + df['Return']).cumprod() - 1
        
        self.cache[cache_key] = df
        return df
    
    def load_signals(self, signal_file: str) -> pd.DataFrame:
        """加载交易信号"""
        try:
            df = pd.read_csv(signal_file)
            df['Date'] = pd.to_datetime(df['Date']).dt.date
            return df
        except Exception as e:
            self.logger.error(f"加载信号文件失败: {e}")
            return pd.DataFrame()


# ============================================================
# Portfolio Manager
# ============================================================
@dataclass
class Position:
    """持仓信息"""
    ticker: str
    shares: int
    entry_price: float
    entry_date: date
    current_price: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class Portfolio:
    """投资组合"""
    
    def __init__(self, initial_capital: float, logger: logging.Logger):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Dict] = []
        self.daily_values: List[Dict] = []
        self.logger = logger
    
    def get_total_value(self, current_prices: Dict[str, float]) -> float:
        """计算总市值"""
        positions_value = sum(
            pos.shares * current_prices.get(ticker, pos.current_price)
            for ticker, pos in self.positions.items()
        )
        return self.cash + positions_value
    
    def buy(self, ticker: str, price: float, date: date, target_weight: float = POSITION_SIZE):
        """买入股票"""
        if ticker in self.positions:
            return False  # 已有持仓，不重复买入
        
        total_value = self.get_total_value({ticker: price})
        target_value = total_value * target_weight
        available_cash = min(self.cash * 0.95, target_value)  # 保留5%现金
        
        if available_cash < 1000:  # 最小交易金额
            return False
        
        # 计算可买入股数
        cost_per_share = price * (1 + COMMISSION + SLIPPAGE)
        shares = int(available_cash / cost_per_share)
        
        if shares <= 0:
            return False
        
        total_cost = shares * cost_per_share
        self.cash -= total_cost
        
        self.positions[ticker] = Position(
            ticker=ticker,
            shares=shares,
            entry_price=price,
            entry_date=date,
            current_price=price,
            market_value=shares * price,
            unrealized_pnl=0,
            unrealized_pnl_pct=0
        )
        
        self.trades.append({
            'date': date,
            'ticker': ticker,
            'action': 'BUY',
            'shares': shares,
            'price': price,
            'cost': total_cost
        })
        
        return True
    
    def sell(self, ticker: str, price: float, date: date, reason: str = 'signal'):
        """卖出股票"""
        if ticker not in self.positions:
            return False
        
        position = self.positions[ticker]
        proceeds = position.shares * price * (1 - COMMISSION - SLIPPAGE)
        
        realized_pnl = position.shares * (price - position.entry_price)
        realized_pnl_pct = (price / position.entry_price - 1) * 100
        
        self.cash += proceeds
        del self.positions[ticker]
        
        self.trades.append({
            'date': date,
            'ticker': ticker,
            'action': 'SELL',
            'shares': position.shares,
            'price': price,
            'proceeds': proceeds,
            'realized_pnl': realized_pnl,
            'realized_pnl_pct': realized_pnl_pct,
            'reason': reason
        })
        
        return True
    
    def update_positions(self, current_prices: Dict[str, float], current_date: date):
        """更新持仓市值"""
        for ticker, position in self.positions.items():
            if ticker in current_prices:
                position.current_price = current_prices[ticker]
                position.market_value = position.shares * position.current_price
                position.unrealized_pnl = position.shares * (position.current_price - position.entry_price)
                position.unrealized_pnl_pct = (position.current_price / position.entry_price - 1) * 100
                
                # 止损止盈检查
                if position.unrealized_pnl_pct < -STOP_LOSS * 100:
                    self.sell(ticker, position.current_price, current_date, 'stop_loss')
                elif position.unrealized_pnl_pct > TAKE_PROFIT * 100:
                    self.sell(ticker, position.current_price, current_date, 'take_profit')
    
    def record_daily_value(self, date: date, prices: Dict[str, float]):
        """记录每日净值"""
        total_value = self.get_total_value(prices)
        self.daily_values.append({
            'date': date,
            'cash': self.cash,
            'positions_value': total_value - self.cash,
            'total_value': total_value,
            'return_pct': (total_value / self.initial_capital - 1) * 100
        })


# ============================================================
# Backtest Engine
# ============================================================
class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.data_loader = DataLoader(logger)
    
    def run_strategy(self, strategy_name: str, signals_df: pd.DataFrame, 
                     start_date: str, end_date: str) -> Dict[str, Any]:
        """
        运行回测策略
        
        策略类型：
        1. CTA_Strategy: 基于CTA信号 (BUY买入, SELL卖出)
        2. Top_Rank_Strategy: 买入排名前N的股票
        3. Long_Only: 买入并持有所有股票
        4. SPY_Benchmark: SPY作为基准
        """
        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"运行回测策略: {strategy_name}")
        self.logger.info(f"{'='*60}")
        
        portfolio = Portfolio(INITIAL_CAPITAL, self.logger)
        
        # 获取所有交易日
        all_dates = sorted(signals_df['Date'].unique())
        all_dates = [d for d in all_dates if pd.to_datetime(start_date).date() <= d <= pd.to_datetime(end_date).date()]
        
        if not all_dates:
            return {}
        
        # 获取股票池
        all_tickers = signals_df['Ticker'].unique()
        
        # 加载所有股票数据
        price_data = {}
        for ticker in all_tickers:
            df = self.data_loader.load_stock_data(ticker, start_date, end_date)
            if not df.empty:
                price_data[ticker] = df.set_index('Date')['close'].to_dict()
        
        # 回测循环
        rebalance_days = 0
        for i, current_date in enumerate(all_dates):
            # 获取当日价格
            current_prices = {
                ticker: prices.get(current_date, 0) 
                for ticker, prices in price_data.items() if current_date in prices
            }
            
            if not current_prices:
                continue
            
            # 更新持仓
            portfolio.update_positions(current_prices, current_date)
            
            # 获取当日信号
            day_signals = signals_df[signals_df['Date'] == current_date]
            
            # 执行策略
            if strategy_name == 'CTA_Strategy':
                self._execute_cta_strategy(portfolio, day_signals, current_prices, current_date)
            elif strategy_name == 'Top10_Strategy':
                if i % 5 == 0:  # 每5天调仓一次
                    rebalance_days += 1
                    self._execute_topN_strategy(portfolio, day_signals, current_prices, current_date, n=10)
            elif strategy_name == 'Top20_Strategy':
                if i % 5 == 0:
                    rebalance_days += 1
                    self._execute_topN_strategy(portfolio, day_signals, current_prices, current_date, n=20)
            
            # 记录净值
            portfolio.record_daily_value(current_date, current_prices)
        
        # 计算绩效指标
        results = self._calculate_metrics(portfolio, all_dates[0], all_dates[-1])
        results['strategy_name'] = strategy_name
        results['total_trades'] = len(portfolio.trades)
        results['rebalance_times'] = rebalance_days
        results['price_data'] = price_data  # 保存用于信号验证
        
        return results
    
    def _execute_cta_strategy(self, portfolio: Portfolio, day_signals: pd.DataFrame, 
                             prices: Dict[str, float], date: date):
        """执行CTA策略"""
        # 卖出SELL信号的股票
        for _, row in day_signals.iterrows():
            ticker = row['Ticker']
            signal = row.get('Signal', 'HOLD')
            
            if ticker in prices:
                if signal == 'SELL' and ticker in portfolio.positions:
                    portfolio.sell(ticker, prices[ticker], date, 'cta_sell_signal')
                elif signal == 'BUY' and ticker not in portfolio.positions:
                    portfolio.buy(ticker, prices[ticker], date)
    
    def _execute_topN_strategy(self, portfolio: Portfolio, day_signals: pd.DataFrame,
                              prices: Dict[str, float], date: date, n: int = 10):
        """执行Top N策略"""
        # 按排名选择前N只股票
        top_stocks = day_signals.nsmallest(n, 'Rank')['Ticker'].tolist()
        
        # 卖出不在Top N的持仓
        for ticker in list(portfolio.positions.keys()):
            if ticker not in top_stocks:
                if ticker in prices:
                    portfolio.sell(ticker, prices[ticker], date, 'not_in_topN')
        
        # 买入Top N中没有持仓的股票
        for ticker in top_stocks:
            if ticker not in portfolio.positions and ticker in prices:
                portfolio.buy(ticker, prices[ticker], date, target_weight=POSITION_SIZE)
    
    def _calculate_metrics(self, portfolio: Portfolio, start_date: date, end_date: date) -> Dict[str, Any]:
        """计算绩效指标"""
        if not portfolio.daily_values:
            return {}
        
        df = pd.DataFrame(portfolio.daily_values)
        df['daily_return'] = df['total_value'].pct_change()
        
        # 基础指标
        total_return = (df['total_value'].iloc[-1] / portfolio.initial_capital - 1) * 100
        
        # 年化收益率
        days = (end_date - start_date).days
        annual_return = ((1 + total_return/100) ** (365/days) - 1) * 100 if days > 0 else 0
        
        # 波动率
        volatility = df['daily_return'].std() * np.sqrt(252) * 100
        
        # 夏普比率 (假设无风险利率5%)
        risk_free_rate = 5
        sharpe_ratio = (annual_return - risk_free_rate) / volatility if volatility > 0 else 0
        
        # 最大回撤
        df['cummax'] = df['total_value'].cummax()
        df['drawdown'] = (df['total_value'] - df['cummax']) / df['cummax']
        max_drawdown = df['drawdown'].min() * 100
        
        # 胜率
        trades_df = pd.DataFrame(portfolio.trades)
        if not trades_df.empty:
            sell_trades = trades_df[trades_df['action'] == 'SELL']
            if not sell_trades.empty:
                win_rate = (sell_trades['realized_pnl'] > 0).mean() * 100
                avg_win = sell_trades[sell_trades['realized_pnl'] > 0]['realized_pnl_pct'].mean() if len(sell_trades[sell_trades['realized_pnl'] > 0]) > 0 else 0
                avg_loss = sell_trades[sell_trades['realized_pnl'] < 0]['realized_pnl_pct'].mean() if len(sell_trades[sell_trades['realized_pnl'] < 0]) > 0 else 0
            else:
                win_rate = 0
                avg_win = 0
                avg_loss = 0
        else:
            win_rate = 0
            avg_win = 0
            avg_loss = 0
        
        return {
            'initial_capital': portfolio.initial_capital,
            'final_value': df['total_value'].iloc[-1],
            'total_return_pct': total_return,
            'annual_return_pct': annual_return,
            'volatility_pct': volatility,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown_pct': max_drawdown,
            'win_rate_pct': win_rate,
            'avg_win_pct': avg_win,
            'avg_loss_pct': avg_loss,
            'trading_days': len(df),
        }


# ============================================================
# Results Analysis
# ============================================================
def print_comparison(results_list: List[Dict], logger: logging.Logger):
    """打印策略对比"""
    logger.info("\n" + "="*100)
    logger.info("策略回测结果对比")
    logger.info("="*100)
    
    metrics = ['total_return_pct', 'annual_return_pct', 'volatility_pct', 
               'sharpe_ratio', 'max_drawdown_pct', 'win_rate_pct']
    
    # 创建对比表
    comparison = pd.DataFrame(results_list)
    
    logger.info(f"\n{'指标':<25} " + " ".join(f"{r['strategy_name']:<20}" for r in results_list))
    logger.info("-"*100)
    
    for metric in metrics:
        metric_name = {
            'total_return_pct': '总收益率 (%)',
            'annual_return_pct': '年化收益率 (%)',
            'volatility_pct': '年化波动率 (%)',
            'sharpe_ratio': '夏普比率',
            'max_drawdown_pct': '最大回撤 (%)',
            'win_rate_pct': '胜率 (%)'
        }.get(metric, metric)
        
        values = [f"{r.get(metric, 0):>18.2f}" for r in results_list]
        logger.info(f"{metric_name:<25} " + " ".join(values))
    
    logger.info("-"*100)
    logger.info(f"{'初始资金':<25} " + " ".join(f"${r['initial_capital']:>16,.0f}" for r in results_list))
    logger.info(f"{'最终市值':<25} " + " ".join(f"${r['final_value']:>16,.0f}" for r in results_list))
    logger.info(f"{'交易次数':<25} " + " ".join(f"{r['total_trades']:>18}" for r in results_list))
    logger.info("="*100)


def calculate_future_returns(signals_df: pd.DataFrame, price_data: Dict, 
                            holding_periods: List[int] = [5, 20, 30], 
                            logger: logging.Logger = None) -> pd.DataFrame:
    """
    计算信号发出后的未来持有收益
    
    关键：使用信号日期的价格作为基准，计算未来N天的真实持有收益
    确保没有时间泄露：只使用信号日期及之前的数据生成信号，
    使用信号日期之后的数据计算收益
    """
    if logger:
        logger.info("\n" + "="*60)
        logger.info("计算信号后的未来持有收益 (无未来数据泄露)")
        logger.info("="*60)
    
    results = []
    
    for _, row in signals_df.iterrows():
        ticker = row['Ticker']
        signal_date = row['Date'] if isinstance(row['Date'], date) else pd.to_datetime(row['Date']).date()
        
        if ticker not in price_data:
            continue
        
        prices = price_data[ticker]
        
        # 获取信号日期的价格
        if signal_date not in prices:
            continue
        
        entry_price = prices[signal_date]
        
        # 获取信号日期后的所有交易日
        future_dates = [d for d in sorted(prices.keys()) if d > signal_date]
        
        result = {
            'Ticker': ticker,
            'Signal_Date': signal_date,
            'Signal': row['Signal'],
            'Rank': row['Rank'],
            'Entry_Price': entry_price,
        }
        
        # 计算各持有期的收益
        for period in holding_periods:
            if len(future_dates) >= period:
                exit_date = future_dates[period - 1]  # period天后
                exit_price = prices[exit_date]
                future_return = (exit_price / entry_price - 1) * 100
                result[f'Future_Return_{period}D'] = future_return
                result[f'Exit_Date_{period}D'] = exit_date
            else:
                # 数据不足，使用最后一天
                if future_dates:
                    exit_date = future_dates[-1]
                    exit_price = prices[exit_date]
                    actual_days = len(future_dates)
                    future_return = (exit_price / entry_price - 1) * 100
                    result[f'Future_Return_{period}D'] = future_return
                    result[f'Exit_Date_{period}D'] = exit_date
                    result[f'Actual_Holding_{period}D'] = actual_days
                else:
                    result[f'Future_Return_{period}D'] = np.nan
        
        results.append(result)
    
    return pd.DataFrame(results)


def validate_signals(signals_df: pd.DataFrame, price_data: Dict, logger: logging.Logger):
    """
    验证信号的有效性 - 使用真实的未来持有收益
    
    重要：此函数计算的是信号发出后持有N天的真实收益，
    用于验证CTA信号的预测能力
    """
    logger.info("\n" + "="*60)
    logger.info("信号有效性验证 (基于真实未来收益)")
    logger.info("="*60)
    
    # 1. 信号分布
    signal_dist = signals_df['Signal'].value_counts()
    logger.info(f"\n信号分布:")
    for signal, count in signal_dist.items():
        logger.info(f"  {signal}: {count} ({count/len(signals_df)*100:.1f}%)")
    
    # 2. 计算真实的未来收益
    future_returns_df = calculate_future_returns(signals_df, price_data, [5, 20, 30], logger)
    
    if future_returns_df.empty:
        logger.warning("无法计算未来收益，数据不足")
        return
    
    # 3. 不同信号的未来收益表现
    logger.info(f"\n信号发出后持有收益表现:")
    logger.info("-" * 60)
    
    for signal in ['BUY', 'HOLD', 'SELL']:
        signal_data = future_returns_df[future_returns_df['Signal'] == signal]
        if signal_data.empty:
            continue
        
        avg_5d = signal_data['Future_Return_5D'].mean()
        avg_20d = signal_data['Future_Return_20D'].mean()
        avg_30d = signal_data['Future_Return_30D'].mean()
        
        count = len(signal_data)
        
        logger.info(f"\n{signal} 信号 (n={count}):")
        logger.info(f"  持有5日平均收益:  {avg_5d:+.2f}%")
        logger.info(f"  持有20日平均收益: {avg_20d:+.2f}%")
        logger.info(f"  持有30日平均收益: {avg_30d:+.2f}%")
    
    # 4. 排名分组的未来收益表现
    logger.info(f"\n排名分组未来收益表现 (持有20日):")
    logger.info("-" * 60)
    
    future_returns_df['Rank_Group'] = pd.cut(
        future_returns_df['Rank'], 
        bins=[0, 10, 30, 70, 100, 999], 
        labels=['Top 10', 'Top 11-30', 'Mid 31-70', 'Bottom 71-100', 'Others']
    )
    
    for group in ['Top 10', 'Top 11-30', 'Mid 31-70', 'Bottom 71-100']:
        group_data = future_returns_df[future_returns_df['Rank_Group'] == group]
        if not group_data.empty:
            avg_20d_return = group_data['Future_Return_20D'].mean()
            win_rate = (group_data['Future_Return_20D'] > 0).mean() * 100
            count = len(group_data)
            logger.info(f"  {group}: 平均收益 {avg_20d_return:+.2f}%, 胜率 {win_rate:.1f}% (n={count})")
    
    # 5. 信号准确率分析
    logger.info(f"\n信号预测准确率:")
    logger.info("-" * 60)
    
    for signal in ['BUY', 'SELL']:
        signal_data = future_returns_df[future_returns_df['Signal'] == signal]
        if signal_data.empty:
            continue
        
        if signal == 'BUY':
            correct = (signal_data['Future_Return_20D'] > 0).sum()
            accuracy = (signal_data['Future_Return_20D'] > 0).mean() * 100
        else:  # SELL
            correct = (signal_data['Future_Return_20D'] < 0).sum()
            accuracy = (signal_data['Future_Return_20D'] < 0).mean() * 100
        
        total = len(signal_data)
        logger.info(f"  {signal} 信号20日预测准确率: {accuracy:.1f}% ({correct}/{total})")
    
    logger.info("="*60)
    
    return future_returns_df


# ============================================================
# Main
# ============================================================
def main():
    logger = setup_logger(level=logging.INFO)
    
    logger.info("="*60)
    logger.info("CTA 策略回测校验系统")
    logger.info("="*60)
    logger.info("重要: 本回测严格避免未来数据泄露，所有收益计算基于信号发出后的真实价格")
    
    # 加载信号数据
    signal_file = "cta_rankings.csv"
    signals_df = pd.read_csv(signal_file)
    signals_df['Date'] = pd.to_datetime(signals_df['Date']).dt.date
    
    # 运行回测
    engine = BacktestEngine(logger)
    
    strategies = [
        'CTA_Strategy',
        'Top10_Strategy', 
        'Top20_Strategy'
    ]
    
    start_date = "2025-01-01"
    end_date = "2026-02-23"
    
    results = []
    price_data_for_validation = None
    
    for strategy in strategies:
        result = engine.run_strategy(strategy, signals_df, start_date, end_date)
        if result:
            results.append(result)
            # 保存price_data用于信号验证
            if price_data_for_validation is None and 'price_data' in result:
                price_data_for_validation = result.pop('price_data')
    
    # 验证信号有效性 (使用真实的未来收益)
    if price_data_for_validation:
        validate_signals(signals_df, price_data_for_validation, logger)
    
    # 打印对比
    if results:
        print_comparison(results, logger)
    
    logger.info("\n回测完成！")
    logger.info("说明: 以上回测结果基于信号发出后的真实未来收益，无未来数据泄露")


if __name__ == "__main__":
    main()
