"""
RiceQuant Real Data CTA Demo
=============================

Using real futures data from RiceQuant for CTA backtesting
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# 路径设置
import sys
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
_SF = os.path.join(_DIR, '..', '..', 'Strategy_Framework')
sys.path.insert(0, os.path.join(_SF, 'data_providers'))
sys.path.insert(0, os.path.join(_SF, '04_Strategy_Execution'))
sys.path.insert(0, os.path.join(_SF, '06_Backtesting'))

from RiceQuantDataProvider_CTA import RiceQuantCTADataProvider
from CTA_Strategies_CN_Futures import TSMOMStrategy, TrendFollowingStrategy, CarryStrategy
from CTA_Strategy_Evaluator import CTAEvaluator

print("="*80)
print("RiceQuant Real Data CTA Strategy Demo")
print("="*80)
print()

# Initialize data provider
print("[1] Initializing RiceQuant data provider...")
provider = RiceQuantCTADataProvider()
print()

# Select symbols from different categories
symbols = {
    'Black Metals': ['RB', 'HC', 'I'],
    'Non-ferrous': ['CU', 'AL', 'ZN'],
    'Energy': ['SC'],
    'Chemicals': ['TA', 'MA'],
    'Agriculture': ['M', 'CF'],
}

all_symbols = []
for cat, syms in symbols.items():
    all_symbols.extend(syms)

print("[2] Loading futures data...")
print(f"    Symbols: {', '.join(all_symbols)}")
print(f"    Period: 2024-01-01 to 2024-12-31")
print()

# Load data
data = provider.get_multiple_futures(all_symbols, '2024-01-01', '2024-12-31')

print(f"[OK] Loaded {len(data)} symbols successfully")
print()

# Display data summary
print("[3] Data Summary:")
for symbol, df in data.items():
    if not df.empty:
        info = provider.get_symbol_info(symbol)
        start_price = df['close'].iloc[0]
        end_price = df['close'].iloc[-1]
        change = (end_price / start_price - 1) * 100
        print(f"    {symbol:4s} ({info.get('name', 'Unknown'):15s}): "
              f"{len(df):4d} days, "
              f"{start_price:10.2f} -> {end_price:10.2f} ({change:+6.2f}%)")

print()

# Generate trading signals
print("[4] Generating Trading Signals...")
print()

# Use latest date for signals
latest_date = max(df.index[-1] for df in data.values())
print(f"Signal Date: {latest_date}")
print()

# TSMOM Strategy
print("TSMOM Strategy Signals:")
tsmom = TSMOMStrategy()
signals = tsmom.generate_signals(data, latest_date)

long_signals = [s for s in signals if s.signal.value == 1]
short_signals = [s for s in signals if s.signal.value == -1]

print(f"  LONG signals ({len(long_signals)}):")
for s in long_signals[:5]:
    print(f"    {s.symbol}: strength={s.strength:.2f}, position={s.target_position:.2f}")

print(f"  SHORT signals ({len(short_signals)}):")
for s in short_signals[:5]:
    print(f"    {s.symbol}: strength={s.strength:.2f}, position={s.target_position:.2f}")

print()

# Trend Following Strategy
print("Trend Following Strategy Signals:")
trend = TrendFollowingStrategy()
signals = trend.generate_signals(data, latest_date)

for s in signals[:8]:
    direction = "LONG " if s.signal.value == 1 else "SHORT" if s.signal.value == -1 else "FLAT "
    print(f"  {s.symbol}: {direction} (strength={s.strength:.2f})")

print()

# Performance Evaluation on Historical Data
print("[5] Historical Performance Evaluation:")
print()

# Simulate strategy returns using signal quality
np.random.seed(42)
strategy_returns = {}

for strategy_name, strategy in [('TSMOM', tsmom), ('TrendFollowing', trend), ('Carry', CarryStrategy())]:
    returns = []
    dates = sorted(list(list(data.values())[0].index))
    
    for i in range(1, len(dates)):
        daily_signals = strategy.generate_signals(data, dates[i])
        
        # Calculate daily return based on signals
        daily_ret = 0
        if daily_signals:
            for s in daily_signals:
                if abs(s.target_position) > 0.1 and s.symbol in data:
                    try:
                        df = data[s.symbol]
                        if dates[i] in df.index and dates[i-1] in df.index:
                            price_now = df.loc[dates[i], 'close']
                            price_prev = df.loc[dates[i-1], 'close']
                            ret = (price_now / price_prev - 1) * np.sign(s.target_position)
                            daily_ret += ret * abs(s.target_position) / len(daily_signals)
                    except:
                        pass
        
        returns.append(daily_ret)
    
    strategy_returns[strategy_name] = pd.Series(returns, index=dates[1:])

# Evaluate each strategy
evaluator = CTAEvaluator()

print("Strategy Performance (2024):")
print("-" * 80)
print(f"{'Strategy':<15} {'Ann Return':>12} {'Sharpe':>10} {'Max DD':>10} {'Win Rate':>10}")
print("-" * 80)

for name, returns in strategy_returns.items():
    metrics = evaluator.evaluate(returns, name)
    print(f"{name:<15} "
          f"{metrics.annualized_return*100:>11.2f}% "
          f"{metrics.sharpe_ratio:>10.2f} "
          f"{metrics.max_drawdown*100:>9.2f}% "
          f"{metrics.win_rate*100:>9.2f}%")

print("-" * 80)
print()

# Equal weight portfolio
print("[6] Equal Weight Portfolio Performance:")
combined_returns = pd.Series(0.0, index=strategy_returns['TSMOM'].index)
for returns in strategy_returns.values():
    combined_returns += returns / len(strategy_returns)

portfolio_metrics = evaluator.evaluate(combined_returns, "Equal_Weight_Portfolio")

print(f"  Annual Return: {portfolio_metrics.annualized_return*100:.2f}%")
print(f"  Sharpe Ratio: {portfolio_metrics.sharpe_ratio:.2f}")
print(f"  Information Ratio: {portfolio_metrics.information_ratio:.2f}")
print(f"  Max Drawdown: {portfolio_metrics.max_drawdown*100:.2f}%")
print(f"  Calmar Ratio: {portfolio_metrics.calmar_ratio:.2f}")
print()

print("="*80)
print("Demo completed successfully!")
print("="*80)
print()
print("Note: This demo uses real futures data from RiceQuant.")
print("Account expires in 26 days. Contact RiceQuant to renew.")
