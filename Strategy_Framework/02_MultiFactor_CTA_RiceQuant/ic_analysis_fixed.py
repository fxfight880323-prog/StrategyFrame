"""
IC序列分析（修复版）- 基于真实回测数据
=====================================

使用修复后的行业中性化回测引擎，计算真实的IC序列

作者: AI Assistant
日期: 2026-03-09
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import warnings
import sys
import io
import os

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
warnings.filterwarnings('ignore')

import rqdatac as rq
from industry_neutralized_backtest import IndustryNeutralizedBacktest


class ICAnalyzer:
    """IC分析器（基于真实数据）"""
    
    def __init__(self):
        self.engine = IndustryNeutralizedBacktest()
        self.ic_results = {}
        
    def calculate_ic(self, factor_values: pd.Series, forward_returns: pd.Series) -> float:
        """
        计算信息系数 (IC)
        IC = Rank(因子值)与Rank(未来收益)的Spearman相关系数
        """
        # 对齐数据
        common_index = factor_values.index.intersection(forward_returns.index)
        if len(common_index) < 10:
            return np.nan
        
        f = factor_values[common_index]
        r = forward_returns[common_index]
        
        # 计算Spearman相关系数（使用排名）
        from scipy.stats import spearmanr
        corr, pvalue = spearmanr(f.rank(), r.rank())
        
        return corr
    
    def backtest_with_ic(self, factor_name: str, factor_type: str,
                         start: str, end: str,
                         industry_neutral: bool = False,
                         size_neutral: bool = False) -> dict:
        """
        回测并计算IC序列
        
        返回:
            dict: 包含IC序列、收益序列等
        """
        dates = pd.date_range(start=start, end=end, freq='ME')
        if len(dates) < 2:
            return {}
        
        ic_list = []
        ic_dates = []
        forward_returns_list = []
        
        for i in range(1, len(dates)):
            curr_date = dates[i].strftime('%Y-%m-%d')
            prev_date = dates[i-1].strftime('%Y-%m-%d')
            
            # 获取股票池
            stocks = self.engine.get_stocks(prev_date)
            if not stocks or len(stocks) < 50:
                continue
            
            # 计算因子信号
            signal = self.engine.calc_factor_signal(stocks, prev_date, factor_name)
            if signal.empty or len(signal) < 30:
                continue
            
            # 应用中性化
            if industry_neutral or size_neutral:
                signal = self.engine.neutralize_factors(
                    signal, prev_date,
                    industry_neutral=industry_neutral,
                    size_neutral=size_neutral
                )
            
            if signal.empty or len(signal) < 30:
                continue
            
            # 计算未来收益
            forward_ret = self._calc_forward_returns(list(signal.index), prev_date, curr_date)
            if forward_ret.empty:
                continue
            
            # 计算IC
            ic = self.calculate_ic(signal, forward_ret)
            if not np.isnan(ic):
                ic_list.append(ic)
                ic_dates.append(dates[i])
                forward_returns_list.append(forward_ret.mean())
        
        return {
            'dates': ic_dates,
            'ic': np.array(ic_list),
            'forward_returns': forward_returns_list,
            'factor_name': factor_name,
            'neutralized': industry_neutral or size_neutral
        }
    
    def _calc_forward_returns(self, stocks: list, start: str, end: str) -> pd.Series:
        """计算股票在期间的未来收益"""
        try:
            prices = self.engine.get_prices(stocks, start, end)
            if prices.empty or len(prices) < 2:
                return pd.Series(dtype=float)
            
            first = prices.iloc[0]
            last = prices.iloc[-1]
            returns = (last / first - 1).fillna(0)
            return returns
        except:
            return pd.Series(dtype=float)
    
    def analyze_all_factors(self, start="2023-01-01", end="2024-01-01"):
        """分析所有因子"""
        print("="*80)
        print(f"IC序列分析 ({start} 至 {end})")
        print("="*80 + "\n")
        
        factors = [
            ('SP', 'value', False, False),
            ('SP', 'value', True, False),   # 行业中性
            ('BP', 'value', False, False),
            ('BP', 'value', True, False),   # 行业中性
            ('EP', 'value', False, False),
            ('EP', 'value', True, False),   # 行业中性
        ]
        
        results = {}
        for factor, ftype, ind_neu, size_neu in factors:
            label = f"{factor}_{'IND' if ind_neu else 'RAW'}"
            print(f"计算: {label} ...")
            
            result = self.backtest_with_ic(factor, ftype, start, end,
                                          industry_neutral=ind_neu,
                                          size_neutral=size_neu)
            if result and len(result['ic']) > 0:
                results[label] = result
                print(f"  样本数: {len(result['ic'])}, 平均IC: {np.mean(result['ic']):.4f}")
            else:
                print(f"  无有效数据")
        
        return results


def plot_ic_series_fixed(results: dict, save_path='charts/ic_series_fixed.png'):
    """绘制IC序列时序图（修复版）"""
    fig, axes = plt.subplots(2, 1, figsize=(16, 10))
    
    colors = {
        'SP_RAW': '#e74c3c',
        'SP_IND': '#3498db',
        'BP_RAW': '#2ecc71',
        'BP_IND': '#9b59b6',
        'EP_RAW': '#f39c12',
        'EP_IND': '#1abc9c'
    }
    
    labels = {
        'SP_RAW': 'SP (原始)',
        'SP_IND': 'SP (行业中性)',
        'BP_RAW': 'BP (原始)',
        'BP_IND': 'BP (行业中性)',
        'EP_RAW': 'EP (原始)',
        'EP_IND': 'EP (行业中性)'
    }
    
    # 上图: IC序列
    ax1 = axes[0]
    for label, data in results.items():
        if label in colors:
            ax1.plot(data['dates'], data['ic'], 
                    label=labels.get(label, label),
                    color=colors[label], linewidth=2, alpha=0.8, marker='o', markersize=4)
    
    ax1.axhline(y=0, color='black', linestyle='--', alpha=0.5)
    ax1.axhline(y=0.02, color='green', linestyle=':', alpha=0.5, label='IC=0.02')
    ax1.axhline(y=-0.02, color='red', linestyle=':', alpha=0.5)
    ax1.fill_between(ax1.get_xlim(), 0, 0.15, alpha=0.1, color='green')
    ax1.fill_between(ax1.get_xlim(), -0.15, 0, alpha=0.1, color='red')
    
    ax1.set_ylabel('IC (信息系数)', fontsize=12)
    ax1.set_title('IC序列时序图 - 原始 vs 行业中性化', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper right', fontsize=9, ncol=2)
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(-0.15, 0.15)
    
    if results:
        ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45)
    
    # 下图: 滚动平均IC (3个月窗口)
    ax2 = axes[1]
    window = 3
    for label, data in results.items():
        if label in colors and len(data['ic']) >= window:
            ic_series = pd.Series(data['ic'], index=data['dates'])
            rolling_ic = ic_series.rolling(window=window, min_periods=1).mean()
            ax2.plot(rolling_ic.index, rolling_ic.values,
                    label=labels.get(label, label),
                    color=colors[label], linewidth=2.5, alpha=0.8)
    
    ax2.axhline(y=0, color='black', linestyle='--', alpha=0.5)
    ax2.axhline(y=0.03, color='green', linestyle=':', alpha=0.5, label='IC=0.03 (良好)')
    
    ax2.set_xlabel('日期', fontsize=12)
    ax2.set_ylabel(f'滚动平均IC ({window}个月)', fontsize=12)
    ax2.set_title(f'滚动平均IC ({window}个月窗口)', fontsize=14, fontweight='bold')
    ax2.legend(loc='upper right', fontsize=9, ncol=2)
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(-0.1, 0.1)
    
    if results:
        ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
    
    plt.suptitle('IC序列分析（修复版）- 基于真实回测数据', fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"[OK] IC序列图已保存: {save_path}")
    plt.close()


def plot_ic_comparison_fixed(results: dict, save_path='charts/ic_comparison_fixed.png'):
    """绘制IC对比图（箱线图+统计）"""
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))
    
    # 左图: 箱线图
    ax1 = axes[0]
    
    ic_data = []
    labels = []
    colors_box = []
    
    color_map = {
        'SP_RAW': '#e74c3c', 'SP_IND': '#3498db',
        'BP_RAW': '#2ecc71', 'BP_IND': '#9b59b6',
        'EP_RAW': '#f39c12', 'EP_IND': '#1abc9c'
    }
    
    for label, data in results.items():
        if len(data['ic']) > 0:
            ic_data.append(data['ic'])
            labels.append(label.replace('_', '\n'))
            colors_box.append(color_map.get(label, 'gray'))
    
    bp = ax1.boxplot(ic_data, labels=labels, patch_artist=True)
    for patch, color in zip(bp['boxes'], colors_box):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    
    ax1.axhline(y=0, color='black', linestyle='-', linewidth=1)
    ax1.axhline(y=0.02, color='green', linestyle='--', alpha=0.5)
    ax1.axhline(y=-0.02, color='red', linestyle='--', alpha=0.5)
    
    ax1.set_ylabel('IC值', fontsize=12)
    ax1.set_title('IC分布对比 - 原始 vs 行业中性化', fontsize=14, fontweight='bold')
    ax1.grid(True, alpha=0.3, axis='y')
    
    # 右图: 统计指标对比
    ax2 = axes[1]
    
    stats_data = []
    for label, data in results.items():
        if len(data['ic']) > 0:
            ic = data['ic']
            stats_data.append({
                'label': label,
                'mean': np.mean(ic),
                'std': np.std(ic),
                'ir': np.mean(ic) / np.std(ic) if np.std(ic) > 0 else 0,
                'positive_ratio': (ic > 0).mean() * 100,
                'color': color_map.get(label, 'gray')
            })
    
    if stats_data:
        x = np.arange(len(stats_data))
        width = 0.35
        
        means = [d['mean'] for d in stats_data]
        stds = [d['std'] for d in stats_data]
        
        bars1 = ax2.bar(x - width/2, means, width, label='平均IC', 
                       color=[d['color'] for d in stats_data], alpha=0.8, edgecolor='black')
        bars2 = ax2.bar(x + width/2, stds, width, label='IC标准差',
                       color=[d['color'] for d in stats_data], alpha=0.4, edgecolor='black', hatch='//')
        
        # 添加数值标签
        for bar, val in zip(bars1, means):
            ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.005,
                    f'{val:.3f}', ha='center', va='bottom', fontsize=9)
        
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=1)
        ax2.set_xticks(x)
        ax2.set_xticklabels([d['label'].replace('_', '\n') for d in stats_data], fontsize=9)
        ax2.set_ylabel('IC值', fontsize=12)
        ax2.set_title('IC统计指标对比', fontsize=14, fontweight='bold')
        ax2.legend(fontsize=10)
        ax2.grid(True, alpha=0.3, axis='y')
    
    plt.suptitle('IC分析对比（修复版）', fontsize=16, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"[OK] IC对比图已保存: {save_path}")
    plt.close()


def plot_ic_heatmap_fixed(results: dict, save_path='charts/ic_heatmap_fixed.png'):
    """绘制IC热力图"""
    fig, ax = plt.subplots(figsize=(16, 6))
    
    # 准备数据矩阵
    factor_names = []
    dates_set = set()
    
    for label, data in results.items():
        factor_names.append(label)
        dates_set.update([d.strftime('%Y-%m') for d in data['dates']])
    
    dates_list = sorted(list(dates_set))
    
    if not dates_list or not factor_names:
        print("[WARNING] 数据不足，跳过热力图")
        return
    
    # 构建IC矩阵
    ic_matrix = np.full((len(factor_names), len(dates_list)), np.nan)
    
    for i, label in enumerate(factor_names):
        data = results[label]
        date_strs = [d.strftime('%Y-%m') for d in data['dates']]
        for j, date_str in enumerate(dates_list):
            if date_str in date_strs:
                idx = date_strs.index(date_str)
                ic_matrix[i, j] = data['ic'][idx]
    
    # 绘制热力图
    im = ax.imshow(ic_matrix, aspect='auto', cmap='RdYlGn', 
                  vmin=-0.15, vmax=0.15, interpolation='nearest')
    
    # 设置标签
    ax.set_yticks(np.arange(len(factor_names)))
    ax.set_yticklabels([f.replace('_', '\n') for f in factor_names], fontsize=10)
    
    ax.set_xticks(np.arange(len(dates_list)))
    ax.set_xticklabels(dates_list, rotation=45, ha='right', fontsize=9)
    
    # 添加颜色条
    cbar = plt.colorbar(im, ax=ax, label='IC值', pad=0.01)
    
    # 添加数值标注
    for i in range(len(factor_names)):
        for j in range(len(dates_list)):
            if not np.isnan(ic_matrix[i, j]):
                text = ax.text(j, i, f'{ic_matrix[i, j]:.2f}',
                            ha="center", va="center", 
                            color="white" if abs(ic_matrix[i, j]) > 0.075 else "black",
                            fontsize=8)
    
    ax.set_xlabel('日期', fontsize=12)
    ax.set_title('IC热力图 - 因子预测能力时序分布（修复版）', fontsize=14, fontweight='bold', pad=15)
    
    plt.tight_layout()
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"[OK] IC热力图已保存: {save_path}")
    plt.close()


def print_ic_summary_fixed(results: dict):
    """打印IC统计摘要"""
    print("\n" + "="*100)
    print("IC序列统计摘要（修复版 - 基于真实回测数据）")
    print("="*100)
    
    print(f"\n{'因子':<15} {'处理方式':<12} {'平均IC':<10} {'IC标准差':<12} {'IC IR':<10} {'IC>0占比':<12} {'样本数':<8}")
    print("-"*100)
    
    for label, data in results.items():
        ic = data['ic']
        if len(ic) == 0:
            continue
        
        factor = data['factor_name']
        neutralized = "行业中性" if data['neutralized'] else "原始"
        
        mean_ic = np.mean(ic)
        std_ic = np.std(ic)
        ic_ir = mean_ic / std_ic if std_ic > 0 else 0
        positive_ratio = (ic > 0).mean() * 100
        n_samples = len(ic)
        
        print(f"{factor:<15} {neutralized:<12} {mean_ic:>8.4f}   {std_ic:>8.4f}     {ic_ir:>8.4f}   {positive_ratio:>8.1f}%    {n_samples:>6}")
    
    print("\n" + "="*100)
    print("行业中性化效果对比")
    print("="*100)
    
    # 对比原始 vs 行业中性
    for factor in ['SP', 'BP', 'EP']:
        raw_key = f"{factor}_RAW"
        neu_key = f"{factor}_IND"
        
        if raw_key in results and neu_key in results:
            raw_ic = results[raw_key]['ic']
            neu_ic = results[neu_key]['ic']
            
            if len(raw_ic) > 0 and len(neu_ic) > 0:
                raw_mean = np.mean(raw_ic)
                neu_mean = np.mean(neu_ic)
                raw_ir = raw_mean / np.std(raw_ic) if np.std(raw_ic) > 0 else 0
                neu_ir = neu_mean / np.std(neu_ic) if np.std(neu_ic) > 0 else 0
                
                print(f"\n{factor}因子:")
                print(f"  原始:     平均IC={raw_mean:.4f}, IC IR={raw_ir:.4f}")
                print(f"  行业中性: 平均IC={neu_mean:.4f}, IC IR={neu_ir:.4f}")
                print(f"  改善:     平均IC{neu_mean-raw_mean:+.4f}, IC IR{neu_ir-raw_ir:+.4f}")
    
    print("="*100)


def main():
    """主函数"""
    print("="*80)
    print("IC Analysis (Fixed) - Based on Real Shenwan Industry Neutralized Backtest")
    print("="*80)
    print()
    
    analyzer = ICAnalyzer()
    
    # Run analysis (2023 full year)
    results = analyzer.analyze_all_factors("2023-01-01", "2024-01-01")
    
    if not results:
        print("[ERROR] No valid IC data obtained")
        return
    
    # Generate charts
    print("\nGenerating visualization charts...")
    plot_ic_series_fixed(results)
    plot_ic_comparison_fixed(results)
    plot_ic_heatmap_fixed(results)
    
    # Print summary
    print_ic_summary_fixed(results)
    
    print()
    print("="*80)
    print("Analysis complete! Charts saved to charts/ directory")
    print("="*80)


if __name__ == "__main__":
    main()
