"""
调试回测流程
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import rqdatac as rq
import pandas as pd
from datetime import datetime, timedelta

rq.init('+8613810062394', 'Fox880323!')

print('=== 调试回测流程 ===')

# 1. 获取股票池
date = '2023-11-01'
stocks = rq.index_components('000300.XSHG', date)
print(f'1. 股票池: {len(stocks)}只')
print(f'   前5只: {list(stocks)[:5]}')

# 2. 获取因子数据
prev_date = '2023-10-31'
stocks_list = list(stocks)[:50]
factor_df = rq.get_factor(stocks_list, 'pe_ratio', prev_date, prev_date)
print(f'\n2. PE因子数据:')
print(f'   类型: {type(factor_df)}')
print(f'   空值: {factor_df is None}')

if factor_df is not None:
    print(f'   形状: {factor_df.shape}')
    print(f'   前5行:\n{factor_df.head()}')
    
    # 计算EP信号
    signals = 1 / factor_df['pe_ratio']
    signals = signals.dropna()
    print(f'\n3. EP信号 (1/PE):')
    print(f'   有效数量: {len(signals)}')
    print(f'   前5个:\n{signals.head()}')
    
    # 排序和选择
    sorted_sig = signals.sort_values(ascending=False)
    longs = sorted_sig.head(10)
    shorts = sorted_sig.tail(10)
    print(f'\n4. 多空组合:')
    print(f'   多头10只: {list(longs.index)}')
    print(f'   空头10只: {list(shorts.index)}')
    
    # 5. 获取价格数据
    start = '2023-11-01'
    end = '2023-12-01'
    test_stocks = list(longs.index) + list(shorts.index)
    prices = rq.get_price(test_stocks, start, end, frequency='1d', fields=['close'])
    print(f'\n5. 价格数据:')
    print(f'   类型: {type(prices)}')
    
    if isinstance(prices, pd.DataFrame):
        print(f'   形状: {prices.shape}')
        print(f'   列: {prices.columns.tolist()}')
        
        if 'close' in prices.columns:
            close_prices = prices['close']
            print(f'   close列类型: {type(close_prices)}')
            print(f'   close列形状: {close_prices.shape}')
            
            # 计算收益
            first = close_prices.iloc[0]
            last = close_prices.iloc[-1]
            print(f'\n6. 首日价格: {first}')
            print(f'   末日价格: {last}')
            
            returns = (last / first - 1)
            print(f'\n7. 个股收益:')
            print(f'   {returns}')
            
            long_ret = returns[longs.index].mean()
            short_ret = returns[shorts.index].mean()
            portfolio_ret = long_ret - short_ret
            print(f'\n8. 组合收益:')
            print(f'   多头收益: {long_ret:.4f}')
            print(f'   空头收益: {short_ret:.4f}')
            print(f'   多空组合: {portfolio_ret:.4f}')
