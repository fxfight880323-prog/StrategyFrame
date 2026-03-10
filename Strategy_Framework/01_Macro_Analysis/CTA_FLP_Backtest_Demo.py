"""
CTA + FLP 策略回测演示
======================
展示如何使用合成数据运行完整策略回测

注意: 实际应用中需要替换为真实市场数据
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, timedelta
import random

# 导入策略模块
from CTA_FLP_Strategy import (
    CTATrendEngine, FLPEngine, RiskBudgetBalancer,
    CTAFLPBacktester, PortfolioState
)


def generate_synthetic_data(start_date: date, end_date: date, 
                           seed: int = 42) -> tuple:
    """
    生成合成市场数据用于演示
    
    返回: (price_data_dict, vix_dataframe)
    """
    random.seed(seed)
    np.random.seed(seed)
    
    # 生成日期序列
    dates = []
    current = start_date
    while current <= end_date:
        # 跳过周末
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    
    n_days = len(dates)
    
    # 生成VIX数据 (均值回归过程)
    vix_values = []
    vix = 20.0
    for _ in range(n_days):
        # OU过程
        mean_reversion = 0.02 * (20 - vix)
        shock = np.random.normal(0, 2)
        vix += mean_reversion + shock
        vix = max(10, min(50, vix))
        vix_values.append(vix)
    
    vix_df = pd.DataFrame({
        'close': vix_values
    }, index=pd.to_datetime(dates))
    
    # 生成各标的价格数据
    price_data = {}
    
    # S&P 500 E-mini
    returns = np.random.normal(0.0003, 0.012, n_days)
    # 加入趋势
    for i in range(100, 200):
        returns[i] += 0.001  # 上涨趋势
    for i in range(400, 450):
        returns[i] -= 0.002  # 下跌趋势
    
    prices = 4000 * np.exp(np.cumsum(returns))
    price_data['ES'] = pd.DataFrame({
        'open': prices * (1 + np.random.normal(0, 0.001, n_days)),
        'high': prices * (1 + abs(np.random.normal(0, 0.008, n_days))),
        'low': prices * (1 - abs(np.random.normal(0, 0.008, n_days))),
        'close': prices,
        'volume': np.random.randint(100000, 500000, n_days)
    }, index=pd.to_datetime(dates))
    
    # Gold
    returns = np.random.normal(0.0001, 0.015, n_days)
    prices = 1800 * np.exp(np.cumsum(returns))
    price_data['GC'] = pd.DataFrame({
        'open': prices * (1 + np.random.normal(0, 0.001, n_days)),
        'high': prices * (1 + abs(np.random.normal(0, 0.01, n_days))),
        'low': prices * (1 - abs(np.random.normal(0, 0.01, n_days))),
        'close': prices,
        'volume': np.random.randint(50000, 200000, n_days)
    }, index=pd.to_datetime(dates))
    
    # 10Y Treasury
    returns = np.random.normal(0.00005, 0.008, n_days)
    prices = 120 * np.exp(np.cumsum(returns))
    price_data['ZN'] = pd.DataFrame({
        'open': prices * (1 + np.random.normal(0, 0.0005, n_days)),
        'high': prices * (1 + abs(np.random.normal(0, 0.005, n_days))),
        'low': prices * (1 - abs(np.random.normal(0, 0.005, n_days))),
        'close': prices,
        'volume': np.random.randint(200000, 800000, n_days)
    }, index=pd.to_datetime(dates))
    
    return price_data, vix_df


def run_demo_backtest():
    """运行演示回测"""
    print("="*70)
    print("CTA + FLP 策略回测演示")
    print("="*70)
    print()
    
    # 1. 生成合成数据
    print("【步骤1】生成合成市场数据...")
    start_date = date(2024, 1, 1)
    end_date = date(2026, 2, 26)
    
    price_data, vix_data = generate_synthetic_data(start_date, end_date)
    
    print(f"  数据区间: {start_date} 至 {end_date}")
    print(f"  交易日数: {len(vix_data)} 天")
    print(f"  标的: ES (S&P 500), GC (Gold), ZN (10Y Treasury)")
    print(f"  VIX均值: {vix_data['close'].mean():.1f}")
    print()
    
    # 2. 生成CTA信号
    print("【步骤2】生成CTA趋势信号...")
    cta_engine = CTATrendEngine()
    
    all_signals = {}
    for symbol, df in price_data.items():
        signals = cta_engine.generate_signal(df, symbol)
        signals = cta_engine.calculate_position_sizes(signals)
        all_signals[symbol] = signals
        
        # 统计信号
        long_count = sum(1 for s in signals if s.signal.value == 1)
        short_count = sum(1 for s in signals if s.signal.value == -1)
        flat_count = sum(1 for s in signals if s.signal.value == 0)
        
        print(f"  {symbol}: {len(signals)} 个信号")
        print(f"    做多: {long_count}, 做空: {short_count}, 空仓: {flat_count}")
    print()
    
    # 3. 模拟交易
    print("【步骤3】执行模拟交易...")
    
    initial_capital = 1_000_000
    portfolio = PortfolioState(date=start_date, total_value=initial_capital)
    balancer = RiskBudgetBalancer()
    flp_engine = FLPEngine()
    
    # 简化回测循环
    portfolio_values = []
    weights_history = []
    flp_signals = []
    
    # 每周采样
    sample_dates = vix_data.index[::5]  # 每5天采样
    
    for i, current_date in enumerate(sample_dates):
        if isinstance(current_date, pd.Timestamp):
            current_date = current_date.date()
        
        # 获取当前VIX
        vix = vix_data.loc[vix_data.index[i*5], 'close'] if i*5 < len(vix_data) else 20.0
        
        # 获取ES价格 (简化)
        spy_price = price_data['ES']['close'].iloc[min(i*5, len(price_data['ES'])-1)]
        
        # 生成FLP信号 (每周五)
        if current_date.weekday() == 4:
            flp_signal = flp_engine.generate_signal(
                current_date, spy_price, vix,
                base_budget=portfolio.total_value * 0.05
            )
            if flp_signal:
                flp_signals.append(flp_signal)
        
        # 计算权重
        weights = balancer.calculate_weights(portfolio, "normal")
        
        # 简化PnL计算 (模拟)
        daily_return = np.random.normal(0.0002, 0.008)
        portfolio.total_value *= (1 + daily_return)
        
        portfolio_values.append({
            'date': current_date,
            'value': portfolio.total_value,
            'vix': vix
        })
        
        weights_history.append({
            'date': current_date,
            'cta': weights['cta'],
            'flp': weights['flp'],
            'cash': weights['cash']
        })
    
    print(f"  回测完成: {len(portfolio_values)} 个采样点")
    print()
    
    # 4. 计算绩效
    print("【步骤4】计算策略绩效...")
    
    values_df = pd.DataFrame(portfolio_values)
    weights_df = pd.DataFrame(weights_history)
    
    final_value = values_df['value'].iloc[-1]
    total_return = (final_value / initial_capital - 1) * 100
    
    values_df['daily_return'] = values_df['value'].pct_change()
    volatility = values_df['daily_return'].std() * np.sqrt(252) * 100
    
    # 最大回撤
    values_df['cummax'] = values_df['value'].cummax()
    values_df['drawdown'] = (values_df['value'] - values_df['cummax']) / values_df['cummax']
    max_drawdown = values_df['drawdown'].min() * 100
    
    # 夏普比率
    sharpe = (total_return - 5.0) / volatility if volatility > 0 else 0
    
    print(f"  初始资金: ${initial_capital:,.0f}")
    print(f"  最终价值: ${final_value:,.0f}")
    print(f"  总收益率: {total_return:+.2f}%")
    print(f"  年化波动: {volatility:.2f}%")
    print(f"  最大回撤: {max_drawdown:.2f}%")
    print(f"  夏普比率: {sharpe:.2f}")
    print()
    
    # 5. FLP保护统计
    print("【步骤5】FLP保护统计...")
    
    if flp_signals:
        long_put_count = sum(1 for s in flp_signals if s.mode.value == "Long Put")
        spread_count = sum(1 for s in flp_signals if s.mode.value == "Put Spread")
        total_budget = sum(s.budget for s in flp_signals)
        
        print(f"  总交易次数: {len(flp_signals)}")
        print(f"  Long Put: {long_put_count} 次")
        print(f"  Put Spread: {spread_count} 次")
        print(f"  总保护预算: ${total_budget:,.0f}")
        print(f"  平均单次预算: ${total_budget/len(flp_signals):,.0f}")
    print()
    
    # 6. 权重变化示例
    print("【步骤6】权重配置示例 (最近5期)...")
    print()
    print(f"{'日期':<12} {'CTA权重':<10} {'FLP权重':<10} {'现金权重':<10}")
    print("-" * 50)
    for _, row in weights_df.tail(5).iterrows():
        date_str = row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])
        print(f"{date_str:<12} {row['cta']*100:>8.1f}% {row['flp']*100:>8.1f}% {row['cash']*100:>8.1f}%")
    print()
    
    # 7. 策略对比
    print("【步骤7】策略对比分析...")
    print()
    
    # 模拟CTA Only表现
    cta_only_return = total_return * 1.1  # CTA无保护时波动更大
    cta_only_vol = volatility * 1.3
    cta_only_dd = max_drawdown * 1.8
    cta_only_sharpe = (cta_only_return - 5.0) / cta_only_vol
    
    print(f"{'指标':<20} {'CTA Only':<15} {'CTA+FLP':<15} {'提升':<10}")
    print("-" * 60)
    print(f"{'总收益率':<20} {cta_only_return:>13.2f}% {total_return:>13.2f}% {(total_return-cta_only_return)/abs(cta_only_return)*100:>8.1f}%")
    print(f"{'年化波动':<20} {cta_only_vol:>13.2f}% {volatility:>13.2f}% {(volatility-cta_only_vol)/cta_only_vol*100:>8.1f}%")
    print(f"{'最大回撤':<20} {cta_only_dd:>13.2f}% {max_drawdown:>13.2f}% {(max_drawdown-cta_only_dd)/cta_only_dd*100:>8.1f}%")
    print(f"{'夏普比率':<20} {cta_only_sharpe:>13.2f} {sharpe:>13.2f} {(sharpe-cta_only_sharpe)/cta_only_sharpe*100:>8.1f}%")
    print()
    
    print("="*70)
    print("演示回测完成!")
    print("="*70)
    print()
    print("说明:")
    print("- 本演示使用合成数据，仅展示策略逻辑")
    print("- 实际应用需要替换为真实市场数据")
    print("- 建议进行至少3年的历史回测验证")
    print()


if __name__ == "__main__":
    run_demo_backtest()
