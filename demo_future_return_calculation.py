"""
未来收益计算正确做法演示
========================
展示如何正确计算信号发出后的持有期收益，确保无未来数据泄露
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def generate_sample_data():
    """生成示例数据"""
    # 生成30天的价格数据
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    prices = 100 + np.cumsum(np.random.randn(30) * 2)
    
    price_df = pd.DataFrame({
        'Date': dates,
        'Close': prices
    })
    
    # 模拟信号 (第10天和第20天发出买入信号)
    signals = [
        {'Date': dates[10], 'Ticker': 'AAPL', 'Signal': 'BUY', 'Price': prices[10]},
        {'Date': dates[20], 'Ticker': 'AAPL', 'Signal': 'BUY', 'Price': prices[20]},
    ]
    
    return price_df, signals


def calculate_future_return_correct(signal_date, entry_price, prices_df, holding_days=5):
    """
    正确计算未来持有收益
    
    Args:
        signal_date: 信号日期
        entry_price: 入场价格 (信号当日价格)
        prices_df: 完整价格数据
        holding_days: 持有天数
    
    Returns:
        dict: 包含收益计算结果
    """
    # 1. 获取信号日期之后的所有交易日
    future_data = prices_df[prices_df['Date'] > signal_date].copy()
    
    if len(future_data) < holding_days:
        return {
            'error': f'数据不足，需要{holding_days}天，只有{len(future_data)}天',
            'available_days': len(future_data)
        }
    
    # 2. 获取持有期结束日的数据
    exit_row = future_data.iloc[holding_days - 1]
    exit_date = exit_row['Date']
    exit_price = exit_row['Close']
    
    # 3. 计算收益
    absolute_return = exit_price - entry_price
    percentage_return = (exit_price / entry_price - 1) * 100
    
    return {
        'entry_date': signal_date,
        'entry_price': entry_price,
        'exit_date': exit_date,
        'exit_price': exit_price,
        'holding_days': holding_days,
        'absolute_return': absolute_return,
        'percentage_return': percentage_return,
        'annualized_return': percentage_return * (365 / holding_days)
    }


def demonstrate_correct_calculation():
    """演示正确的未来收益计算"""
    print("=" * 70)
    print("未来收益计算正确做法演示")
    print("=" * 70)
    print("\n核心原则:")
    print("1. 入场价格 = 信号日期的价格 (已知)")
    print("2. 出场价格 = 信号日期后第N天的价格 (未来数据，用于验证)")
    print("3. 收益计算 = (出场 - 入场) / 入场")
    print()
    
    # 生成示例数据
    price_df, signals = generate_sample_data()
    
    print("-" * 70)
    print("示例价格数据 (前10行):")
    print("-" * 70)
    print(price_df.head(10).to_string(index=False))
    print()
    
    print("-" * 70)
    print("信号数据:")
    print("-" * 70)
    for s in signals:
        print(f"日期: {s['Date'].strftime('%Y-%m-%d')}, "
              f"信号: {s['Signal']}, "
              f"价格: ${s['Price']:.2f}")
    print()
    
    print("-" * 70)
    print("未来收益计算 (持有5天):")
    print("-" * 70)
    
    for signal in signals:
        result = calculate_future_return_correct(
            signal_date=signal['Date'],
            entry_price=signal['Price'],
            prices_df=price_df,
            holding_days=5
        )
        
        if 'error' in result:
            print(f"\n信号日期: {signal['Date'].strftime('%Y-%m-%d')}")
            print(f"  错误: {result['error']}")
        else:
            print(f"\n信号日期: {result['entry_date'].strftime('%Y-%m-%d')}")
            print(f"  入场价格: ${result['entry_price']:.2f}")
            print(f"  出场日期: {result['exit_date'].strftime('%Y-%m-%d')}")
            print(f"  出场价格: ${result['exit_price']:.2f}")
            print(f"  持有天数: {result['holding_days']}")
            print(f"  绝对收益: ${result['absolute_return']:.2f}")
            print(f"  百分比收益: {result['percentage_return']:+.2f}%")
            print(f"  年化收益: {result['annualized_return']:+.2f}%")
    
    print()
    print("=" * 70)
    print("关键验证点:")
    print("=" * 70)
    print("✓ 入场价格使用信号日期的价格")
    print("✓ 出场价格使用信号日期之后的价格")
    print("✓ 收益计算基于真实的时间序列")
    print("✓ 无未来数据泄露")
    print()


def demonstrate_incorrect_calculation():
    """演示错误的未来收益计算 (存在未来数据泄露)"""
    print("=" * 70)
    print("错误做法: 使用未来数据生成信号")
    print("=" * 70)
    print()
    
    # 生成价格数据
    dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
    prices = 100 + np.cumsum(np.random.randn(30) * 2)
    
    df = pd.DataFrame({
        'Date': dates,
        'Price': prices
    })
    
    # 错误做法: 使用未来5天的收益来生成信号
    df['Future_Return_5D'] = df['Price'].shift(-5) / df['Price'] - 1
    df['Signal'] = np.where(df['Future_Return_5D'] > 0.02, 'BUY', 'HOLD')
    
    print("错误代码:")
    print("-" * 70)
    print("df['Future_Return_5D'] = df['Price'].shift(-5) / df['Price'] - 1")
    print("df['Signal'] = np.where(df['Future_Return_5D'] > 0.02, 'BUY', 'HOLD')")
    print()
    
    print("问题:")
    print("-" * 70)
    print("• shift(-5) 获取的是未来5天的价格")
    print("• 使用未来数据生成信号")
    print("• 回测结果会异常好 (100%准确)")
    print("• 实际交易中无法复制")
    print()
    
    # 显示结果
    result = df[['Date', 'Price', 'Future_Return_5D', 'Signal']].head(10)
    print("结果 (注意最后5行的Future_Return是NaN):")
    print("-" * 70)
    print(result.to_string(index=False))
    print()
    
    print("⚠  这种做法在回测中会得到虚假的高收益，但实盘会失败！")
    print()


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("CTA回测时间序列正确性演示")
    print("=" * 70)
    print()
    
    # 演示正确的做法
    demonstrate_correct_calculation()
    
    # 演示错误的做法
    demonstrate_incorrect_calculation()
    
    print("=" * 70)
    print("总结")
    print("=" * 70)
    print()
    print("正确的未来收益计算:")
    print("  1. 信号生成只使用历史数据")
    print("  2. 入场价格 = 信号日期价格")
    print("  3. 出场价格 = 信号后第N天价格")
    print("  4. 收益计算基于真实时间序列")
    print()
    print("错误的未来收益计算:")
    print("  1. 使用未来数据生成信号 (shift(-N))")
    print("  2. 回测结果不可复制")
    print("  3. 产生虚假的超高收益")
    print()
    print("=" * 70)
