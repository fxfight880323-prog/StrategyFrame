"""
CTA + Earnings Cross Analysis for S&P 500
==========================================

Analyze S&P 500 stocks using CTA (trend-following) framework combined with earnings data.
Generate sector-level recommendations based on:
1. CTA technical signals (trend, momentum)
2. Earnings surprise and growth metrics
3. Sector rotation analysis

Output: Sector ranking and stock picks within each sector
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging
import warnings
warnings.filterwarnings('ignore')

# Setup logging
def setup_logger(name: str = "cta_earnings") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# Data Models
# ============================================================
class SignalType(Enum):
    STRONG_BUY = 5
    BUY = 4
    WEAK_BUY = 3
    HOLD = 2
    WEAK_SELL = 1
    SELL = 0
    STRONG_SELL = -1

@dataclass
class EarningsData:
    """Earnings data for a stock"""
    symbol: str
    report_date: date
    eps_actual: float
    eps_estimate: float
    revenue_actual: float
    revenue_estimate: float
    eps_surprise_pct: float
    revenue_surprise_pct: float
    eps_growth_yoy: float
    revenue_growth_yoy: float
    
    @property
    def eps_beat(self) -> bool:
        return self.eps_actual > self.eps_estimate
    
    @property
    def revenue_beat(self) -> bool:
        return self.revenue_actual > self.revenue_estimate

@dataclass
class CTASignal:
    """CTA technical signal"""
    symbol: str
    date: date
    signal: SignalType
    trend_score: float  # 0-100
    momentum_score: float  # 0-100
    volatility: float
    price: float
    ma20: float
    ma60: float
    rsi: float

@dataclass
class CrossSignal:
    """Combined CTA + Earnings signal"""
    symbol: str
    sector: str
    date: date
    cta_signal: SignalType
    earnings_signal: SignalType
    combined_score: float  # -100 to 100
    cta_weight: float
    earnings_weight: float
    metadata: Dict = field(default_factory=dict)

@dataclass
class SectorAnalysis:
    """Sector-level analysis result"""
    sector: str
    avg_combined_score: float
    bullish_stocks: int
    bearish_stocks: int
    top_picks: List[str]
    bottom_picks: List[str]
    momentum_trend: str  # "accelerating", "decelerating", "stable"
    recommendation: str  # "Overweight", "Neutral", "Underweight"


# ============================================================
# S&P 500 Sector Mapping
# ============================================================
SP500_SECTORS = {
    'Technology': {
        'tickers': ['AAPL', 'MSFT', 'NVDA', 'AVGO', 'META', 'TSLA', 'GOOGL', 'GOOG', 'AMD', 'CRM',
                   'ADBE', 'ORCL', 'ACN', 'IBM', 'QCOM', 'INTU', 'TXN', 'AMAT', 'NOW', 'PANW'],
        'weight': 0.30
    },
    'Communication Services': {
        'tickers': ['GOOGL', 'META', 'NFLX', 'VZ', 'T', 'DIS', 'CMCSA', 'TMUS', 'CHTR', 'VFC'],
        'weight': 0.08
    },
    'Consumer Discretionary': {
        'tickers': ['AMZN', 'TSLA', 'HD', 'MCD', 'NKE', 'LOW', 'SBUX', 'BKNG', 'TJX', 'MAR'],
        'weight': 0.10
    },
    'Consumer Staples': {
        'tickers': ['WMT', 'PG', 'KO', 'COST', 'PEP', 'PM', 'CVS', 'MDLZ', 'CL', 'GIS'],
        'weight': 0.06
    },
    'Healthcare': {
        'tickers': ['LLY', 'JNJ', 'UNH', 'MRK', 'ABBV', 'PFE', 'TMO', 'ABT', 'DHR', 'BMY'],
        'weight': 0.13
    },
    'Financials': {
        'tickers': ['BRK-B', 'JPM', 'V', 'MA', 'BAC', 'WFC', 'GS', 'MS', 'BLK', 'C'],
        'weight': 0.13
    },
    'Industrials': {
        'tickers': ['GE', 'CAT', 'BA', 'HON', 'UPS', 'UNP', 'RTX', 'LMT', 'DE', 'ADP'],
        'weight': 0.08
    },
    'Energy': {
        'tickers': ['XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'WMB'],
        'weight': 0.04
    },
    'Materials': {
        'tickers': ['LIN', 'SHW', 'APD', 'FCX', 'NEM', 'ECL', 'DOW', 'NUE', 'STLD', 'PPG'],
        'weight': 0.02
    },
    'Utilities': {
        'tickers': ['NEE', 'SO', 'DUK', 'D', 'AEP', 'EXC', 'SRE', 'XEL', 'ED', 'WEC'],
        'weight': 0.02
    },
    'Real Estate': {
        'tickers': ['AMT', 'PLD', 'CCI', 'EQIX', 'PSA', 'O', 'WELL', 'SBAC', 'DLR', 'SPG'],
        'weight': 0.02
    }
}


def get_sector_for_ticker(ticker: str) -> str:
    """Get sector for a given ticker"""
    for sector, data in SP500_SECTORS.items():
        if ticker.upper() in [t.upper() for t in data['tickers']]:
            return sector
    return "Unknown"


# ============================================================
# Data Provider Interface
# ============================================================
class DataProvider:
    """Base class for data providers"""
    
    def get_price_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError
    
    def get_earnings_data(self, symbol: str) -> List[EarningsData]:
        raise NotImplementedError
    
    def get_sp500_tickers(self) -> List[str]:
        return [ticker for sector in SP500_SECTORS.values() for ticker in sector['tickers']]


class MockDataProvider(DataProvider):
    """Mock data provider for testing"""
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or setup_logger()
        self.cache = {}
    
    def get_price_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Generate mock price data with realistic sector characteristics"""
        cache_key = f"{symbol}_{start_date}_{end_date}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        n = len(dates)
        
        # Different volatility profiles by sector
        sector = get_sector_for_ticker(symbol)
        vol_map = {
            'Technology': 0.018,
            'Energy': 0.022,
            'Financials': 0.015,
            'Healthcare': 0.012,
            'Utilities': 0.008,
        }
        base_vol = vol_map.get(sector, 0.015)
        
        np.random.seed(hash(symbol) % 2**32)
        
        # Add trend component based on sector momentum
        sector_trends = {
            'Technology': 0.0004,
            'Communication Services': 0.0003,
            'Healthcare': 0.0002,
            'Financials': 0.0001,
            'Energy': -0.0001,
            'Utilities': 0.00005,
        }
        trend = sector_trends.get(sector, 0)
        
        returns = np.random.normal(trend, base_vol, n)
        
        # Add earnings announcement effect (if near earnings)
        earnings_dates = pd.date_range(start=start_date, end=end_date, freq='QE')
        for ed in earnings_dates:
            if ed in dates:
                idx = dates.get_loc(ed)
                if idx > 0:
                    # Random earnings surprise effect
                    surprise = np.random.choice([-1, 1]) * np.random.uniform(0.02, 0.05)
                    returns[idx] += surprise
        
        start_price = np.random.uniform(50, 500)
        prices = start_price * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'date': dates,
            'open': prices * (1 + np.random.normal(0, 0.002, n)),
            'high': prices * (1 + abs(np.random.normal(0, 0.01, n))),
            'low': prices * (1 - abs(np.random.normal(0, 0.01, n))),
            'close': prices,
            'volume': np.random.randint(1000000, 50000000, n),
        })
        
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.set_index('date')
        
        self.cache[cache_key] = df
        return df
    
    def get_earnings_data(self, symbol: str) -> List[EarningsData]:
        """Generate mock earnings data"""
        np.random.seed(hash(symbol) % 2**32)
        
        # Generate quarterly earnings for past year
        quarters = [
            date(2024, 3, 31),
            date(2024, 6, 30),
            date(2024, 9, 30),
            date(2024, 12, 31),
        ]
        
        earnings_list = []
        base_eps = np.random.uniform(1.0, 5.0)
        base_revenue = np.random.uniform(5e9, 50e9)
        
        for i, q_date in enumerate(quarters):
            # Simulate earnings growth
            growth = np.random.uniform(-0.1, 0.3)
            eps_actual = base_eps * (1 + growth) ** i
            eps_estimate = eps_actual * np.random.uniform(0.9, 1.1)
            
            revenue_actual = base_revenue * (1 + growth * 0.8) ** i
            revenue_estimate = revenue_actual * np.random.uniform(0.95, 1.05)
            
            eps_surprise = (eps_actual - eps_estimate) / abs(eps_estimate) * 100
            revenue_surprise = (revenue_actual - revenue_estimate) / abs(revenue_estimate) * 100
            
            earnings_list.append(EarningsData(
                symbol=symbol,
                report_date=q_date,
                eps_actual=eps_actual,
                eps_estimate=eps_estimate,
                revenue_actual=revenue_actual,
                revenue_estimate=revenue_estimate,
                eps_surprise_pct=eps_surprise,
                revenue_surprise_pct=revenue_surprise,
                eps_growth_yoy=growth * 100,
                revenue_growth_yoy=growth * 80
            ))
        
        return earnings_list


# ============================================================
# CTA Signal Generator
# ============================================================
class CTASignalGenerator:
    """Generate CTA technical signals"""
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or setup_logger()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate technical indicators"""
        df = df.copy()
        
        # Moving averages
        df['ma20'] = df['close'].rolling(20).mean()
        df['ma60'] = df['close'].rolling(60).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        
        # Bollinger Bands
        df['bb_middle'] = df['close'].rolling(20).mean()
        bb_std = df['close'].rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + 2 * bb_std
        df['bb_lower'] = df['bb_middle'] - 2 * bb_std
        
        # Volatility
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(20).std() * np.sqrt(252)
        
        return df
    
    def generate_signal(self, symbol: str, df: pd.DataFrame, current_date: date) -> CTASignal:
        """Generate CTA signal for a stock"""
        df = self.calculate_indicators(df)
        
        # Get latest data
        df_filtered = df[df.index <= current_date]
        if len(df_filtered) < 60:
            return CTASignal(
                symbol=symbol, date=current_date, signal=SignalType.HOLD,
                trend_score=50, momentum_score=50, volatility=0.2,
                price=0, ma20=0, ma60=0, rsi=50
            )
        
        latest = df_filtered.iloc[-1]
        
        # Trend score (0-100)
        trend_score = 50
        if latest['close'] > latest['ma20'] > latest['ma60']:
            trend_score = 80
        elif latest['close'] > latest['ma20']:
            trend_score = 65
        elif latest['close'] < latest['ma20'] < latest['ma60']:
            trend_score = 20
        elif latest['close'] < latest['ma20']:
            trend_score = 35
        
        # Momentum score
        momentum_score = 50
        if latest['macd'] > latest['macd_signal'] and latest['rsi'] > 50:
            momentum_score = 75
        elif latest['macd'] < latest['macd_signal'] and latest['rsi'] < 50:
            momentum_score = 25
        
        # Combined signal
        combined = (trend_score + momentum_score) / 2
        
        if combined >= 80:
            signal = SignalType.STRONG_BUY
        elif combined >= 65:
            signal = SignalType.BUY
        elif combined >= 55:
            signal = SignalType.WEAK_BUY
        elif combined >= 45:
            signal = SignalType.HOLD
        elif combined >= 35:
            signal = SignalType.WEAK_SELL
        elif combined >= 20:
            signal = SignalType.SELL
        else:
            signal = SignalType.STRONG_SELL
        
        return CTASignal(
            symbol=symbol,
            date=current_date,
            signal=signal,
            trend_score=trend_score,
            momentum_score=momentum_score,
            volatility=latest.get('volatility', 0.2),
            price=latest['close'],
            ma20=latest['ma20'],
            ma60=latest['ma60'],
            rsi=latest['rsi']
        )


# ============================================================
# Earnings Signal Generator
# ============================================================
class EarningsSignalGenerator:
    """Generate earnings-based signals"""
    
    def generate_signal(self, earnings_data: List[EarningsData]) -> SignalType:
        """Generate signal based on earnings data"""
        if not earnings_data:
            return SignalType.HOLD
        
        # Use most recent quarter
        latest = earnings_data[-1]
        
        # Score components
        score = 50  # Neutral base
        
        # EPS surprise
        if latest.eps_surprise_pct > 10:
            score += 25
        elif latest.eps_surprise_pct > 5:
            score += 15
        elif latest.eps_surprise_pct > 0:
            score += 5
        elif latest.eps_surprise_pct < -10:
            score -= 25
        elif latest.eps_surprise_pct < -5:
            score -= 15
        elif latest.eps_surprise_pct < 0:
            score -= 5
        
        # Revenue surprise
        if latest.revenue_surprise_pct > 5:
            score += 10
        elif latest.revenue_surprise_pct < -5:
            score -= 10
        
        # Growth
        if latest.eps_growth_yoy > 20:
            score += 15
        elif latest.eps_growth_yoy > 10:
            score += 10
        elif latest.eps_growth_yoy < -10:
            score -= 15
        
        # Convert score to signal
        if score >= 85:
            return SignalType.STRONG_BUY
        elif score >= 70:
            return SignalType.BUY
        elif score >= 60:
            return SignalType.WEAK_BUY
        elif score >= 40:
            return SignalType.HOLD
        elif score >= 30:
            return SignalType.WEAK_SELL
        elif score >= 15:
            return SignalType.SELL
        else:
            return SignalType.STRONG_SELL


# ============================================================
# Cross Analysis Engine
# ============================================================
class CTAEarningsCrossAnalyzer:
    """
    CTA + Earnings Cross Analysis Engine
    
    Combines technical and fundamental signals for sector analysis
    """
    
    def __init__(self, data_provider: DataProvider, logger: logging.Logger = None):
        self.provider = data_provider
        self.logger = logger or setup_logger()
        self.cta_generator = CTASignalGenerator(logger)
        self.earnings_generator = EarningsSignalGenerator()
        
        # Weights for combined score
        self.cta_weight = 0.6
        self.earnings_weight = 0.4
    
    def analyze_stock(self, symbol: str, current_date: date) -> Optional[CrossSignal]:
        """Analyze a single stock"""
        try:
            # Get data
            start_date = (datetime.strptime(str(current_date), '%Y-%m-%d') - timedelta(days=180)).strftime('%Y-%m-%d')
            end_date = str(current_date)
            
            price_df = self.provider.get_price_data(symbol, start_date, end_date)
            earnings_data = self.provider.get_earnings_data(symbol)
            
            if price_df.empty:
                return None
            
            # Generate signals
            cta_signal = self.cta_generator.generate_signal(symbol, price_df, current_date)
            earnings_signal = self.earnings_generator.generate_signal(earnings_data)
            
            # Calculate combined score (-100 to 100)
            cta_score = (cta_signal.trend_score + cta_signal.momentum_score) / 2 - 50
            earnings_score = (earnings_signal.value - 2) * 25  # Convert to -100 to 100 scale
            
            combined = cta_score * self.cta_weight + earnings_score * self.earnings_weight
            
            sector = get_sector_for_ticker(symbol)
            
            return CrossSignal(
                symbol=symbol,
                sector=sector,
                date=current_date,
                cta_signal=cta_signal.signal,
                earnings_signal=earnings_signal,
                combined_score=combined,
                cta_weight=self.cta_weight,
                earnings_weight=self.earnings_weight,
                metadata={
                    'trend_score': cta_signal.trend_score,
                    'momentum_score': cta_signal.momentum_score,
                    'price': cta_signal.price,
                    'rsi': cta_signal.rsi,
                    'eps_surprise': earnings_data[-1].eps_surprise_pct if earnings_data else 0,
                    'revenue_surprise': earnings_data[-1].revenue_surprise_pct if earnings_data else 0,
                }
            )
        except Exception as e:
            self.logger.debug(f"Error analyzing {symbol}: {e}")
            return None
    
    def analyze_sector(self, sector: str, current_date: date) -> SectorAnalysis:
        """Analyze all stocks in a sector"""
        tickers = SP500_SECTORS.get(sector, {}).get('tickers', [])
        
        signals = []
        for ticker in tickers:
            signal = self.analyze_stock(ticker, current_date)
            if signal:
                signals.append(signal)
        
        if not signals:
            return SectorAnalysis(
                sector=sector, avg_combined_score=0,
                bullish_stocks=0, bearish_stocks=0,
                top_picks=[], bottom_picks=[],
                momentum_trend="stable", recommendation="Neutral"
            )
        
        # Calculate metrics
        avg_score = np.mean([s.combined_score for s in signals])
        bullish = len([s for s in signals if s.combined_score > 20])
        bearish = len([s for s in signals if s.combined_score < -20])
        
        # Sort by combined score
        sorted_signals = sorted(signals, key=lambda x: x.combined_score, reverse=True)
        top_picks = [s.symbol for s in sorted_signals[:5]]
        bottom_picks = [s.symbol for s in sorted_signals[-5:]]
        
        # Determine momentum trend
        if avg_score > 30:
            trend = "accelerating"
            rec = "Overweight"
        elif avg_score > 10:
            trend = "improving"
            rec = "Overweight"
        elif avg_score > -10:
            trend = "stable"
            rec = "Neutral"
        elif avg_score > -30:
            trend = "weakening"
            rec = "Underweight"
        else:
            trend = "decelerating"
            rec = "Underweight"
        
        return SectorAnalysis(
            sector=sector,
            avg_combined_score=avg_score,
            bullish_stocks=bullish,
            bearish_stocks=bearish,
            top_picks=top_picks,
            bottom_picks=bottom_picks,
            momentum_trend=trend,
            recommendation=rec
        )
    
    def analyze_all_sectors(self, current_date: date) -> List[SectorAnalysis]:
        """Analyze all S&P 500 sectors"""
        self.logger.info(f"Analyzing all sectors for {current_date}")
        
        results = []
        for sector in SP500_SECTORS.keys():
            self.logger.info(f"  Analyzing {sector}...")
            analysis = self.analyze_sector(sector, current_date)
            results.append(analysis)
        
        # Sort by average combined score
        results.sort(key=lambda x: x.avg_combined_score, reverse=True)
        
        return results


# ============================================================
# Report Generator
# ============================================================
class ReportGenerator:
    """Generate analysis reports"""
    
    def generate_sector_report(self, analyses: List[SectorAnalysis]) -> str:
        """Generate sector ranking report"""
        lines = []
        lines.append("=" * 100)
        lines.append("CTA + EARNINGS CROSS ANALYSIS REPORT - S&P 500 SECTOR RECOMMENDATIONS")
        lines.append("=" * 100)
        lines.append("")
        
        # Sector ranking table
        lines.append("SECTOR RANKING (Top to Bottom)")
        lines.append("-" * 100)
        lines.append(f"{'Rank':<6} {'Sector':<25} {'Score':>10} {'Bull/Bear':>12} {'Trend':<15} {'Recommendation':<15}")
        lines.append("-" * 100)
        
        for i, analysis in enumerate(analyses, 1):
            bull_bear = f"{analysis.bullish_stocks}/{analysis.bearish_stocks}"
            lines.append(
                f"{i:<6} {analysis.sector:<25} "
                f"{analysis.avg_combined_score:>10.2f} "
                f"{bull_bear:>12} "
                f"{analysis.momentum_trend:<15} "
                f"{analysis.recommendation:<15}"
            )
        
        lines.append("-" * 100)
        lines.append("")
        
        # Top recommendations
        lines.append("TOP RECOMMENDED SECTORS")
        lines.append("=" * 100)
        top_3 = [a for a in analyses if a.recommendation == "Overweight"][:3]
        
        for analysis in top_3:
            lines.append(f"\n{analysis.sector.upper()} - Score: {analysis.avg_combined_score:.2f}")
            lines.append(f"  Trend: {analysis.momentum_trend}")
            lines.append(f"  Bullish/Bearish stocks: {analysis.bullish_stocks}/{analysis.bearish_stocks}")
            lines.append(f"  Top picks: {', '.join(analysis.top_picks)}")
            lines.append(f"  Avoid: {', '.join(analysis.bottom_picks)}")
        
        lines.append("")
        lines.append("SECTORS TO UNDERWEIGHT")
        lines.append("=" * 100)
        bottom_3 = [a for a in analyses if a.recommendation == "Underweight"][-3:]
        
        for analysis in bottom_3:
            lines.append(f"\n{analysis.sector.upper()} - Score: {analysis.avg_combined_score:.2f}")
            lines.append(f"  Trend: {analysis.momentum_trend}")
            lines.append(f"  Bullish/Bearish stocks: {analysis.bullish_stocks}/{analysis.bearish_stocks}")
            lines.append(f"  Bottom picks: {', '.join(analysis.bottom_picks)}")
        
        lines.append("")
        lines.append("=" * 100)
        
        return "\n".join(lines)
    
    def generate_stock_level_report(self, analyzer: CTAEarningsCrossAnalyzer, 
                                    sector: str, current_date: date) -> str:
        """Generate detailed stock-level report for a sector"""
        tickers = SP500_SECTORS.get(sector, {}).get('tickers', [])
        
        lines = []
        lines.append(f"\n{sector.upper()} - STOCK LEVEL ANALYSIS")
        lines.append("=" * 100)
        lines.append("")
        
        signals = []
        for ticker in tickers:
            signal = analyzer.analyze_stock(ticker, current_date)
            if signal:
                signals.append(signal)
        
        # Sort by combined score
        signals.sort(key=lambda x: x.combined_score, reverse=True)
        
        lines.append(f"{'Ticker':<8} {'CTA':<12} {'Earnings':<12} {'Combined':>10} {'Trend':>8} {'Mom':>8} {'EPS Surp':>10} {'Rev Surp':>10}")
        lines.append("-" * 100)
        
        for signal in signals:
            meta = signal.metadata
            lines.append(
                f"{signal.symbol:<8} "
                f"{signal.cta_signal.name:<12} "
                f"{signal.earnings_signal.name:<12} "
                f"{signal.combined_score:>10.2f} "
                f"{meta.get('trend_score', 0):>8.1f} "
                f"{meta.get('momentum_score', 0):>8.1f} "
                f"{meta.get('eps_surprise', 0):>9.1f}% "
                f"{meta.get('revenue_surprise', 0):>9.1f}%"
            )
        
        lines.append("-" * 100)
        
        return "\n".join(lines)


# ============================================================
# Main Execution
# ============================================================
def main():
    """Main execution function"""
    print("=" * 100)
    print("CTA + EARNINGS CROSS ANALYSIS FOR S&P 500")
    print("=" * 100)
    print()
    print("This system combines CTA (trend-following) signals with earnings data")
    print("to generate sector-level recommendations for S&P 500 stocks.")
    print()
    
    # Initialize components
    logger = setup_logger()
    provider = MockDataProvider(logger)
    analyzer = CTAEarningsCrossAnalyzer(provider, logger)
    report_gen = ReportGenerator()
    
    current_date = date(2024, 12, 31)
    
    # Run analysis
    print("Running analysis...")
    print()
    
    sector_analyses = analyzer.analyze_all_sectors(current_date)
    
    # Generate and print reports
    sector_report = report_gen.generate_sector_report(sector_analyses)
    print(sector_report)
    
    # Detailed reports for top and bottom sectors
    print("\n\nDETAILED STOCK-LEVEL ANALYSIS")
    print("=" * 100)
    
    top_sector = sector_analyses[0]
    bottom_sector = sector_analyses[-1]
    
    top_detail = report_gen.generate_stock_level_report(analyzer, top_sector.sector, current_date)
    print(top_detail)
    
    bottom_detail = report_gen.generate_stock_level_report(analyzer, bottom_sector.sector, current_date)
    print(bottom_detail)
    
    # Summary
    print("\n" + "=" * 100)
    print("ANALYSIS SUMMARY")
    print("=" * 100)
    print()
    print(f"Analysis Date: {current_date}")
    print(f"Total Sectors Analyzed: {len(sector_analyses)}")
    print(f"Overweight Recommendations: {len([a for a in sector_analyses if a.recommendation == 'Overweight'])}")
    print(f"Neutral Recommendations: {len([a for a in sector_analyses if a.recommendation == 'Neutral'])}")
    print(f"Underweight Recommendations: {len([a for a in sector_analyses if a.recommendation == 'Underweight'])}")
    print()
    print(f"TOP SECTOR: {top_sector.sector} (Score: {top_sector.avg_combined_score:.2f})")
    print(f"  Recommended stocks: {', '.join(top_sector.top_picks[:3])}")
    print()
    print(f"BOTTOM SECTOR: {bottom_sector.sector} (Score: {bottom_sector.avg_combined_score:.2f})")
    print(f"  Stocks to avoid: {', '.join(bottom_sector.bottom_picks[:3])}")
    print()
    print("=" * 100)


if __name__ == "__main__":
    main()
