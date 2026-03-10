#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测结果可视化
==============
生成收益曲线、回撤图等可视化图表
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import json

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

def plot_backtest_results(report_dir: str):
    """绘制回测结果图表"""
    
    # 读取数据
    daily_values = pd.read_csv(f'{report_dir}/daily_values.csv')
    daily_values['date'] = pd.to_datetime(daily_values['date'])
    
    with open(f'{report_dir}/performance.json', 'r', encoding='utf-8') as f:
        performance = json.load(f)
    
    # 创建图表
    fig, axes = plt.subplots(3, 1, figsize=(14, 12))
    fig.suptitle('中证A500 月度换仓回测结果 (2000-2026)', fontsize=16, fontweight='bold')
    
    # 1. 收益曲线
    ax1 = axes[0]
    ax1.plot(daily_values['date'], daily_values['total_value'] / 1e6, 
             label='Portfolio Value', color='steelblue', linewidth=1.5)
    ax1.axhline(y=1, color='red', linestyle='--', alpha=0.5, label='Initial Capital')
    ax1.set_ylabel('Value (Million $)', fontsize=11)
    ax1.set_title(f'Portfolio Value | Final: ${performance["期末资金"]:,.0f} | Return: {performance["总收益率"]:.1f}%', 
                  fontsize=12)
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax1.xaxis.set_major_locator(mdates.YearLocator(2))
    
    # 2. 回撤曲线
    ax2 = axes[1]
    cumulative = daily_values['total_value']
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max * 100
    
    ax2.fill_between(daily_values['date'], drawdown, 0, 
                     color='coral', alpha=0.6, label='Drawdown')
    ax2.set_ylabel('Drawdown (%)', fontsize=11)
    ax2.set_title(f'Max Drawdown: {performance["最大回撤"]:.2f}%', fontsize=12)
    ax2.legend(loc='lower left')
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax2.xaxis.set_major_locator(mdates.YearLocator(2))
    
    # 3. 每日收益分布
    ax3 = axes[2]
    daily_returns = daily_values['daily_return'].dropna() * 100
    ax3.hist(daily_returns, bins=100, color='lightgreen', edgecolor='black', alpha=0.7)
    ax3.axvline(x=0, color='red', linestyle='--', linewidth=2)
    ax3.axvline(x=daily_returns.mean(), color='blue', linestyle='--', 
                linewidth=2, label=f'Mean: {daily_returns.mean():.3f}%')
    ax3.set_xlabel('Daily Return (%)', fontsize=11)
    ax3.set_ylabel('Frequency', fontsize=11)
    ax3.set_title(f'Daily Return Distribution | Win Rate: {performance["胜率"]:.1f}% | '
                  f'Volatility: {performance["年化波动率"]:.1f}%', fontsize=12)
    ax3.legend()
    ax3.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{report_dir}/backtest_charts.png', dpi=150, bbox_inches='tight')
    print(f"图表已保存: {report_dir}/backtest_charts.png")
    plt.close()
    
    # 创建绩效指标表格图
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.axis('off')
    
    metrics_data = [
        ['初始资金', f"${performance['初始资金']:,.0f}"],
        ['期末资金', f"${performance['期末资金']:,.0f}"],
        ['总收益率', f"{performance['总收益率']:.2f}%"],
        ['年化收益率', f"{performance['年化收益率']:.2f}%"],
        ['年化波动率', f"{performance['年化波动率']:.2f}%"],
        ['最大回撤', f"{performance['最大回撤']:.2f}%"],
        ['夏普比率', f"{performance['夏普比率']:.2f}"],
        ['卡玛比率', f"{performance['卡玛比率']:.2f}"],
        ['胜率', f"{performance['胜率']:.2f}%"],
        ['盈亏比', f"{performance['盈亏比']:.2f}"],
        ['交易次数', f"{performance['交易次数']:,}"],
        ['换仓次数', f"{performance['换仓次数']}"],
        ['合规分数', f"{performance['合规分数']}/100"],
    ]
    
    table = ax.table(cellText=metrics_data, 
                     colLabels=['指标', '数值'],
                     cellLoc='left',
                     loc='center',
                     colWidths=[0.4, 0.3])
    
    table.auto_set_font_size(False)
    table.set_fontsize(11)
    table.scale(1, 2)
    
    # 设置表头样式
    for i in range(2):
        table[(0, i)].set_facecolor('#4472C4')
        table[(0, i)].set_text_props(weight='bold', color='white')
    
    # 设置交替行颜色
    for i in range(1, len(metrics_data) + 1):
        for j in range(2):
            if i % 2 == 0:
                table[(i, j)].set_facecolor('#E7E6E6')
    
    plt.title('回测绩效指标汇总', fontsize=14, fontweight='bold', pad=20)
    plt.savefig(f'{report_dir}/performance_table.png', dpi=150, bbox_inches='tight')
    print(f"绩效表已保存: {report_dir}/performance_table.png")
    plt.close()

if __name__ == "__main__":
    report_dir = "Backtest_Report_2000-01-01_2026-02-28"
    plot_backtest_results(report_dir)
    print("可视化完成!")
