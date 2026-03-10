"""
CTA + Earnings Detailed Analysis with Visualization
====================================================

Generate detailed stock-level analysis and visualizations for CTA-Earnings cross signals.

Outputs:
- Interactive charts (sector heatmap, score distribution, trend analysis)
- Excel report with detailed stock metrics
- Top/bottom picks for each sector
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Rectangle
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import logging
import warnings
warnings.filterwarnings('ignore')

# Import previous modules
from CTA_Earnings_Sector_Analysis import (
    CTAEarningsCrossAnalyzer, MockDataProvider, SP500_SECTORS,
    get_sector_for_ticker, setup_logger
)

# Set up matplotlib for Chinese characters
plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False


class DetailedAnalyzer:
    """Generate detailed analysis with visualizations"""
    
    def __init__(self, analyzer: CTAEarningsCrossAnalyzer):
        self.analyzer = analyzer
        self.logger = setup_logger()
        self.results_cache = {}
    
    def analyze_all_stocks(self, current_date: date) -> pd.DataFrame:
        """Analyze all S&P 500 stocks and return DataFrame"""
        all_tickers = [t for sector in SP500_SECTORS.values() for t in sector['tickers']]
        
        data = []
        for ticker in all_tickers:
            signal = self.analyzer.analyze_stock(ticker, current_date)
            if signal:
                data.append({
                    'Ticker': signal.symbol,
                    'Sector': signal.sector,
                    'CTA_Signal': signal.cta_signal.name,
                    'Earnings_Signal': signal.earnings_signal.name,
                    'Combined_Score': signal.combined_score,
                    'CTA_Weight': signal.cta_weight,
                    'Earnings_Weight': signal.earnings_weight,
                    'Trend_Score': signal.metadata.get('trend_score', 0),
                    'Momentum_Score': signal.metadata.get('momentum_score', 0),
                    'Price': signal.metadata.get('price', 0),
                    'RSI': signal.metadata.get('rsi', 0),
                    'EPS_Surprise': signal.metadata.get('eps_surprise', 0),
                    'Revenue_Surprise': signal.metadata.get('revenue_surprise', 0),
                })
        
        df = pd.DataFrame(data)
        return df.sort_values('Combined_Score', ascending=False)
    
    def get_sector_details(self, sector: str, current_date: date) -> pd.DataFrame:
        """Get detailed analysis for a specific sector"""
        tickers = SP500_SECTORS.get(sector, {}).get('tickers', [])
        
        data = []
        for ticker in tickers:
            signal = self.analyzer.analyze_stock(ticker, current_date)
            if signal:
                data.append({
                    'Ticker': signal.symbol,
                    'CTA_Signal': signal.cta_signal.name,
                    'Earnings_Signal': signal.earnings_signal.name,
                    'Combined_Score': signal.combined_score,
                    'Trend_Score': signal.metadata.get('trend_score', 0),
                    'Momentum_Score': signal.metadata.get('momentum_score', 0),
                    'Price': signal.metadata.get('price', 0),
                    'RSI': signal.metadata.get('rsi', 0),
                    'EPS_Surprise_Pct': signal.metadata.get('eps_surprise', 0),
                    'Revenue_Surprise_Pct': signal.metadata.get('revenue_surprise', 0),
                    'Recommendation': self._get_recommendation(signal.combined_score)
                })
        
        df = pd.DataFrame(data)
        return df.sort_values('Combined_Score', ascending=False)
    
    def _get_recommendation(self, score: float) -> str:
        """Get recommendation based on score"""
        if score >= 30:
            return "Strong Buy"
        elif score >= 15:
            return "Buy"
        elif score >= 5:
            return "Weak Buy"
        elif score >= -5:
            return "Hold"
        elif score >= -15:
            return "Weak Sell"
        elif score >= -30:
            return "Sell"
        else:
            return "Strong Sell"
    
    def create_sector_heatmap(self, df: pd.DataFrame, save_path: str = None):
        """Create sector heatmap visualization"""
        # Prepare data for heatmap
        pivot_data = df.groupby(['Sector'])['Combined_Score'].mean().sort_values(ascending=True)
        
        fig, ax = plt.subplots(figsize=(12, 8))
        
        # Create color map
        colors = ['#d73027' if x < -10 else '#fc8d59' if x < 0 else '#91bfdb' if x < 15 else '#4575b4' 
                  for x in pivot_data.values]
        
        bars = ax.barh(pivot_data.index, pivot_data.values, color=colors, edgecolor='black', linewidth=0.5)
        
        # Add value labels
        for bar, val in zip(bars, pivot_data.values):
            width = bar.get_width()
            label_x = width + 1 if width >= 0 else width - 1
            ha = 'left' if width >= 0 else 'right'
            ax.text(label_x, bar.get_y() + bar.get_height()/2, f'{val:.2f}', 
                   ha=ha, va='center', fontsize=10, fontweight='bold')
        
        ax.set_xlabel('Combined Score', fontsize=12, fontweight='bold')
        ax.set_title('CTA + Earnings Cross Analysis\nSector Ranking (S&P 500)', fontsize=14, fontweight='bold')
        ax.axvline(x=0, color='black', linestyle='-', linewidth=0.8)
        ax.grid(axis='x', alpha=0.3)
        ax.set_xlim(-20, 25)
        
        # Add legend
        legend_elements = [
            mpatches.Patch(color='#4575b4', label='Overweight (Score > 15)'),
            mpatches.Patch(color='#91bfdb', label='Neutral (0-15)'),
            mpatches.Patch(color='#fc8d59', label='Cautious (-10-0)'),
            mpatches.Patch(color='#d73027', label='Underweight (< -10)')
        ]
        ax.legend(handles=legend_elements, loc='lower right', fontsize=9)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Sector heatmap saved: {save_path}")
        
        return fig
    
    def create_score_distribution(self, df: pd.DataFrame, save_path: str = None):
        """Create score distribution chart"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 1. Combined Score Distribution
        ax1 = axes[0, 0]
        ax1.hist(df['Combined_Score'], bins=30, color='steelblue', edgecolor='black', alpha=0.7)
        ax1.axvline(df['Combined_Score'].mean(), color='red', linestyle='--', linewidth=2, label=f'Mean: {df["Combined_Score"].mean():.2f}')
        ax1.axvline(0, color='black', linestyle='-', linewidth=1)
        ax1.set_xlabel('Combined Score')
        ax1.set_ylabel('Number of Stocks')
        ax1.set_title('Combined Score Distribution')
        ax1.legend()
        ax1.grid(alpha=0.3)
        
        # 2. CTA vs Earnings Score Scatter
        ax2 = axes[0, 1]
        cta_scores = []
        earnings_scores = []
        for _, row in df.iterrows():
            cta_score = (row['Trend_Score'] + row['Momentum_Score']) / 2 - 50
            earnings_score = (row['EPS_Surprise'] + row['Revenue_Surprise']) / 2
            cta_scores.append(cta_score)
            earnings_scores.append(earnings_score)
        
        scatter = ax2.scatter(cta_scores, earnings_scores, c=df['Combined_Score'], 
                            cmap='RdYlGn', alpha=0.6, s=50)
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax2.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
        ax2.set_xlabel('CTA Score')
        ax2.set_ylabel('Earnings Score')
        ax2.set_title('CTA vs Earnings Score')
        plt.colorbar(scatter, ax=ax2, label='Combined Score')
        
        # 3. Sector Bull/Bear Count
        ax3 = axes[1, 0]
        sector_stats = df.groupby('Sector').apply(
            lambda x: pd.Series({
                'Bullish': len(x[x['Combined_Score'] > 15]),
                'Neutral': len(x[(x['Combined_Score'] >= -10) & (x['Combined_Score'] <= 15)]),
                'Bearish': len(x[x['Combined_Score'] < -10])
            })
        )
        
        sector_stats.plot(kind='barh', stacked=True, ax=ax3, 
                         color=['#2ecc71', '#f1c40f', '#e74c3c'])
        ax3.set_xlabel('Number of Stocks')
        ax3.set_title('Bullish/Neutral/Bearish Distribution by Sector')
        ax3.legend(loc='lower right')
        
        # 4. Top 10 Stocks
        ax4 = axes[1, 1]
        top10 = df.nlargest(10, 'Combined_Score')
        colors = ['#2ecc71' if x >= 30 else '#3498db' if x >= 15 else '#95a5a6' for x in top10['Combined_Score']]
        bars = ax4.barh(top10['Ticker'], top10['Combined_Score'], color=colors)
        ax4.set_xlabel('Combined Score')
        ax4.set_title('Top 10 Stocks by Combined Score')
        ax4.invert_yaxis()
        
        # Add value labels
        for bar, val in zip(bars, top10['Combined_Score']):
            ax4.text(val + 1, bar.get_y() + bar.get_height()/2, f'{val:.1f}', 
                    va='center', fontsize=9)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Score distribution chart saved: {save_path}")
        
        return fig
    
    def create_sector_detail_chart(self, sector: str, current_date: date, save_path: str = None):
        """Create detailed chart for a specific sector"""
        df = self.get_sector_details(sector, current_date)
        
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle(f'{sector} Sector - Detailed Analysis', fontsize=16, fontweight='bold')
        
        # 1. Stock Scores
        ax1 = axes[0, 0]
        colors = ['#2ecc71' if x >= 30 else '#3498db' if x >= 15 else '#f1c40f' if x >= -10 else '#e74c3c' 
                  for x in df['Combined_Score']]
        bars = ax1.barh(df['Ticker'], df['Combined_Score'], color=colors)
        ax1.set_xlabel('Combined Score')
        ax1.set_title('Stock Scores')
        ax1.axvline(x=0, color='black', linestyle='-', linewidth=0.8)
        
        # 2. CTA vs Earnings Breakdown
        ax2 = axes[0, 1]
        x = np.arange(len(df))
        width = 0.35
        ax2.bar(x - width/2, df['Trend_Score'], width, label='Trend Score', color='#3498db')
        ax2.bar(x + width/2, df['Momentum_Score'], width, label='Momentum Score', color='#9b59b6')
        ax2.set_xticks(x)
        ax2.set_xticklabels(df['Ticker'], rotation=45, ha='right')
        ax2.set_ylabel('Score')
        ax2.set_title('CTA Component Breakdown')
        ax2.legend()
        ax2.grid(axis='y', alpha=0.3)
        
        # 3. EPS Surprise
        ax3 = axes[1, 0]
        colors = ['#2ecc71' if x > 0 else '#e74c3c' for x in df['EPS_Surprise_Pct']]
        ax3.bar(df['Ticker'], df['EPS_Surprise_Pct'], color=colors)
        ax3.set_xticklabels(df['Ticker'], rotation=45, ha='right')
        ax3.set_ylabel('EPS Surprise %')
        ax3.set_title('Earnings Surprise')
        ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
        ax3.grid(axis='y', alpha=0.3)
        
        # 4. RSI Distribution
        ax4 = axes[1, 1]
        ax4.scatter(df['RSI'], df['Combined_Score'], s=100, alpha=0.6, c=df['Combined_Score'], cmap='RdYlGn')
        ax4.axvline(x=70, color='red', linestyle='--', label='Overbought (70)')
        ax4.axvline(x=30, color='green', linestyle='--', label='Oversold (30)')
        ax4.set_xlabel('RSI')
        ax4.set_ylabel('Combined Score')
        ax4.set_title('RSI vs Combined Score')
        ax4.legend()
        ax4.grid(alpha=0.3)
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"{sector} detail chart saved: {save_path}")
        
        return fig
    
    def export_to_excel(self, df: pd.DataFrame, sector_analyses: List, save_path: str = 'CTA_Earnings_Analysis.xlsx'):
        """Export detailed analysis to Excel"""
        with pd.ExcelWriter(save_path, engine='openpyxl') as writer:
            # Sheet 1: All Stocks Summary
            df.to_excel(writer, sheet_name='All Stocks', index=False)
            
            # Sheet 2: Sector Summary
            sector_df = pd.DataFrame([
                {
                    'Sector': a.sector,
                    'Avg_Score': a.avg_combined_score,
                    'Bullish_Count': a.bullish_stocks,
                    'Bearish_Count': a.bearish_stocks,
                    'Top_Picks': ', '.join(a.top_picks[:3]),
                    'Trend': a.momentum_trend,
                    'Recommendation': a.recommendation
                }
                for a in sector_analyses
            ])
            sector_df.to_excel(writer, sheet_name='Sector Summary', index=False)
            
            # Sheet 3: Top Picks
            top_picks = df[df['Combined_Score'] >= 20].sort_values('Combined_Score', ascending=False)
            top_picks.to_excel(writer, sheet_name='Top Picks (Score>=20)', index=False)
            
            # Sheet 4: Stocks to Avoid
            bottom_picks = df[df['Combined_Score'] <= -15].sort_values('Combined_Score')
            bottom_picks.to_excel(writer, sheet_name='Stocks to Avoid (Score<=-15)', index=False)
            
            # Sheet 5: Per Sector Details (separate sheets)
            for sector in SP500_SECTORS.keys():
                sector_df = df[df['Sector'] == sector].sort_values('Combined_Score', ascending=False)
                sheet_name = sector[:31]  # Excel sheet name max 31 chars
                sector_df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        print(f"Excel report saved: {save_path}")
        return save_path


def main():
    """Main execution"""
    print("="*100)
    print("CTA + EARNINGS DETAILED ANALYSIS WITH VISUALIZATION")
    print("="*100)
    print()
    
    # Initialize
    logger = setup_logger()
    provider = MockDataProvider(logger)
    analyzer = CTAEarningsCrossAnalyzer(provider, logger)
    detailed = DetailedAnalyzer(analyzer)
    
    current_date = date(2024, 12, 31)
    
    # Run analysis
    print("Analyzing all S&P 500 stocks...")
    df = detailed.analyze_all_stocks(current_date)
    
    print(f"Analyzed {len(df)} stocks")
    print()
    
    # Get sector analyses
    sector_analyses = analyzer.analyze_all_sectors(current_date)
    
    # Create visualizations
    print("Generating visualizations...")
    
    # 1. Sector heatmap
    fig1 = detailed.create_sector_heatmap(df, 'sector_heatmap.png')
    
    # 2. Score distribution
    fig2 = detailed.create_score_distribution(df, 'score_distribution.png')
    
    # 3. Detailed charts for top 3 sectors
    top_3_sectors = [a.sector for a in sector_analyses[:3]]
    for sector in top_3_sectors:
        detailed.create_sector_detail_chart(sector, current_date, f'{sector.replace(" ", "_")}_detail.png')
    
    # Export to Excel
    print("\nExporting to Excel...")
    detailed.export_to_excel(df, sector_analyses, 'CTA_Earnings_Detailed_Analysis.xlsx')
    
    # Print detailed summary
    print("\n" + "="*100)
    print("TOP 20 STOCKS - DETAILED METRICS")
    print("="*100)
    print()
    
    top20 = df.head(20)
    print(top20[['Ticker', 'Sector', 'Combined_Score', 'CTA_Signal', 'Earnings_Signal', 
                'Trend_Score', 'Momentum_Score', 'EPS_Surprise', 'Revenue_Surprise']].to_string(index=False))
    
    print("\n" + "="*100)
    print("BOTTOM 10 STOCKS - TO AVOID")
    print("="*100)
    print()
    
    bottom10 = df.tail(10)
    print(bottom10[['Ticker', 'Sector', 'Combined_Score', 'CTA_Signal', 'Earnings_Signal']].to_string(index=False))
    
    # Sector-wise top picks
    print("\n" + "="*100)
    print("SECTOR-WISE TOP PICKS")
    print("="*100)
    print()
    
    for sector in ['Technology', 'Healthcare', 'Financials', 'Energy']:
        sector_df = df[df['Sector'] == sector].head(3)
        print(f"\n{sector.upper()}:")
        for _, row in sector_df.iterrows():
            print(f"  {row['Ticker']:<6} Score: {row['Combined_Score']:>6.2f}  "
                  f"CTA: {row['CTA_Signal']:<12}  Earnings: {row['Earnings_Signal']:<12}")
    
    print("\n" + "="*100)
    print("Analysis complete! Generated files:")
    print("  - sector_heatmap.png")
    print("  - score_distribution.png")
    print("  - [Sector]_detail.png (for top 3 sectors)")
    print("  - CTA_Earnings_Detailed_Analysis.xlsx")
    print("="*100)
    
    plt.show()


if __name__ == "__main__":
    main()
