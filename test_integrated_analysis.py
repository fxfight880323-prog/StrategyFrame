"""
测试综合分析模块 - 使用模拟数据
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime

# 生成模拟CTA数据
def create_mock_cta_data():
    """创建模拟CTA分析数据"""
    tickers = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'TSLA', 'AMD', 
               'JPM', 'V', 'JNJ', 'UNH', 'XOM', 'CVX', 'WMT', 'PG',
               'TSM', 'ASML', 'AVGO', 'CRM', 'NFLX']
    
    data = []
    for i, ticker in enumerate(tickers):
        score = np.random.normal(60, 15)
        score = max(20, min(95, score))  # 限制在20-95
        
        if score >= 70:
            signal = 'BUY'
        elif score >= 40:
            signal = 'HOLD'
        else:
            signal = 'SELL'
        
        data.append({
            'Ticker': ticker,
            '总评分': score,
            '信号': signal,
            '趋势': 'Up' if score > 60 else ('Down' if score < 40 else 'Neutral'),
            '排名': i + 1,
            'RSI': np.random.uniform(30, 80),
            'MACD': np.random.uniform(-2, 2),
        })
    
    df = pd.DataFrame(data)
    df = df.sort_values('总评分', ascending=False).reset_index(drop=True)
    df['排名'] = range(1, len(df) + 1)
    return df

# 生成模拟财报数据
def create_mock_earnings_data():
    """创建模拟财报预期数据"""
    tickers = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'META', 'TSLA', 'AMD', 
               'JPM', 'V', 'JNJ', 'UNH', 'XOM', 'CVX', 'WMT', 'PG',
               'TSM', 'ASML', 'AVGO', 'CRM', 'NFLX']
    
    expectations = ['High', 'Low', 'Reasonable', 'Unknown']
    weights = [0.2, 0.3, 0.4, 0.1]  # 合理的分布
    
    data = []
    for ticker in tickers:
        exp = np.random.choice(expectations, p=weights)
        
        data.append({
            'Ticker': ticker,
            '预期判断': exp,
            '平均EPS惊喜': np.random.uniform(-0.1, 0.25),
            '平均价格反应': np.random.uniform(-5, 8),
            '一致性评分': np.random.uniform(0.3, 0.9),
            '下次财报日期': '2026-03-15',
            '超预期次数': np.random.randint(1, 8),
            '低于预期次数': np.random.randint(0, 4),
        })
    
    return pd.DataFrame(data)

# 保存模拟数据
cta_df = create_mock_cta_data()
earnings_df = create_mock_earnings_data()

# 使用CSV格式避免Excel依赖问题
cta_df.to_csv('mag7_cta_analysis.csv', index=False)
earnings_df.to_csv('us_stocks_earnings_expectation.csv', index=False)

print("模拟数据已生成:")
print(f"  CTA数据: {len(cta_df)} 只股票")
print(f"  财报数据: {len(earnings_df)} 只股票")
print("\nCTA排名前5:")
print(cta_df.head()[['Ticker', '总评分', '信号', '排名']])
print("\n财报预期分布:")
print(earnings_df['预期判断'].value_counts())
