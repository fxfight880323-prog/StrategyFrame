"""
详细调试回测流程 - 单步检查
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import rqdatac as rq
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

rq.init('+8613810062394', 'Fox880323!')

print('=== 调试回测流程 - 单步检查 ===\n')

# 模拟一个月的回测
date = '2023-11-01'
prev_date = '2023-10-31'

# 1. 获取股票池
print('1. 获取股票池...')
stocks = rq.index_components('000300.XSHG', prev_date)
print(f'   获取到 {len(stocks)} 只股票')
stocks_list = list(stocks)[:100]  # 取前100只加快测试
print(f'   使用前100只')

# 2. 获取因子数据
print('\n2. 获取PE因子数据...')
factor_df = rq.get_factor(stocks_list, 'pe_ratio', prev_date, prev_date)
print(f'   因子数据形状: {factor_df.shape}')
print(f'   列: {factor_df.columns.tolist()}')
print(f'   前3行:\n{factor_df.head(3)}')

# 3. 计算信号
print('\n3. 计算EP信号 (1/PE)...')
pe_ratio = factor_df['pe_ratio']
print(f'   PE数据类型: {type(pe_ratio)}')
print(f'   PE索引: {pe_ratio.index[:3]}')

# 计算EP
ep = 1 / pe_ratio
ep = ep.dropna()
print(f'   EP有效数量: {len(ep)}')
print(f'   EP前5个:\n{ep.head()}')

# 4. 标准化
print('\n4. 标准化信号...')
if len(ep) > 10:
    ep = ep.clip(ep.quantile(0.05), ep.quantile(0.95))
    if ep.std() > 0:
        ep = (ep - ep.mean()) / ep.std()
print(f'   标准化后EP前5个:\n{ep.head()}')

# 5. 构建多空组合
print('\n5. 构建多空组合...')
sorted_ep = ep.sort_values(ascending=False)
print(f'   排序后前5个:\n{sorted_ep.head()}')
print(f'   排序后后5个:\n{sorted_ep.tail()}')

# 提取股票代码
def get_code(idx):
    if isinstance(idx, tuple):
        return idx[0]
    return idx

longs = [get_code(idx) for idx in sorted_ep.head(10).index]
shorts = [get_code(idx) for idx in sorted_ep.tail(10).index]
print(f'   多头10只: {longs}')
print(f'   空头10只: {shorts}')

# 6. 获取价格数据
print('\n6. 获取价格数据...')
all_stocks = list(set(longs + shorts))
print(f'   需要获取价格的股票数: {len(all_stocks)}')

start = prev_date
end = date
prices = rq.get_price(all_stocks, start, end, frequency='1d', fields=['close'])
print(f'   价格数据类型: {type(prices)}')
print(f'   价格数据形状: {prices.shape}')

if isinstance(prices, pd.DataFrame):
    print(f'   列: {prices.columns.tolist()}')
    if 'close' in prices.columns:
        close = prices['close']
        print(f'   close数据类型: {type(close)}')
        print(f'   close形状: {close.shape}')
        print(f'   close索引: {close.index[:3]}')
        
        # 7. 计算收益
        print('\n7. 计算收益...')
        if len(close) >= 2:
            first = close.iloc[0]
            last = close.iloc[-1]
            print(f'   首日价格:\n{first}')
            print(f'   末日价格:\n{last}')
            
            returns = (last / first - 1)
            print(f'   个股收益:\n{returns}')
            
            # 8. 计算组合收益
            print('\n8. 计算组合收益...')
            long_rets = returns[longs]
            short_rets = returns[shorts]
            print(f'   多头收益:\n{long_rets}')
            print(f'   空头收益:\n{short_rets}')
            
            long_mean = long_rets.mean()
            short_mean = short_rets.mean()
            portfolio_ret = long_mean - short_mean
            
            print(f'\n   多头平均收益: {long_mean:.4f}')
            print(f'   空头平均收益: {short_mean:.4f}')
            print(f'   多空组合收益: {portfolio_ret:.4f}')

print('\n=== 调试结束 ===')
