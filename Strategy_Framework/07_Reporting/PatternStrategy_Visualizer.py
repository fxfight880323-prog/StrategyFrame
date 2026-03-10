"""
技术形态策略可视化模块
=======================

为技术形态分析策略生成:
- 形态识别图表
- 信号分布热力图
- 回测绩效图表
- 综合HTML报告
"""

import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime
from typing import Dict, List
import logging
import os

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle, FancyBboxPatch
from matplotlib.collections import LineCollection
import matplotlib.patches as mpatches

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


# ============================================================
# 日志
# ============================================================
def setup_logger(name: str = "pattern_visualizer") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# 技术形态可视化器
# ============================================================
class PatternVisualizer:
    """技术形态可视化器"""
    
    def __init__(self, output_dir: str = None, logger: logging.Logger = None):
        self.output_dir = output_dir or f"Report_{date.today().isoformat()}"
        self.logger = logger or setup_logger()
        os.makedirs(self.output_dir, exist_ok=True)
    
    def plot_stock_with_patterns(self, symbol: str, df: pd.DataFrame, 
                                  signals: Dict, save: bool = True) -> str:
        """
        绘制股票K线图及技术形态
        
        Args:
            symbol: 股票代码
            df: 价格数据
            signals: 信号数据
            save: 是否保存
        
        Returns:
            保存的文件路径
        """
        if df.empty or len(df) < 30:
            return None
        
        fig, axes = plt.subplots(3, 1, figsize=(14, 12), 
                                 gridspec_kw={'height_ratios': [3, 1, 1]})
        
        # 准备数据
        df = df.copy()
        df['Date'] = pd.to_datetime(df['Date'])
        
        # ========== 主图: 价格 + 均线 + 形态 ==========
        ax1 = axes[0]
        
        # 绘制K线 (简化版)
        for idx, row in df.iterrows():
            color = 'green' if row['Close'] >= row['Open'] else 'red'
            ax1.plot([row['Date'], row['Date']], [row['Low'], row['High']], 
                    color='black', linewidth=0.5)
            ax1.plot([row['Date'], row['Date']], [row['Open'], row['Close']], 
                    color=color, linewidth=2)
        
        # 绘制均线
        if 'MA_20' in df.columns:
            ax1.plot(df['Date'], df['MA_20'], label='MA20', color='blue', alpha=0.7)
        if 'MA_50' in df.columns:
            ax1.plot(df['Date'], df['MA_50'], label='MA50', color='orange', alpha=0.7)
        
        # 绘制布林带
        if 'BB_Upper' in df.columns:
            ax1.fill_between(df['Date'], df['BB_Upper'], df['BB_Lower'], 
                           alpha=0.1, color='gray')
            ax1.plot(df['Date'], df['BB_Upper'], '--', color='gray', alpha=0.5)
            ax1.plot(df['Date'], df['BB_Lower'], '--', color='gray', alpha=0.5)
        
        # 标记信号
        if signals:
            last_date = df['Date'].iloc[-1]
            last_price = df['Close'].iloc[-1]
            
            signal_colors = {
                '强烈买入': 'darkgreen',
                '买入': 'green',
                '偏买入': 'lightgreen',
                '中性': 'gray',
                '偏卖出': 'orange',
                '卖出': 'red',
                '强烈卖出': 'darkred',
            }
            
            signal_color = signal_colors.get(signals.get('signal', '中性'), 'gray')
            
            # 添加信号标注
            ax1.axvline(x=last_date, color=signal_color, linestyle='--', alpha=0.7)
            ax1.annotate(
                f"{signals.get('signal', '')}\n{signals.get('pattern', '')}",
                xy=(last_date, last_price),
                xytext=(10, 30),
                textcoords='offset points',
                bbox=dict(boxstyle='round,pad=0.5', facecolor=signal_color, alpha=0.3),
                fontsize=10,
                fontweight='bold'
            )
        
        ax1.set_title(f'{symbol} 技术分析', fontsize=14, fontweight='bold')
        ax1.set_ylabel('价格')
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # ========== 副图1: 成交量 ==========
        ax2 = axes[1]
        colors = ['green' if c >= o else 'red' for c, o in zip(df['Close'], df['Open'])]
        ax2.bar(df['Date'], df['Volume'], color=colors, alpha=0.7)
        
        if 'Volume_MA' in df.columns:
            ax2.plot(df['Date'], df['Volume_MA'], color='blue', linewidth=1, label='VMA20')
        
        ax2.set_ylabel('成交量')
        ax2.legend(loc='upper left')
        ax2.grid(True, alpha=0.3)
        
        # ========== 副图2: MACD ==========
        ax3 = axes[2]
        
        if 'MACD' in df.columns:
            ax3.plot(df['Date'], df['MACD'], label='MACD', color='blue')
            ax3.plot(df['Date'], df['MACD_Signal'], label='Signal', color='red')
            
            # MACD柱状图
            colors_macd = ['green' if v >= 0 else 'red' for v in df['MACD_Hist']]
            ax3.bar(df['Date'], df['MACD_Hist'], color=colors_macd, alpha=0.5)
        
        ax3.set_ylabel('MACD')
        ax3.set_xlabel('日期')
        ax3.legend(loc='upper left')
        ax3.grid(True, alpha=0.3)
        ax3.axhline(y=0, color='black', linewidth=0.5)
        
        plt.tight_layout()
        
        if save:
            filepath = f"{self.output_dir}/{symbol}_pattern.png"
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()
            return filepath
        else:
            plt.show()
            return None
    
    def plot_signal_distribution(self, signals_df: pd.DataFrame, save: bool = True) -> str:
        """
        绘制信号分布图
        """
        if signals_df.empty:
            return None
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 1. 信号强度分布 (饼图)
        ax1 = axes[0, 0]
        signal_counts = signals_df['Signal'].value_counts()
        colors = {'强烈买入': 'darkgreen', '买入': 'green', '偏买入': 'lightgreen',
                 '中性': 'gray', '偏卖出': 'orange', '卖出': 'red', '强烈卖出': 'darkred'}
        
        wedges, texts, autotexts = ax1.pie(
            signal_counts.values,
            labels=signal_counts.index,
            autopct='%1.1f%%',
            colors=[colors.get(s, 'gray') for s in signal_counts.index],
            startangle=90
        )
        ax1.set_title('信号强度分布', fontsize=12, fontweight='bold')
        
        # 2. 形态分布 (柱状图)
        ax2 = axes[0, 1]
        pattern_counts = signals_df['Pattern'].value_counts().head(10)
        ax2.barh(pattern_counts.index, pattern_counts.values, color='steelblue')
        ax2.set_xlabel('出现次数')
        ax2.set_title('技术形态分布 (Top 10)', fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3, axis='x')
        
        # 3. 价格行为信号分布
        ax3 = axes[1, 0]
        action_counts = signals_df['Price_Action'].value_counts()
        colors_action = ['green' if '买入' in str(s) or '好反应' in str(s) 
                        else 'red' if '卖出' in str(s) or '坏反应' in str(s)
                        else 'gray' for s in action_counts.index]
        ax3.bar(range(len(action_counts)), action_counts.values, color=colors_action)
        ax3.set_xticks(range(len(action_counts)))
        ax3.set_xticklabels(action_counts.index, rotation=45, ha='right')
        ax3.set_ylabel('出现次数')
        ax3.set_title('价格行为信号分布', fontsize=12, fontweight='bold')
        ax3.grid(True, alpha=0.3, axis='y')
        
        # 4. 置信度分布
        ax4 = axes[1, 1]
        ax4.hist(signals_df['Confidence'], bins=20, color='skyblue', edgecolor='black', alpha=0.7)
        ax4.axvline(signals_df['Confidence'].mean(), color='red', linestyle='--', 
                   label=f'平均: {signals_df["Confidence"].mean():.2f}')
        ax4.set_xlabel('置信度')
        ax4.set_ylabel('股票数量')
        ax4.set_title('信号置信度分布', fontsize=12, fontweight='bold')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        
        plt.tight_layout()
        
        if save:
            filepath = f"{self.output_dir}/signal_distribution.png"
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()
            return filepath
        else:
            plt.show()
            return None
    
    def plot_backtest_performance(self, portfolio_df: pd.DataFrame, 
                                   trades_df: pd.DataFrame = None,
                                   save: bool = True) -> str:
        """
        绘制回测绩效图表
        """
        if portfolio_df.empty:
            return None
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        portfolio_df['Date'] = pd.to_datetime(portfolio_df['Date'])
        
        # 1. 累计收益曲线
        ax1 = axes[0, 0]
        ax1.plot(portfolio_df['Date'], portfolio_df['Cumulative_Return'] * 100, 
                linewidth=2, color='blue')
        ax1.fill_between(portfolio_df['Date'], 
                        portfolio_df['Cumulative_Return'] * 100, 0, 
                        alpha=0.3, color='blue')
        ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax1.set_ylabel('收益率 (%)')
        ax1.set_title('累计收益率', fontsize=12, fontweight='bold')
        ax1.grid(True, alpha=0.3)
        
        # 2. 资产分配
        ax2 = axes[0, 1]
        ax2.plot(portfolio_df['Date'], portfolio_df['Cash'], 
                label='现金', linewidth=1.5)
        ax2.plot(portfolio_df['Date'], portfolio_df['Positions_Value'], 
                label='持仓', linewidth=1.5)
        ax2.plot(portfolio_df['Date'], portfolio_df['Total_Value'], 
                label='总资产', linewidth=2, color='green')
        ax2.set_ylabel('价值 ($)')
        ax2.set_title('资产分配', fontsize=12, fontweight='bold')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 3. 持仓数量变化
        ax3 = axes[1, 0]
        ax3.fill_between(portfolio_df['Date'], portfolio_df['Num_Positions'], 
                        alpha=0.5, color='purple')
        ax3.set_ylabel('持仓数量')
        ax3.set_title('持仓数量变化', fontsize=12, fontweight='bold')
        ax3.grid(True, alpha=0.3)
        
        # 4. 交易盈亏分布
        ax4 = axes[1, 1]
        if trades_df is not None and not trades_df.empty:
            trades_df = trades_df.copy()
            trades_df['PnL_Pct'] = trades_df.get('PnL_Pct', trades_df.get('PnL_%', 0))
            
            colors = ['green' if pnl > 0 else 'red' for pnl in trades_df['PnL_Pct']]
            ax4.bar(range(len(trades_df)), trades_df['PnL_Pct'], color=colors, alpha=0.7)
            ax4.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
            ax4.set_xlabel('交易编号')
            ax4.set_ylabel('盈亏 (%)')
            ax4.set_title('交易盈亏分布', fontsize=12, fontweight='bold')
            ax4.grid(True, alpha=0.3, axis='y')
        else:
            ax4.text(0.5, 0.5, '无交易数据', ha='center', va='center', 
                    transform=ax4.transAxes, fontsize=12)
            ax4.set_title('交易盈亏分布', fontsize=12, fontweight='bold')
        
        plt.tight_layout()
        
        if save:
            filepath = f"{self.output_dir}/backtest_performance.png"
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()
            return filepath
        else:
            plt.show()
            return None
    
    def create_signal_heatmap(self, signals_df: pd.DataFrame, save: bool = True) -> str:
        """
        创建信号热力图
        """
        if signals_df.empty or 'Signal' not in signals_df.columns:
            return None
        
        fig, ax = plt.subplots(figsize=(12, max(8, len(signals_df) * 0.3)))
        
        # 信号强度映射到数值
        signal_map = {
            '强烈买入': 3,
            '买入': 2,
            '偏买入': 1,
            '中性': 0,
            '偏卖出': -1,
            '卖出': -2,
            '强烈卖出': -3,
        }
        
        signals_df = signals_df.copy()
        signals_df['Signal_Value'] = signals_df['Signal'].map(signal_map)
        
        # 按信号强度排序
        signals_df = signals_df.sort_values('Signal_Value', ascending=True)
        
        # 创建颜色映射
        colors = []
        for val in signals_df['Signal_Value']:
            if val >= 3:
                colors.append('#006400')  # 深绿
            elif val >= 2:
                colors.append('#228B22')  # 绿色
            elif val >= 1:
                colors.append('#90EE90')  # 浅绿
            elif val == 0:
                colors.append('#808080')  # 灰色
            elif val >= -1:
                colors.append('#FFB6C1')  # 浅红
            elif val >= -2:
                colors.append('#DC143C')  # 红色
            else:
                colors.append('#8B0000')  # 深红
        
        # 绘制横向条形图
        bars = ax.barh(signals_df['Symbol'], signals_df['Signal_Value'], color=colors)
        
        # 添加数值标签
        for bar, val in zip(bars, signals_df['Signal_Value']):
            width = bar.get_width()
            ax.text(width, bar.get_y() + bar.get_height()/2, 
                   f'{val:+d}', ha='left' if width > 0 else 'right', 
                   va='center', fontsize=8)
        
        ax.set_xlabel('信号强度')
        ax.set_title('技术形态信号热力图', fontsize=14, fontweight='bold')
        ax.axvline(x=0, color='black', linewidth=1)
        ax.grid(True, alpha=0.3, axis='x')
        
        plt.tight_layout()
        
        if save:
            filepath = f"{self.output_dir}/signal_heatmap.png"
            plt.savefig(filepath, dpi=150, bbox_inches='tight')
            plt.close()
            return filepath
        else:
            plt.show()
            return None
    
    def create_html_report(self, signals_df: pd.DataFrame, 
                          portfolio_df: pd.DataFrame = None,
                          trades_df: pd.DataFrame = None,
                          title: str = "技术形态分析报告") -> str:
        """
        生成HTML综合报告
        """
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>{title}</title>
            <style>
                body {{
                    font-family: 'Microsoft YaHei', Arial, sans-serif;
                    margin: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    max-width: 1400px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #333;
                    border-bottom: 3px solid #2196F3;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #555;
                    margin-top: 30px;
                    border-left: 4px solid #2196F3;
                    padding-left: 10px;
                }}
                .summary-box {{
                    display: flex;
                    justify-content: space-around;
                    margin: 20px 0;
                    flex-wrap: wrap;
                }}
                .stat-card {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 8px;
                    text-align: center;
                    min-width: 150px;
                    margin: 10px;
                }}
                .stat-value {{
                    font-size: 28px;
                    font-weight: bold;
                }}
                .stat-label {{
                    font-size: 14px;
                    opacity: 0.9;
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
                    background-color: #2196F3;
                    color: white;
                }}
                tr:hover {{
                    background-color: #f5f5f5;
                }}
                .signal-buy {{
                    color: #4CAF50;
                    font-weight: bold;
                }}
                .signal-sell {{
                    color: #F44336;
                    font-weight: bold;
                }}
                .signal-neutral {{
                    color: #9E9E9E;
                }}
                .chart-container {{
                    margin: 20px 0;
                    text-align: center;
                }}
                .chart-container img {{
                    max-width: 100%;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                }}
                .timestamp {{
                    text-align: right;
                    color: #999;
                    font-size: 12px;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>{title}</h1>
                <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        """
        
        # 汇总统计
        if not signals_df.empty:
            total = len(signals_df)
            buy_signals = len(signals_df[signals_df['Signal'].str.contains('买入', na=False)])
            sell_signals = len(signals_df[signals_df['Signal'].str.contains('卖出', na=False)])
            avg_confidence = signals_df['Confidence'].mean()
            
            html_content += f"""
                <h2>汇总统计</h2>
                <div class="summary-box">
                    <div class="stat-card">
                        <div class="stat-value">{total}</div>
                        <div class="stat-label">分析标的</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{buy_signals}</div>
                        <div class="stat-label">买入信号</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{sell_signals}</div>
                        <div class="stat-label">卖出信号</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{avg_confidence:.1%}</div>
                        <div class="stat-label">平均置信度</div>
                    </div>
                </div>
            """
        
        # 信号图表
        html_content += """
            <h2>信号分布</h2>
            <div class="chart-container">
                <img src="signal_distribution.png" alt="信号分布">
            </div>
            <div class="chart-container">
                <img src="signal_heatmap.png" alt="信号热力图">
            </div>
        """
        
        # 回测绩效
        if portfolio_df is not None and not portfolio_df.empty:
            html_content += """
                <h2>回测绩效</h2>
                <div class="chart-container">
                    <img src="backtest_performance.png" alt="回测绩效">
                </div>
            """
        
        # 信号详情表
        if not signals_df.empty:
            html_content += """
                <h2>详细信号</h2>
                <table>
                    <tr>
                        <th>标的</th>
                        <th>信号</th>
                        <th>形态</th>
                        <th>趋势</th>
                        <th>价格</th>
                        <th>目标价</th>
                        <th>止损价</th>
                        <th>置信度</th>
                    </tr>
            """
            
            for _, row in signals_df.head(50).iterrows():
                signal_class = 'signal-neutral'
                if '买入' in str(row['Signal']):
                    signal_class = 'signal-buy'
                elif '卖出' in str(row['Signal']):
                    signal_class = 'signal-sell'
                
                html_content += f"""
                    <tr>
                        <td>{row['Symbol']}</td>
                        <td class="{signal_class}">{row['Signal']}</td>
                        <td>{row['Pattern']}</td>
                        <td>{row['Trend']}</td>
                        <td>${row['Price']:.2f}</td>
                        <td>${row['Target']:.2f}</td>
                        <td>${row['Stop_Loss']:.2f}</td>
                        <td>{row['Confidence']:.1%}</td>
                    </tr>
                """
            
            html_content += "</table>"
        
        html_content += f"""
                <div class="timestamp">
                    报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                </div>
            </div>
        </body>
        </html>
        """
        
        # 保存文件
        filepath = f"{self.output_dir}/pattern_analysis_report.html"
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return filepath


# ============================================================
# 测试
# ============================================================
def test_visualizer():
    """测试可视化器"""
    print("="*60)
    print("技术形态可视化测试")
    print("="*60)
    print()
    
    from TechnicalPatternAnalyzer import PatternBatchAnalyzer
    
    # 批量分析
    analyzer = PatternBatchAnalyzer()
    signals_df = analyzer.analyze_stocks(['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'TSLA', 'META'])
    
    print("\n分析结果:")
    print(signals_df[['Symbol', 'Signal', 'Pattern', 'Price']].to_string(index=False))
    
    # 可视化
    viz = PatternVisualizer()
    
    print("\n生成图表...")
    
    # 信号分布图
    viz.plot_signal_distribution(signals_df)
    print("  ✓ signal_distribution.png")
    
    # 信号热力图
    viz.create_signal_heatmap(signals_df)
    print("  ✓ signal_heatmap.png")
    
    # HTML报告
    html_path = viz.create_html_report(signals_df)
    print(f"  ✓ {html_path}")
    
    print("\n图表已保存到:", viz.output_dir)


if __name__ == "__main__":
    test_visualizer()
