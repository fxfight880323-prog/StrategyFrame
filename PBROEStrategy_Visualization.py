"""
PB-ROE 策略可视化模块
====================
生成PB-ROE选股结果的可视化图表
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
import glob
import warnings
warnings.filterwarnings('ignore')

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def find_latest_pb_data() -> pd.DataFrame:
    """找到最新的PB-ROE数据文件"""
    files = glob.glob("pbroe_selection_*.csv")
    if not files:
        # 生成模拟数据用于演示
        return generate_mock_data()
    
    files.sort(reverse=True)
    return pd.read_csv(files[0])


def generate_mock_data() -> pd.DataFrame:
    """生成模拟数据用于演示"""
    np.random.seed(42)
    
    industries = ['食品饮料', '医药生物', '银行', '非银金融', '家用电器', 
                  '电子', '电气设备', '化工', '汽车', '公用事业']
    
    data = []
    for i in range(30):
        industry = np.random.choice(industries)
        
        # 根据行业调整基础值
        if industry == '银行':
            base_pb, base_roe = 0.8, 12
        elif industry == '食品饮料':
            base_pb, base_roe = 3.5, 20
        elif industry == '医药生物':
            base_pb, base_roe = 4.0, 18
        else:
            base_pb, base_roe = 2.0, 15
        
        # 添加随机波动
        pb = base_pb * np.random.uniform(0.6, 1.4)
        roe = base_roe * np.random.uniform(0.8, 1.3)
        
        # 高分股票
        if i < 10:
            pb = np.random.uniform(0.8, 2.0)
            roe = np.random.uniform(18, 30)
        
        data.append({
            'symbol': f'{600000 + i}.XSHG',
            'industry': industry,
            'pb': round(pb, 2),
            'roe_ttm': round(roe, 2),
            'roe_pb_ratio': round(roe / pb, 2),
            'total_score': round(np.random.uniform(60, 95), 1),
            'pb_score': round(np.random.uniform(50, 100), 1),
            'roe_score': round(np.random.uniform(50, 100), 1),
        })
    
    df = pd.DataFrame(data)
    df = df.sort_values('total_score', ascending=False)
    return df


def plot_pb_roe_scatter(df: pd.DataFrame, output_dir: str = "charts"):
    """
    绘制PB-ROE散点图
    
    X轴: PB (市净率)
    Y轴: ROE (净资产收益率)
    气泡大小: 综合评分
    颜色: 行业
    """
    os.makedirs(output_dir, exist_ok=True)
    
    fig, ax = plt.subplots(figsize=(14, 10))
    
    # 准备数据
    industries = df['industry'].unique()
    colors = plt.cm.Set3(np.linspace(0, 1, len(industries)))
    color_map = dict(zip(industries, colors))
    
    # 绘制散点
    for industry in industries:
        subset = df[df['industry'] == industry]
        ax.scatter(subset['pb'], subset['roe_ttm'], 
                  s=subset['total_score'] * 5,  # 气泡大小
                  c=[color_map[industry]], 
                  alpha=0.6, 
                  edgecolors='black', 
                  linewidth=0.5,
                  label=industry)
    
    # 添加分界线
    ax.axhline(y=15, color='green', linestyle='--', alpha=0.5, label='ROE=15%')
    ax.axvline(x=3, color='red', linestyle='--', alpha=0.5, label='PB=3')
    
    # 添加理想区域
    ax.fill_between([0, 2], [15, 15], [30, 30], alpha=0.1, color='green', label='理想区域')
    
    # 标注高分股票
    for i, row in df.head(5).iterrows():
        ax.annotate(row['symbol'].split('.')[0], 
                   (row['pb'], row['roe_ttm']),
                   xytext=(5, 5), textcoords='offset points',
                   fontsize=9, fontweight='bold')
    
    ax.set_xlabel('PB (Price-to-Book Ratio)', fontsize=12, fontweight='bold')
    ax.set_ylabel('ROE (Return on Equity, %)', fontsize=12, fontweight='bold')
    ax.set_title('PB-ROE Scatter Plot - Value Stock Selection', 
                 fontsize=16, fontweight='bold', pad=20)
    ax.legend(loc='upper right', fontsize=9)
    ax.grid(True, alpha=0.3)
    
    # 添加说明文字
    ax.text(0.02, 0.98, 'Bubble size = Total Score\nIdeal zone: Low PB + High ROE', 
            transform=ax.transAxes, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.8))
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/01_pb_roe_scatter.png', dpi=300, bbox_inches='tight')
    print("✓ 生成: 01_pb_roe_scatter.png")
    plt.close()


def plot_score_breakdown(df: pd.DataFrame, output_dir: str = "charts"):
    """
    绘制评分分解图
    """
    os.makedirs(output_dir, exist_ok=True)
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1. 综合评分排名 (Top 15)
    ax1 = axes[0, 0]
    top15 = df.head(15).sort_values('total_score')
    colors = plt.cm.RdYlGn(np.linspace(0.3, 0.9, len(top15)))
    bars = ax1.barh(range(len(top15)), top15['total_score'], color=colors, edgecolor='black')
    ax1.set_yticks(range(len(top15)))
    ax1.set_yticklabels([s.split('.')[0] for s in top15['symbol']], fontsize=10)
    ax1.set_xlabel('Total Score', fontsize=11)
    ax1.set_title('Top 15 Stocks by Total Score', fontweight='bold')
    ax1.grid(axis='x', alpha=0.3)
    
    # 添加数值
    for i, (bar, score) in enumerate(zip(bars, top15['total_score'])):
        ax1.text(score + 1, i, f'{score:.1f}', va='center', fontsize=9)
    
    # 2. ROE/PB性价比排名
    ax2 = axes[0, 1]
    df_sorted = df.sort_values('roe_pb_ratio', ascending=True).tail(15)
    colors = plt.cm.Blues(np.linspace(0.4, 0.9, len(df_sorted)))
    bars = ax2.barh(range(len(df_sorted)), df_sorted['roe_pb_ratio'], color=colors, edgecolor='black')
    ax2.set_yticks(range(len(df_sorted)))
    ax2.set_yticklabels([s.split('.')[0] for s in df_sorted['symbol']], fontsize=10)
    ax2.set_xlabel('ROE/PB Ratio', fontsize=11)
    ax2.set_title('Top 15 by ROE/PB Ratio', fontweight='bold')
    ax2.grid(axis='x', alpha=0.3)
    
    # 3. 行业分布
    ax3 = axes[1, 0]
    industry_counts = df['industry'].value_counts().head(8)
    colors = plt.cm.Set3(np.linspace(0, 1, len(industry_counts)))
    wedges, texts, autotexts = ax3.pie(industry_counts.values, labels=industry_counts.index,
                                        autopct='%1.1f%%', colors=colors, startangle=90,
                                        textprops={'fontsize': 10})
    ax3.set_title('Industry Distribution', fontweight='bold')
    
    # 4. 评分分布直方图
    ax4 = axes[1, 1]
    ax4.hist(df['total_score'], bins=15, alpha=0.7, color='steelblue', edgecolor='black')
    ax4.axvline(df['total_score'].mean(), color='red', linestyle='--', linewidth=2,
               label=f'Mean: {df["total_score"].mean():.1f}')
    ax4.axvline(80, color='green', linestyle='--', linewidth=1, alpha=0.7, label='High Score (80)')
    ax4.set_xlabel('Total Score', fontsize=11)
    ax4.set_ylabel('Frequency', fontsize=11)
    ax4.set_title('Score Distribution', fontweight='bold')
    ax4.legend()
    ax4.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/02_score_breakdown.png', dpi=300, bbox_inches='tight')
    print("✓ 生成: 02_score_breakdown.png")
    plt.close()


def plot_industry_comparison(df: pd.DataFrame, output_dir: str = "charts"):
    """
    绘制行业对比图
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 计算行业平均值
    industry_stats = df.groupby('industry').agg({
        'pb': 'mean',
        'roe_ttm': 'mean',
        'total_score': 'mean',
        'symbol': 'count'
    }).round(2)
    industry_stats.columns = ['Avg PB', 'Avg ROE', 'Avg Score', 'Count']
    industry_stats = industry_stats.sort_values('Avg Score', ascending=False).head(10)
    
    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    
    # 1. 行业平均评分
    ax1 = axes[0, 0]
    colors = plt.cm.RdYlGn(np.linspace(0.3, 0.9, len(industry_stats)))
    bars = ax1.barh(range(len(industry_stats)), industry_stats['Avg Score'], color=colors, edgecolor='black')
    ax1.set_yticks(range(len(industry_stats)))
    ax1.set_yticklabels(industry_stats.index, fontsize=10)
    ax1.set_xlabel('Average Score', fontsize=11)
    ax1.set_title('Average Score by Industry', fontweight='bold')
    ax1.grid(axis='x', alpha=0.3)
    
    # 2. 行业平均PB
    ax2 = axes[0, 1]
    pb_sorted = industry_stats.sort_values('Avg PB')
    colors = plt.cm.Reds(np.linspace(0.3, 0.9, len(pb_sorted)))
    bars = ax2.barh(range(len(pb_sorted)), pb_sorted['Avg PB'], color=colors, edgecolor='black')
    ax2.set_yticks(range(len(pb_sorted)))
    ax2.set_yticklabels(pb_sorted.index, fontsize=10)
    ax2.set_xlabel('Average PB', fontsize=11)
    ax2.set_title('Average PB by Industry', fontweight='bold')
    ax2.grid(axis='x', alpha=0.3)
    
    # 3. 行业平均ROE
    ax3 = axes[1, 0]
    roe_sorted = industry_stats.sort_values('Avg ROE', ascending=False)
    colors = plt.cm.Greens(np.linspace(0.3, 0.9, len(roe_sorted)))
    bars = ax3.barh(range(len(roe_sorted)), roe_sorted['Avg ROE'], color=colors, edgecolor='black')
    ax3.set_yticks(range(len(roe_sorted)))
    ax3.set_yticklabels(roe_sorted.index, fontsize=10)
    ax3.set_xlabel('Average ROE (%)', fontsize=11)
    ax3.set_title('Average ROE by Industry', fontweight='bold')
    ax3.grid(axis='x', alpha=0.3)
    
    # 4. 行业选股数量
    ax4 = axes[1, 1]
    count_sorted = industry_stats.sort_values('Count', ascending=False)
    colors = plt.cm.Blues(np.linspace(0.3, 0.9, len(count_sorted)))
    bars = ax4.bar(range(len(count_sorted)), count_sorted['Count'], color=colors, edgecolor='black')
    ax4.set_xticks(range(len(count_sorted)))
    ax4.set_xticklabels(count_sorted.index, rotation=45, ha='right', fontsize=10)
    ax4.set_ylabel('Number of Stocks', fontsize=11)
    ax4.set_title('Selected Stocks Count by Industry', fontweight='bold')
    ax4.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/03_industry_comparison.png', dpi=300, bbox_inches='tight')
    print("✓ 生成: 03_industry_comparison.png")
    plt.close()


def generate_html_report(df: pd.DataFrame, output_dir: str = "charts"):
    """生成HTML报告"""
    os.makedirs(output_dir, exist_ok=True)
    
    # 准备数据
    top10 = df.head(10)
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>PB-ROE Strategy Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1400px; margin: 0 auto; background-color: white; padding: 30px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; border-bottom: 3px solid #27ae60; padding-bottom: 10px; }}
        h2 {{ color: #34495e; margin-top: 30px; border-left: 4px solid #27ae60; padding-left: 10px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #27ae60; color: white; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .metric {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                   color: white; padding: 20px 30px; margin: 10px; border-radius: 10px; }}
        .metric-value {{ font-size: 32px; font-weight: bold; }}
        .chart {{ margin: 20px 0; text-align: center; }}
        .chart img {{ max-width: 100%; border: 1px solid #ddd; border-radius: 5px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 PB-ROE Value Strategy Report</h1>
        <p>Report Date: {date.today().isoformat()}</p>
        
        <h2>📈 Key Metrics</h2>
        <div class="metric">
            <div class="metric-value">{len(df)}</div>
            <div>Selected Stocks</div>
        </div>
        <div class="metric">
            <div class="metric-value">{df['total_score'].mean():.1f}</div>
            <div>Avg Score</div>
        </div>
        <div class="metric">
            <div class="metric-value">{df['pb'].mean():.2f}</div>
            <div>Avg PB</div>
        </div>
        <div class="metric">
            <div class="metric-value">{df['roe_ttm'].mean():.1f}%</div>
            <div>Avg ROE</div>
        </div>
        
        <h2>🏆 Top 10 Recommended Stocks</h2>
        <table>
            <tr>
                <th>Rank</th>
                <th>Symbol</th>
                <th>Industry</th>
                <th>PB</th>
                <th>ROE</th>
                <th>ROE/PB</th>
                <th>Total Score</th>
            </tr>
    """
    
    for i, (_, row) in enumerate(top10.iterrows(), 1):
        html += f"""
            <tr>
                <td>{i}</td>
                <td>{row['symbol'].split('.')[0]}</td>
                <td>{row['industry']}</td>
                <td>{row['pb']:.2f}</td>
                <td>{row['roe_ttm']:.2f}%</td>
                <td>{row['roe_pb_ratio']:.2f}</td>
                <td><strong>{row['total_score']:.1f}</strong></td>
            </tr>
        """
    
    html += """
        </table>
        
        <h2>📊 Visualizations</h2>
        <div class="chart">
            <h3>PB-ROE Scatter Plot</h3>
            <img src="01_pb_roe_scatter.png" alt="PB-ROE Scatter">
        </div>
        <div class="chart">
            <h3>Score Breakdown</h3>
            <img src="02_score_breakdown.png" alt="Score Breakdown">
        </div>
        <div class="chart">
            <h3>Industry Comparison</h3>
            <img src="03_industry_comparison.png" alt="Industry Comparison">
        </div>
    </div>
</body>
</html>
"""
    
    with open(f'{output_dir}/pbroe_report.html', 'w', encoding='utf-8') as f:
        f.write(html)
    
    print("✓ 生成: pbroe_report.html")


def main():
    """主函数"""
    print("="*60)
    print("PB-ROE 策略可视化")
    print("="*60)
    
    # 加载数据
    df = find_latest_pb_data()
    print(f"\n加载数据: {len(df)} 只股票")
    
    # 生成图表
    print("\n生成图表...")
    plot_pb_roe_scatter(df)
    plot_score_breakdown(df)
    plot_industry_comparison(df)
    
    # 生成HTML报告
    print("\n生成报告...")
    generate_html_report(df)
    
    print("\n" + "="*60)
    print("可视化完成!")
    print("图表位置: charts/")
    print("报告位置: charts/pbroe_report.html")
    print("="*60)


if __name__ == "__main__":
    main()
