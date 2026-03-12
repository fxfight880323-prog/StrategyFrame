"""
Multi-Factor + CTA Strategy Backtest with REAL Data (yfinance)
==============================================================

Uses Yahoo Finance real market data to backtest:
1. Value + Momentum factor strategy on stocks
2. CTA trend-following on futures/commodities
3. Combined multi-factor CTA portfolio

Period: 2014-01-01 to 2024-12-31 (11 years)
"""

import warnings
warnings.filterwarnings('ignore')

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

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
# Configuration
# ============================================================
@dataclass
class BacktestConfig:
    start_date: str = '2014-01-01'
    end_date: str = '2024-12-31'
    initial_capital: float = 10_000_000  # ¥10M / $10M
    commission_rate: float = 0.0003      # 3bps
    slippage: float = 0.001              # 10bps

    # Factor strategy
    value_weight: float = 0.4
    momentum_weight: float = 0.3
    quality_weight: float = 0.15
    lowvol_weight: float = 0.15

    # CTA params
    cta_fast_ma: int = 20
    cta_slow_ma: int = 60
    cta_vol_lookback: int = 20
    cta_target_vol: float = 0.15

    # Portfolio allocation
    stock_allocation: float = 0.60
    cta_allocation: float = 0.40
    rebalance_freq: str = 'ME'  # month-end

    # Risk limits
    max_position_pct: float = 0.10
    max_drawdown_limit: float = 0.20


# ============================================================
# Stock Universe (Yahoo Finance tickers)
# ============================================================
# A-Share proxies via US-listed ETFs + individual HK/US stocks
STOCK_UNIVERSE = {
    # China A-share / HK proxies
    'FXI':   'iShares China Large-Cap ETF',
    'MCHI':  'iShares MSCI China ETF',
    'KWEB':  'KraneShares CSI China Internet ETF',
    'GXC':   'SPDR S&P China ETF',
    # Developed markets
    'SPY':   'S&P 500 ETF',
    'EFA':   'iShares MSCI EAFE ETF',
    'EWJ':   'iShares MSCI Japan ETF',
    'VGK':   'Vanguard FTSE Europe ETF',
    # Emerging markets
    'EEM':   'iShares MSCI Emerging Markets ETF',
    'VWO':   'Vanguard FTSE Emerging Markets ETF',
    # Sectors (for factor diversity)
    'XLF':   'Financial Select Sector SPDR',
    'XLE':   'Energy Select Sector SPDR',
    'XLK':   'Technology Select Sector SPDR',
    'XLV':   'Health Care Select Sector SPDR',
    'XLI':   'Industrial Select Sector SPDR',
    'XLP':   'Consumer Staples Select Sector SPDR',
    'XLY':   'Consumer Discretionary Select Sector SPDR',
    'XLU':   'Utilities Select Sector SPDR',
    'XLRE':  'Real Estate Select Sector SPDR',
    'XLB':   'Materials Select Sector SPDR',
}

# CTA Universe - commodity & financial futures proxies
CTA_UNIVERSE = {
    'GC=F':   'Gold Futures',
    'SI=F':   'Silver Futures',
    'CL=F':   'Crude Oil WTI Futures',
    'NG=F':   'Natural Gas Futures',
    'HG=F':   'Copper Futures',
    'ZC=F':   'Corn Futures',
    'ZS=F':   'Soybean Futures',
    'ZW=F':   'Wheat Futures',
    'ES=F':   'S&P 500 E-mini Futures',
    'NQ=F':   'Nasdaq 100 E-mini Futures',
    'ZN=F':   '10-Year T-Note Futures',
    'ZB=F':   '30-Year T-Bond Futures',
    'DX=F':   'US Dollar Index Futures',
    '6E=F':   'Euro FX Futures',
    '6J=F':   'Japanese Yen Futures',
}


# ============================================================
# Data Fetching
# ============================================================
def fetch_price_data(tickers: Dict[str, str], start: str, end: str) -> pd.DataFrame:
    """Fetch daily close prices for all tickers from Yahoo Finance."""
    logger.info(f"Fetching {len(tickers)} tickers from Yahoo Finance ({start} to {end})...")

    all_data = {}
    failed = []

    for ticker, name in tickers.items():
        try:
            df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
            if df is not None and len(df) > 100:
                # Handle MultiIndex columns from yfinance
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                all_data[ticker] = df['Close']
                logger.info(f"  {ticker} ({name}): {len(df)} days")
            else:
                failed.append(ticker)
                logger.warning(f"  {ticker}: insufficient data ({len(df) if df is not None else 0} days)")
        except Exception as e:
            failed.append(ticker)
            logger.warning(f"  {ticker}: FAILED - {e}")

    if not all_data:
        raise RuntimeError("No data fetched!")

    prices = pd.DataFrame(all_data)
    prices.index = pd.to_datetime(prices.index)
    # Remove timezone if present
    if prices.index.tz is not None:
        prices.index = prices.index.tz_localize(None)

    logger.info(f"Fetched {len(all_data)}/{len(tickers)} tickers, {len(prices)} trading days")
    if failed:
        logger.warning(f"Failed tickers: {failed}")

    return prices


def fetch_fundamental_data(tickers: List[str]) -> pd.DataFrame:
    """Fetch fundamental data (PE, PB, dividend yield) for factor construction."""
    logger.info(f"Fetching fundamental data for {len(tickers)} tickers...")

    records = []
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            info = t.info
            records.append({
                'ticker': ticker,
                'pe_ratio': info.get('trailingPE', np.nan),
                'pb_ratio': info.get('priceToBook', np.nan),
                'ps_ratio': info.get('priceToSalesTrailing12Months', np.nan),
                'dividend_yield': info.get('dividendYield', 0) or 0,
                'roe': info.get('returnOnEquity', np.nan),
                'profit_margin': info.get('profitMargins', np.nan),
                'debt_to_equity': info.get('debtToEquity', np.nan),
                'beta': info.get('beta', np.nan),
                'market_cap': info.get('marketCap', np.nan),
            })
        except Exception as e:
            logger.warning(f"  {ticker}: fundamental data failed - {e}")
            records.append({'ticker': ticker})

    return pd.DataFrame(records).set_index('ticker')


# ============================================================
# Factor Construction
# ============================================================
class FactorEngine:
    """Constructs value, momentum, quality, and low-volatility factors from price data."""

    def __init__(self, prices: pd.DataFrame, fundamentals: Optional[pd.DataFrame] = None):
        self.prices = prices
        self.returns = prices.pct_change()
        self.fundamentals = fundamentals

    def value_factor(self) -> pd.DataFrame:
        """
        Value factor: rank stocks by valuation metrics.
        Uses price-based proxies when fundamentals unavailable at each historical point.
        - 12-month price reversal (contrarian value proxy)
        - Dividend yield proxy (low vol + high yield = value)
        """
        # Long-term reversal as value proxy (cheap = beaten down)
        ret_12m = self.prices.pct_change(252)
        # Rank: lower past return = cheaper = higher value score
        value_score = -ret_12m.rank(axis=1, pct=True)
        return value_score

    def momentum_factor(self) -> pd.DataFrame:
        """
        Classic 12-1 momentum: past 12 month return, skip most recent month.
        """
        # 12-month return
        ret_12m = self.prices.pct_change(252)
        # 1-month return
        ret_1m = self.prices.pct_change(21)
        # 12-1 momentum
        mom = ret_12m - ret_1m
        mom_score = mom.rank(axis=1, pct=True)
        return mom_score

    def quality_factor(self) -> pd.DataFrame:
        """
        Quality proxy: stability of returns (higher Sharpe = higher quality).
        Uses rolling 6-month Sharpe ratio.
        """
        rolling_ret = self.returns.rolling(126).mean()
        rolling_vol = self.returns.rolling(126).std()
        sharpe = rolling_ret / (rolling_vol + 1e-8)
        quality_score = sharpe.rank(axis=1, pct=True)
        return quality_score

    def lowvol_factor(self) -> pd.DataFrame:
        """
        Low volatility: lower realized vol = higher score.
        """
        vol_60d = self.returns.rolling(60).std() * np.sqrt(252)
        # Lower vol = higher score
        lowvol_score = -vol_60d.rank(axis=1, pct=True)
        return lowvol_score

    def composite_factor(self, config: BacktestConfig) -> pd.DataFrame:
        """Weighted composite of all factors."""
        val = self.value_factor()
        mom = self.momentum_factor()
        qual = self.quality_factor()
        lvol = self.lowvol_factor()

        composite = (
            config.value_weight * val.fillna(0) +
            config.momentum_weight * mom.fillna(0) +
            config.quality_weight * qual.fillna(0) +
            config.lowvol_weight * lvol.fillna(0)
        )
        return composite


# ============================================================
# CTA Trend Following Engine
# ============================================================
class CTAEngine:
    """CTA trend-following strategy on futures."""

    def __init__(self, prices: pd.DataFrame, config: BacktestConfig):
        self.prices = prices
        self.returns = prices.pct_change()
        self.config = config

    def generate_signals(self) -> pd.DataFrame:
        """
        Dual moving average crossover with volatility-targeted position sizing.
        Signal = sign(fast_ma - slow_ma) * vol_scalar
        """
        fast_ma = self.prices.rolling(self.config.cta_fast_ma).mean()
        slow_ma = self.prices.rolling(self.config.cta_slow_ma).mean()

        # Trend signal: +1 long, -1 short
        raw_signal = np.sign(fast_ma - slow_ma)

        # Volatility targeting
        realized_vol = self.returns.rolling(self.config.cta_vol_lookback).std() * np.sqrt(252)
        vol_scalar = self.config.cta_target_vol / (realized_vol + 1e-8)
        vol_scalar = vol_scalar.clip(0, 2)  # cap leverage at 2x

        # Position = signal * vol_scalar, equal weight across instruments
        n_instruments = len(self.prices.columns)
        positions = raw_signal * vol_scalar / n_instruments

        return positions

    def backtest(self) -> Tuple[pd.Series, pd.DataFrame]:
        """Run CTA backtest, return portfolio returns and positions."""
        positions = self.generate_signals()

        # Shift positions by 1 day (trade next day)
        positions = positions.shift(1)

        # Daily PnL
        daily_pnl = (positions * self.returns).sum(axis=1)

        # Apply transaction costs
        turnover = positions.diff().abs().sum(axis=1)
        costs = turnover * (self.config.commission_rate + self.config.slippage)
        daily_pnl -= costs

        return daily_pnl, positions


# ============================================================
# Factor Strategy Backtester
# ============================================================
class FactorBacktester:
    """Factor strategy backtester supporting long-short and long-only modes."""

    def __init__(self, prices: pd.DataFrame, factor_scores: pd.DataFrame, config: BacktestConfig):
        self.prices = prices
        self.returns = prices.pct_change()
        self.factor_scores = factor_scores
        self.config = config

    def backtest(self, long_pct: float = 0.3, short_pct: float = 0.3) -> pd.Series:
        """Long-short factor portfolio."""
        return self._run(long_pct, short_pct, mode='long_short')

    def backtest_long_only(self, top_pct: float = 0.5) -> pd.Series:
        """Long-only factor-tilted portfolio: score-weighted top N%."""
        return self._run(top_pct, 0, mode='long_only')

    def _run(self, long_pct, short_pct, mode='long_short') -> pd.Series:
        monthly_dates = self.factor_scores.resample(self.config.rebalance_freq).last().index
        positions = pd.DataFrame(0.0, index=self.prices.index, columns=self.prices.columns)

        for i, date in enumerate(monthly_dates):
            if date not in self.factor_scores.index:
                continue

            scores = self.factor_scores.loc[date].dropna()
            if len(scores) < 5:
                continue

            next_date = monthly_dates[i + 1] if i + 1 < len(monthly_dates) else self.prices.index[-1]
            mask = (self.prices.index > date) & (self.prices.index <= next_date)

            if mode == 'long_only':
                n_long = max(1, int(len(scores) * long_pct))
                top = scores.nlargest(n_long)
                # Score-weighted (shift to positive)
                w = top - top.min() + 1e-6
                w = w / w.sum()
                for col in w.index:
                    positions.loc[mask, col] = w[col]
            else:
                n_long = max(1, int(len(scores) * long_pct))
                n_short = max(1, int(len(scores) * short_pct))
                long_stocks = scores.nlargest(n_long).index
                short_stocks = scores.nsmallest(n_short).index
                for col in self.prices.columns:
                    if col in long_stocks:
                        positions.loc[mask, col] = 1.0 / n_long
                    elif col in short_stocks:
                        positions.loc[mask, col] = -1.0 / n_short

        daily_pnl = (positions * self.returns).sum(axis=1)
        turnover = positions.diff().abs().sum(axis=1)
        costs = turnover * (self.config.commission_rate + self.config.slippage)
        daily_pnl -= costs
        return daily_pnl


# ============================================================
# Performance Analytics
# ============================================================
def calc_performance(daily_returns: pd.Series, name: str = 'Strategy') -> Dict:
    """Calculate comprehensive performance metrics."""
    daily_returns = daily_returns.dropna()
    if len(daily_returns) < 30:
        return {'name': name, 'error': 'insufficient data'}

    cum_returns = (1 + daily_returns).cumprod()
    total_return = cum_returns.iloc[-1] - 1

    n_years = len(daily_returns) / 252
    ann_return = (1 + total_return) ** (1 / n_years) - 1
    ann_vol = daily_returns.std() * np.sqrt(252)

    # Risk-free rate ~ 2.5% for the period
    rf = 0.025
    sharpe = (ann_return - rf) / ann_vol if ann_vol > 0 else 0

    # Sortino
    downside = daily_returns[daily_returns < 0]
    downside_vol = downside.std() * np.sqrt(252) if len(downside) > 0 else 1e-8
    sortino = (ann_return - rf) / downside_vol

    # Max drawdown
    rolling_max = cum_returns.cummax()
    drawdown = (cum_returns - rolling_max) / rolling_max
    max_dd = drawdown.min()

    # Calmar
    calmar = ann_return / abs(max_dd) if max_dd != 0 else 0

    # Win rate
    win_rate = (daily_returns > 0).sum() / len(daily_returns)

    # Monthly stats
    monthly = daily_returns.resample('ME').sum()
    monthly_win = (monthly > 0).sum() / len(monthly) if len(monthly) > 0 else 0
    best_month = monthly.max()
    worst_month = monthly.min()

    # Yearly returns
    yearly = daily_returns.resample('YE').apply(lambda x: (1 + x).prod() - 1)

    return {
        'name': name,
        'total_return': float(total_return),
        'annualized_return': float(ann_return),
        'annualized_volatility': float(ann_vol),
        'sharpe_ratio': float(sharpe),
        'sortino_ratio': float(sortino),
        'max_drawdown': float(max_dd),
        'calmar_ratio': float(calmar),
        'daily_win_rate': float(win_rate),
        'monthly_win_rate': float(monthly_win),
        'best_month': float(best_month),
        'worst_month': float(worst_month),
        'n_years': float(n_years),
        'n_days': int(len(daily_returns)),
        'yearly_returns': {str(d.year): float(r) for d, r in yearly.items()},
    }


def print_performance_table(results: List[Dict]):
    """Pretty-print performance comparison table."""
    print("\n" + "=" * 100)
    print(f"{'Strategy':<25} {'Ann.Ret':>8} {'Ann.Vol':>8} {'Sharpe':>8} {'Sortino':>8} {'MaxDD':>8} {'Calmar':>8} {'WinRate':>8}")
    print("=" * 100)

    for r in results:
        if 'error' in r:
            print(f"{r['name']:<25} {'ERROR':>8}")
            continue
        print(
            f"{r['name']:<25}"
            f" {r['annualized_return']*100:>7.2f}%"
            f" {r['annualized_volatility']*100:>7.2f}%"
            f" {r['sharpe_ratio']:>8.2f}"
            f" {r['sortino_ratio']:>8.2f}"
            f" {r['max_drawdown']*100:>7.2f}%"
            f" {r['calmar_ratio']:>8.2f}"
            f" {r['monthly_win_rate']*100:>7.1f}%"
        )
    print("=" * 100)


def print_yearly_table(results: List[Dict]):
    """Print year-by-year return comparison."""
    # Collect all years
    all_years = set()
    for r in results:
        if 'yearly_returns' in r:
            all_years.update(r['yearly_returns'].keys())
    all_years = sorted(all_years)

    print("\n" + "=" * 80)
    header = f"{'Year':<6}"
    for r in results:
        header += f" {r['name'][:18]:>18}"
    print(header)
    print("=" * 80)

    for year in all_years:
        row = f"{year:<6}"
        for r in results:
            yr = r.get('yearly_returns', {}).get(year, None)
            if yr is not None:
                row += f" {yr*100:>17.2f}%"
            else:
                row += f" {'N/A':>18}"
        print(row)
    print("=" * 80)


# ============================================================
# Main Backtest Runner
# ============================================================
def run_full_backtest():
    """Run the complete multi-factor + CTA backtest with real data."""

    config = BacktestConfig()

    print("=" * 80)
    print("MULTI-FACTOR + CTA STRATEGY BACKTEST (REAL DATA)")
    print(f"Period: {config.start_date} to {config.end_date}")
    print(f"Initial Capital: ${config.initial_capital:,.0f}")
    print(f"Data Source: Yahoo Finance (yfinance)")
    print("=" * 80)

    # --------------------------------------------------------
    # 1. Fetch Data
    # --------------------------------------------------------
    print("\n[1/5] Fetching real market data...")
    stock_prices = fetch_price_data(STOCK_UNIVERSE, config.start_date, config.end_date)
    cta_prices = fetch_price_data(CTA_UNIVERSE, config.start_date, config.end_date)

    # --------------------------------------------------------
    # 2. Build Factors
    # --------------------------------------------------------
    print("\n[2/5] Constructing factors...")
    engine = FactorEngine(stock_prices)

    value_scores = engine.value_factor()
    mom_scores = engine.momentum_factor()
    quality_scores = engine.quality_factor()
    lowvol_scores = engine.lowvol_factor()
    composite_scores = engine.composite_factor(config)

    logger.info(f"Factor scores computed for {len(stock_prices.columns)} stocks over {len(stock_prices)} days")

    # --------------------------------------------------------
    # 3. Run Factor Backtests
    # --------------------------------------------------------
    print("\n[3/5] Running factor strategy backtests...")

    factor_results = {}
    factors = {
        'Value (12m Rev)': value_scores,
        'Momentum (12-1)': mom_scores,
        'Quality (Sharpe)': quality_scores,
        'Low Volatility': lowvol_scores,
        'Composite': composite_scores,
    }

    # Long-short
    for name, scores in factors.items():
        bt = FactorBacktester(stock_prices, scores, config)
        pnl = bt.backtest()
        factor_results[name] = pnl
        perf = calc_performance(pnl, name)
        logger.info(f"  {name} (L/S): Ann.Ret={perf.get('annualized_return', 0)*100:.2f}%, Sharpe={perf.get('sharpe_ratio', 0):.2f}")

    # Long-only factor-tilted (more realistic for ETFs)
    lo_results = {}
    for name, scores in factors.items():
        bt = FactorBacktester(stock_prices, scores, config)
        pnl = bt.backtest_long_only(top_pct=0.5)
        lo_name = f"{name} (LO)"
        lo_results[lo_name] = pnl
        perf = calc_performance(pnl, lo_name)
        logger.info(f"  {lo_name}: Ann.Ret={perf.get('annualized_return', 0)*100:.2f}%, Sharpe={perf.get('sharpe_ratio', 0):.2f}")

    # --------------------------------------------------------
    # 4. Run CTA Backtest
    # --------------------------------------------------------
    print("\n[4/5] Running CTA trend-following backtest...")
    cta_engine = CTAEngine(cta_prices, config)
    cta_pnl, cta_positions = cta_engine.backtest()
    cta_perf = calc_performance(cta_pnl, 'CTA Trend')
    logger.info(f"  CTA: Ann.Ret={cta_perf.get('annualized_return', 0)*100:.2f}%, Sharpe={cta_perf.get('sharpe_ratio', 0):.2f}")

    # --------------------------------------------------------
    # 5. Combined Portfolio
    # --------------------------------------------------------
    print("\n[5/5] Constructing combined portfolios...")

    # Use long-only composite for combinations
    lo_composite = lo_results['Composite (LO)']

    # Align dates
    common_idx = lo_composite.index.intersection(cta_pnl.index)
    stock_ret = lo_composite.loc[common_idx]
    cta_ret = cta_pnl.loc[common_idx]

    # Combined: 60% LO factor + 40% CTA
    combined_pnl = config.stock_allocation * stock_ret + config.cta_allocation * cta_ret

    # Also: equal weight all LO factors + CTA
    all_lo_pnl = pd.DataFrame({k: v for k, v in lo_results.items()})
    avg_lo_pnl = all_lo_pnl.mean(axis=1)
    combined_v2 = 0.6 * avg_lo_pnl.loc[common_idx] + 0.4 * cta_ret

    # L/S version for comparison
    ls_composite = factor_results['Composite']
    combined_ls = 0.6 * ls_composite.loc[common_idx] + 0.4 * cta_ret

    # --------------------------------------------------------
    # Results
    # --------------------------------------------------------
    print("\n" + "=" * 80)
    print("BACKTEST RESULTS")
    print("=" * 80)

    all_results = []

    # Long-short factor results
    for name, pnl in factor_results.items():
        all_results.append(calc_performance(pnl, name))

    # Long-only factor results
    for name, pnl in lo_results.items():
        all_results.append(calc_performance(pnl, name))

    all_results.append(cta_perf)
    all_results.append(calc_performance(combined_pnl, 'LO+CTA (60/40)'))
    all_results.append(calc_performance(combined_v2, 'AvgLO+CTA (60/40)'))
    all_results.append(calc_performance(combined_ls, 'LS+CTA (60/40)'))

    # Benchmarks
    if 'SPY' in stock_prices.columns:
        spy_ret = stock_prices['SPY'].pct_change().dropna()
        all_results.append(calc_performance(spy_ret, 'Benchmark (SPY B&H)'))

    # Equal-weight buy-and-hold all ETFs
    ew_ret = stock_prices.pct_change().mean(axis=1).dropna()
    all_results.append(calc_performance(ew_ret, 'EqualWeight B&H'))

    print_performance_table(all_results)
    print_yearly_table(all_results)

    # --------------------------------------------------------
    # Factor Correlation
    # --------------------------------------------------------
    print("\n" + "=" * 80)
    print("FACTOR RETURN CORRELATIONS")
    print("=" * 80)
    corr_df = pd.DataFrame({k: v for k, v in factor_results.items()})
    corr_df['CTA'] = cta_pnl
    corr_matrix = corr_df.corr()
    print(corr_matrix.round(3).to_string())

    # --------------------------------------------------------
    # Save Results
    # --------------------------------------------------------
    output = {
        'metadata': {
            'backtest_period': f"{config.start_date} to {config.end_date}",
            'data_source': 'Yahoo Finance (yfinance) - REAL DATA',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'stock_universe': list(STOCK_UNIVERSE.keys()),
            'cta_universe': list(CTA_UNIVERSE.keys()),
            'config': {
                'initial_capital': config.initial_capital,
                'commission_rate': config.commission_rate,
                'slippage': config.slippage,
                'stock_allocation': config.stock_allocation,
                'cta_allocation': config.cta_allocation,
                'value_weight': config.value_weight,
                'momentum_weight': config.momentum_weight,
                'quality_weight': config.quality_weight,
                'lowvol_weight': config.lowvol_weight,
            }
        },
        'results': {r['name']: r for r in all_results},
    }

    output_path = 'backtests/real_data_yfinance_results.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    logger.info(f"Results saved to {output_path}")

    # Save equity curves
    equity_data = pd.DataFrame({k: (1 + v).cumprod() for k, v in lo_results.items()})
    equity_data['CTA'] = (1 + cta_pnl).cumprod()
    equity_data['LO+CTA'] = (1 + combined_pnl).cumprod()
    equity_data['AvgLO+CTA'] = (1 + combined_v2).cumprod()
    if 'SPY' in stock_prices.columns:
        equity_data['SPY_BH'] = (1 + stock_prices['SPY'].pct_change()).cumprod()
    equity_data.to_csv('backtests/real_data_equity_curves.csv')
    logger.info("Equity curves saved to backtests/real_data_equity_curves.csv")

    return all_results, equity_data


if __name__ == '__main__':
    results, equity = run_full_backtest()
