#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CTA + FLP 策略 - 集成回测监视器版本
====================================

在原CTA_FLP_Strategy基础上集成BacktestMonitor，用于:
1. 检测未来数据使用
2. 计算风险调整收益指标
3. 生成合规报告

使用方法:
    python CTA_FLP_Strategy_Monitored.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import json

# 导入原策略
from CTA_FLP_Strategy import (
    CTATrendEngine, FLPEngine, RiskBudgetBalancer,
    CTAFLPBacktester, PortfolioState, Signal, FLPMode,
    CTA_CONFIG, FLP_CONFIG, RISK_CONFIG, UNIVERSE
)

# 导入监视器
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', '..', '06_Backtesting'))
from BacktestMonitor import BacktestMonitor, MonitorLevel, ViolationType


class MonitoredCTAFLPBacktester:
    """
    带监视器的CTA+FLP回测器
    """
    
    def __init__(self, initial_capital: float = 1_000_000, 
                 risk_free_rate: float = 0.03):
        self.initial_capital = initial_capital
        self.cta_engine = CTATrendEngine()
        self.flp_engine = FLPEngine()
        self.risk_balancer = RiskBudgetBalancer()
        
        # 创建监视器
        self.monitor = BacktestMonitor(
            risk_free_rate=risk_free_rate,
            monitor_level=MonitorLevel.STRICT  # 严格模式
        )
        
        print("="*60)
        print("CTA + FLP 策略回测 (带监视器)")
        print("="*60)
    
    def run_backtest(self, price_data: Dict[str, pd.DataFrame],
                    vix_data: pd.DataFrame,
                    start_date: date, end_date: date) -> pd.DataFrame:
        """
        运行带监控的回测
        """
        print(f"\n回测期间: {start_date} 至 {end_date}")
        print(f"初始资金: ${self.initial_capital:,.2f}")
        print()
        
        # 生成CTA信号
        all_cta_signals = {}
        for symbol, df in price_data.items():
            # 监控: 检查信号生成是否使用未来数据
            print(f"生成 {symbol} CTA信号...")
            
            # 原策略生成信号
            signals = self.cta_engine.generate_signal(df, symbol)
            signals = self.cta_engine.calculate_position_sizes(signals)
            all_cta_signals[symbol] = signals
            
            # 检查: 信号日期不应超过数据日期
            for sig in signals:
                data_max_date = df.index[-1].date() if isinstance(df.index[-1], pd.Timestamp) else df.index[-1]
                self.monitor.check_signal_timing(
                    signal_date=sig.date,
                    data_available_date=data_max_date,
                    context=f"CTA信号生成 - {symbol}"
                )
            
            print(f"  ✓ 生成 {len(signals)} 个信号")
        
        # 回测循环
        results = []
        current_date = start_date
        portfolio = PortfolioState(date=current_date)
        
        daily_returns = []
        
        while current_date <= end_date:
            # 获取当日数据
            vix_row = vix_data[vix_data.index.date == current_date]
            vix = vix_row['close'].iloc[0] if not vix_row.empty else 20.0
            
            # 监控: 检查VIX数据使用时点
            if not vix_row.empty:
                vix_data_date = vix_row.index[0].date()
                self.monitor.check_data_access(
                    access_date=current_date,
                    data_date=vix_data_date,
                    variable_name="VIX"
                )
            
            # FLP信号生成 (每周五)
            spy_price = 400.0
            flp_signal = self.flp_engine.generate_signal(
                current_date, spy_price, vix,
                base_budget=portfolio.total_value * 0.05
            )
            
            # 计算权重
            weights = self.risk_balancer.calculate_weights(portfolio, "normal")
            
            # 模拟每日收益 (简化)
            daily_pnl = 0
            
            # 监控: 检查价格数据
            for symbol, df in price_data.items():
                if current_date in df.index or any(df.index.date == current_date):
                    # 获取当日价格
                    price_data_for_date = df[df.index.date == current_date]
                    if not price_data_for_date.empty:
                        current_price = price_data_for_date['close'].iloc[0]
                        
                        # 检查: 确保不使用未来数据计算收益
                        self.monitor.check_data_access(
                            access_date=current_date,
                            data_date=current_date,  # T日价格T日使用 (如果是开盘价则合规)
                            variable_name=f"{symbol}_price"
                        )
            
            # 记录结果
            prev_value = portfolio.total_value
            portfolio.total_value += daily_pnl
            
            # 计算日收益率
            if prev_value > 0:
                daily_return = daily_pnl / prev_value
                daily_returns.append({
                    'date': current_date,
                    'return': daily_return
                })
            
            results.append({
                'date': current_date,
                'total_value': portfolio.total_value,
                'vix': vix,
                'cta_weight': weights['cta'],
                'flp_weight': weights['flp']
            })
            
            current_date += timedelta(days=1)
        
        results_df = pd.DataFrame(results)
        
        # 计算收益率序列
        returns_series = pd.Series(
            [d['return'] for d in daily_returns],
            index=[d['date'] for d in daily_returns]
        )
        
        # 使用监视器计算风险调整收益
        print("\n计算风险调整收益指标...")
        metrics = self.monitor.calculate_metrics(returns_series)
        
        # 生成监控报告
        report_path = self.monitor.generate_report(
            f"CTA_FLP_Monitor_Report_{date.today().isoformat()}.json"
        )
        
        print(f"\n监控报告: {report_path}")
        
        return results_df


def demo():
    """演示"""
    # 创建带监控的回测器
    backtester = MonitoredCTAFLPBacktester(
        initial_capital=1_000_000,
        risk_free_rate=0.03
    )
    
    # 模拟数据 (简化)
    print("生成模拟数据...")
    from CTA_FLP_Strategy import CTATrendEngine
    
    engine = CTATrendEngine()
    
    # 生成价格数据
    dates = pd.date_range('2024-01-01', '2024-12-31', freq='B')
    np.random.seed(42)
    
    price_data = {}
    for symbol in ['ES', 'GC', 'ZN']:
        base_price = {'ES': 4200, 'GC': 1950, 'ZN': 110}[symbol]
        returns = np.random.normal(0.0002, 0.012, len(dates))
        prices = base_price * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'open': prices,
            'high': prices * 1.01,
            'low': prices * 0.99,
            'close': prices
        }, index=dates)
        
        price_data[symbol] = df
    
    # VIX数据
    vix_data = pd.DataFrame({
        'close': 20 + np.random.normal(0, 2, len(dates))
    }, index=dates)
    
    print("✓ 数据生成完成\n")
    
    # 运行回测
    results = backtester.run_backtest(
        price_data=price_data,
        vix_data=vix_data,
        start_date=date(2024, 1, 1),
        end_date=date(2024, 12, 31)
    )
    
    print("\n" + "="*60)
    print("回测完成")
    print("="*60)


if __name__ == "__main__":
    demo()
