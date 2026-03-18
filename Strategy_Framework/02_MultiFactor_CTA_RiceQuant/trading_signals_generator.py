"""
Buy the Dip — Trading Signals & Record Generator
==================================================

Generates:
1. CURRENT live trading signals (today's position recommendation)
2. Historical trade record (every position change with P&L)
3. Monthly performance summary
4. Trade statistics (win rate, avg gain/loss, holding period)

Uses the best strategies from backtest:
- Losing Streak (best Sharpe)
- Composite Dip (best alpha)
- Trend-Filtered Dip (safest)

Data: Yahoo Finance (yfinance) — REAL DATA
"""

import warnings
warnings.filterwarnings('ignore')

import json
import logging
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# ============================================================
# Data & Indicators
# ============================================================
def fetch_spy_data(start: str = '2020-01-01', end: str = None) -> Dict[str, pd.DataFrame]:
    """Fetch SPY + VIX data."""
    if end is None:
        end = datetime.now().strftime('%Y-%m-%d')

    tickers = {'SPY': 'S&P 500 ETF', '^VIX': 'VIX Index'}
    data = {}
    for t, name in tickers.items():
        try:
            df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
            if df is not None and len(df) > 10:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                data[t] = df
                logger.info(f"  {t} ({name}): {len(df)} days, last={df.index[-1].strftime('%Y-%m-%d')}")
        except Exception as e:
            logger.warning(f"  {t}: FAILED - {e}")
    return data


def compute_indicators(spy: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators."""
    close = spy['Close']
    df = pd.DataFrame(index=close.index)
    df['date'] = close.index
    df['close'] = close.values
    df['open'] = spy['Open'].values
    df['high'] = spy['High'].values
    df['low'] = spy['Low'].values
    df['volume'] = spy['Volume'].values
    df['ret'] = close.pct_change()
    df['ret_pct'] = df['ret'] * 100

    # RSI (14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-8)
    df['rsi'] = 100 - (100 / (1 + rs))

    # Drawdown from 50-day high
    rolling_high = close.rolling(50).max()
    df['drawdown'] = ((close - rolling_high) / rolling_high)
    df['drawdown_pct'] = df['drawdown'] * 100

    # Bollinger Bands (20, 2)
    df['bb_mid'] = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df['bb_lower'] = df['bb_mid'] - 2 * bb_std
    df['bb_upper'] = df['bb_mid'] + 2 * bb_std
    df['bb_pct'] = (close - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-8)

    # Consecutive down days
    down_day = (df['ret'] < 0).astype(int)
    streak = pd.Series(0, index=close.index)
    for i in range(1, len(streak)):
        if down_day.iloc[i] == 1:
            streak.iloc[i] = streak.iloc[i - 1] + 1
        else:
            streak.iloc[i] = 0
    df['down_streak'] = streak.values

    # Moving averages
    df['ma20'] = close.rolling(20).mean()
    df['ma50'] = close.rolling(50).mean()
    df['ma200'] = close.rolling(200).mean()

    # Volatility
    df['vol_21'] = df['ret'].rolling(21).std() * np.sqrt(252) * 100  # annualized %

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    df['macd'] = ema12 - ema26
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    return df


# ============================================================
# Signal Generation
# ============================================================
def generate_signals(indicators: pd.DataFrame, vix: pd.Series = None) -> pd.DataFrame:
    """
    Generate daily trading signals for all dip strategies.
    Returns a DataFrame with position sizes for each strategy.
    """
    n = len(indicators)
    signals = pd.DataFrame(index=indicators.index)
    signals['date'] = indicators['date']
    signals['close'] = indicators['close']

    # ---------- Strategy 1: Losing Streak ----------
    pos = pd.Series(1.0, index=indicators.index)
    pos[indicators['down_streak'] >= 3] = 1.2
    pos[indicators['down_streak'] >= 4] = 1.4
    pos[indicators['down_streak'] >= 5] = 1.6
    signals['losing_streak_pos'] = pos

    # ---------- Strategy 2: RSI Dip ----------
    pos = pd.Series(1.0, index=indicators.index)
    pos[indicators['rsi'] < 30] = 1.5
    pos[indicators['rsi'] < 20] = 1.8
    pos[indicators['rsi'] > 70] = 0.85
    pos[indicators['rsi'] > 80] = 0.7
    signals['rsi_dip_pos'] = pos

    # ---------- Strategy 3: Drawdown Dip ----------
    pos = pd.Series(1.0, index=indicators.index)
    dd = indicators['drawdown']
    pos[dd < -0.03] = 1.2
    pos[dd < -0.05] = 1.4
    pos[dd < -0.10] = 1.6
    pos[dd > -0.01] = 0.95
    signals['dd_dip_pos'] = pos

    # ---------- Strategy 4: Bollinger Dip ----------
    pos = pd.Series(1.0, index=indicators.index)
    bb = indicators['bb_pct']
    pos[bb < 0.0] = 1.5
    pos[bb < 0.15] = 1.3
    pos[bb > 0.85] = 0.85
    pos[bb > 1.0] = 0.75
    signals['bb_dip_pos'] = pos

    # ---------- Strategy 5: VIX Spike ----------
    if vix is not None:
        vix_aligned = vix.reindex(indicators.index, method='ffill')
        pos = pd.Series(1.0, index=indicators.index)
        pos[vix_aligned > 25] = 1.3
        pos[vix_aligned > 35] = 1.5
        pos[vix_aligned > 45] = 1.7
        pos[vix_aligned < 15] = 0.9
        signals['vix_spike_pos'] = pos
        signals['vix'] = vix_aligned
    else:
        signals['vix_spike_pos'] = 1.0
        signals['vix'] = np.nan

    # ---------- Strategy 6: Trend-Filtered Composite ----------
    uptrend = indicators['close'] > indicators['ma200']
    score = pd.Series(0.0, index=indicators.index)
    score[indicators['rsi'] < 35] += 1
    score[indicators['rsi'] < 25] += 1
    score[indicators['drawdown'] < -0.03] += 1
    score[indicators['drawdown'] < -0.07] += 1
    score[indicators['bb_pct'] < 0.2] += 1
    if vix is not None:
        score[vix_aligned > 25] += 1

    pos_up = (1.0 + score * 0.15).clip(1.0, 1.8)
    pos_down = (0.7 + score * 0.05).clip(0.5, 1.0)
    pos = pd.Series(1.0, index=indicators.index)
    pos[uptrend] = pos_up[uptrend]
    pos[~uptrend] = pos_down[~uptrend]
    signals['trend_filtered_pos'] = pos

    # ---------- Composite (average) ----------
    strat_cols = [c for c in signals.columns if c.endswith('_pos')]
    signals['composite_pos'] = signals[strat_cols].mean(axis=1).round(3)

    # Add indicator values for reference
    signals['rsi'] = indicators['rsi'].round(1)
    signals['drawdown_pct'] = indicators['drawdown_pct'].round(2)
    signals['bb_pct'] = indicators['bb_pct'].round(3)
    signals['down_streak'] = indicators['down_streak']
    signals['ma200'] = indicators['ma200'].round(2)
    signals['vol_21'] = indicators['vol_21'].round(1)
    signals['trend'] = np.where(indicators['close'] > indicators['ma200'], 'UP', 'DOWN')

    return signals


# ============================================================
# Trade Record Generator
# ============================================================
def generate_trade_record(signals: pd.DataFrame, strategy_col: str = 'composite_pos',
                           initial_capital: float = 1_000_000) -> pd.DataFrame:
    """
    Generate detailed trade record with P&L for a given strategy.
    Every position change is recorded as a trade.
    """
    trades = []
    pos = signals[strategy_col].shift(1)  # positions are applied next day
    spy_ret = signals['close'].pct_change()

    capital = initial_capital
    current_pos = None
    entry_date = None
    entry_price = None
    entry_capital = capital

    for i in range(1, len(signals)):
        date = signals.index[i]
        close = signals['close'].iloc[i]
        target_pos = pos.iloc[i]
        ret = spy_ret.iloc[i]

        if pd.isna(target_pos) or pd.isna(ret):
            continue

        # Daily P&L
        if current_pos is not None:
            daily_pnl = capital * current_pos * ret
            capital += daily_pnl
            # Transaction cost on position change
            if current_pos != target_pos:
                cost = abs(target_pos - current_pos) * capital * 0.0003
                capital -= cost

        # Position change = new trade
        if current_pos != target_pos:
            # Close previous trade
            if current_pos is not None and entry_date is not None:
                trade_pnl = capital - entry_capital
                trade_ret = trade_pnl / entry_capital
                holding_days = (date - entry_date).days
                trades.append({
                    'entry_date': entry_date.strftime('%Y-%m-%d'),
                    'exit_date': date.strftime('%Y-%m-%d'),
                    'entry_price': round(entry_price, 2),
                    'exit_price': round(close, 2),
                    'position': current_pos,
                    'action': f"{'BUY DIP' if current_pos > 1.05 else 'TRIM' if current_pos < 0.95 else 'HOLD'} {current_pos:.2f}x",
                    'entry_capital': round(entry_capital, 0),
                    'exit_capital': round(capital, 0),
                    'pnl': round(trade_pnl, 0),
                    'return_pct': round(trade_ret * 100, 2),
                    'holding_days': holding_days,
                })

            # Open new trade
            entry_date = date
            entry_price = close
            entry_capital = capital
            current_pos = target_pos

    # Close last open trade
    if current_pos is not None and entry_date is not None:
        trade_pnl = capital - entry_capital
        trade_ret = trade_pnl / entry_capital
        trades.append({
            'entry_date': entry_date.strftime('%Y-%m-%d'),
            'exit_date': signals.index[-1].strftime('%Y-%m-%d'),
            'entry_price': round(entry_price, 2),
            'exit_price': round(signals['close'].iloc[-1], 2),
            'position': current_pos,
            'action': f"{'BUY DIP' if current_pos > 1.05 else 'TRIM' if current_pos < 0.95 else 'HOLD'} {current_pos:.2f}x",
            'entry_capital': round(entry_capital, 0),
            'exit_capital': round(capital, 0),
            'pnl': round(trade_pnl, 0),
            'return_pct': round(trade_ret * 100, 2),
            'holding_days': (signals.index[-1] - entry_date).days,
        })

    return pd.DataFrame(trades)


# ============================================================
# Display Functions
# ============================================================
def print_current_signals(signals: pd.DataFrame, indicators: pd.DataFrame):
    """Print today's trading signals."""
    last = signals.iloc[-1]
    prev = signals.iloc[-2] if len(signals) > 1 else last
    last_ind = indicators.iloc[-1]

    print("\n" + "=" * 80)
    print(f"  LIVE TRADING SIGNALS — {last['date'].strftime('%Y-%m-%d')}")
    print("=" * 80)

    print(f"\n  SPY Close:    ${last['close']:.2f}")
    print(f"  Daily Change: {last_ind['ret_pct']:+.2f}%")
    print(f"  RSI (14):     {last['rsi']:.1f}")
    print(f"  VIX:          {last['vix']:.1f}" if not pd.isna(last['vix']) else "  VIX:          N/A")
    print(f"  Drawdown:     {last['drawdown_pct']:.2f}% from 50-day high")
    print(f"  BB %B:        {last['bb_pct']:.3f}")
    print(f"  Down Streak:  {int(last['down_streak'])} days")
    print(f"  200-MA:       ${last['ma200']:.2f} ({'ABOVE' if last['trend'] == 'UP' else 'BELOW'})")
    print(f"  Ann. Vol:     {last['vol_21']:.1f}%")
    print(f"  MACD Hist:    {last_ind['macd_hist']:.2f}")

    print(f"\n  {'─' * 76}")
    print(f"  {'Strategy':<28} {'Position':>10} {'Signal':>12} {'vs Yesterday':>14}")
    print(f"  {'─' * 76}")

    strat_names = {
        'losing_streak_pos': 'Losing Streak (3+)',
        'rsi_dip_pos': 'RSI Dip (30/50)',
        'dd_dip_pos': 'Drawdown Dip',
        'bb_dip_pos': 'Bollinger Band Dip',
        'vix_spike_pos': 'VIX Spike',
        'trend_filtered_pos': 'Trend-Filtered Dip',
        'composite_pos': 'COMPOSITE (Avg)',
    }

    for col, name in strat_names.items():
        pos = last[col]
        prev_pos = prev[col]
        change = pos - prev_pos

        if pos > 1.3:
            signal = "STRONG BUY"
        elif pos > 1.05:
            signal = "BUY DIP"
        elif pos < 0.8:
            signal = "REDUCE"
        elif pos < 0.95:
            signal = "TRIM"
        else:
            signal = "HOLD"

        change_str = f"{change:+.3f}" if abs(change) > 0.001 else "—"
        marker = " **" if col == 'composite_pos' else ""

        print(f"  {name:<28} {pos:>9.3f}x {signal:>12} {change_str:>14}{marker}")

    print(f"  {'─' * 76}")

    # Overall recommendation
    comp = last['composite_pos']
    print(f"\n  RECOMMENDATION: ", end="")
    if comp > 1.3:
        print(f"STRONG BUY THE DIP — increase to {comp:.2f}x SPY exposure")
    elif comp > 1.1:
        print(f"BUY THE DIP — increase to {comp:.2f}x SPY exposure")
    elif comp > 1.02:
        print(f"MILD DIP — slightly increase to {comp:.2f}x SPY exposure")
    elif comp < 0.85:
        print(f"REDUCE EXPOSURE — cut to {comp:.2f}x SPY exposure")
    elif comp < 0.95:
        print(f"TRIM — reduce to {comp:.2f}x SPY exposure")
    else:
        print(f"HOLD — maintain {comp:.2f}x SPY exposure (no dip signal)")

    # Dip checklist
    print(f"\n  DIP CHECKLIST:")
    checks = [
        (last['rsi'] < 30, f"  [{'x' if last['rsi'] < 30 else ' '}] RSI < 30 (currently {last['rsi']:.1f})"),
        (last['drawdown_pct'] < -5, f"  [{'x' if last['drawdown_pct'] < -5 else ' '}] Drawdown > 5% (currently {last['drawdown_pct']:.2f}%)"),
        (last['bb_pct'] < 0.15, f"  [{'x' if last['bb_pct'] < 0.15 else ' '}] Below Bollinger lower band ({last['bb_pct']:.3f})"),
        (last['down_streak'] >= 3, f"  [{'x' if last['down_streak'] >= 3 else ' '}] 3+ down days (currently {int(last['down_streak'])})"),
    ]
    if not pd.isna(last['vix']):
        checks.append(
            (last['vix'] > 25, f"  [{'x' if last['vix'] > 25 else ' '}] VIX > 25 (currently {last['vix']:.1f})")
        )
    checks.append(
        (last['trend'] == 'UP', f"  [{'x' if last['trend'] == 'UP' else ' '}] SPY above 200-MA (trend: {last['trend']})")
    )

    triggered = sum(1 for c, _ in checks if c)
    for _, text in checks:
        print(text)
    print(f"\n  Dip signals triggered: {triggered}/{len(checks)}")


def print_trade_record(trades: pd.DataFrame, title: str = "COMPOSITE"):
    """Print formatted trade record."""
    if trades.empty:
        print("  No trades recorded.")
        return

    print(f"\n{'=' * 130}")
    print(f"  TRADE RECORD — {title}")
    print(f"{'=' * 130}")
    print(f"  {'Entry Date':<12} {'Exit Date':<12} {'Action':<18} {'Entry$':>10} {'Exit$':>10}"
          f" {'PnL':>12} {'Return':>8} {'Days':>6} {'Capital':>14}")
    print(f"  {'─' * 124}")

    for _, t in trades.iterrows():
        pnl_str = f"${t['pnl']:>+,.0f}"
        cap_str = f"${t['exit_capital']:>,.0f}"
        print(
            f"  {t['entry_date']:<12} {t['exit_date']:<12} {t['action']:<18}"
            f" ${t['entry_price']:>8.2f} ${t['exit_price']:>8.2f}"
            f" {pnl_str:>12} {t['return_pct']:>+7.2f}% {t['holding_days']:>5}d {cap_str:>14}"
        )

    print(f"  {'─' * 124}")


def print_trade_stats(trades: pd.DataFrame, title: str = "COMPOSITE"):
    """Print trade statistics."""
    if trades.empty:
        return

    wins = trades[trades['pnl'] > 0]
    losses = trades[trades['pnl'] <= 0]

    dip_trades = trades[trades['position'] > 1.05]
    dip_wins = dip_trades[dip_trades['pnl'] > 0]

    print(f"\n{'=' * 80}")
    print(f"  TRADE STATISTICS — {title}")
    print(f"{'=' * 80}")

    print(f"\n  Total Trades:          {len(trades)}")
    print(f"  Winning Trades:        {len(wins)} ({len(wins)/len(trades)*100:.1f}%)")
    print(f"  Losing Trades:         {len(losses)} ({len(losses)/len(trades)*100:.1f}%)")
    print(f"\n  Avg Win:               {wins['return_pct'].mean():+.2f}%" if len(wins) > 0 else "")
    print(f"  Avg Loss:              {losses['return_pct'].mean():+.2f}%" if len(losses) > 0 else "")
    print(f"  Win/Loss Ratio:        {abs(wins['return_pct'].mean() / losses['return_pct'].mean()):.2f}x" if len(losses) > 0 and losses['return_pct'].mean() != 0 else "")
    print(f"  Avg Holding Period:    {trades['holding_days'].mean():.1f} days")
    print(f"\n  Best Trade:            {trades['return_pct'].max():+.2f}% ({trades.loc[trades['return_pct'].idxmax(), 'entry_date']})")
    print(f"  Worst Trade:           {trades['return_pct'].min():+.2f}% ({trades.loc[trades['return_pct'].idxmin(), 'entry_date']})")
    print(f"\n  Total P&L:             ${trades['pnl'].sum():>+,.0f}")
    print(f"  Final Capital:         ${trades.iloc[-1]['exit_capital']:>,.0f}")

    if len(dip_trades) > 0:
        print(f"\n  --- DIP TRADES ONLY (position > 1.05x) ---")
        print(f"  Dip Trades:            {len(dip_trades)}")
        print(f"  Dip Win Rate:          {len(dip_wins)/len(dip_trades)*100:.1f}%")
        print(f"  Avg Dip Return:        {dip_trades['return_pct'].mean():+.2f}%")
        print(f"  Avg Dip Hold:          {dip_trades['holding_days'].mean():.1f} days")


def print_recent_signals(signals: pd.DataFrame, n: int = 30):
    """Print recent daily signal history."""
    recent = signals.tail(n)

    print(f"\n{'=' * 140}")
    print(f"  RECENT SIGNAL HISTORY (last {n} trading days)")
    print(f"{'=' * 140}")
    print(f"  {'Date':<12} {'Close':>8} {'Ret%':>7} {'RSI':>6} {'VIX':>6} {'DD%':>7} {'BB%':>6}"
          f" {'Streak':>7} {'Trend':>6}"
          f" {'LStreak':>8} {'RSI':>6} {'DD':>6} {'BB':>6} {'VIX':>6} {'TrFilt':>7} {'COMP':>7}")
    print(f"  {'─' * 136}")

    for _, row in recent.iterrows():
        vix_str = f"{row['vix']:.1f}" if not pd.isna(row['vix']) else "N/A"

        # Highlight dip rows
        comp = row['composite_pos']
        marker = " <<" if comp > 1.15 else " <" if comp > 1.05 else ""

        print(
            f"  {row['date'].strftime('%Y-%m-%d'):<12}"
            f" {row['close']:>8.2f}"
            f" {(row['close']/signals['close'].shift(1).loc[row.name] - 1)*100 if row.name != signals.index[0] else 0:>+6.2f}%"
            f" {row['rsi']:>6.1f}"
            f" {vix_str:>6}"
            f" {row['drawdown_pct']:>6.2f}%"
            f" {row['bb_pct']:>6.3f}"
            f" {int(row['down_streak']):>7}"
            f" {row['trend']:>6}"
            f" {row['losing_streak_pos']:>7.2f}x"
            f" {row['rsi_dip_pos']:>5.2f}x"
            f" {row['dd_dip_pos']:>5.2f}x"
            f" {row['bb_dip_pos']:>5.2f}x"
            f" {row['vix_spike_pos']:>5.2f}x"
            f" {row['trend_filtered_pos']:>6.2f}x"
            f" {comp:>6.3f}x{marker}"
        )
    print(f"  {'─' * 136}")
    print(f"  << = DIP SIGNAL (composite > 1.15x)   < = MILD DIP (composite > 1.05x)")


def print_monthly_summary(signals: pd.DataFrame):
    """Print monthly P&L summary for composite strategy."""
    spy_ret = signals['close'].pct_change()
    pos = signals['composite_pos'].shift(1)
    strat_ret = pos * spy_ret

    # Monthly aggregation
    monthly_spy = spy_ret.resample('ME').apply(lambda x: (1 + x).prod() - 1) * 100
    monthly_strat = strat_ret.resample('ME').apply(lambda x: (1 + x).prod() - 1) * 100
    monthly_alpha = monthly_strat - monthly_spy

    df = pd.DataFrame({
        'SPY_ret': monthly_spy,
        'Strat_ret': monthly_strat,
        'Alpha': monthly_alpha,
    }).dropna()

    # Pivot to year x month
    df['year'] = df.index.year
    df['month'] = df.index.month

    years = sorted(df['year'].unique())

    print(f"\n{'=' * 110}")
    print(f"  MONTHLY RETURNS — COMPOSITE DIP STRATEGY vs SPY (%)")
    print(f"{'=' * 110}")

    # Header
    print(f"  {'Year':>6}", end="")
    for m in range(1, 13):
        print(f" {['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m-1]:>8}", end="")
    print(f" {'Total':>8}")
    print(f"  {'─' * 106}")

    for year in years:
        yr_data = df[df['year'] == year]

        # Strategy returns
        print(f"  {year} S", end="")
        yr_total = 0
        for m in range(1, 13):
            mdata = yr_data[yr_data['month'] == m]
            if len(mdata) > 0:
                val = mdata['Strat_ret'].iloc[0]
                yr_total += val
                print(f" {val:>+7.2f}%", end="")
            else:
                print(f" {'':>8}", end="")
        print(f" {yr_total:>+7.2f}%")

        # SPY returns
        print(f"  {year} B", end="")
        yr_total = 0
        for m in range(1, 13):
            mdata = yr_data[yr_data['month'] == m]
            if len(mdata) > 0:
                val = mdata['SPY_ret'].iloc[0]
                yr_total += val
                print(f" {val:>+7.2f}%", end="")
            else:
                print(f" {'':>8}", end="")
        print(f" {yr_total:>+7.2f}%")

        # Alpha
        print(f"  {year} α", end="")
        yr_total = 0
        for m in range(1, 13):
            mdata = yr_data[yr_data['month'] == m]
            if len(mdata) > 0:
                val = mdata['Alpha'].iloc[0]
                yr_total += val
                print(f" {val:>+7.2f}%", end="")
            else:
                print(f" {'':>8}", end="")
        print(f" {yr_total:>+7.2f}%")
        print()

    print(f"  S = Strategy  |  B = Benchmark (SPY)  |  α = Alpha (Strategy - SPY)")
    print(f"{'=' * 110}")


# ============================================================
# Main
# ============================================================
def run_signal_generator():
    """Generate all signals and trade records."""

    print("=" * 80)
    print("  BUY THE DIP — TRADING SIGNALS & RECORD GENERATOR")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # Fetch data (5 years for trade record + current)
    print("\n[1/5] Fetching real market data...")
    data = fetch_spy_data(start='2020-01-01')
    spy = data['SPY']
    vix_close = data['^VIX']['Close'] if '^VIX' in data else None

    # Compute indicators
    print("\n[2/5] Computing indicators & signals...")
    indicators = compute_indicators(spy)
    signals = generate_signals(indicators, vix_close)

    # Current signals
    print_current_signals(signals, indicators)

    # Recent signal history
    print_recent_signals(signals, n=30)

    # Trade records for each strategy
    print("\n[3/5] Generating trade records...")

    strategies = {
        'COMPOSITE (Avg All)': 'composite_pos',
        'LOSING STREAK (3+)': 'losing_streak_pos',
        'RSI DIP (30/50)': 'rsi_dip_pos',
        'TREND-FILTERED DIP': 'trend_filtered_pos',
        'DRAWDOWN DIP': 'dd_dip_pos',
    }

    all_trades = {}
    for name, col in strategies.items():
        trades = generate_trade_record(signals, strategy_col=col, initial_capital=1_000_000)
        all_trades[name] = trades

        # Only show full records for top 2 strategies
        if name in ['COMPOSITE (Avg All)', 'TREND-FILTERED DIP']:
            # Show last 30 trades
            recent_trades = trades.tail(30)
            print_trade_record(recent_trades, title=f"{name} (Last 30 Trades)")

        print_trade_stats(trades, title=name)

    # Monthly summary
    print("\n[4/5] Monthly performance summary...")
    print_monthly_summary(signals)

    # Save everything
    print("\n[5/5] Saving outputs...")

    # Save signals CSV
    signals_out = signals.copy()
    signals_out['date'] = signals_out['date'].dt.strftime('%Y-%m-%d')
    signals_out.to_csv('backtests/trading_signals_daily.csv', index=False)
    logger.info("  Daily signals → backtests/trading_signals_daily.csv")

    # Save trade records
    for name, trades in all_trades.items():
        fname = name.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('/', '_')
        trades.to_csv(f'backtests/trade_record_{fname}.csv', index=False)
    logger.info("  Trade records → backtests/trade_record_*.csv")

    # Save current signal as JSON
    last = signals.iloc[-1]
    current_signal = {
        'date': last['date'].strftime('%Y-%m-%d'),
        'spy_close': float(last['close']),
        'rsi': float(last['rsi']),
        'vix': float(last['vix']) if not pd.isna(last['vix']) else None,
        'drawdown_pct': float(last['drawdown_pct']),
        'bb_pct': float(last['bb_pct']),
        'down_streak': int(last['down_streak']),
        'trend': last['trend'],
        'ma200': float(last['ma200']),
        'vol_21': float(last['vol_21']),
        'signals': {
            'losing_streak': float(last['losing_streak_pos']),
            'rsi_dip': float(last['rsi_dip_pos']),
            'drawdown_dip': float(last['dd_dip_pos']),
            'bollinger_dip': float(last['bb_dip_pos']),
            'vix_spike': float(last['vix_spike_pos']),
            'trend_filtered': float(last['trend_filtered_pos']),
            'composite': float(last['composite_pos']),
        },
        'recommendation': (
            'STRONG BUY DIP' if last['composite_pos'] > 1.3 else
            'BUY DIP' if last['composite_pos'] > 1.1 else
            'MILD DIP' if last['composite_pos'] > 1.02 else
            'REDUCE' if last['composite_pos'] < 0.85 else
            'TRIM' if last['composite_pos'] < 0.95 else
            'HOLD'
        ),
    }
    with open('backtests/current_signal.json', 'w') as f:
        json.dump(current_signal, f, indent=2)
    logger.info("  Current signal → backtests/current_signal.json")

    print("\n" + "=" * 80)
    print("  ALL OUTPUTS SAVED TO backtests/")
    print("=" * 80)

    return signals, all_trades


if __name__ == '__main__':
    signals, trades = run_signal_generator()
