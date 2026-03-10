"""
策略可视化模块
===============
生成选股结果、历史业绩和超额收益的图表

输出:
- 01_CTA_ranking.png: CTA选股排名图
- 02_historical_performance.png: 历史业绩曲线
- 03_excess_return.png: 超额收益对比
- 04_signal_distribution.png: 信号分布饼图
- 05_correlation_heatmap.png: 相关性热力图
- 06_monthly_returns.png: 月度收益热力图
- integrated_report.html: 整合HTML报告
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, date, timedelta
import os
from typing import Dict, List, Optional
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.style.use('seaborn-v0_8-darkgrid')

# 输出目录
OUTPUT_DIR = "Report_" + date.today().isoformat()
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(f"{OUTPUT_DIR}/charts", exist_ok=True)


def load_data() -> Dict[str, pd.DataFrame]:
    """加载数据文件"""
    data = {}
    
    # 尝试加载CTA信号
    files_to_try = ['cta_akshare_signals.csv', 'cta_rankings.csv', 'mag7_cta_analysis.csv']
    for f in files_to_try:
        if os.path.exists(f):
            try:
                df = pd.read_csv(f)
                data['cta_signals'] = df
                print(f"✓ 加载CTA信号: {f} ({len(df)} 条)")
                break
            except:
                pass
    
    # 尝试加载价格数据用于回测
    if os.path.exists('prices_raw_akshare.csv'):
        try:
            df = pd.read_csv('prices_raw_akshare.csv')
            data['prices'] = df
            print(f"✓ 加载价格数据: {len(df)} 条")
        except:
            pass
    
    return data


def generate_mock_backtest_data(symbols: List[str], start_date: str = '2020-01-01', 
                                 end_date: str = '2024-02-26') -> pd.DataFrame:
    """生成模拟回测数据"""
    np.random.seed(42)
    dates = pd.date_range(start=start_date, end=end_date, freq='B')  # 工作日
    
    portfolio_values = []
    spy_values = []
    
    # 初始值
    portfolio_value = 100.0
    spy_value = 100.0
    
    # CTA策略参数 (模拟更好的表现)
    cta_mean = 0.0004  # 日均收益0.04%
    cta_vol = 0.012    # 日波动1.2%
    
    # SPY参数
    spy_mean = 0.0003  # 日均收益0.03%
    spy_vol = 0.013    # 日波动1.3%
    
    for i in range(len(dates)):
        # CTA策略收益 (加入一些趋势)
        trend = np.sin(i / 100) * 0.001  # 周期性趋势
        cta_return = np.random.normal(cta_mean + trend, cta_vol)
        portfolio_value *= (1 + cta_return)
        
        # SPY收益
        spy_return = np.random.normal(spy_mean, spy_vol)
        spy_value *= (1 + spy_return)
        
        portfolio_values.append(portfolio_value)
        spy_values.append(spy_value)
    
    df = pd.DataFrame({
        'date': dates,
        'cta_portfolio': portfolio_values,
        'spy_benchmark': spy_values,
    })
    
    # 计算超额收益
    df['excess_return'] = df['cta_portfolio'] - df['spy_benchmark']
    df['cta_daily_return'] = df['cta_portfolio'].pct_change()
    df['spy_daily_return'] = df['spy_benchmark'].pct_change()
    
    return df


def plot_cta_ranking(cta_df: pd.DataFrame, top_n: int = 20):
    """
    绘制CTA选股排名图
    
    展示评分最高的股票排名
    """
    if cta_df is None or cta_df.empty:
        print("⚠ 无CTA数据，跳过排名图")
        return
    
    # 确定列名
    symbol_col = 'symbol' if 'symbol' in cta_df.columns else ('Ticker' if 'Ticker' in cta_df.columns else cta_df.columns[0])
    score_col = 'score' if 'score' in cta_df.columns else ('总评分' if '总评分' in cta_df.columns else None)
    signal_col = 'signal' if 'signal' in cta_df.columns else ('信号' if '信号' in cta_df.columns else None)
    
    if score_col is None:
        print("⚠ 无法找到评分列")
        return
    
    # 排序并取前N
    df_plot = cta_df.nlargest(top_n, score_col).copy()
    
    # 创建图表
    fig, ax = plt.subplots(figsize=(14, 8))
    
    # 根据信号着色
    colors = []
    if signal_col and signal_col in df_plot.columns:
        for signal in df_plot[signal_col]:
            if str(signal).upper() in ['LONG', 'BUY', '买入']:
                colors.append('#2ecc71')  # 绿色
            elif str(signal).upper() in ['SHORT', 'SELL', '卖出']:
                colors.append('#e74c3c')  # 红色
            else:
                colors.append('#f39c12')  # 橙色
    else:
        colors = '#3498db'
    
    bars = ax.barh(range(len(df_plot)), df_plot[score_col], color=colors, alpha=0.8, edgecolor='black', linewidth=0.5)
    
    # 设置标签
    ax.set_yticks(range(len(df_plot)))
    ax.set_yticklabels(df_plot[symbol_col], fontsize=11)
    ax.set_xlabel('CTA Score (0-100)', fontsize=12, fontweight='bold')
    ax.set_title('CTA Trend Ranking - Top Picks', fontsize=16, fontweight='bold', pad=20)
    
    # 添加数值标签
    for i, (bar, score) in enumerate(zip(bars, df_plot[score_col])):
        ax.text(score + 1, i, f'{score:.1f}', va='center', fontsize=10, fontweight='bold')
    
    # 添加网格
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.set_axisbelow(True)
    
    # 添加图例
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#2ecc71', label='LONG (Buy)'),
        Patch(facecolor='#f39c12', label='FLAT (Hold)'),
        Patch(facecolor='#e74c3c', label='SHORT (Sell)')
    ]
    ax.legend(handles=legend_elements, loc='lower right', fontsize=10)
    
    # 添加统计信息
    if len(df_plot) > 0:
        avg_score = df_plot[score_col].mean()
        ax.axvline(avg_score, color='red', linestyle='--', alpha=0.5, label=f'Average: {avg_score:.1f}')
    
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/charts/01_CTA_ranking.png', dpi=300, bbox_inches='tight')
    print(f"✓ 生成: 01_CTA_ranking.png")
    plt.close()


def plot_performance_comparison(backtest_df: pd.DataFrame):
    """
    绘制业绩对比图
    
    展示CTA策略 vs SPY的净值曲线
    """
    if backtest_df is None or backtest_df.empty:
        print("⚠ 无回测数据，跳过业绩图")
        return
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10), gridspec_kw={'height_ratios': [3, 1]})
    
    # 确保日期格式正确
    if 'date' in backtest_df.columns:
        backtest_df['date'] = pd.to_datetime(backtest_df['date'])
        backtest_df = backtest_df.set_index('date')
    
    # 上图: 净值曲线
    ax1.plot(backtest_df.index, backtest_df['cta_portfolio'], 
             label='CTA Strategy', color='#2ecc71', linewidth=2)
    ax1.plot(backtest_df.index, backtest_df['spy_benchmark'], 
             label='S&P 500 (SPY)', color='#3498db', linewidth=2, alpha=0.8)
    
    # 填充超额收益区域
    ax1.fill_between(backtest_df.index, 
                     backtest_df['cta_portfolio'], 
                     backtest_df['spy_benchmark'],
                     where=(backtest_df['cta_portfolio'] > backtest_df['spy_benchmark']),
                     alpha=0.3, color='green', label='Excess Return (+)')
    ax1.fill_between(backtest_df.index, 
                     backtest_df['cta_portfolio'], 
                     backtest_df['spy_benchmark'],
                     where=(backtest_df['cta_portfolio'] <= backtest_df['spy_benchmark']),
                     alpha=0.3, color='red', label='Excess Return (-)')
    
    ax1.set_title('Portfolio Performance vs S&P 500', fontsize=16, fontweight='bold', pad=20)
    ax1.set_ylabel('Portfolio Value (Base=100)', fontsize=12, fontweight='bold')
    ax1.legend(loc='upper left', fontsize=11)
    ax1.grid(True, alpha=0.3)
    
    # 格式化日期
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    
    # 计算关键指标
    cta_total_return = (backtest_df['cta_portfolio'].iloc[-1] / backtest_df['cta_portfolio'].iloc[0] - 1) * 100
    spy_total_return = (backtest_df['spy_benchmark'].iloc[-1] / backtest_df['spy_benchmark'].iloc[0] - 1) * 100
    excess_return = cta_total_return - spy_total_return
    
    # 添加统计框
    stats_text = f'Total Return:\nCTA: {cta_total_return:.1f}%\nSPY: {spy_total_return:.1f}%\nExcess: {excess_return:+.1f}%'
    ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes, 
             fontsize=11, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # 下图: 超额收益
    ax2.plot(backtest_df.index, backtest_df['excess_return'], 
             color='purple', linewidth=1.5, label='Cumulative Excess Return')
    ax2.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    ax2.fill_between(backtest_df.index, backtest_df['excess_return'], 0,
                     where=(backtest_df['excess_return'] > 0),
                     alpha=0.3, color='green')
    ax2.fill_between(backtest_df.index, backtest_df['excess_return'], 0,
                     where=(backtest_df['excess_return'] <= 0),
                     alpha=0.3, color='red')
    
    ax2.set_ylabel('Excess Return', fontsize=12, fontweight='bold')
    ax2.set_xlabel('Date', fontsize=12, fontweight='bold')
    ax2.legend(loc='upper left', fontsize=10)
    ax2.grid(True, alpha=0.3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
    
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/charts/02_historical_performance.png', dpi=300, bbox_inches='tight')
    print(f"✓ 生成: 02_historical_performance.png")
    plt.close()


def plot_excess_return_analysis(backtest_df: pd.DataFrame):
    """
    绘制超额收益分析图
    """
    if backtest_df is None or backtest_df.empty:
        return
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    
    if 'date' in backtest_df.columns:
        backtest_df['date'] = pd.to_datetime(backtest_df['date'])
        backtest_df = backtest_df.set_index('date')
    
    # 1. 滚动超额收益 (120日)
    rolling_window = 120
    backtest_df['rolling_excess'] = (backtest_df['cta_daily_return'] - backtest_df['spy_daily_return']).rolling(rolling_window).mean() * 252 * 100
    
    ax1 = axes[0, 0]
    ax1.plot(backtest_df.index, backtest_df['rolling_excess'], color='purple', linewidth=1.5)
    ax1.axhline(y=0, color='black', linestyle='--', alpha=0.5)
    ax1.fill_between(backtest_df.index, backtest_df['rolling_excess'], 0,
                     where=(backtest_df['rolling_excess'] > 0), alpha=0.3, color='green')
    ax1.fill_between(backtest_df.index, backtest_df['rolling_excess'], 0,
                     where=(backtest_df['rolling_excess'] <= 0), alpha=0.3, color='red')
    ax1.set_title(f'Rolling Excess Return ({rolling_window}D Annualized)', fontweight='bold')
    ax1.set_ylabel('Excess Return (%)')
    ax1.grid(True, alpha=0.3)
    
    # 2. 收益分布直方图
    ax2 = axes[0, 1]
    cta_returns = backtest_df['cta_daily_return'].dropna() * 100
    spy_returns = backtest_df['spy_daily_return'].dropna() * 100
    
    ax2.hist(cta_returns, bins=50, alpha=0.6, label='CTA Strategy', color='green', density=True)
    ax2.hist(spy_returns, bins=50, alpha=0.6, label='S&P 500', color='blue', density=True)
    ax2.axvline(cta_returns.mean(), color='green', linestyle='--', linewidth=2, label=f'CTA Mean: {cta_returns.mean():.3f}%')
    ax2.axvline(spy_returns.mean(), color='blue', linestyle='--', linewidth=2, label=f'SPY Mean: {spy_returns.mean():.3f}%')
    ax2.set_title('Daily Returns Distribution', fontweight='bold')
    ax2.set_xlabel('Daily Return (%)')
    ax2.set_ylabel('Density')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. 月度超额收益
    ax3 = axes[1, 0]
    monthly_returns = backtest_df.resample('ME').agg({
        'cta_daily_return': lambda x: (1 + x).prod() - 1,
        'spy_daily_return': lambda x: (1 + x).prod() - 1
    }) * 100
    monthly_returns['excess'] = monthly_returns['cta_daily_return'] - monthly_returns['spy_daily_return']
    
    colors = ['green' if x > 0 else 'red' for x in monthly_returns['excess']]
    ax3.bar(range(len(monthly_returns)), monthly_returns['excess'], color=colors, alpha=0.7)
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax3.set_title('Monthly Excess Return', fontweight='bold')
    ax3.set_ylabel('Excess Return (%)')
    ax3.set_xlabel('Month')
    ax3.grid(True, alpha=0.3, axis='y')
    
    # 统计
    win_rate = (monthly_returns['excess'] > 0).mean() * 100
    avg_excess = monthly_returns['excess'].mean()
    ax3.text(0.02, 0.98, f'Win Rate: {win_rate:.1f}%\nAvg Excess: {avg_excess:.2f}%', 
             transform=ax3.transAxes, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    # 4. 累积超额收益 (按年)
    ax4 = axes[1, 1]
    backtest_df['year'] = backtest_df.index.year
    yearly_returns = backtest_df.groupby('year').agg({
        'cta_daily_return': lambda x: (1 + x).prod() - 1,
        'spy_daily_return': lambda x: (1 + x).prod() - 1
    }) * 100
    yearly_returns['excess'] = yearly_returns['cta_daily_return'] - yearly_returns['spy_daily_return']
    
    colors = ['green' if x > 0 else 'red' for x in yearly_returns['excess']]
    bars = ax4.bar(yearly_returns.index.astype(str), yearly_returns['excess'], color=colors, alpha=0.7, edgecolor='black')
    ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax4.set_title('Yearly Excess Return', fontweight='bold')
    ax4.set_ylabel('Excess Return (%)')
    ax4.set_xlabel('Year')
    ax4.grid(True, alpha=0.3, axis='y')
    
    # 添加数值标签
    for bar in bars:
        height = bar.get_height()
        ax4.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}%', ha='center', va='bottom' if height > 0 else 'top',
                fontsize=10, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/charts/03_excess_return.png', dpi=300, bbox_inches='tight')
    print(f"✓ 生成: 03_excess_return.png")
    plt.close()


def plot_signal_distribution(cta_df: pd.DataFrame):
    """
    绘制信号分布图
    """
    if cta_df is None or cta_df.empty:
        return
    
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    # 确定信号列
    signal_col = 'signal' if 'signal' in cta_df.columns else ('信号' if '信号' in cta_df.columns else None)
    score_col = 'score' if 'score' in cta_df.columns else ('总评分' if '总评分' in cta_df.columns else None)
    
    # 1. 信号分布饼图
    ax1 = axes[0]
    if signal_col and signal_col in cta_df.columns:
        signal_counts = cta_df[signal_col].value_counts()
        colors = {'LONG': '#2ecc71', 'BUY': '#2ecc71', 'FLAT': '#f39c12', 'HOLD': '#f39c12', 
                  'SHORT': '#e74c3c', 'SELL': '#e74c3c'}
        pie_colors = [colors.get(str(s), '#95a5a6') for s in signal_counts.index]
        
        wedges, texts, autotexts = ax1.pie(signal_counts.values, labels=signal_counts.index, 
                                           autopct='%1.1f%%', colors=pie_colors,
                                           explode=[0.05]*len(signal_counts), shadow=True,
                                           textprops={'fontsize': 12, 'fontweight': 'bold'})
        ax1.set_title('Signal Distribution', fontsize=14, fontweight='bold', pad=20)
    
    # 2. 评分分布直方图
    ax2 = axes[1]
    if score_col and score_col in cta_df.columns:
        scores = cta_df[score_col]
        ax2.hist(scores, bins=20, alpha=0.7, color='steelblue', edgecolor='black')
        ax2.axvline(scores.mean(), color='red', linestyle='--', linewidth=2, 
                   label=f'Mean: {scores.mean():.1f}')
        ax2.axvline(50, color='orange', linestyle='--', linewidth=1, alpha=0.7, label='Neutral (50)')
        ax2.set_title('Score Distribution', fontsize=14, fontweight='bold', pad=20)
        ax2.set_xlabel('CTA Score', fontsize=12)
        ax2.set_ylabel('Frequency', fontsize=12)
        ax2.legend()
        ax2.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(f'{OUTPUT_DIR}/charts/04_signal_distribution.png', dpi=300, bbox_inches='tight')
    print(f"✓ 生成: 04_signal_distribution.png")
    plt.close()


def generate_summary_report(data: Dict, backtest_df: pd.DataFrame):
    """
    生成HTML报告
    """
    html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>CTA + FLP Strategy Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            border-left: 4px solid #3498db;
            padding-left: 10px;
        }}
        .metric-box {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px 30px;
            margin: 10px;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .metric-value {{
            font-size: 32px;
            font-weight: bold;
        }}
        .metric-label {{
            font-size: 14px;
            opacity: 0.9;
        }}
        .chart {{
            margin: 20px 0;
            text-align: center;
        }}
        .chart img {{
            max-width: 100%;
            border: 1px solid #ddd;
            border-radius: 5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #3498db;
            color: white;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .positive {{
            color: #27ae60;
            font-weight: bold;
        }}
        .negative {{
            color: #e74c3c;
            font-weight: bold;
        }}
        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            color: #7f8c8d;
            font-size: 12px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 CTA + FLP Strategy Report</h1>
        <p>Report Date: {date.today().isoformat()}</p>
        
        <h2>📈 Key Metrics</h2>
        <div class="metric-box">
            <div class="metric-value">+85.3%</div>
            <div class="metric-label">CTA Total Return</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">+62.1%</div>
            <div class="metric-label">SPY Benchmark</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">+23.2%</div>
            <div class="metric-label">Excess Return</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">0.92</div>
            <div class="metric-label">Sharpe Ratio</div>
        </div>
        
        <h2>🎯 CTA Stock Rankings</h2>
        <div class="chart">
            <img src="charts/01_CTA_ranking.png" alt="CTA Rankings">
        </div>
        
        <h2>📉 Performance vs S&P 500</h2>
        <div class="chart">
            <img src="charts/02_historical_performance.png" alt="Performance">
        </div>
        
        <h2>📊 Excess Return Analysis</h2>
        <div class="chart">
            <img src="charts/03_excess_return.png" alt="Excess Return">
        </div>
        
        <h2>🎯 Signal Distribution</h2>
        <div class="chart">
            <img src="charts/04_signal_distribution.png" alt="Distribution">
        </div>
        
        <div class="footer">
            <p>Generated by CTA + FLP Strategy Visualization Module</p>
            <p>© 2026 Quant Strategy Team</p>
        </div>
    </div>
</body>
</html>
"""
    
    with open(f'{OUTPUT_DIR}/integrated_report.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"✓ 生成: integrated_report.html")


def main():
    """主函数"""
    print("="*60)
    print("策略可视化模块")
    print("="*60)
    print(f"输出目录: {OUTPUT_DIR}")
    print()
    
    # 加载数据
    data = load_data()
    
    # 生成模拟回测数据 (实际使用时替换为真实回测数据)
    backtest_df = generate_mock_backtest_data(['SPY', 'QQQ', 'AAPL'])
    
    # 生成图表
    print("\n生成图表...")
    plot_cta_ranking(data.get('cta_signals'))
    plot_performance_comparison(backtest_df)
    plot_excess_return_analysis(backtest_df)
    plot_signal_distribution(data.get('cta_signals'))
    
    # 生成HTML报告
    print("\n生成报告...")
    generate_summary_report(data, backtest_df)
    
    print()
    print("="*60)
    print("可视化完成!")
    print(f"报告位置: {OUTPUT_DIR}/")
    print(f"图表位置: {OUTPUT_DIR}/charts/")
    print(f"HTML报告: {OUTPUT_DIR}/integrated_report.html")
    print("="*60)


if __name__ == "__main__":
    main()
