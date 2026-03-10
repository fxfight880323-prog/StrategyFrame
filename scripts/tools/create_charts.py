"""
Create Visualization Charts for CTA+Earnings Analysis
=====================================================
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from datetime import date
# 路径设置
import sys
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', '..', 'Strategy_Framework', '02_Sector_Analysis'))

from CTA_Earnings_Sector_Analysis import (
    CTAEarningsCrossAnalyzer, MockDataProvider, SP500_SECTORS, setup_logger
)

print("Generating charts...")

# Get data
logger = setup_logger()
provider = MockDataProvider(logger)
analyzer = CTAEarningsCrossAnalyzer(provider, logger)
current_date = date(2024, 12, 31)

# Collect data
all_data = []
for sector, data in SP500_SECTORS.items():
    for ticker in data['tickers']:
        signal = analyzer.analyze_stock(ticker, current_date)
        if signal:
            all_data.append({
                'Ticker': signal.symbol,
                'Sector': signal.sector,
                'Combined_Score': signal.combined_score,
                'CTA_Signal': signal.cta_signal.name,
                'Earnings_Signal': signal.earnings_signal.name,
                'Trend_Score': signal.metadata.get('trend_score', 0),
                'Momentum_Score': signal.metadata.get('momentum_score', 0),
            })

df = pd.DataFrame(all_data)

# Chart 1: Sector Heatmap
print("  Creating sector heatmap...")
fig, ax = plt.subplots(figsize=(12, 8))
sector_scores = df.groupby('Sector')['Combined_Score'].mean().sort_values(ascending=True)

colors = ['#d73027' if x < 0 else '#fc8d59' if x < 10 else '#91bfdb' if x < 20 else '#4575b4' 
          for x in sector_scores.values]

bars = ax.barh(sector_scores.index, sector_scores.values, color=colors, edgecolor='black', linewidth=0.5)

for bar, val in zip(bars, sector_scores.values):
    width = bar.get_width()
    label_x = width + 0.5 if width >= 0 else width - 0.5
    ha = 'left' if width >= 0 else 'right'
    ax.text(label_x, bar.get_y() + bar.get_height()/2, f'{val:.1f}', 
           ha=ha, va='center', fontsize=10, fontweight='bold')

ax.set_xlabel('Combined Score', fontsize=12, fontweight='bold')
ax.set_title('CTA + Earnings Cross Analysis\nS&P 500 Sector Ranking', fontsize=14, fontweight='bold')
ax.axvline(x=0, color='black', linestyle='-', linewidth=0.8)
ax.grid(axis='x', alpha=0.3)
ax.set_xlim(-5, 25)

legend_elements = [
    mpatches.Patch(color='#4575b4', label='Strong Buy (>20)'),
    mpatches.Patch(color='#91bfdb', label='Buy (10-20)'),
    mpatches.Patch(color='#fc8d59', label='Neutral (0-10)'),
    mpatches.Patch(color='#d73027', label='Avoid (<0)')
]
ax.legend(handles=legend_elements, loc='lower right')

plt.tight_layout()
plt.savefig('sector_heatmap.png', dpi=150, bbox_inches='tight')
print("    Saved: sector_heatmap.png")
plt.close()

# Chart 2: Top 20 Stocks
print("  Creating top stocks chart...")
fig, ax = plt.subplots(figsize=(12, 8))
top20 = df.nlargest(20, 'Combined_Score')

colors = ['#27ae60' if x >= 30 else '#3498db' if x >= 20 else '#95a5a6' for x in top20['Combined_Score']]
bars = ax.barh(range(len(top20)), top20['Combined_Score'].values, color=colors)
ax.set_yticks(range(len(top20)))
ax.set_yticklabels([f"{t} ({s})" for t, s in zip(top20['Ticker'], top20['Sector'])], fontsize=9)
ax.set_xlabel('Combined Score', fontsize=12, fontweight='bold')
ax.set_title('Top 20 Stocks - CTA + Earnings', fontsize=14, fontweight='bold')
ax.invert_yaxis()

for i, (bar, val) in enumerate(zip(bars, top20['Combined_Score'])):
    ax.text(val + 0.5, bar.get_y() + bar.get_height()/2, f'{val:.1f}', 
           va='center', fontsize=9)

ax.grid(axis='x', alpha=0.3)
plt.tight_layout()
plt.savefig('top_stocks.png', dpi=150, bbox_inches='tight')
print("    Saved: top_stocks.png")
plt.close()

# Chart 3: Score Distribution
print("  Creating score distribution...")
fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Distribution histogram
ax1 = axes[0]
ax1.hist(df['Combined_Score'], bins=25, color='steelblue', edgecolor='black', alpha=0.7)
ax1.axvline(df['Combined_Score'].mean(), color='red', linestyle='--', linewidth=2, 
           label=f'Mean: {df["Combined_Score"].mean():.1f}')
ax1.axvline(0, color='black', linestyle='-', linewidth=1)
ax1.set_xlabel('Combined Score')
ax1.set_ylabel('Number of Stocks')
ax1.set_title('Score Distribution')
ax1.legend()
ax1.grid(alpha=0.3)

# Bull/Bear by sector
ax2 = axes[1]
sector_counts = df.groupby('Sector').apply(
    lambda x: pd.Series({
        'Strong Buy': len(x[x['Combined_Score'] >= 30]),
        'Buy': len(x[(x['Combined_Score'] >= 15) & (x['Combined_Score'] < 30)]),
        'Neutral': len(x[(x['Combined_Score'] > -10) & (x['Combined_Score'] < 15)]),
        'Sell': len(x[x['Combined_Score'] <= -10])
    })
)
sector_counts = sector_counts.sort_values('Strong Buy', ascending=True)
sector_counts.plot(kind='barh', stacked=True, ax=ax2, 
                  color=['#27ae60', '#3498db', '#f39c12', '#e74c3c'])
ax2.set_xlabel('Number of Stocks')
ax2.set_title('Recommendation Distribution by Sector')
ax2.legend(loc='lower right')

plt.tight_layout()
plt.savefig('score_distribution.png', dpi=150, bbox_inches='tight')
print("    Saved: score_distribution.png")
plt.close()

# Chart 4: CTA vs Earnings Matrix
print("  Creating CTA vs Earnings matrix...")
fig, ax = plt.subplots(figsize=(10, 8))

cta_map = {'STRONG_BUY': 3, 'BUY': 2, 'WEAK_BUY': 1, 'HOLD': 0, 
           'WEAK_SELL': -1, 'SELL': -2, 'STRONG_SELL': -3}
earnings_map = {'STRONG_BUY': 3, 'BUY': 2, 'WEAK_BUY': 1, 'HOLD': 0, 
                'WEAK_SELL': -1, 'SELL': -2, 'STRONG_SELL': -3}

df['CTA_Val'] = df['CTA_Signal'].map(cta_map)
df['Earnings_Val'] = df['Earnings_Signal'].map(earnings_map)

scatter = ax.scatter(df['CTA_Val'], df['Earnings_Val'], c=df['Combined_Score'], 
                    cmap='RdYlGn', s=100, alpha=0.6, edgecolors='black', linewidth=0.5)
ax.axhline(y=0, color='black', linestyle='--', alpha=0.3)
ax.axvline(x=0, color='black', linestyle='--', alpha=0.3)
ax.set_xlabel('CTA Signal', fontsize=12, fontweight='bold')
ax.set_ylabel('Earnings Signal', fontsize=12, fontweight='bold')
ax.set_title('CTA vs Earnings Signal Matrix', fontsize=14, fontweight='bold')
ax.set_xticks([-3, -2, -1, 0, 1, 2, 3])
ax.set_xticklabels(['Strong\nSell', 'Sell', 'Weak\nSell', 'Hold', 'Weak\nBuy', 'Buy', 'Strong\nBuy'])
ax.set_yticks([-3, -2, -1, 0, 1, 2, 3])
ax.set_yticklabels(['Strong\nSell', 'Sell', 'Weak\nSell', 'Hold', 'Weak\nBuy', 'Buy', 'Strong\nBuy'])
ax.grid(alpha=0.3)
plt.colorbar(scatter, ax=ax, label='Combined Score')
plt.tight_layout()
plt.savefig('cta_earnings_matrix.png', dpi=150, bbox_inches='tight')
print("    Saved: cta_earnings_matrix.png")
plt.close()

print("\nAll charts generated successfully!")
print("  - sector_heatmap.png")
print("  - top_stocks.png")
print("  - score_distribution.png")
print("  - cta_earnings_matrix.png")
