"""
RiceQuant Data Provider for CTA
================================

Using RiceQuant API to fetch China futures data

Usage:
    provider = RiceQuantCTADataProvider(api_key=YOUR_KEY)
    df = provider.get_futures_data('RB', '2024-01-01', '2024-12-31')
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import time
import warnings
warnings.filterwarnings('ignore')

# Try import RiceQuant API
try:
    import rqdatac
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False
    print("Warning: RiceQuant API (rqdatac) not installed. Using mock data mode.")
    print("Install: pip install rqdatac")


# ============================================================
# Configuration
# ============================================================

# Futures mapping for RiceQuant
RQ_FUTURES_MAPPING = {
    # SHFE
    'RB': {'rq_code': 'RB', 'exchange': 'SHFE', 'name': 'Rebar', 'multiplier': 10},
    'HC': {'rq_code': 'HC', 'exchange': 'SHFE', 'name': 'Hot Coil', 'multiplier': 10},
    'CU': {'rq_code': 'CU', 'exchange': 'SHFE', 'name': 'Copper', 'multiplier': 5},
    'AL': {'rq_code': 'AL', 'exchange': 'SHFE', 'name': 'Aluminum', 'multiplier': 5},
    'ZN': {'rq_code': 'ZN', 'exchange': 'SHFE', 'name': 'Zinc', 'multiplier': 5},
    'NI': {'rq_code': 'NI', 'exchange': 'SHFE', 'name': 'Nickel', 'multiplier': 1},
    'SN': {'rq_code': 'SN', 'exchange': 'SHFE', 'name': 'Tin', 'multiplier': 1},
    'AU': {'rq_code': 'AU', 'exchange': 'SHFE', 'name': 'Gold', 'multiplier': 1000},
    'AG': {'rq_code': 'AG', 'exchange': 'SHFE', 'name': 'Silver', 'multiplier': 15},
    'FU': {'rq_code': 'FU', 'exchange': 'SHFE', 'name': 'Fuel Oil', 'multiplier': 10},
    'BU': {'rq_code': 'BU', 'exchange': 'SHFE', 'name': 'Asphalt', 'multiplier': 10},
    
    # DCE
    'I':  {'rq_code': 'I', 'exchange': 'DCE', 'name': 'Iron Ore', 'multiplier': 100},
    'J':  {'rq_code': 'J', 'exchange': 'DCE', 'name': 'Coke', 'multiplier': 100},
    'JM': {'rq_code': 'JM', 'exchange': 'DCE', 'name': 'Coking Coal', 'multiplier': 60},
    'M':  {'rq_code': 'M', 'exchange': 'DCE', 'name': 'Soybean Meal', 'multiplier': 10},
    'Y':  {'rq_code': 'Y', 'exchange': 'DCE', 'name': 'Soybean Oil', 'multiplier': 10},
    'P':  {'rq_code': 'P', 'exchange': 'DCE', 'name': 'Palm Oil', 'multiplier': 10},
    'C':  {'rq_code': 'C', 'exchange': 'DCE', 'name': 'Corn', 'multiplier': 10},
    'L':  {'rq_code': 'L', 'exchange': 'DCE', 'name': 'PE', 'multiplier': 5},
    'PP': {'rq_code': 'PP', 'exchange': 'DCE', 'name': 'PP', 'multiplier': 5},
    'V':  {'rq_code': 'V', 'exchange': 'DCE', 'name': 'PVC', 'multiplier': 5},
    'EG': {'rq_code': 'EG', 'exchange': 'DCE', 'name': 'Ethylene Glycol', 'multiplier': 10},
    
    # CZCE
    'TA': {'rq_code': 'TA', 'exchange': 'CZCE', 'name': 'PTA', 'multiplier': 5},
    'MA': {'rq_code': 'MA', 'exchange': 'CZCE', 'name': 'Methanol', 'multiplier': 10},
    'RM': {'rq_code': 'RM', 'exchange': 'CZCE', 'name': 'Rapeseed Meal', 'multiplier': 10},
    'OI': {'rq_code': 'OI', 'exchange': 'CZCE', 'name': 'Rapeseed Oil', 'multiplier': 10},
    'CF': {'rq_code': 'CF', 'exchange': 'CZCE', 'name': 'Cotton', 'multiplier': 5},
    'SR': {'rq_code': 'SR', 'exchange': 'CZCE', 'name': 'Sugar', 'multiplier': 10},
    
    # INE
    'SC': {'rq_code': 'SC', 'exchange': 'INE', 'name': 'Crude Oil', 'multiplier': 1000},
    'LU': {'rq_code': 'LU', 'exchange': 'INE', 'name': 'Low Sulfur Fuel Oil', 'multiplier': 10},
    
    # CFFEX
    'IF': {'rq_code': 'IF', 'exchange': 'CFFEX', 'name': 'CSI 300', 'multiplier': 300},
    'IC': {'rq_code': 'IC', 'exchange': 'CFFEX', 'name': 'CSI 500', 'multiplier': 200},
    'IM': {'rq_code': 'IM', 'exchange': 'CFFEX', 'name': 'CSI 1000', 'multiplier': 200},
    'T':  {'rq_code': 'T', 'exchange': 'CFFEX', 'name': '10Y Treasury', 'multiplier': 10000},
    'TF': {'rq_code': 'TF', 'exchange': 'CFFEX', 'name': '5Y Treasury', 'multiplier': 10000},
}

# Category mapping
CATEGORY_MAP = {
    'Black': ['RB', 'HC', 'I', 'J', 'JM'],
    'Non-ferrous': ['CU', 'AL', 'ZN', 'NI', 'SN'],
    'Energy': ['SC', 'LU', 'FU', 'BU'],
    'Chemicals': ['TA', 'MA', 'PP', 'L', 'V', 'EG'],
    'Agriculture': ['M', 'Y', 'P', 'RM', 'OI', 'C'],
    'Soft': ['CF', 'SR'],
    'Precious': ['AU', 'AG'],
    'Index': ['IF', 'IC', 'IM'],
    'Bond': ['T', 'TF'],
}


def setup_logger(name: str = "rq_cta") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


class RiceQuantCTADataProvider:
    """RiceQuant Futures Data Provider"""
    
    def __init__(self, username: str = None, password: str = None, 
                 api_key: str = None, logger: logging.Logger = None):
        self.logger = logger or setup_logger()
        self.connected = False
        self.cache = {}
        self.api_key = api_key
        
        if RQ_AVAILABLE:
            self._connect(username, password)
        else:
            self.logger.warning("RiceQuant API not installed, using mock data mode")
    
    def _connect(self, username: str = None, password: str = None):
        try:
            self.logger.info("Connecting to RiceQuant API...")
            
            # Try init without parameters first (if already configured)
            try:
                rqdatac.init()
                self.connected = True
                self.logger.info("RiceQuant API connected successfully (using existing config)")
            except:
                # Fallback to provided credentials
                if username and password:
                    rqdatac.init(username=username, password=password)
                    self.connected = True
                    self.logger.info("RiceQuant API connected successfully (using credentials)")
                else:
                    raise Exception("No valid credentials provided")
            
            # Test connection
            test_data = rqdatac.all_instruments(type='Future')
            self.logger.info(f"Available futures: {len(test_data)}")
            
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            self.connected = False
    
    def get_futures_data(self, 
                        symbol: str, 
                        start_date: str, 
                        end_date: str,
                        frequency: str = '1d',
                        fields: List[str] = None) -> pd.DataFrame:
        """Get futures data"""
        cache_key = f"{symbol}_{start_date}_{end_date}_{frequency}"
        if cache_key in self.cache:
            return self.cache[cache_key].copy()
        
        if not self.connected:
            return self._get_mock_data(symbol, start_date, end_date)
        
        try:
            rq_info = RQ_FUTURES_MAPPING.get(symbol)
            if not rq_info:
                self.logger.warning(f"Unknown symbol: {symbol}")
                return self._get_mock_data(symbol, start_date, end_date)
            
            rq_code = rq_info['rq_code']
            
            self.logger.info(f"Fetching {symbol} ({rq_code}) data...")
            
            dominant_code = f"{rq_code}888"
            
            df = rqdatac.get_price(
                dominant_code,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                fields=fields or ['open', 'high', 'low', 'close', 'volume', 'open_interest'],
                adjust_type='none'
            )
            
            if df is None or df.empty:
                self.logger.warning(f"No data returned for {symbol}, using mock data")
                return self._get_mock_data(symbol, start_date, end_date)
            
            df = df.reset_index()
            if 'order_book_id' in df.columns:
                df = df.drop(columns=['order_book_id'])
            
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
            elif 'datetime' in df.columns:
                df['datetime'] = pd.to_datetime(df['datetime'])
                df = df.set_index('datetime')
            
            column_map = {
                'open': 'open', 'high': 'high', 'low': 'low', 'close': 'close',
                'volume': 'volume', 'total_turnover': 'turnover',
                'open_interest': 'open_interest',
            }
            df = df.rename(columns=column_map)
            
            df['symbol'] = symbol
            df['rq_code'] = dominant_code
            
            self.cache[cache_key] = df.copy()
            
            self.logger.info(f"Success: {len(df)} records ({df.index[0].date()} ~ {df.index[-1].date()})")
            
            return df
            
        except Exception as e:
            self.logger.error(f"Fetch failed: {e}")
            return self._get_mock_data(symbol, start_date, end_date)
    
    def get_multiple_futures(self, 
                            symbols: List[str],
                            start_date: str,
                            end_date: str,
                            frequency: str = '1d') -> Dict[str, pd.DataFrame]:
        """Batch get futures data"""
        results = {}
        for symbol in symbols:
            df = self.get_futures_data(symbol, start_date, end_date, frequency)
            if not df.empty:
                results[symbol] = df
            time.sleep(0.1)
        
        return results
    
    def _get_mock_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Generate mock data when API unavailable"""
        from CTA_Strategies_CN_Futures import MockFuturesDataProvider
        
        mock_provider = MockFuturesDataProvider(self.logger)
        return mock_provider.get_futures_data(symbol, start_date, end_date)
    
    def get_symbol_info(self, symbol: str) -> Dict:
        """Get symbol info"""
        return RQ_FUTURES_MAPPING.get(symbol, {})
    
    def get_symbols_by_category(self, category: str) -> List[str]:
        """Get symbols by category"""
        return CATEGORY_MAP.get(category, [])


class CTADatamanager:
    """CTA Data Manager with local cache"""
    
    def __init__(self, provider: RiceQuantCTADataProvider, 
                 cache_dir: str = './cta_data_cache'):
        self.provider = provider
        self.cache_dir = cache_dir
        self.logger = provider.logger
        
        import os
        os.makedirs(cache_dir, exist_ok=True)
    
    def load_data(self, symbols: List[str], 
                  start_date: str, 
                  end_date: str,
                  use_cache: bool = True) -> Dict[str, pd.DataFrame]:
        """Load data with cache support"""
        results = {}
        
        for symbol in symbols:
            cache_file = f"{self.cache_dir}/{symbol}_{start_date}_{end_date}.parquet"
            
            if use_cache:
                try:
                    import os
                    if os.path.exists(cache_file):
                        df = pd.read_parquet(cache_file)
                        results[symbol] = df
                        self.logger.info(f"{symbol}: loaded from cache ({len(df)} records)")
                        continue
                except Exception as e:
                    self.logger.debug(f"Cache load failed: {e}")
            
            df = self.provider.get_futures_data(symbol, start_date, end_date)
            if not df.empty:
                results[symbol] = df
                
                if use_cache:
                    try:
                        df.to_parquet(cache_file)
                    except Exception as e:
                        self.logger.debug(f"Cache save failed: {e}")
        
        return results


if __name__ == "__main__":
    print("="*70)
    print("RiceQuant CTA Data Provider Test")
    print("="*70)
    print()
    
    API_KEY = "Mg8lEL3dGgIyxrwc2rNsqVneytgqpSq4n0h4S8M-XQnZ9domysurqc3Lh1NlmAwAKSBTUr5qwFJ-aPEeFfR3L2rK5pq-HddOdS6vDBfDv187cVUdC9sejifx7V1lQjQWRm19YVrhx1poB-uThWtc3F6kzslu4cn9myNayWNzfo8=OPgej69FUSOnYfosbz62TAjuWXo_85kHZiUQUZCjXl78r0HUqN3HGJBXF7CIsXCHAAsQ7xieZzwD-_G8vn_3pkfFaAy2pLrhjk4BSLkVcNDwfPJovTa4hxIKfGAZ5G_HtNIHSUZcHnenxQnZljuvnzsixT3G-3Gr4UunAz9-72A="
    
    provider = RiceQuantCTADataProvider(api_key=API_KEY)
    
    print("\n[Symbol Info]")
    for symbol in ['RB', 'CU', 'SC', 'IF']:
        info = provider.get_symbol_info(symbol)
        print(f"  {symbol}: {info.get('name', 'Unknown')} ({info.get('exchange', 'Unknown')})")
    
    print("\n[Data Fetch Test]")
    test_symbols = ['RB', 'CU']
    start_date = '2024-01-01'
    end_date = '2024-03-01'
    
    data = provider.get_multiple_futures(test_symbols, start_date, end_date)
    
    print("\n[Data Preview]")
    for symbol, df in data.items():
        print(f"\n{symbol}:")
        print(df.head(3).to_string())
        print(f"  Total: {len(df)} records")
    
    print()
    print("="*70)
    print("Test completed!")
    print("="*70)
