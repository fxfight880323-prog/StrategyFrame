"""
Quick Sector Analysis Report Generator
======================================

Generate Excel report with detailed stock-level analysis
"""

import pandas as pd
import numpy as np
from datetime import date
# 路径设置
import sys
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', '..', 'Strategy_Framework', '02_Sector_Analysis'))

from CTA_Earnings_Sector_Analysis import (
    CTAEarningsCrossAnalyzer, MockDataProvider, SP500_SECTORS, setup_logger
)

print("="*80)
print("S&P 500 CTA + Earnings Cross Analysis")
print("="*80)
print()

# Initialize
logger = setup_logger()
provider = MockDataProvider(logger)
analyzer = CTAEarningsCrossAnalyzer(provider, logger)

current_date = date(2024, 12, 31)

# Analyze all stocks
print("Analyzing S&P 500 stocks...")
all_data = []

for sector, data in SP500_SECTORS.items():
    print(f"  Processing {sector}...")
    for ticker in data['tickers']:
        signal = analyzer.analyze_stock(ticker, current_date)
        if signal:
            all_data.append({
                'Ticker': signal.symbol,
                'Sector': signal.sector,
                'CTA_Signal': signal.cta_signal.name,
                'Earnings_Signal': signal.earnings_signal.name,
                'Combined_Score': round(signal.combined_score, 2),
                'Trend_Score': round(signal.metadata.get('trend_score', 0), 1),
                'Momentum_Score': round(signal.metadata.get('momentum_score', 0), 1),
                'Price': round(signal.metadata.get('price', 0), 2),
                'RSI': round(signal.metadata.get('rsi', 0), 1),
                'EPS_Surprise_Pct': round(signal.metadata.get('eps_surprise', 0), 2),
                'Revenue_Surprise_Pct': round(signal.metadata.get('revenue_surprise', 0), 2),
            })

df = pd.DataFrame(all_data)
df = df.sort_values('Combined_Score', ascending=False)

print(f"\nAnalyzed {len(df)} stocks")
print()

# Create Excel report
print("Generating Excel report...")
with pd.ExcelWriter('SP500_CTA_Earnings_Analysis.xlsx', engine='openpyxl') as writer:
    # All stocks sorted by score
    df.to_excel(writer, sheet_name='All Stocks Ranked', index=False)
    
    # Top picks
    top_picks = df[df['Combined_Score'] >= 20]
    top_picks.to_excel(writer, sheet_name='Strong Buy (Score>=20)', index=False)
    
    # Bottom picks
    bottom_picks = df[df['Combined_Score'] <= -15]
    bottom_picks.to_excel(writer, sheet_name='Sell (Score<=-15)', index=False)
    
    # Per sector
    for sector in SP500_SECTORS.keys():
        sector_df = df[df['Sector'] == sector].sort_values('Combined_Score', ascending=False)
        sheet_name = sector[:31]
        sector_df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    # Sector summary
    sector_summary = df.groupby('Sector').agg({
        'Combined_Score': 'mean',
        'Ticker': 'count'
    }).round(2)
    sector_summary.columns = ['Avg_Score', 'Stock_Count']
    sector_summary = sector_summary.sort_values('Avg_Score', ascending=False)
    sector_summary.to_excel(writer, sheet_name='Sector Summary')

print("Excel report saved: SP500_CTA_Earnings_Analysis.xlsx")

# Print summary
print("\n" + "="*80)
print("TOP 20 STOCKS (CTA + Earnings)")
print("="*80)
print(df.head(20)[['Ticker', 'Sector', 'Combined_Score', 'CTA_Signal', 'Earnings_Signal']].to_string(index=False))

print("\n" + "="*80)
print("SECTOR RANKING")
print("="*80)
print(sector_summary.to_string())

print("\n" + "="*80)
print("SECTOR-WISE TOP PICKS")
print("="*80)

for sector in ['Technology', 'Healthcare', 'Financials', 'Energy', 'Real Estate']:
    top3 = df[df['Sector'] == sector].head(3)
    print(f"\n{sector}:")
    for _, row in top3.iterrows():
        print(f"  {row['Ticker']:<6} Score: {row['Combined_Score']:>6.2f}  "
              f"Trend: {row['Trend_Score']:>5.1f}  EPS: {row['EPS_Surprise_Pct']:>+6.1f}%")

print("\n" + "="*80)
print("Report generation complete!")
print("="*80)
