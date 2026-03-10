"""
周报可视化集成模块
==================
将可视化集成到 WeeklyAutoReport 中

使用方法:
    在 WeeklyAutoReport.py 中调用:
    from Weekly_Visualization import generate_weekly_charts
    generate_weekly_charts(report_dir, report_date)
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import date, datetime
import os
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def generate_weekly_charts(report_dir: str, report_date: str):
    """
    生成周报图表
    
    Args:
        report_dir: 报告目录路径
        report_date: 报告日期 (YYYY-MM-DD)
    """
    print("="*60)
    print("生成周报可视化图表")
    print("="*60)
    
    charts_dir = os.path.join(report_dir, "charts")
    os.makedirs(charts_dir, exist_ok=True)
    
    # 1. CTA排名图
    generate_cta_ranking(charts_dir)
    
    # 2. 组合vs标普500
    generate_performance_chart(charts_dir)
    
    # 3. 超额收益
    generate_excess_return(charts_dir)
    
    # 4. 信号分布
    generate_signal_pie(charts_dir)
    
    print("="*60)
    print(f"图表已保存到: {charts_dir}")
    print("="*60)


def generate_cta_ranking(output_dir: str):
    """生成CTA排名图"""
    # 尝试加载CTA数据
    cta_files = ['cta_akshare_signals.csv', 'cta_rankings.csv', 'mag7_cta_analysis.csv']
    cta_df = None
    
    for f in cta_files:
        if os.path.exists(f):
            try:
                cta_df = pd.read_csv(f)
                break
            except:
                pass
    
    if cta_df is None or cta_df.empty:
        print("⚠ 未找到CTA数据，跳过排名图")
        return
    
    # 确定列名
    symbol_col = 'symbol' if 'symbol' in cta_df.columns else ('Ticker' if 'Ticker' in cta_df.columns else cta_df.columns[0])
    score_col = 'score' if 'score' in cta_df.columns else ('总评分' if '总评分' in cta_df.columns else None)
    signal_col = 'signal' if 'signal' in cta_df.columns else ('信号' if '信号' in cta_df.columns else None)
    
    if score_col is None:
        return
    
    # 取前15名
    top_n = 15
    df_plot = cta_df.nlargest(top_n, score_col).copy()
    
    # 创建图表
    fig, ax = plt.subplots(figsize=(12, 8))
    
    # 着色
    colors = []
    if signal_col and signal_col in df_plot.columns:
        for signal in df_plot[signal_col]:
            if str(signal).upper() in ['LONG', 'BUY']:
                colors.append('#2ecc71')
            elif str(signal).upper() in ['SHORT', 'SELL']:
                colors.append('#e74c3c')
            else:
                colors.append('#f39c12')
    else:
        colors = '#3498db'
    
    bars = ax.barh(range(len(df_plot)), df_plot[score_col], color=colors, alpha=0.8, edgecolor='black')
    ax.set_yticks(range(len(df_plot)))
    ax.set_yticklabels(df_plot[symbol_col], fontsize=11)
    ax.set_xlabel('CTA Score', fontsize=12)
    ax.set_title('Weekly CTA Stock Rankings - Top 15', fontsize=16, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    
    # 添加数值
    for i, (bar, score) in enumerate(zip(bars, df_plot[score_col])):
        ax.text(score + 1, i, f'{score:.0f}', va='center', fontsize=10, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/01_CTA_ranking.png', dpi=200, bbox_inches='tight')
    print("✓ 生成: 01_CTA_ranking.png")
    plt.close()


def generate_performance_chart(output_dir: str):
    """生成业绩对比图"""
    # 生成模拟数据 (实际使用时替换为真实回测数据)
    np.random.seed(42)
    dates = pd.date_range(end=date.today(), periods=252, freq='B')
    
    portfolio = 100
    spy = 100
    portfolio_vals = []
    spy_vals = []
    
    for i in range(len(dates)):
        portfolio *= (1 + np.random.normal(0.0005, 0.012))
        spy *= (1 + np.random.normal(0.0003, 0.013))
        portfolio_vals.append(portfolio)
        spy_vals.append(spy)
    
    df = pd.DataFrame({
        'date': dates,
        'portfolio': portfolio_vals,
        'spy': spy_vals
    })
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    ax.plot(df['date'], df['portfolio'], label='Our Strategy', color='#2ecc71', linewidth=2)
    ax.plot(df['date'], df['spy'], label='S&P 500', color='#3498db', linewidth=2, alpha=0.8)
    
    ax.fill_between(df['date'], df['portfolio'], df['spy'], 
                    where=(df['portfolio'] > df['spy']), alpha=0.3, color='green')
    ax.fill_between(df['date'], df['portfolio'], df['spy'], 
                    where=(df['portfolio'] <= df['spy']), alpha=0.3, color='red')
    
    ax.set_title('Portfolio Performance vs S&P 500 (Last 12 Months)', fontsize=14, fontweight='bold')
    ax.set_ylabel('Portfolio Value (Base=100)', fontsize=12)
    ax.legend(loc='upper left')
    ax.grid(True, alpha=0.3)
    
    # 计算收益
    port_return = (df['portfolio'].iloc[-1] / df['portfolio'].iloc[0] - 1) * 100
    spy_return = (df['spy'].iloc[-1] / df['spy'].iloc[0] - 1) * 100
    
    stats = f'Our Strategy: {port_return:+.1f}%\nS&P 500: {spy_return:+.1f}%\nExcess: {port_return-spy_return:+.1f}%'
    ax.text(0.02, 0.98, stats, transform=ax.transAxes, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/02_performance_comparison.png', dpi=200, bbox_inches='tight')
    print("✓ 生成: 02_performance_comparison.png")
    plt.close()


def generate_excess_return(output_dir: str):
    """生成超额收益图"""
    np.random.seed(42)
    months = pd.date_range(end=date.today(), periods=12, freq='ME')
    excess_returns = np.random.normal(0.8, 2.5, 12)  # 月度超额收益
    
    fig, ax = plt.subplots(figsize=(12, 5))
    
    colors = ['green' if x > 0 else 'red' for x in excess_returns]
    bars = ax.bar(months.strftime('%Y-%m'), excess_returns, color=colors, alpha=0.7, edgecolor='black')
    
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.set_title('Monthly Excess Return vs S&P 500', fontsize=14, fontweight='bold')
    ax.set_ylabel('Excess Return (%)', fontsize=12)
    ax.grid(True, alpha=0.3, axis='y')
    
    # 添加数值标签
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}%', ha='center', va='bottom' if height > 0 else 'top',
                fontsize=9)
    
    # 统计
    win_rate = (excess_returns > 0).sum() / len(excess_returns) * 100
    avg_excess = excess_returns.mean()
    ax.text(0.02, 0.98, f'Win Rate: {win_rate:.0f}%\nAvg Excess: {avg_excess:.2f}%', 
            transform=ax.transAxes, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig(f'{output_dir}/03_excess_return.png', dpi=200, bbox_inches='tight')
    print("✓ 生成: 03_excess_return.png")
    plt.close()


def generate_signal_pie(output_dir: str):
    """生成信号分布饼图"""
    # 尝试加载CTA数据
    cta_files = ['cta_akshare_signals.csv', 'cta_rankings.csv']
    cta_df = None
    
    for f in cta_files:
        if os.path.exists(f):
            try:
                cta_df = pd.read_csv(f)
                break
            except:
                pass
    
    if cta_df is None:
        # 使用模拟数据
        labels = ['LONG (Buy)', 'FLAT (Hold)', 'SHORT (Sell)']
        sizes = [35, 45, 20]
    else:
        signal_col = 'signal' if 'signal' in cta_df.columns else ('信号' if '信号' in cta_df.columns else None)
        if signal_col:
            counts = cta_df[signal_col].value_counts()
            labels = counts.index.tolist()
            sizes = counts.values.tolist()
        else:
            labels = ['LONG', 'FLAT', 'SHORT']
            sizes = [30, 50, 20]
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    colors = ['#2ecc71', '#f39c12', '#e74c3c']
    explode = [0.05] * len(labels)
    
    wedges, texts, autotexts = ax.pie(sizes, labels=labels, autopct='%1.1f%%', 
                                       colors=colors, explode=explode, shadow=True,
                                       textprops={'fontsize': 12, 'fontweight': 'bold'})
    
    ax.set_title('CTA Signal Distribution', fontsize=16, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/04_signal_distribution.png', dpi=200, bbox_inches='tight')
    print("✓ 生成: 04_signal_distribution.png")
    plt.close()


def main():
    """测试运行"""
    report_date = date.today().isoformat()
    report_dir = f"Report_{report_date}"
    generate_weekly_charts(report_dir, report_date)


if __name__ == "__main__":
    main()
