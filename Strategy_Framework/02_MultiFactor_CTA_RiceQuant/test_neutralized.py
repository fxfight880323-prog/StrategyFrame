"""
测试行业中性化回测（完整3个月）
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import rqdatac as rq

rq.init('+8613810062394', 'Fox880323!')

print('\n=== 手动完整回测（3个月）===\n')

dates = pd.date_range(start='2023-01-01', end='2023-04-01', freq='ME')
date_list = [d.strftime('%Y-%m-%d') for d in dates]
print(f'回测日期: {date_list}')

portfolio = 1.0
monthly_returns = []

for i in range(1, len(dates)):
    curr_date = dates[i].strftime('%Y-%m-%d')
    prev_date = dates[i-1].strftime('%Y-%m-%d')
    
    print(f'\n--- 第{i}期: {prev_date} -> {curr_date} ---')
    
    # 获取股票池
    stocks = rq.index_components('000300.XSHG', prev_date)
    print(f'  股票池: {len(stocks)}只')
    
    # 计算因子信号
    date_obj = datetime.strptime(prev_date, '%Y-%m-%d') - timedelta(days=1)
    trade_date = rq.get_previous_trading_date(date_obj).strftime('%Y-%m-%d')
    
    df = rq.get_factor(stocks, 'ps_ratio', trade_date, trade_date)
    values = 1 / df['ps_ratio'].replace([np.inf, -np.inf], np.nan)
    values = values.dropna()
    if values.index.nlevels > 1:
        values.index = values.index.get_level_values(0)
    
    values = values.clip(values.quantile(0.05), values.quantile(0.95))
    if values.std() > 0:
        values = (values - values.mean()) / values.std()
    
    # 排序选股票
    sorted_vals = values.sort_values(ascending=False)
    longs = list(sorted_vals.head(20).index)
    shorts = list(sorted_vals.tail(20).index)
    
    # 计算收益
    all_stocks = list(set(longs + shorts))
    prices = rq.get_price(all_stocks, prev_date, curr_date, frequency='1d', fields=['close'])
    
    if prices.empty:
        print(f'  价格数据为空！')
        ret = 0
    else:
        close = prices['close']
        prices_df = close.unstack(level=0)
        
        first_prices = prices_df.iloc[0]
        last_prices = prices_df.iloc[-1]
        stock_returns = (last_prices / first_prices - 1).fillna(0)
        
        long_rets = [stock_returns[s] for s in longs if s in stock_returns.index]
        short_rets = [stock_returns[s] for s in shorts if s in stock_returns.index]
        
        long_mean = np.mean(long_rets) if long_rets else 0
        short_mean = np.mean(short_rets) if short_rets else 0
        ret = long_mean - short_mean
    
    portfolio *= (1 + ret)
    monthly_returns.append(ret)
    
    print(f'  多头收益: {long_mean:.4f}, 空头收益: {short_mean:.4f}, 多空收益: {ret:.4f}')
    print(f'  累计净值: {portfolio:.4f}')

# 计算统计指标
print(f'\n=== 回测结果 ===')
print(f'总收益: {(portfolio - 1)*100:.2f}%')
print(f'月收益: {monthly_returns}')

if monthly_returns:
    rets = pd.Series(monthly_returns)
    ann_ret = (portfolio ** (12/len(rets))) - 1 if portfolio > 0 else -1
    vol = rets.std() * np.sqrt(12)
    ir = ann_ret / vol if vol > 0 else 0
    win_rate = (rets > 0).sum() / len(rets)
    
    print(f'年化收益: {ann_ret*100:.2f}%')
    print(f'年化波动: {vol*100:.2f}%')
    print(f'信息比率: {ir:.2f}')
    print(f'胜率: {win_rate*100:.1f}%')

