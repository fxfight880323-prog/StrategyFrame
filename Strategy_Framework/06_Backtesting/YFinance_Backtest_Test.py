#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Yahoo Finance 数据回测测试 (带重试机制)
========================================

测试使用YFinance获取数据并进行简单回测
包含频率限制处理和重试机制
"""

import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
import logging
import time

# 使用yfinance
try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False
    print("请先安装yfinance: pip install yfinance")
    sys.exit(1)


# 日志设置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger("yfinance_test")


class YFinanceDataProvider:
    """Yahoo Finance 数据提供器 (带重试)"""
    
    def __init__(self):
        self.cache = {}
        self.last_request_time = 0
        self.min_request_interval = 2  # 最小请求间隔2秒
    
    def _rate_limit(self):
        """频率限制"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            sleep_time = self.min_request_interval - elapsed
            logger.debug(f"等待 {sleep_time:.1f}秒...")
            time.sleep(sleep_time)
        self.last_request_time = time.time()
    
    def get_stock_data(self, symbol: str, period: str = "1y", interval: str = "1d", 
                      max_retries: int = 3) -> pd.DataFrame:
        """
        获取股票数据 (带重试)
        
        Args:
            symbol: 股票代码
            period: 时间周期
            interval: 数据间隔
            max_retries: 最大重试次数
        
        Returns:
            DataFrame with OHLCV data
        """
        cache_key = f"{symbol}_{period}_{interval}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        for attempt in range(max_retries):
            try:
                # 频率限制
                self._rate_limit()
                
                logger.info(f"正在获取 {symbol} 数据... (尝试 {attempt + 1}/{max_retries})")
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=period, interval=interval)
                
                if df.empty:
                    logger.warning(f"  {symbol}: 无数据返回")
                    return pd.DataFrame()
                
                # 标准化列名
                df = df.reset_index()
                
                # 处理日期列
                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date'])
                elif 'Datetime' in df.columns:
                    df = df.rename(columns={'Datetime': 'Date'})
                    df['Date'] = pd.to_datetime(df['Date'])
                
                # 标准化列名
                column_map = {
                    'Open': 'Open',
                    'High': 'High',
                    'Low': 'Low',
                    'Close': 'Close',
                    'Volume': 'Volume',
                }
                df = df.rename(columns=column_map)
                
                # 按日期排序
                df = df.sort_values('Date').reset_index(drop=True)
                
                self.cache[cache_key] = df
                logger.info(f"  成功: {len(df)} 条记录 ({df['Date'].min().date()} ~ {df['Date'].max().date()})")
                return df
                
            except Exception as e:
                error_msg = str(e)
                if "Rate limited" in error_msg or "Too Many Requests" in error_msg:
                    wait_time = 5 * (attempt + 1)  # 递增等待
                    logger.warning(f"  频率限制，等待 {wait_time}秒后重试...")
                    time.sleep(wait_time)
                else:
                    logger.error(f"  获取失败: {error_msg}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
        
        logger.error(f"  最终失败: {symbol}")
        return pd.DataFrame()
    
    def get_multiple_stocks(self, symbols: list, period: str = "1y") -> dict:
        """批量获取多只股票数据"""
        results = {}
        for symbol in symbols:
            df = self.get_stock_data(symbol, period)
            if not df.empty:
                results[symbol] = df
        return results


class SimpleCTABacktest:
    """简单CTA策略回测 (20/60日均线)"""
    
    def __init__(self, initial_capital: float = 100000):
        self.initial_capital = initial_capital
        self.data_provider = YFinanceDataProvider()
    
    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算CTA信号"""
        df = df.copy()
        
        # 计算均线
        df['MA_20'] = df['Close'].rolling(20).mean()
        df['MA_60'] = df['Close'].rolling(60).mean()
        
        # 计算收益率
        df['Returns'] = df['Close'].pct_change()
        
        # 生成信号 (1=多头, -1=空头)
        df['Signal'] = np.where(df['MA_20'] > df['MA_60'], 1, -1)
        
        # 策略收益 (信号滞后一期)
        df['Strategy_Returns'] = df['Signal'].shift(1) * df['Returns']
        
        # 累计收益
        df['Cumulative_Market'] = (1 + df['Returns'].fillna(0)).cumprod()
        df['Cumulative_Strategy'] = (1 + df['Strategy_Returns'].fillna(0)).cumprod()
        
        return df
    
    def run_backtest(self, symbol: str, period: str = "2y") -> dict:
        """执行回测"""
        logger.info(f"\n{'='*60}")
        logger.info(f"回测: {symbol}")
        logger.info(f"{'='*60}")
        
        # 获取数据
        df = self.data_provider.get_stock_data(symbol, period)
        if df.empty or len(df) < 60:
            logger.error("数据不足，无法回测")
            return None
        
        # 计算信号
        df = self.calculate_signals(df)
        
        # 计算绩效指标
        final_market = df['Cumulative_Market'].iloc[-1] - 1
        final_strategy = df['Cumulative_Strategy'].iloc[-1] - 1
        
        # 年化收益
        days = (df['Date'].iloc[-1] - df['Date'].iloc[0]).days
        years = days / 365.25
        
        annual_market = (1 + final_market) ** (1/years) - 1 if years > 0 else 0
        annual_strategy = (1 + final_strategy) ** (1/years) - 1 if years > 0 else 0
        
        # 波动率
        volatility = df['Strategy_Returns'].std() * np.sqrt(252)
        
        # 最大回撤
        cummax = df['Cumulative_Strategy'].cummax()
        drawdown = (df['Cumulative_Strategy'] - cummax) / cummax
        max_drawdown = drawdown.min()
        
        # 夏普比率
        sharpe = annual_strategy / volatility if volatility > 0 else 0
        
        # 交易次数 (信号变化次数)
        trades = df['Signal'].diff().abs().sum() / 2
        
        result = {
            'symbol': symbol,
            'data_points': len(df),
            'start_date': df['Date'].min().date(),
            'end_date': df['Date'].max().date(),
            'market_return': final_market,
            'strategy_return': final_strategy,
            'excess_return': final_strategy - final_market,
            'annual_market_return': annual_market,
            'annual_strategy_return': annual_strategy,
            'volatility': volatility,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe,
            'trades': int(trades),
            'data': df
        }
        
        return result
    
    def print_report(self, result: dict):
        """打印回测报告"""
        if not result:
            return
        
        print("\n" + "="*60)
        print("回测结果报告")
        print("="*60)
        print(f"标的: {result['symbol']}")
        print(f"数据区间: {result['start_date']} ~ {result['end_date']}")
        print(f"数据点数: {result['data_points']} 天")
        print(f"交易次数: {result['trades']}")
        print()
        print("收益表现:")
        print(f"  买入持有收益: {result['market_return']*100:+.2f}%")
        print(f"  策略收益:     {result['strategy_return']*100:+.2f}%")
        print(f"  超额收益:     {result['excess_return']*100:+.2f}%")
        print()
        print("年化表现:")
        print(f"  买入持有年化: {result['annual_market_return']*100:+.2f}%")
        print(f"  策略年化:     {result['annual_strategy_return']*100:+.2f}%")
        print()
        print("风险指标:")
        print(f"  波动率:       {result['volatility']*100:.2f}%")
        print(f"  最大回撤:     {result['max_drawdown']*100:.2f}%")
        print(f"  夏普比率:     {result['sharpe_ratio']:.2f}")
        print("="*60)


def test_single_stock():
    """测试单只股票数据获取"""
    print("="*60)
    print("Yahoo Finance 单只股票数据测试")
    print("="*60)
    print()
    
    provider = YFinanceDataProvider()
    
    # 测试SPY
    symbol = "SPY"
    df = provider.get_stock_data(symbol, period="3mo")
    
    if not df.empty:
        print(f"\n✓ 数据获取成功: {symbol}")
        print(f"  数据条数: {len(df)}")
        print(f"  日期范围: {df['Date'].min().date()} ~ {df['Date'].max().date()}")
        print(f"  最新价格: ${df['Close'].iloc[-1]:.2f}")
        print(f"\n最近5日数据:")
        print(df.tail(5)[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].to_string(index=False))
        return True
    else:
        print(f"\n✗ 数据获取失败: {symbol}")
        return False


def run_backtest_demo():
    """运行回测演示"""
    print("\n" + "="*60)
    print("CTA策略回测演示")
    print("="*60)
    print("策略: 20/60日均线交叉")
    print("规则: MA20上穿MA60买入，下穿卖出")
    print()
    
    backtest = SimpleCTABacktest(initial_capital=100000)
    
    # 测试几只股票
    symbols = ['SPY', 'QQQ', 'AAPL']
    all_results = []
    
    for symbol in symbols:
        result = backtest.run_backtest(symbol, period="2y")
        if result:
            backtest.print_report(result)
            all_results.append(result)
        print()
    
    # 汇总
    if all_results:
        print("\n" + "="*60)
        print("回测汇总对比")
        print("="*60)
        print(f"{'标的':<10} {'策略收益':>12} {'买入持有':>12} {'超额收益':>12} {'夏普比率':>10} {'交易次数':>10}")
        print("-"*60)
        for r in all_results:
            print(f"{r['symbol']:<10} {r['strategy_return']*100:>11.2f}% {r['market_return']*100:>11.2f}% {r['excess_return']*100:>11.2f}% {r['sharpe_ratio']:>10.2f} {r['trades']:>10}")
        print("="*60)


def main():
    """主函数"""
    print("="*60)
    print("Yahoo Finance 数据回测测试")
    print("="*60)
    print()
    print("注意: Yahoo Finance有频率限制，已添加2秒请求间隔")
    print()
    
    # 1. 单只股票测试
    success = test_single_stock()
    
    if success:
        # 2. 回测演示
        run_backtest_demo()
    else:
        print("\n数据获取失败，跳过回测演示")
        print("建议:")
        print("  1. 检查网络连接")
        print("  2. 等待几分钟后重试")
        print("  3. 考虑使用其他数据源 (如AKShare)")
    
    print("\n" + "="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    main()
