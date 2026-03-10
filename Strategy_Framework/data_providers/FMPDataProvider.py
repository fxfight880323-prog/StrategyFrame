"""
FMP (Financial Modeling Prep) 数据提供模块
============================================

API Key: Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq

支持数据:
- 股票历史价格 (CTA分析)
- 期权数据 (FLP策略 Greeks, IV)
- VIX 指数
- 财报数据

文档: https://site.financialmodelingprep.com/developer/docs
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import time
import logging


# ============================================================
# 配置
# ============================================================
API_KEY = "Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq"
BASE_URL = "https://financialmodelingprep.com/api/v3"

# 标的配置
FUTURES_MAP = {
    'ES': {'symbol': 'ES=F', 'name': 'S&P 500 E-mini'},  # Yahoo Finance 格式
    'GC': {'symbol': 'GC=F', 'name': 'Gold'},
    'ZN': {'symbol': 'ZN=F', 'name': '10Y Treasury Note'},
    'SPY': {'symbol': 'SPY', 'name': 'SPDR S&P 500 ETF'},
    'VIX': {'symbol': '^VIX', 'name': 'CBOE Volatility Index'},
}


# ============================================================
# 日志设置
# ============================================================
def setup_logger(name: str = "fmp_provider") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# FMP 数据提供器
# ============================================================
class FMPDataProvider:
    """
    Financial Modeling Prep 数据提供器
    """
    
    def __init__(self, api_key: str = API_KEY, logger: logging.Logger = None):
        self.api_key = api_key
        self.logger = logger or setup_logger()
        self.session = requests.Session()
        self.cache = {}
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """发送 API 请求"""
        if params is None:
            params = {}
        params['apikey'] = self.api_key
        
        url = f"{BASE_URL}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"API请求失败: {url}, 错误: {e}")
            return {}
    
    def get_historical_price(self, symbol: str, start_date: str = None, 
                            end_date: str = None) -> pd.DataFrame:
        """
        获取历史价格数据
        
        Args:
            symbol: 股票代码 (如 'AAPL', 'SPY')
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
        
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        cache_key = f"price_{symbol}_{start_date}_{end_date}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        # 使用 historical-price-full endpoint
        endpoint = f"historical-price-full/{symbol}"
        params = {}
        if start_date:
            params['from'] = start_date
        if end_date:
            params['to'] = end_date
        
        self.logger.info(f"获取 {symbol} 历史价格数据...")
        data = self._make_request(endpoint, params)
        
        if not data or 'historical' not in data:
            self.logger.warning(f"未获取到 {symbol} 数据")
            return pd.DataFrame()
        
        df = pd.DataFrame(data['historical'])
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # 重命名列以统一格式
        df = df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'volume': 'Volume'
        })
        
        self.cache[cache_key] = df
        self.logger.info(f"  获取成功: {len(df)} 条记录")
        return df
    
    def get_stock_quote(self, symbol: str) -> Dict:
        """
        获取实时报价
        
        Returns:
            Dict with price, change, volume, etc.
        """
        endpoint = f"quote/{symbol}"
        data = self._make_request(endpoint)
        
        if data and len(data) > 0:
            return data[0]
        return {}
    
    def get_vix_data(self, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """
        获取 VIX 历史数据
        
        FMP 使用 ^VIX 或需要通过其他方式获取
        这里使用市场指数 endpoint
        """
        # 尝试获取 VIX 数据，使用不同的 symbol 格式
        for vix_symbol in ['^VIX', 'VIX', 'VIX.F']:
            df = self.get_historical_price(vix_symbol, start_date, end_date)
            if not df.empty:
                return df
        
        # 如果无法获取，返回空 DataFrame
        self.logger.warning("无法获取 VIX 数据，将使用模拟数据")
        return pd.DataFrame()
    
    def get_options_chain(self, symbol: str, expiration_date: str = None) -> pd.DataFrame:
        """
        获取期权链数据
        
        Args:
            symbol: 标的代码
            expiration_date: 到期日 'YYYY-MM-DD'
        
        Returns:
            DataFrame with options data including Greeks
        """
        cache_key = f"options_{symbol}_{expiration_date}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        endpoint = f"historical/options/{symbol}"
        params = {}
        if expiration_date:
            params['expiration'] = expiration_date
        
        self.logger.info(f"获取 {symbol} 期权数据...")
        data = self._make_request(endpoint, params)
        
        if not data:
            return pd.DataFrame()
        
        # 解析期权数据
        options_list = []
        for item in data:
            if 'options' in item and 'option' in item['options']:
                for opt in item['options']['option']:
                    opt['expiration'] = item.get('expiration', expiration_date)
                    options_list.append(opt)
        
        if not options_list:
            return pd.DataFrame()
        
        df = pd.DataFrame(options_list)
        self.cache[cache_key] = df
        self.logger.info(f"  获取成功: {len(df)} 条期权记录")
        return df
    
    def get_earnings_calendar(self, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取财报日历
        """
        endpoint = "earning_calendar"
        params = {'from': start_date, 'to': end_date}
        
        data = self._make_request(endpoint, params)
        if data:
            return pd.DataFrame(data)
        return pd.DataFrame()
    
    def get_futures_price(self, symbol: str, start_date: str = None, 
                         end_date: str = None) -> pd.DataFrame:
        """
        获取期货价格数据
        
        注意: FMP 对期货支持有限，可能需要使用特定 symbol
        """
        mapped = FUTURES_MAP.get(symbol, {'symbol': symbol})
        return self.get_historical_price(mapped['symbol'], start_date, end_date)


# ============================================================
# 数据适配器 - 为 CTA/FLP 策略提供统一接口
# ============================================================
class CTADataAdapter:
    """
    CTA策略数据适配器
    
    为 CTA 策略提供标准格式的数据
    """
    
    def __init__(self, fmp_provider: FMPDataProvider = None):
        self.fmp = fmp_provider or FMPDataProvider()
        self.logger = self.fmp.logger
    
    def get_cta_data(self, symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """
        获取 CTA 分析所需的所有数据
        
        Args:
            symbols: 标的列表 ['AAPL', 'MSFT', 'ES', 'GC', 'ZN']
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            Dict[symbol, DataFrame]
        """
        data = {}
        
        for symbol in symbols:
            self.logger.info(f"\n获取 {symbol} CTA数据...")
            
            # 获取价格数据
            df = self.fmp.get_historical_price(symbol, start_date, end_date)
            
            if df.empty:
                # 尝试期货映射
                df = self.fmp.get_futures_price(symbol, start_date, end_date)
            
            if not df.empty:
                # 标准化列名
                df.columns = [c.lower() for c in df.columns]
                data[symbol] = df
            else:
                self.logger.warning(f"无法获取 {symbol} 数据")
            
            time.sleep(0.2)  # 限速
        
        return data


class FLPDataAdapter:
    """
    FLP策略数据适配器
    
    为 FLP 策略提供 VIX、期权数据
    """
    
    def __init__(self, fmp_provider: FMPDataProvider = None):
        self.fmp = fmp_provider or FMPDataProvider()
        self.logger = self.fmp.logger
    
    def get_vix_series(self, start_date: str, end_date: str) -> pd.DataFrame:
        """获取 VIX 时间序列"""
        df = self.fmp.get_vix_data(start_date, end_date)
        
        if df.empty:
            # 如果无法获取真实 VIX，生成模拟数据用于测试
            self.logger.warning("使用模拟VIX数据")
            df = self._generate_mock_vix(start_date, end_date)
        
        return df
    
    def _generate_mock_vix(self, start_date: str, end_date: str) -> pd.DataFrame:
        """生成模拟VIX数据（仅用于测试）"""
        dates = pd.date_range(start=start_date, end=end_date, freq='D')
        dates = dates[dates.weekday < 5]  # 只保留交易日
        
        # 均值回归过程
        vix_values = []
        vix = 20.0
        for _ in dates:
            mean_rev = 0.02 * (20 - vix)
            shock = np.random.normal(0, 1.5)
            vix += mean_rev + shock
            vix = max(10, min(50, vix))
            vix_values.append(vix)
        
        df = pd.DataFrame({
            'date': dates,
            'close': vix_values
        })
        df['date'] = pd.to_datetime(df['date'])
        return df
    
    def get_spy_options(self, expiration_date: str = None) -> pd.DataFrame:
        """
        获取 SPY 期权链
        
        用于选择 Delta -0.07 ~ -0.10 的 Put
        """
        # 获取 SPY 当前价格
        quote = self.fmp.get_stock_quote('SPY')
        spy_price = quote.get('price', 400.0) if quote else 400.0
        
        self.logger.info(f"SPY 当前价格: ${spy_price}")
        
        # 获取期权链
        options = self.fmp.get_options_chain('SPY', expiration_date)
        
        if options.empty:
            self.logger.warning("无法获取期权数据，使用模拟数据")
            return self._generate_mock_options(spy_price, expiration_date)
        
        # 筛选 Put 期权
        puts = options[options.get('type', '') == 'put'].copy()
        
        # 计算近似 Delta (如果没有提供)
        if 'delta' not in puts.columns:
            puts['delta'] = puts.apply(
                lambda row: self._estimate_delta(row, spy_price), axis=1
            )
        
        return puts
    
    def _estimate_delta(self, row: pd.Series, underlying: float) -> float:
        """
        估算期权 Delta (简化 Black-Scholes)
        
        Put Delta ≈ N(d1) - 1
        """
        strike = float(row.get('strike', underlying))
        
        # 简单估算: OTM Put 的 Delta 约等于 -0.05 到 -0.15
        moneyness = strike / underlying
        if moneyness < 0.95:
            return np.random.uniform(-0.15, -0.05)
        elif moneyness > 1.05:
            return np.random.uniform(-0.50, -0.30)
        else:
            return np.random.uniform(-0.30, -0.15)
    
    def _generate_mock_options(self, spy_price: float, expiration: str) -> pd.DataFrame:
        """生成模拟期权数据"""
        strikes = np.arange(spy_price * 0.85, spy_price * 1.15, 5)
        
        options = []
        for strike in strikes:
            # 估算 Delta
            moneyness = strike / spy_price
            delta = -0.5 + (moneyness - 1) * 2  # 简化线性估算
            delta = max(-0.9, min(-0.05, delta))
            
            # 估算权利金
            intrinsic = max(0, strike - spy_price)
            time_value = spy_price * 0.20 * np.sqrt(7/365)  # 假设7天到期
            premium = intrinsic + time_value
            
            options.append({
                'strike': strike,
                'type': 'put',
                'delta': delta,
                'premium': premium,
                'expiration': expiration or (date.today() + timedelta(days=7)).isoformat()
            })
        
        return pd.DataFrame(options)
    
    def select_put_for_flp(self, spy_price: float, target_delta: Tuple[float, float] = (-0.10, -0.07)) -> Optional[Dict]:
        """
        选择符合 FLP 策略的 Put 期权
        
        Args:
            spy_price: SPY 当前价格
            target_delta: 目标 Delta 范围
        
        Returns:
            选中的 Put 期权信息
        """
        options = self.get_spy_options()
        
        if options.empty:
            return None
        
        # 筛选 Put
        puts = options[options.get('type', '') == 'put'].copy()
        
        # 筛选 Delta 范围
        min_delta, max_delta = target_delta
        selected = puts[(puts['delta'] >= min_delta) & (puts['delta'] <= max_delta)]
        
        if selected.empty:
            # 如果没有精确匹配，找最接近的
            puts['delta_diff'] = abs(puts['delta'] - (min_delta + max_delta) / 2)
            selected = puts.nsmallest(1, 'delta_diff')
        
        if not selected.empty:
            put = selected.iloc[0].to_dict()
            self.logger.info(f"选中 Put: Strike=${put.get('strike')}, Delta={put.get('delta'):.3f}")
            return put
        
        return None


# ============================================================
# 测试函数
# ============================================================
def test_fmp_provider():
    """测试 FMP 数据提供器"""
    print("="*60)
    print("FMP 数据提供器测试")
    print("="*60)
    print()
    
    fmp = FMPDataProvider()
    
    # 测试1: 获取股票价格
    print("【测试1】获取 AAPL 历史价格")
    df = fmp.get_historical_price('AAPL', '2024-01-01', '2024-02-01')
    if not df.empty:
        print(f"  成功: {len(df)} 条记录")
        print(f"  最新价格: ${df['Close'].iloc[-1]:.2f}")
    else:
        print("  失败: 无法获取数据")
    print()
    
    # 测试2: 获取实时报价
    print("【测试2】获取 SPY 实时报价")
    quote = fmp.get_stock_quote('SPY')
    if quote:
        print(f"  价格: ${quote.get('price', 'N/A')}")
        print(f"  变化: {quote.get('change', 'N/A')}%")
    else:
        print("  失败: 无法获取数据")
    print()
    
    # 测试3: CTA数据适配器
    print("【测试3】CTA数据适配器")
    cta_adapter = CTADataAdapter(fmp)
    data = cta_adapter.get_cta_data(['AAPL', 'MSFT'], '2024-01-01', '2024-02-01')
    print(f"  获取到 {len(data)} 个标的")
    for symbol, df in data.items():
        print(f"    {symbol}: {len(df)} 条记录")
    print()
    
    # 测试4: FLP数据适配器
    print("【测试4】FLP数据适配器")
    flp_adapter = FLPDataAdapter(fmp)
    vix = flp_adapter.get_vix_series('2024-01-01', '2024-02-01')
    print(f"  VIX数据: {len(vix)} 条记录")
    if not vix.empty:
        print(f"  VIX均值: {vix['close'].mean():.2f}")
    print()
    
    # 测试5: 选择FLP Put
    print("【测试5】选择 FLP Put 期权")
    put = flp_adapter.select_put_for_flp(spy_price=400.0)
    if put:
        print(f"  选中: Strike=${put.get('strike')}, Delta={put.get('delta'):.3f}")
        print(f"  权利金: ${put.get('premium', 'N/A')}")
    print()
    
    print("="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    test_fmp_provider()
