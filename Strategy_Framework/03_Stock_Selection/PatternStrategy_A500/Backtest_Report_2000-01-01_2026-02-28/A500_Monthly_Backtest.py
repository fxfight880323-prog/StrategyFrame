#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中证A500 月度换仓回测系统
==========================

回测设置:
- 回测期间: 2000/01/01 - 2026/02/28
- 换仓频率: 月度 (每月第一个交易日)
- 选股数量: Top 20
- 权重分配: 等权重

输出:
- 组合收益曲线
- 回撤分析
- 夏普比率等风险指标
- 完整交易记录
"""

import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
import logging
import json
import os

# 导入形态分析器
from A500_Pattern_Analyzer import PatternAnalyzer, A500DataProvider

# 导入监视器
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', '..', '..', '06_Backtesting'))
from BacktestMonitor import BacktestMonitor, MonitorLevel


# ============================================================
# 配置参数
# ============================================================
@dataclass
class BacktestConfig:
    """回测配置"""
    start_date: date = date(2000, 1, 1)
    end_date: date = date(2026, 2, 28)
    initial_capital: float = 1_000_000
    top_n: int = 20                    # 每月选股数量
    rebalance_freq: str = 'M'          # 月度换仓
    commission_rate: float = 0.001     # 手续费 0.1%
    slippage: float = 0.001            # 滑点 0.1%
    risk_free_rate: float = 0.03       # 无风险利率 3%


@dataclass
class TradeRecord:
    """交易记录"""
    trade_id: int
    date: date
    symbol: str
    name: str
    action: str          # BUY / SELL
    price: float
    shares: int
    amount: float
    commission: float
    reason: str          # 换仓/止损等


@dataclass
class Position:
    """持仓记录"""
    symbol: str
    name: str
    entry_date: date
    entry_price: float
    shares: int
    current_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float = 0


# ============================================================
# 月度回测引擎
# ============================================================
class A500MonthlyBacktest:
    """A500月度换仓回测引擎"""
    
    def __init__(self, config: BacktestConfig = None):
        self.config = config or BacktestConfig()
        self.data_provider = A500DataProvider()
        self.pattern_analyzer = PatternAnalyzer()
        
        # 回测状态
        self.cash = self.config.initial_capital
        self.positions: Dict[str, Position] = {}
        self.trade_records: List[TradeRecord] = []
        self.daily_values: List[Dict] = []
        self.monthly_signals: List[Dict] = []
        
        self.trade_id = 0
        self.current_date = self.config.start_date
        
        # 创建监视器
        self.monitor = BacktestMonitor(
            risk_free_rate=self.config.risk_free_rate,
            monitor_level=MonitorLevel.NORMAL
        )
        
        # 获取交易日历
        self.trading_days = self._generate_trading_calendar()
        
        print("="*70)
        print("中证A500 月度换仓回测系统")
        print("="*70)
        print(f"回测期间: {self.config.start_date} 至 {self.config.end_date}")
        print(f"初始资金: ${self.config.initial_capital:,.2f}")
        print(f"月度选股: Top {self.config.top_n}")
        print(f"手续费: {self.config.commission_rate*100:.2f}%")
        print(f"滑点: {self.config.slippage*100:.2f}%")
        print("="*70)
        print()
    
    def _generate_trading_calendar(self) -> List[date]:
        """生成交易日历（简化版，排除周末）"""
        days = []
        current = self.config.start_date
        while current <= self.config.end_date:
            if current.weekday() < 5:  # 周一到周五
                days.append(current)
            current += timedelta(days=1)
        return days
    
    def _get_month_end_dates(self) -> List[date]:
        """获取每月最后一个交易日"""
        month_ends = []
        current_year = self.config.start_date.year
        current_month = self.config.start_date.month
        
        while True:
            # 获取下月第一天
            if current_month == 12:
                next_month = date(current_year + 1, 1, 1)
            else:
                next_month = date(current_year, current_month + 1, 1)
            
            # 本月最后一天
            last_day = next_month - timedelta(days=1)
            
            # 找到最近的交易日
            while last_day not in self.trading_days and last_day >= self.config.start_date:
                last_day -= timedelta(days=1)
            
            if last_day >= self.config.start_date and last_day <= self.config.end_date:
                month_ends.append(last_day)
            
            # 更新年月
            if current_month == 12:
                current_year += 1
                current_month = 1
            else:
                current_month += 1
            
            if date(current_year, current_month, 1) > self.config.end_date:
                break
        
        return month_ends
    
    def _get_stock_price(self, symbol: str, query_date: date, price_type: str = 'close') -> float:
        """
        获取股票在某日期的价格
        
        实际应用中应该从数据库获取
        这里使用模拟数据演示
        """
        np.random.seed(hash(symbol + str(query_date)) % 10000)
        
        # 基础价格根据股票代码确定
        base = hash(symbol) % 100 + 10
        
        # 时间趋势 (2000-2026年的大趋势)
        days_from_start = (query_date - self.config.start_date).days
        trend = 1 + (days_from_start / 365) * 0.08  # 年化8%增长
        
        # 随机波动
        volatility = np.random.normal(0, 0.02)
        
        # 周期性波动
        cycle = np.sin(days_from_start / 365 * 2 * np.pi) * 0.1
        
        price = base * trend * (1 + volatility) * (1 + cycle)
        
        if price_type == 'open':
            price *= (1 + np.random.normal(0, 0.005))
        elif price_type == 'high':
            price *= (1 + abs(np.random.normal(0, 0.015)))
        elif price_type == 'low':
            price *= (1 - abs(np.random.normal(0, 0.015)))
        
        return round(max(price, 1.0), 2)
    
    def _get_a500_components_historical(self, query_date: date) -> pd.DataFrame:
        """获取某时间点的A500成分股列表"""
        # 实际应用中应该获取历史成分股
        # 这里使用模拟的成分股列表
        
        np.random.seed(hash(str(query_date)) % 10000)
        
        # 模拟500只成分股
        symbols = []
        for i in range(500):
            code = f"{i+1:06d}"
            symbols.append({
                '代码': code,
                '名称': f'股票{code}',
                '行业': np.random.choice(['科技', '金融', '消费', '医药', '制造'])
            })
        
        return pd.DataFrame(symbols)
    
    def _analyze_stocks_for_month(self, analysis_date: date) -> pd.DataFrame:
        """
        分析某月的股票形态
        
        由于无法获取2000-2026完整历史数据，使用模拟评分
        """
        print(f"  分析 {analysis_date.strftime('%Y-%m')} 形态...")
        
        components = self._get_a500_components_historical(analysis_date)
        
        results = []
        np.random.seed(hash(str(analysis_date)) % 10000)
        
        for _, row in components.iterrows():
            symbol = row['代码']
            name = row['名称']
            
            # 获取当前价格
            current_price = self._get_stock_price(symbol, analysis_date)
            
            # 模拟形态评分 (根据时间种子保持一致性)
            base_score = np.random.uniform(30, 90)
            
            # 趋势加分 (模拟不同月份的市场环境)
            month = analysis_date.month
            if month in [1, 4, 10, 11]:  # 传统上涨月份
                base_score += np.random.uniform(0, 10)
            elif month in [6, 8]:  # 传统调整月份
                base_score -= np.random.uniform(0, 10)
            
            total_score = min(100, max(0, base_score))
            
            # 确定信号
            if total_score >= 80:
                signal = "强烈买入"
            elif total_score >= 65:
                signal = "买入"
            elif total_score >= 50:
                signal = "偏买入"
            else:
                signal = "中性"
            
            # 形态类型
            patterns = ["双底形态", "杯柄形态", "上升三角形", "多头排列", "趋势上升", "震荡整理"]
            pattern = np.random.choice(patterns, p=[0.2, 0.15, 0.15, 0.2, 0.2, 0.1])
            
            results.append({
                'symbol': symbol,
                'name': name,
                'industry': row['行业'],
                'score': total_score,
                'signal': signal,
                'pattern': pattern,
                'price': current_price
            })
        
        df = pd.DataFrame(results)
        df = df.sort_values('score', ascending=False).reset_index(drop=True)
        
        return df
    
    def _execute_trade(self, symbol: str, name: str, action: str, 
                      price: float, shares: int, reason: str) -> float:
        """执行交易"""
        # 计算金额
        amount = price * shares
        
        # 手续费和滑点
        commission = amount * self.config.commission_rate
        slippage_cost = amount * self.config.slippage
        
        total_cost = amount + commission + slippage_cost
        
        if action == 'BUY':
            if total_cost > self.cash:
                # 资金不足，调整股数
                max_shares = int(self.cash / (price * (1 + self.config.commission_rate + self.config.slippage)))
                shares = max_shares
                amount = price * shares
                commission = amount * self.config.commission_rate
                slippage_cost = amount * self.config.slippage
                total_cost = amount + commission + slippage_cost
            
            self.cash -= total_cost
            
        else:  # SELL
            self.cash += amount - commission - slippage_cost
        
        # 记录交易
        self.trade_id += 1
        trade = TradeRecord(
            trade_id=self.trade_id,
            date=self.current_date,
            symbol=symbol,
            name=name,
            action=action,
            price=price,
            shares=shares,
            amount=amount,
            commission=commission + slippage_cost,
            reason=reason
        )
        self.trade_records.append(trade)
        
        return amount
    
    def _rebalance_portfolio(self, target_stocks: pd.DataFrame):
        """换仓操作"""
        print(f"  执行换仓: {len(target_stocks)} 只股票")
        
        # 1. 卖出不在目标列表中的持仓
        current_holdings = set(self.positions.keys())
        target_symbols = set(target_stocks['symbol'].tolist())
        
        sell_list = current_holdings - target_symbols
        for symbol in sell_list:
            pos = self.positions[symbol]
            sell_price = self._get_stock_price(symbol, self.current_date)
            
            self._execute_trade(
                symbol=symbol,
                name=pos.name,
                action='SELL',
                price=sell_price,
                shares=pos.shares,
                reason='换仓卖出'
            )
            
            del self.positions[symbol]
            print(f"    卖出 {symbol}: {pos.shares} 股 @ ${sell_price:.2f}")
        
        # 2. 计算每只股票的目标仓位
        portfolio_value = self._get_portfolio_value()
        target_value_per_stock = portfolio_value / self.config.top_n
        
        # 3. 买入/调整目标股票
        for _, row in target_stocks.iterrows():
            symbol = row['symbol']
            name = row['name']
            buy_price = self._get_stock_price(symbol, self.current_date)
            
            target_shares = int(target_value_per_stock / buy_price)
            
            if symbol in self.positions:
                # 调整持仓
                pos = self.positions[symbol]
                diff = target_shares - pos.shares
                
                if diff > 0:
                    # 加仓
                    self._execute_trade(symbol, name, 'BUY', buy_price, diff, '换仓加仓')
                    pos.shares = target_shares
                    print(f"    加仓 {symbol}: {diff} 股 @ ${buy_price:.2f}")
                elif diff < 0:
                    # 减仓
                    self._execute_trade(symbol, name, 'SELL', buy_price, abs(diff), '换仓减仓')
                    pos.shares = target_shares
                    print(f"    减仓 {symbol}: {abs(diff)} 股 @ ${buy_price:.2f}")
            else:
                # 新建仓
                if target_shares > 0:
                    self._execute_trade(symbol, name, 'BUY', buy_price, target_shares, '换仓买入')
                    self.positions[symbol] = Position(
                        symbol=symbol,
                        name=name,
                        entry_date=self.current_date,
                        entry_price=buy_price,
                        shares=target_shares,
                        current_price=buy_price,
                        market_value=buy_price * target_shares,
                        unrealized_pnl=0
                    )
                    print(f"    买入 {symbol}: {target_shares} 股 @ ${buy_price:.2f}")
    
    def _get_portfolio_value(self) -> float:
        """计算组合总价值"""
        position_value = sum(pos.market_value for pos in self.positions.values())
        return self.cash + position_value
    
    def _update_positions(self):
        """更新持仓市值"""
        for symbol, pos in self.positions.items():
            current_price = self._get_stock_price(symbol, self.current_date)
            pos.current_price = current_price
            pos.market_value = current_price * pos.shares
            pos.unrealized_pnl = (current_price - pos.entry_price) * pos.shares
    
    def _record_daily_value(self):
        """记录每日净值"""
        total_value = self._get_portfolio_value()
        
        # 计算当日收益
        if self.daily_values:
            prev_value = self.daily_values[-1]['total_value']
            daily_return = (total_value - prev_value) / prev_value if prev_value > 0 else 0
        else:
            daily_return = 0
        
        self.daily_values.append({
            'date': self.current_date,
            'cash': self.cash,
            'position_value': total_value - self.cash,
            'total_value': total_value,
            'daily_return': daily_return,
            'num_positions': len(self.positions)
        })
    
    def run_backtest(self) -> pd.DataFrame:
        """运行回测"""
        print("开始回测...")
        print()
        
        # 获取换仓日期 (每月最后一个交易日)
        rebalance_dates = self._get_month_end_dates()
        print(f"换仓次数: {len(rebalance_dates)} 次")
        print()
        
        # 遍历每个交易日
        month_idx = 0
        for i, current_date in enumerate(self.trading_days):
            self.current_date = current_date
            
            # 更新持仓市值
            self._update_positions()
            
            # 检查是否需要换仓
            if month_idx < len(rebalance_dates) and current_date == rebalance_dates[month_idx]:
                print(f"\n【换仓】{current_date.strftime('%Y-%m-%d')} ({month_idx+1}/{len(rebalance_dates)})")
                
                # 分析股票
                signals_df = self._analyze_stocks_for_month(current_date)
                
                # 记录信号
                top_signals = signals_df.head(self.config.top_n)
                self.monthly_signals.append({
                    'date': current_date,
                    'top_stocks': top_signals.to_dict('records')
                })
                
                print(f"  Top 5: {', '.join(top_signals.head(5)['symbol'].tolist())}")
                
                # 执行换仓
                self._rebalance_portfolio(top_signals)
                
                month_idx += 1
            
            # 记录每日净值
            self._record_daily_value()
            
            # 显示进度
            if (i + 1) % 252 == 0 or current_date == self.config.end_date:
                total_value = self._get_portfolio_value()
                ret = (total_value / self.config.initial_capital - 1) * 100
                print(f"  进度: {current_date} | 总资产: ${total_value:,.0f} | 收益: {ret:+.2f}%")
        
        print("\n" + "="*70)
        print("回测完成")
        print("="*70)
        
        return pd.DataFrame(self.daily_values)
    
    def calculate_performance(self) -> Dict:
        """计算绩效指标"""
        print("\n计算绩效指标...")
        
        values_df = pd.DataFrame(self.daily_values)
        values_df['date'] = pd.to_datetime(values_df['date'])
        values_df.set_index('date', inplace=True)
        
        # 日收益率
        daily_returns = values_df['daily_return'].dropna()
        
        # 使用监视器计算指标
        metrics = self.monitor.calculate_metrics(daily_returns)
        
        # 额外指标
        total_return = (values_df['total_value'].iloc[-1] / self.config.initial_capital - 1)
        
        results = {
            '初始资金': self.config.initial_capital,
            '期末资金': values_df['total_value'].iloc[-1],
            '总收益率': total_return * 100,
            '年化收益率': metrics.annual_return * 100,
            '年化波动率': metrics.volatility * 100,
            '最大回撤': metrics.max_drawdown * 100,
            '夏普比率': metrics.sharpe_ratio,
            '索提诺比率': metrics.sortino_ratio,
            '卡玛比率': metrics.calmar_ratio,
            '胜率': metrics.win_rate * 100,
            '盈亏比': metrics.profit_factor,
            'VaR_95': metrics.var_95 * 100,
            '交易次数': len(self.trade_records),
            '换仓次数': len(self.monthly_signals),
            '合规分数': metrics.compliance_score
        }
        
        return results
    
    def generate_report(self, output_dir: str = None):
        """生成完整报告"""
        if output_dir is None:
            output_dir = f"Backtest_Report_{self.config.start_date}_{self.config.end_date}"
        
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"\n生成报告: {output_dir}")
        
        # 1. 保存净值曲线
        values_df = pd.DataFrame(self.daily_values)
        values_path = f"{output_dir}/daily_values.csv"
        values_df.to_csv(values_path, index=False, encoding='utf-8-sig')
        print(f"  ✓ 净值曲线: {values_path}")
        
        # 2. 保存交易记录
        if self.trade_records:
            trades_df = pd.DataFrame([asdict(t) for t in self.trade_records])
            trades_path = f"{output_dir}/trade_records.csv"
            trades_df.to_csv(trades_path, index=False, encoding='utf-8-sig')
            print(f"  ✓ 交易记录: {trades_path}")
        
        # 3. 保存月度选股
        signals_data = []
        for month_data in self.monthly_signals:
            for stock in month_data['top_stocks']:
                signals_data.append({
                    'date': month_data['date'],
                    **stock
                })
        if signals_data:
            signals_df = pd.DataFrame(signals_data)
            signals_path = f"{output_dir}/monthly_signals.csv"
            signals_df.to_csv(signals_path, index=False, encoding='utf-8-sig')
            print(f"  ✓ 月度选股: {signals_path}")
        
        # 4. 保存绩效报告
        performance = self.calculate_performance()
        perf_path = f"{output_dir}/performance.json"
        with open(perf_path, 'w', encoding='utf-8') as f:
            json.dump(performance, f, indent=2, ensure_ascii=False)
        print(f"  ✓ 绩效报告: {perf_path}")
        
        # 5. 生成监视器报告
        monitor_path = self.monitor.generate_report(f"{output_dir}/monitor_report.json")
        print(f"  ✓ 监控报告: {monitor_path}")
        
        return output_dir, performance
    
    def print_summary(self, performance: Dict):
        """打印回测摘要"""
        print("\n" + "="*70)
        print("回测结果摘要")
        print("="*70)
        
        print(f"\n【资金表现】")
        print(f"  初始资金:        ${performance['初始资金']:>15,.2f}")
        print(f"  期末资金:        ${performance['期末资金']:>15,.2f}")
        print(f"  总收益率:        {performance['总收益率']:>15.2f}%")
        print(f"  年化收益率:      {performance['年化收益率']:>15.2f}%")
        
        print(f"\n【风险指标】")
        print(f"  年化波动率:      {performance['年化波动率']:>15.2f}%")
        print(f"  最大回撤:        {performance['最大回撤']:>15.2f}%")
        print(f"  VaR (95%):       {performance['VaR_95']:>15.2f}%")
        
        print(f"\n【风险调整收益】")
        print(f"  夏普比率:        {performance['夏普比率']:>15.2f}")
        print(f"  索提诺比率:      {performance['索提诺比率']:>15.2f}")
        print(f"  卡玛比率:        {performance['卡玛比率']:>15.2f}")
        
        print(f"\n【交易统计】")
        print(f"  交易次数:        {performance['交易次数']:>15} 次")
        print(f"  月度换仓:        {performance['换仓次数']:>15} 次")
        print(f"  胜率:            {performance['胜率']:>15.1f}%")
        print(f"  盈亏比:          {performance['盈亏比']:>15.2f}")
        
        print(f"\n【合规检查】")
        print(f"  合规分数:        {performance['合规分数']:>15.1f}/100")
        
        print("="*70)


def main():
    """主函数"""
    # 创建配置
    config = BacktestConfig(
        start_date=date(2000, 1, 1),
        end_date=date(2026, 2, 28),
        initial_capital=1_000_000,
        top_n=20,
        commission_rate=0.001,
        slippage=0.001
    )
    
    # 创建回测引擎
    engine = A500MonthlyBacktest(config)
    
    # 运行回测
    daily_values = engine.run_backtest()
    
    # 生成报告
    output_dir, performance = engine.generate_report()
    
    # 打印摘要
    engine.print_summary(performance)
    
    print(f"\n报告已保存至: {output_dir}")


if __name__ == "__main__":
    main()
