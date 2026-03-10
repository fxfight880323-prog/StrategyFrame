#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测系统演示 (模拟数据版)
==========================

使用模拟数据展示完整的CTA回测流程
同时提供Yahoo Finance/AKShare接口
"""

import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger("backtest_demo")


class MockDataProvider:
    """模拟数据提供器 (用于演示)"""
    
    def generate_stock_data(self, symbol: str, days: int = 500, 
                           trend: str = "random") -> pd.DataFrame:
        """
        生成模拟股票数据
        
        Args:
            symbol: 股票代码
            days: 天数
            trend: 趋势类型 ('bull', 'bear', 'random', 'cycle')
        """
        np.random.seed(42)  # 可重复
        
        dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
        
        # 基础价格
        base_price = np.random.uniform(50, 200)
        
        # 生成收益率
        if trend == "bull":
            # 牛市: 正收益偏多
            returns = np.random.normal(0.0008, 0.015, days)
        elif trend == "bear":
            # 熊市: 负收益偏多
            returns = np.random.normal(-0.0005, 0.02, days)
        elif trend == "cycle":
            # 周期性
            t = np.linspace(0, 4*np.pi, days)
            cycle = 0.01 * np.sin(t)
            returns = np.random.normal(0, 0.015, days) + cycle
        else:
            # 随机游走
            returns = np.random.normal(0, 0.015, days)
        
        # 计算价格
        prices = base_price * (1 + returns).cumprod()
        
        # 生成OHLC
        df = pd.DataFrame({
            'Date': dates,
            'Open': prices * (1 + np.random.normal(0, 0.005, days)),
            'High': prices * (1 + np.random.uniform(0, 0.02, days)),
            'Low': prices * (1 - np.random.uniform(0, 0.02, days)),
            'Close': prices,
            'Volume': np.random.randint(1000000, 10000000, days),
        })
        
        # 确保High/Low合理
        df['High'] = df[['Open', 'Close', 'High']].max(axis=1)
        df['Low'] = df[['Open', 'Close', 'Low']].min(axis=1)
        
        return df


class CTAStrategyBacktest:
    """CTA策略回测引擎"""
    
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.data_provider = MockDataProvider()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()
        
        # 移动平均线
        df['MA_Fast'] = df['Close'].rolling(20).mean()
        df['MA_Slow'] = df['Close'].rolling(60).mean()
        
        # 日收益率
        df['Daily_Return'] = df['Close'].pct_change()
        
        # MACD
        df['EMA_12'] = df['Close'].ewm(span=12).mean()
        df['EMA_26'] = df['Close'].ewm(span=26).mean()
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        df['MACD_Signal'] = df['MACD'].ewm(span=9).mean()
        
        # RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        return df
    
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """生成交易信号"""
        df = df.copy()
        
        # 双均线交叉信号
        df['Signal_MA'] = np.where(df['MA_Fast'] > df['MA_Slow'], 1, 0)
        df['Position_MA'] = df['Signal_MA'].shift(1)  # 滞后一期
        
        # MACD信号
        df['Signal_MACD'] = np.where(df['MACD'] > df['MACD_Signal'], 1, 0)
        
        # 综合信号 (双均线 + MACD确认)
        df['Signal'] = np.where(
            (df['Signal_MA'] == 1) & (df['Signal_MACD'] == 1), 1,  # 买入
            np.where((df['Signal_MA'] == 0) & (df['Signal_MACD'] == 0), -1, 0)  # 卖出
        )
        
        df['Position'] = df['Signal'].shift(1).fillna(0)
        
        return df
    
    def run_backtest(self, symbol: str, df: pd.DataFrame = None) -> dict:
        """
        执行回测
        
        Returns:
            回测结果字典
        """
        print(f"\n{'='*70}")
        print(f"CTA策略回测: {symbol}")
        print(f"{'='*70}")
        
        # 使用传入数据或生成模拟数据
        if df is None:
            df = self.data_provider.generate_stock_data(symbol, days=500, trend="cycle")
        
        print(f"数据区间: {df['Date'].min().date()} ~ {df['Date'].max().date()}")
        print(f"数据条数: {len(df)} 天")
        print(f"初始价格: ${df['Close'].iloc[0]:.2f}")
        print(f"最新价格: ${df['Close'].iloc[-1]:.2f}")
        print()
        
        # 计算指标和信号
        df = self.calculate_indicators(df)
        df = self.generate_signals(df)
        
        # 计算策略收益
        df['Strategy_Return'] = df['Position'] * df['Daily_Return']
        
        # 累计收益
        df['Cumulative_Market'] = (1 + df['Daily_Return'].fillna(0)).cumprod()
        df['Cumulative_Strategy'] = (1 + df['Strategy_Return'].fillna(0)).cumprod()
        
        # 资金曲线
        df['Portfolio_Value'] = self.initial_capital * df['Cumulative_Strategy']
        
        # 计算绩效指标
        total_days = len(df)
        years = total_days / 252  # 交易日
        
        # 收益率
        total_market_return = df['Cumulative_Market'].iloc[-1] - 1
        total_strategy_return = df['Cumulative_Strategy'].iloc[-1] - 1
        excess_return = total_strategy_return - total_market_return
        
        # 年化收益
        annual_market = (1 + total_market_return) ** (1/years) - 1 if years > 0 else 0
        annual_strategy = (1 + total_strategy_return) ** (1/years) - 1 if years > 0 else 0
        
        # 风险指标
        strategy_returns = df['Strategy_Return'].dropna()
        volatility = strategy_returns.std() * np.sqrt(252)
        
        # 最大回撤
        cummax = df['Cumulative_Strategy'].cummax()
        drawdown = (df['Cumulative_Strategy'] - cummax) / cummax
        max_drawdown = drawdown.min()
        
        # 夏普比率 (假设无风险利率3%)
        sharpe = (annual_strategy - 0.03) / volatility if volatility > 0 else 0
        
        # 交易统计
        trades = df['Signal'].diff().abs().sum() / 2
        
        # 胜率
        trade_returns = df[df['Position'] != 0]['Strategy_Return']
        win_rate = (trade_returns > 0).sum() / len(trade_returns) if len(trade_returns) > 0 else 0
        
        result = {
            'symbol': symbol,
            'df': df,
            'total_return': total_strategy_return,
            'market_return': total_market_return,
            'excess_return': excess_return,
            'annual_return': annual_strategy,
            'annual_market': annual_market,
            'volatility': volatility,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe,
            'trades': int(trades),
            'win_rate': win_rate,
            'final_value': df['Portfolio_Value'].iloc[-1],
        }
        
        self._print_report(result)
        
        return result
    
    def _print_report(self, result: dict):
        """打印回测报告"""
        print("-"*70)
        print("回测绩效报告")
        print("-"*70)
        print(f"{'总收益率:':<20} {result['total_return']*100:>10.2f}%")
        print(f"{'买入持有收益:':<20} {result['market_return']*100:>10.2f}%")
        print(f"{'超额收益:':<20} {result['excess_return']*100:>10.2f}%")
        print()
        print(f"{'年化收益率:':<20} {result['annual_return']*100:>10.2f}%")
        print(f"{'年化波动率:':<20} {result['volatility']*100:>10.2f}%")
        print(f"{'最大回撤:':<20} {result['max_drawdown']*100:>10.2f}%")
        print(f"{'夏普比率:':<20} {result['sharpe_ratio']:>10.2f}")
        print()
        print(f"{'交易次数:':<20} {result['trades']:>10}")
        print(f"{'胜率:':<20} {result['win_rate']*100:>10.1f}%")
        print(f"{'初始资金:':<20} ${self.initial_capital:>10,.0f}")
        print(f"{'最终资金:':<20} ${result['final_value']:>10,.0f}")
        print("="*70)


def run_demo():
    """运行演示"""
    print("="*70)
    print("CTA策略回测系统演示")
    print("="*70)
    print()
    print("策略说明:")
    print("  - 双均线交叉 (MA20/MA60)")
    print("  - MACD确认")
    print("  - 做多/空仓 切换")
    print()
    
    backtest = CTAStrategyBacktest(initial_capital=100000)
    
    # 测试不同市场环境
    scenarios = [
        ('SPY', 'cycle'),    # 周期性市场
        ('AAPL', 'bull'),    # 牛市
        ('TSLA', 'random'),  # 随机游走
    ]
    
    results = []
    
    for symbol, trend in scenarios:
        df = backtest.data_provider.generate_stock_data(symbol, days=500, trend=trend)
        result = backtest.run_backtest(symbol, df)
        results.append(result)
    
    # 汇总对比
    print("\n" + "="*70)
    print("回测结果汇总")
    print("="*70)
    print(f"{'标的':<10} {'策略收益':>12} {'买入持有':>12} {'超额收益':>12} {'夏普比率':>10} {'最大回撤':>10}")
    print("-"*70)
    
    for r in results:
        print(f"{r['symbol']:<10} "
              f"{r['total_return']*100:>11.2f}% "
              f"{r['market_return']*100:>11.2f}% "
              f"{r['excess_return']*100:>11.2f}% "
              f"{r['sharpe_ratio']:>10.2f} "
              f"{r['max_drawdown']*100:>9.2f}%")
    
    print("="*70)
    
    # 展示最近交易信号
    print("\n" + "="*70)
    print("最新交易信号示例 (SPY)")
    print("="*70)
    
    spy_df = results[0]['df']
    recent = spy_df.tail(10)[['Date', 'Close', 'MA_Fast', 'MA_Slow', 'Signal', 'RSI']].copy()
    recent['Date'] = recent['Date'].dt.strftime('%Y-%m-%d')
    recent['Signal_Text'] = recent['Signal'].map({1: '买入', 0: '持有', -1: '卖出'})
    
    print(recent[['Date', 'Close', 'MA_Fast', 'MA_Slow', 'Signal_Text', 'RSI']].to_string(index=False))
    
    print("\n" + "="*70)
    print("提示: 如需使用真实数据，请:")
    print("  1. Yahoo Finance: pip install yfinance")
    print("  2. AKShare: pip install akshare (A股)")
    print("  3. RiceQuant: pip install rqdatac")
    print("="*70)


if __name__ == "__main__":
    run_demo()
