"""
米筐CTA策略快速演�?
==================

最简单的使用示例，快速验证系统是否正常工�?
"""

import pandas as pd
import numpy as np
from datetime import datetime

# API密钥
API_KEY = "Mg8lEL3dGgIyxrwc2rNsqVneytgqpSq4n0h4S8M-XQnZ9domysurqc3Lh1NlmAwAKSBTUr5qwFJ-aPEeFfR3L2rK5pq-HddOdS6vDBfDv187cVUdC9sejifx7V1lQjQWRm19YVrhx1poB-uThWtc3F6kzslu4cn9myNayWNzfo8=OPgej69FUSOnYfosbz62TAjuWXo_85kHZiUQUZCjXl78r0HUqN3HGJBXF7CIsXCHAAsQ7xieZzwD-_G8vn_3pkfFaAy2pLrhjk4BSLkVcNDwfPJovTa4hxIKfGAZ5G_HtNIHSUZcHnenxQnZljuvnzsixT3G-3Gr4UunAz9-72A="

def main():
    print("="*70)
    print("RiceQuant CTA Strategy Demo")
    print("="*70)
    print()
    
    # Import modules
    try:
        from RiceQuantDataProvider_CTA import RiceQuantCTADataProvider
        from CTA_Strategies_CN_Futures import TSMOMStrategy, TrendFollowingStrategy
        from CTA_Strategy_Evaluator import CTAEvaluator
        print("[OK] Modules imported successfully")
    except ImportError as e:
        print(f"[ERROR] Import failed: {e}")
        return
    
    # Initialize data provider
    print("\nInitializing data provider...")
    provider = RiceQuantCTADataProvider(api_key=API_KEY)
    
    # Show available symbols
    print("\n[Available Symbols]")
    categories = {
        'Black Metals': ['RB', 'HC', 'I'],
        'Non-ferrous': ['CU', 'AL', 'ZN'],
        'Energy': ['SC', 'LU'],
        'Chemicals': ['TA', 'MA', 'PP'],
        'Index': ['IF', 'IC'],
    }
    
    for cat, symbols in categories.items():
        print(f"  {cat}: {', '.join(symbols)}")
    
    # Data retrieval example
    print("\n[Data Retrieval Example]")
    print("Fetching RB (Rebar) 2024 data...")
    
    df = provider.get_futures_data('RB', '2024-01-01', '2024-03-01')
    
    if not df.empty:
        print(f"[OK] Retrieved {len(df)} records")
        print("\nData preview:")
        print(df.head(3).to_string())
    else:
        print("[ERROR] Data retrieval failed")
        return
    
    # Strategy demo
    print("\n[Strategy Signal Demo]")
    
    # Load multiple symbols
    symbols = ['RB', 'CU', 'SC']
    data = {}
    for sym in symbols:
        df = provider.get_futures_data(sym, '2024-01-01', '2024-06-01')
        if not df.empty:
            data[sym] = df
    
    print(f"Loaded data for {len(data)} symbols")
    
    # TSMOM Strategy
    print("\nTSMOM Strategy Signals:")
    tsmom = TSMOMStrategy()
    
    test_date = list(data.values())[0].index[-1] if data else None
    if test_date:
        signals = tsmom.generate_signals(data, test_date)
        
        # Show top 5 signals
        for signal in signals[:5]:
            direction = "LONG" if signal.signal.value == 1 else "SHORT" if signal.signal.value == -1 else "FLAT"
            print(f"  {signal.symbol}: {direction} "
                  f"(Strength:{signal.strength:.2f}, "
                  f"Position:{signal.target_position:.2f})")
    
    # Trend Following Strategy
    print("\nTrend Following Strategy Signals:")
    trend = TrendFollowingStrategy()
    
    if test_date:
        signals = trend.generate_signals(data, test_date)
        
        for signal in signals[:5]:
            direction = "LONG" if signal.signal.value == 1 else "SHORT" if signal.signal.value == -1 else "FLAT"
            print(f"  {signal.symbol}: {direction} "
                  f"(Strength:{signal.strength:.2f})")
    
    # Performance evaluation demo
    print("\n[Performance Evaluation Demo]")
    
    # Simulate returns series
    np.random.seed(42)
    dates = pd.date_range('2024-01-01', '2024-12-31', freq='B')
    returns = pd.Series(np.random.normal(0.0003, 0.012, len(dates)), index=dates)
    
    evaluator = CTAEvaluator()
    metrics = evaluator.evaluate(returns, "Demo_Strategy")
    
    print(f"  Total Return: {metrics.total_return*100:.2f}%")
    print(f"  Annual Return: {metrics.annualized_return*100:.2f}%")
    print(f"  Sharpe Ratio: {metrics.sharpe_ratio:.3f}")
    print(f"  Information Ratio: {metrics.information_ratio:.3f}")
    print(f"  Max Drawdown: {metrics.max_drawdown*100:.2f}%")
    
    print("\n" + "="*70)
    print("Demo completed!")
    print("="*70)
    print()
    print("Next steps:")
    print("  1. Run full backtest: python CTA_RiceQuant_Backtest.py")
    print("  2. Read documentation: README_RiceQuant_CTA.md")
    print("  3. Install RiceQuant API for real data: pip install rqdatac")

if __name__ == "__main__":
    main()
