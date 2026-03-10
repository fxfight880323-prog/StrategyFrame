"""
调试优化版回测
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import rqdatac as rq
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

rq.init('+8613810062394', 'Fox880323!')

print('=== 调试回测流程 ===')

# 单个月回测
dates = pd.date_range(start='2023-10-01', end='2023-12-01', freq='ME')
print(f'调仓日期: {dates}')

for i in range(1, len(dates)):
    curr_date = dates[i].strftime('%Y-%m-%d')
    prev_date = dates[i-1].strftime('%Y-%m-%d')
    
    print(f'\n--- 回测月份: {prev_date} -> {curr_date} ---')
    
    # 1. 获取股票池
    stocks = rq.index_components('000300.XSHG', prev_date)
    print(f'股票池: {len(stocks)}只')
    
    # 2. 计算价值信号
    pe_df = rq.get_factor(list(stocks)[:50], 'pe_ratio', prev_date, prev_date)
    value_sig = pd.Series(dtype=float)
    if pe_df is not None and not pe_df.empty:
        ep = 1 / pe_df['pe_ratio'].replace([np.inf, -np.inf], np.nan)
        ep = ep.dropna()
        if len(ep) > 10 and ep.std() > 0:
            ep = (ep - ep.mean()) / ep.std()
            value_sig = ep
            print(f'价值信号: {len(value_sig)}只, mean={value_sig.mean():.4f}')
    
    # 3. 计算动量信号
    start_dt = pd.to_datetime(prev_date) - timedelta(days=12*30)
    prices = rq.get_price(list(stocks)[:50], start_dt.strftime('%Y-%m-%d'), prev_date, frequency='1d', fields=['close'])
    mom_sig = pd.Series(dtype=float)
    if prices is not None and not prices.empty:
        for stock in list(stocks)[:50]:
            try:
                if 'close' in prices.columns and stock in prices['close'].columns:
                    p = prices['close'][stock].dropna()
                    if len(p) >= 2:
                        mom_sig[stock] = (p.iloc[-1] / p.iloc[0]) - 1
            except:
                pass
        if len(mom_sig) > 10 and mom_sig.std() > 0:
            mom_sig = mom_sig.clip(mom_sig.quantile(0.05), mom_sig.quantile(0.95))
            mom_sig = (mom_sig - mom_sig.mean()) / mom_sig.std()
            print(f'动量信号: {len(mom_sig)}只, mean={mom_sig.mean():.4f}')
    
    # 4. 复合信号
    composite = pd.Series(0, index=list(stocks)[:50], dtype=float)
    total_weight = 0
    
    if not value_sig.empty:
        for idx, val in value_sig.items():
            stock = idx[0] if isinstance(idx, tuple) else idx
            if stock in composite.index:
                composite[stock] += val * 0.5
        total_weight += 0.5
    
    if not mom_sig.empty:
        for idx, val in mom_sig.items():
            if idx in composite.index:
                composite[idx] += val * 0.5
        total_weight += 0.5
    
    print(f'total_weight={total_weight}')
    if total_weight > 0:
        composite = composite[composite != 0]
        composite = composite / total_weight
        print(f'复合信号: {len(composite)}只')
    
    # 5. 多空组合
    if len(composite) >= 20:
        sorted_sig = composite.sort_values(ascending=False)
        longs = list(sorted_sig.head(10).index)
        shorts = list(sorted_sig.tail(10).index)
        print(f'多头: {len(longs)}只, 空头: {len(shorts)}只')
        print(f'多头前3: {longs[:3]}')
        print(f'空头前3: {shorts[:3]}')
        
        # 6. 计算收益
        all_stocks = list(set(longs + shorts))
        prices_next = rq.get_price(all_stocks, prev_date, curr_date, frequency='1d', fields=['close'])
        if prices_next is not None and not prices_next.empty:
            if 'close' in prices_next.columns:
                close_prices = prices_next['close']
                print(f'价格数据形状: {close_prices.shape}')
                
                # 计算收益
                first = close_prices.iloc[0]
                last = close_prices.iloc[-1]
                stock_returns = (last / first - 1).fillna(0)
                print(f'个股收益数量: {len(stock_returns)}')
                
                long_rets = [stock_returns[s] for s in longs if s in stock_returns.index]
                short_rets = [stock_returns[s] for s in shorts if s in stock_returns.index]
                
                long_mean = np.mean(long_rets) if long_rets else 0
                short_mean = np.mean(short_rets) if short_rets else 0
                portfolio_ret = long_mean - short_mean
                
                print(f'多头收益: {long_mean:.4f}')
                print(f'空头收益: {short_mean:.4f}')
                print(f'组合收益: {portfolio_ret:.4f}')
            else:
                print('价格数据没有close列')
        else:
            print('未获取到价格数据')
    else:
        print(f'信号数量不足: {len(composite)}')

print('\n=== 调试结束 ===')
