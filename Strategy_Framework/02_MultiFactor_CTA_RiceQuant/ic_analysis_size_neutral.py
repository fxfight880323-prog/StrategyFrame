"""
IC序列分析 - 市值中性化 vs 行业中性化 vs 双中性化
=================================================

对比四种处理方式：
1. 原始因子 (RAW)
2. 市值中性化 (SIZE)
3. 行业中性化 (IND)
4. 市值+行业双中性化 (DOUBLE)

作者: AI Assistant
日期: 2026-03-09
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
from scipy.stats import spearmanr
import warnings
import sys
import os

plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
warnings.filterwarnings('ignore')

import rqdatac as rq
from industry_neutralized_backtest import IndustryNeutralizedBacktest


class ICAnalyzerComplete:
    """完整IC分析器（含市值和行业中性化）"""
    
    def __init__(self):
        self.engine = IndustryNeutralizedBacktest()
    
    def calculate_ic(self, factor_values, forward_returns):
        """计算Spearman IC"""
        common_index = factor_values.index.intersection(forward_returns.index)
        if len(common_index) < 10:
            return np.nan
        f = factor_values[common_index]
        r = forward_returns[common_index]
        corr, _ = spearmanr(f.rank(), r.rank())
        return corr
    
    def backtest_with_ic(self, factor_name, start, end,
                        industry_neutral=False, size_neutral=False):
        """回测并计算IC序列"""
        dates = pd.date_range(start=start, end=end, freq='ME')
        if len(dates) < 2:
            return {}
        
        ic_list = []
        ic_dates = []
        
        for i in range(1, len(dates)):
            curr_date = dates[i].strftime('%Y-%m-%d')
            prev_date = dates[i-1].strftime('%Y-%m-%d')
            
            stocks = self.engine.get_stocks(prev_date)
            if not stocks or len(stocks) < 50:
                continue
            
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
            
            forward_ret = self._calc_forward_returns(list(signal.index), prev_date, curr_date)
            if forward_ret.empty:
                continue
            
            ic = self.calculate_ic(signal, forward_ret)
            if not np.isnan(ic):
                ic_list.append(ic)
                ic_dates.append(dates[i])
        
        mode = []
        if size_neutral:
            mode.append('SIZE')
        if industry_neutral:
            mode.append('IND')
        mode_str = '+'.join(mode) if mode else 'RAW'
        
        return {
            'dates': ic_dates,
            'ic': np.array(ic_list),
            'factor_name': factor_name,
            'mode': mode_str,
            'industry_neutral': industry_neutral,
            'size_neutral': size_neutral
        }
    
    def _calc_forward_returns(self, stocks, start, end):
        """计算未来收益"""
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
    
    def analyze_factor_all_modes(self, factor_name, start="2023-01-01", end="2024-01-01"):
        """分析单个因子的所有中性化模式"""
        print(f"\n分析 {factor_name} 因子...")
        
        modes = [
            (False, False, "原始"),
            (True, False, "市值中性"),
            (False, True, "行业中性"),
            (True, True, "双中性")
        ]
        
        results = {}
        for size_neu, ind_neu, label in modes:
            result = self.backtest_with_ic(factor_name, start, end,
                                          industry_neutral=ind_neu,
                                          size_neutral=size_neu)
            if result and len(result['ic']) > 0:
                results[label] = result
                ic_ir = np.mean(result['ic']) / np.std(result['ic']) if np.std(result['ic']) > 0 else 0
                print(f"  {label:8s}: 样本={len(result['ic']):2d}, 平均IC={np.mean(result['ic']):.4f}, IC IR={ic_ir:.4f}")
        
        return results


def plot_ic_comparison_complete(all_results, save_path='charts/ic_size_neutral_comparison.png'):
    """绘制完整IC对比图（4种模式）"""
    fig = plt.figure(figsize=(18, 12))
    gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.25)
    
    colors = {
        '原始': '#e74c3c',
        '市值中性': '#3498db',
        '行业中性': '#2ecc71',
        '双中性': '#9b59b6'
    }
    
    factors = ['SP', 'BP', 'EP']
    
    # === 第1行: IC时序图 ===
    for idx, factor in enumerate(factors):
        ax = fig.add_subplot(gs[0, idx if idx < 2 else 1])
        
        if factor not in all_results:
            continue
        
        factor_results = all_results[factor]
        for label, data in factor_results.items():
            if label in colors and len(data['ic']) > 0:
                ax.plot(data['dates'], data['ic'], 
                       label=label, color=colors[label], 
                       linewidth=2, marker='o', markersize=4, alpha=0.8)
        
        ax.axhline(y=0, color='black', linestyle='--', alpha=0.5)
        ax.axhline(y=0.02, color='green', linestyle=':', alpha=0.5)
        ax.axhline(y=-0.02, color='red', linestyle=':', alpha=0.5)
        ax.fill_between(ax.get_xlim(), 0, 0.15, alpha=0.1, color='green')
        ax.fill_between(ax.get_xlim(), -0.15, 0, alpha=0.1, color='red')
        
        ax.set_ylabel('IC', fontsize=10)
        ax.set_title(f'{factor}因子 IC序列', fontsize=12, fontweight='bold')
        if idx == 0:
            ax.legend(loc='upper right', fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.set_ylim(-0.15, 0.15)
        
        if data['dates']:
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
    
    # === 第2行: 箱线图 ===
    ax_box = fig.add_subplot(gs[1, :])
    
    box_data = []
    box_labels = []
    box_colors = []
    
    for factor in factors:
        if factor not in all_results:
            continue
        for label in ['原始', '市值中性', '行业中性', '双中性']:
            if label in all_results[factor]:
                box_data.append(all_results[factor][label]['ic'])
                box_labels.append(f"{factor}\n{label}")
                box_colors.append(colors[label])
    
    if box_data:
        bp = ax_box.boxplot(box_data, labels=box_labels, patch_artist=True)
        for patch, color in zip(bp['boxes'], box_colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.6)
        
        ax_box.axhline(y=0, color='black', linestyle='-', linewidth=1)
        ax_box.axhline(y=0.02, color='green', linestyle='--', alpha=0.5)
        ax_box.set_ylabel('IC值', fontsize=11)
        ax_box.set_title('IC分布对比', fontsize=13, fontweight='bold')
        ax_box.grid(True, alpha=0.3, axis='y')
    
    # === 第3行: 统计指标 ===
    ax_stats = fig.add_subplot(gs[2, :])
    
    stats_rows = []
    for factor in factors:
        if factor not in all_results:
            continue
        factor_results = all_results[factor]
        for label in ['原始', '市值中性', '行业中性', '双中性']:
            if label in factor_results:
                ic = factor_results[label]['ic']
                stats_rows.append({
                    'name': f"{factor}-{label}",
                    'mean': np.mean(ic),
                    'std': np.std(ic),
                    'ir': np.mean(ic) / np.std(ic) if np.std(ic) > 0 else 0,
                    'pos_ratio': (ic > 0).mean() * 100,
                    'color': colors[label]
                })
    
    if stats_rows:
        x = np.arange(len(stats_rows))
        width = 0.25
        
        means = [r['mean'] for r in stats_rows]
        stds = [r['std'] for r in stats_rows]
        irs = [r['ir'] for r in stats_rows]
        
        bars1 = ax_stats.bar(x - width, means, width, label='平均IC', color='steelblue', alpha=0.8)
        bars2 = ax_stats.bar(x, stds, width, label='IC标准差', color='coral', alpha=0.8)
        bars3 = ax_stats.bar(x + width, irs, width, label='IC IR', color='seagreen', alpha=0.8)
        
        # 数值标签
        for bar, val in zip(bars1, means):
            ax_stats.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                         f'{val:.3f}', ha='center', va='bottom', fontsize=7)
        for bar, val in zip(bars3, irs):
            ax_stats.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                         f'{val:.2f}', ha='center', va='bottom', fontsize=7, color='seagreen')
        
        ax_stats.axhline(y=0, color='black', linestyle='-', linewidth=1)
        ax_stats.set_xticks(x)
        ax_stats.set_xticklabels([r['name'] for r in stats_rows], rotation=45, ha='right', fontsize=8)
        ax_stats.set_ylabel('值', fontsize=11)
        ax_stats.set_title('IC统计指标对比', fontsize=13, fontweight='bold')
        ax_stats.legend(fontsize=9, loc='upper right')
        ax_stats.grid(True, alpha=0.3, axis='y')
    
    plt.suptitle('IC分析完整对比 - 原始 vs 市值中性 vs 行业中性 vs 双中性', 
                fontsize=15, fontweight='bold', y=0.98)
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"[OK] 完整IC对比图已保存: {save_path}")
    plt.close()


def plot_ic_heatmap_complete(all_results, save_path='charts/ic_size_neutral_heatmap.png'):
    """绘制IC热力图（按月份）"""
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    axes = axes.flatten()
    
    factors = ['SP', 'BP', 'EP']
    modes = ['原始', '市值中性', '行业中性', '双中性']
    
    for idx, mode in enumerate(modes):
        ax = axes[idx]
        
        # 收集该模式下的所有IC数据
        dates_set = set()
        ic_data = {}
        
        for factor in factors:
            if factor in all_results and mode in all_results[factor]:
                data = all_results[factor][mode]
                dates_set.update([d.strftime('%Y-%m') for d in data['dates']])
                ic_data[factor] = data
        
        dates_list = sorted(list(dates_set))
        if not dates_list:
            ax.text(0.5, 0.5, '无数据', ha='center', va='center', transform=ax.transAxes)
            ax.set_title(f'{mode}', fontsize=12)
            continue
        
        # 构建矩阵
        ic_matrix = np.full((len(factors), len(dates_list)), np.nan)
        for i, factor in enumerate(factors):
            if factor in ic_data:
                date_strs = [d.strftime('%Y-%m') for d in ic_data[factor]['dates']]
                for j, date_str in enumerate(dates_list):
                    if date_str in date_strs:
                        idx_date = date_strs.index(date_str)
                        ic_matrix[i, j] = ic_data[factor]['ic'][idx_date]
        
        # 绘制热力图
        im = ax.imshow(ic_matrix, aspect='auto', cmap='RdYlGn', vmin=-0.15, vmax=0.15)
        
        ax.set_yticks(np.arange(len(factors)))
        ax.set_yticklabels(factors, fontsize=10)
        ax.set_xticks(np.arange(len(dates_list)))
        ax.set_xticklabels(dates_list, rotation=45, ha='right', fontsize=8)
        
        # 添加数值标注
        for i in range(len(factors)):
            for j in range(len(dates_list)):
                if not np.isnan(ic_matrix[i, j]):
                    text = ax.text(j, i, f'{ic_matrix[i, j]:.2f}',
                                 ha="center", va="center",
                                 color="white" if abs(ic_matrix[i, j]) > 0.075 else "black",
                                 fontsize=8)
        
        ax.set_title(f'{mode}', fontsize=12, fontweight='bold')
        plt.colorbar(im, ax=ax, label='IC', pad=0.01)
    
    plt.suptitle('IC热力图 - 四种处理方式对比', fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    plt.savefig(save_path, dpi=300, bbox_inches='tight')
    print(f"[OK] IC热力图已保存: {save_path}")
    plt.close()


def print_summary_complete(all_results):
    """打印完整统计摘要"""
    print("\n" + "="*120)
    print("IC分析完整对比 - 市值中性化 vs 行业中性化 vs 双中性化")
    print("="*120)
    
    factors = ['SP', 'BP', 'EP']
    modes = ['原始', '市值中性', '行业中性', '双中性']
    
    # 表头
    print(f"\n{'因子':<6} {'处理方式':<10} {'平均IC':<10} {'IC标准差':<12} {'IC IR':<10} {'IC>0%':<10} {'样本':<6}")
    print("-"*120)
    
    for factor in factors:
        if factor not in all_results:
            continue
        
        for mode in modes:
            if mode not in all_results[factor]:
                continue
            
            data = all_results[factor][mode]
            ic = data['ic']
            
            mean_ic = np.mean(ic)
            std_ic = np.std(ic)
            ic_ir = mean_ic / std_ic if std_ic > 0 else 0
            pos_ratio = (ic > 0).mean() * 100
            n = len(ic)
            
            print(f"{factor:<6} {mode:<10} {mean_ic:>8.4f}   {std_ic:>8.4f}     {ic_ir:>8.4f}   {pos_ratio:>7.1f}%   {n:>4}")
        print("-"*120)
    
    # 中性化效果对比
    print("\n" + "="*120)
    print("中性化效果对比")
    print("="*120)
    
    for factor in factors:
        if factor not in all_results:
            continue
        
        print(f"\n【{factor}因子】")
        
        if '原始' in all_results[factor]:
            raw_ic = all_results[factor]['原始']['ic']
            raw_ir = np.mean(raw_ic) / np.std(raw_ic) if np.std(raw_ic) > 0 else 0
            
            for mode in ['市值中性', '行业中性', '双中性']:
                if mode in all_results[factor]:
                    neu_ic = all_results[factor][mode]['ic']
                    neu_ir = np.mean(neu_ic) / np.std(neu_ic) if np.std(neu_ic) > 0 else 0
                    
                    mean_change = np.mean(neu_ic) - np.mean(raw_ic)
                    ir_change = neu_ir - raw_ir
                    
                    print(f"  {mode:8s}: 平均IC {np.mean(raw_ic):.4f} -> {np.mean(neu_ic):.4f} ({mean_change:+.4f}), "
                          f"IC IR {raw_ir:.4f} -> {neu_ir:.4f} ({ir_change:+.4f})")
    
    print("="*120)


def main():
    print("="*120)
    print("IC序列分析 - 市值中性化 vs 行业中性化 vs 双中性化")
    print("="*120)
    
    analyzer = ICAnalyzerComplete()
    
    factors = ['SP', 'BP', 'EP']
    all_results = {}
    
    for factor in factors:
        results = analyzer.analyze_factor_all_modes(factor, "2023-01-01", "2024-01-01")
        if results:
            all_results[factor] = results
    
    if not all_results:
        print("[ERROR] 未获得有效数据")
        return
    
    print("\n生成可视化图表...")
    plot_ic_comparison_complete(all_results)
    plot_ic_heatmap_complete(all_results)
    
    print_summary_complete(all_results)
    
    print("\n" + "="*120)
    print("分析完成！")
    print("="*120)


if __name__ == "__main__":
    main()
