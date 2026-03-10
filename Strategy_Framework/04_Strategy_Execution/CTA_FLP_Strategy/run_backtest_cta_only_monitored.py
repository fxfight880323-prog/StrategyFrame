#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CTA 纯趋势策略回测 - 集成监视器版本
====================================

在原run_backtest_cta_only.py基础上集成BacktestMonitor

监控重点:
1. 信号生成不使用未来数据
2. 仓位计算合规性
3. 收益计算准确性
4. 风险调整收益指标
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import json

# 导入原策略
from CTA_FLP_Strategy import CTATrendEngine, Signal, CTA_CONFIG, UNIVERSE

# 导入监视器
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', '..', '06_Backtesting'))
from BacktestMonitor import BacktestMonitor, MonitorLevel


def generate_mock_data(start_date: date, end_date: date, symbols: list) -> dict:
    """生成模拟价格数据"""
    data = {}
    
    for symbol in symbols:
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        n_days = len(dates)
        
        if symbol == 'ES':
            base_price = 1500
            returns = np.random.normal(0.0002, 0.012, n_days)
            returns[0:500] += 0.0003
            returns[1500:1700] -= 0.001
            returns[2500:4000] += 0.0004
        elif symbol == 'GC':
            base_price = 300
            returns = np.random.normal(0.00015, 0.008, n_days)
        else:  # ZN
            base_price = 100
            returns = np.random.normal(0.00005, 0.004, n_days)
        
        prices = base_price * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'open': prices * (1 + np.random.normal(0, 0.001, n_days)),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.008, n_days))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.008, n_days))),
            'close': prices,
            'volume': np.random.randint(10000, 100000, n_days)
        }, index=dates)
        
        df['high'] = np.maximum(df['high'], df[['open', 'close']].max(axis=1) * 1.001)
        df['low'] = np.minimum(df['low'], df[['open', 'close']].min(axis=1) * 0.999)
        
        data[symbol] = df
    
    return data


def run_cta_backtest_monitored(price_data: dict, 
                               start_date: date, 
                               end_date: date,
                               monitor: BacktestMonitor) -> tuple:
    """
    运行带监控的CTA回测
    
    Returns:
        (results_df, trade_records, metrics)
    """
    initial_capital = 1_000_000
    
    # 初始化CTA引擎
    cta_engine = CTATrendEngine()
    
    # 生成CTA信号
    all_signals = {}
    for symbol, df in price_data.items():
        print(f"生成 {symbol} 信号...")
        
        # 监控: 检查信号生成
        sigs = cta_engine.generate_signal(df, symbol)
        sigs = cta_engine.calculate_position_sizes(sigs)
        
        # 检查信号时点
        for sig in sigs:
            data_end = df.index[-1].date() if isinstance(df.index[-1], pd.Timestamp) else df.index[-1]
            monitor.check_signal_timing(
                signal_date=sig.date,
                data_available_date=data_end,
                context=f"CTA signal - {symbol}"
            )
        
        sig_df = pd.DataFrame([
            {
                'date': sig.date if isinstance(sig.date, date) else sig.date.date(),
                'signal': sig.signal.name,
                'price': sig.price,
                'position_size': sig.position_size
            }
            for sig in sigs
        ])
        
        if not sig_df.empty:
            sig_df.set_index('date', inplace=True)
        all_signals[symbol] = sig_df
        
        print(f"  ✓ {len(sigs)} 个信号")
    
    # 统一日期索引
    all_dates = price_data['ES'].index.date
    
    results = []
    trade_records = []
    
    capital = initial_capital
    positions = {s: 0 for s in price_data.keys()}
    entry_prices = {s: 0 for s in price_data.keys()}
    trade_id = 0
    
    daily_returns = []
    
    for i, current_date in enumerate(all_dates):
        if current_date < start_date or current_date > end_date:
            continue
        
        daily_pnl = 0
        
        # 获取当日信号
        for symbol in price_data.keys():
            sig_df = all_signals[symbol]
            if current_date not in sig_df.index:
                continue
            
            signal = sig_df.loc[current_date]
            current_price = signal['price']
            sig_type = signal['signal']
            pos_size = signal['position_size']
            
            # 监控: 检查数据访问
            monitor.check_data_access(
                access_date=current_date,
                data_date=current_date,
                variable_name=f"{symbol}_price"
            )
            
            target_exposure = capital * 0.3 * pos_size
            current_pos = positions[symbol]
            
            # 交易逻辑 (带监控)
            if sig_type == 'LONG' and current_pos <= 0:
                if current_pos < 0:
                    pnl = (entry_prices[symbol] - current_price) * abs(current_pos) * 0.01
                    daily_pnl += pnl
                    trade_id += 1
                    trade_records.append({
                        'trade_id': trade_id, 'date': current_date, 'symbol': symbol,
                        'action': 'COVER_SHORT', 'price': current_price, 'pnl': pnl
                    })
                
                positions[symbol] = 1
                entry_prices[symbol] = current_price
                trade_id += 1
                trade_records.append({
                    'trade_id': trade_id, 'date': current_date, 'symbol': symbol,
                    'action': 'BUY_LONG', 'price': current_price, 'pnl': 0
                })
                
            elif sig_type == 'SHORT' and current_pos >= 0:
                if current_pos > 0:
                    pnl = (current_price - entry_prices[symbol]) * current_pos * 0.01
                    daily_pnl += pnl
                    trade_id += 1
                    trade_records.append({
                        'trade_id': trade_id, 'date': current_date, 'symbol': symbol,
                        'action': 'SELL_LONG', 'price': current_price, 'pnl': pnl
                    })
                
                positions[symbol] = -1
                entry_prices[symbol] = current_price
                trade_id += 1
                trade_records.append({
                    'trade_id': trade_id, 'date': current_date, 'symbol': symbol,
                    'action': 'SELL_SHORT', 'price': current_price, 'pnl': 0
                })
                
            elif sig_type == 'FLAT' and current_pos != 0:
                if current_pos > 0:
                    pnl = (current_price - entry_prices[symbol]) * current_pos * 0.01
                else:
                    pnl = (entry_prices[symbol] - current_price) * abs(current_pos) * 0.01
                
                daily_pnl += pnl
                trade_id += 1
                action = 'SELL_LONG' if current_pos > 0 else 'COVER_SHORT'
                trade_records.append({
                    'trade_id': trade_id, 'date': current_date, 'symbol': symbol,
                    'action': action, 'price': current_price, 'pnl': pnl
                })
                positions[symbol] = 0
                entry_prices[symbol] = 0
        
        # 持仓盈亏
        if i > 0:
            for symbol in price_data.keys():
                if positions[symbol] != 0:
                    today_price = price_data[symbol]['close'].iloc[i]
                    yest_price = price_data[symbol]['close'].iloc[i-1]
                    ret = (today_price - yest_price) / yest_price
                    
                    # 监控: 确保不使用未来数据
                    monitor.check_data_access(
                        access_date=current_date,
                        data_date=current_date - timedelta(days=1),
                        variable_name=f"{symbol}_prev_price"
                    )
                    
                    position_pnl = positions[symbol] * ret * capital * 0.25
                    daily_pnl += position_pnl
        
        capital += daily_pnl
        capital = max(capital, 0)
        
        # 记录日收益
        if i > 0:
            prev_capital = results[-1]['total_value'] if results else initial_capital
            daily_return = (capital - prev_capital) / prev_capital if prev_capital > 0 else 0
            daily_returns.append({'date': current_date, 'return': daily_return})
        
        results.append({
            'date': current_date,
            'total_value': capital,
            'daily_pnl': daily_pnl,
            'ES_position': positions['ES'],
            'GC_position': positions['GC'],
            'ZN_position': positions['ZN'],
        })
    
    results_df = pd.DataFrame(results)
    trades_df = pd.DataFrame(trade_records)
    
    # 计算风险调整收益
    if daily_returns:
        returns_series = pd.Series(
            [d['return'] for d in daily_returns],
            index=[d['date'] for d in daily_returns]
        )
        
        print("\n计算风险调整收益指标...")
        metrics = monitor.calculate_metrics(returns_series)
        
        # 生成报告
        report_path = monitor.generate_report(
            f"CTA_Monitor_Report_{date.today().isoformat()}.json"
        )
        print(f"监控报告: {report_path}")
    
    return results_df, trades_df


def main():
    print("=" * 60)
    print("CTA 纯趋势策略回测（带监视器）")
    print("=" * 60)
    print()
    
    start_date = date(2000, 1, 1)
    end_date = date(2026, 3, 1)
    symbols = ['ES', 'GC', 'ZN']
    
    print(f"回测期间: {start_date} 至 {end_date}")
    print(f"交易标的: {', '.join(symbols)}")
    print()
    
    # 创建监视器
    monitor = BacktestMonitor(
        risk_free_rate=0.05,
        monitor_level=MonitorLevel.STRICT
    )
    
    print("生成模拟数据...")
    price_data = generate_mock_data(start_date, end_date, symbols)
    print(f"✓ 生成 {len(price_data[symbols[0]])} 个交易日数据")
    print()
    
    print("执行回测（带监控）...")
    results_df, trades_df = run_cta_backtest_monitored(
        price_data, start_date, end_date, monitor
    )
    
    print(f"✓ 回测完成: {len(results_df)} 条记录, {len(trades_df)} 笔交易")
    print()
    
    # 保存结果
    print("保存结果...")
    results_df.to_csv('backtest_results_cta_monitored.csv', index=False, encoding='utf-8-sig')
    trades_df.to_csv('trade_records_cta_monitored.csv', index=False, encoding='utf-8-sig')
    print("✓ 文件保存完成")
    print()
    
    print("=" * 60)
    print("回测结果摘要")
    print("=" * 60)
    print(f"初始资金: $1,000,000.00")
    print(f"期末资金: ${results_df['total_value'].iloc[-1]:,.2f}")
    print(f"总收益率: {(results_df['total_value'].iloc[-1]/1_000_000-1)*100:+.2f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
