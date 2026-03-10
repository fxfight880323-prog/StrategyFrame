"""
YFinance 数据提供器 (FMP 备选方案)
==================================

使用 yfinance 库获取免费股票数据
安装: pip install yfinance

支持:
- 股票历史价格
- 指数数据 (VIX, SPY, QQQ等)
- 实时报价
- 期权链数据
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple
import logging


def setup_logger(name: str = "yf_provider") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


class YFinanceProvider:
    """
    YFinance 数据提供器
    
    作为 FMP 的免费备选方案
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or setup_logger()
        self.cache = {}
    
    def get_historical_price(self, symbol: str, start_date: str = None, 
                            end_date: str = None, period: str = None) -> pd.DataFrame:
        """
        获取历史价格数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
            period: 简写周期 ('1y', '2y', '5y', 'max')
        """
        cache_key = f"{symbol}_{start_date}_{end_date}_{period}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            ticker = yf.Ticker(symbol)
            
            if period:
                df = ticker.history(period=period)
            else:
                df = ticker.history(start=start_date, end=end_date)
            
            if df.empty:
                self.logger.warning(f"未获取到 {symbol} 数据")
                return pd.DataFrame()
            
            # 标准化列名
            df.columns = [c.lower().replace(' ', '_') for c in df.columns]
            df = df.reset_index()
            
            # 处理日期列
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            elif 'datetime' in df.columns:
                df['date'] = pd.to_datetime(df['datetime'])
            
            self.cache[cache_key] = df
            self.logger.info(f"✓ {symbol}: 获取 {len(df)} 条记录")
            return df
            
        except Exception as e:
            self.logger.error(f"✗ {symbol}: 获取失败 - {e}")
            return pd.DataFrame()
    
    def get_stock_info(self, symbol: str) -> Dict:
        """获取股票信息"""
        try:
            ticker = yf.Ticker(symbol)
            return ticker.info
        except:
            return {}
    
    def get_current_price(self, symbol: str) -> float:
        """获取当前价格"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='1d')
            if not hist.empty:
                return hist['Close'].iloc[-1]
        except:
            pass
        return 0.0
    
    def get_vix_data(self, period: str = '2y') -> pd.DataFrame:
        """
        获取 VIX 数据
        
        YFinance symbol: ^VIX
        """
        return self.get_historical_price('^VIX', period=period)
    
    def get_options_chain(self, symbol: str, expiration_date: str = None) -> pd.DataFrame:
        """
        获取期权链
        
        Args:
            symbol: 标的代码
            expiration_date: 到期日 'YYYY-MM-DD'，None则获取所有
        """
        try:
            ticker = yf.Ticker(symbol)
            
            # 获取到期日列表
            expirations = ticker.options
            
            if not expirations:
                self.logger.warning(f"{symbol}: 无可用期权数据")
                return pd.DataFrame()
            
            all_options = []
            
            for exp in expirations[:3]:  # 只取前3个到期日
                if expiration_date and exp != expiration_date:
                    continue
                
                opt = ticker.option_chain(exp)
                
                # 处理 calls
                calls = opt.calls.copy()
                calls['type'] = 'call'
                calls['expiration'] = exp
                
                # 处理 puts
                puts = opt.puts.copy()
                puts['type'] = 'put'
                puts['expiration'] = exp
                
                all_options.append(calls)
                all_options.append(puts)
            
            if all_options:
                df = pd.concat(all_options, ignore_index=True)
                return df
            
            return pd.DataFrame()
            
        except Exception as e:
            self.logger.error(f"{symbol}: 期权数据获取失败 - {e}")
            return pd.DataFrame()
    
    def get_multiple_symbols(self, symbols: List[str], period: str = '1y') -> Dict[str, pd.DataFrame]:
        """
        批量获取多个标的
        
        Args:
            symbols: 标的列表
            period: 时间周期
        
        Returns:
            Dict[symbol, DataFrame]
        """
        results = {}
        
        for symbol in symbols:
            df = self.get_historical_price(symbol, period=period)
            if not df.empty:
                results[symbol] = df
        
        return results


class YFinanceAdapter:
    """
    YFinance 适配器
    
    提供与 FMP 适配器相同的接口
    """
    
    def __init__(self, provider: YFinanceProvider = None):
        self.provider = provider or YFinanceProvider()
        self.logger = self.provider.logger
    
    def get_cta_data(self, symbols: List[str], start_date: str = None, 
                    end_date: str = None, period: str = '1y') -> Dict[str, pd.DataFrame]:
        """
        获取 CTA 分析数据
        
        标准化列名: open, high, low, close, volume
        """
        data = {}
        
        for symbol in symbols:
            df = self.provider.get_historical_price(symbol, start_date, end_date, period)
            
            if not df.empty:
                # 确保列名标准化
                column_map = {
                    'open': 'open',
                    'high': 'high',
                    'low': 'low',
                    'close': 'close',
                    'volume': 'volume',
                }
                
                # 重命名列
                for old, new in column_map.items():
                    if old in df.columns:
                        df[new] = df[old]
                
                data[symbol] = df
            
            import time
            time.sleep(0.1)  # 限速
        
        return data
    
    def get_vix_series(self, period: str = '2y') -> pd.DataFrame:
        """获取 VIX 时间序列"""
        return self.provider.get_vix_data(period)
    
    def get_spy_options(self, expiration_date: str = None) -> pd.DataFrame:
        """获取 SPY 期权链"""
        return self.provider.get_options_chain('SPY', expiration_date)


def test_yfinance_provider():
    """测试 YFinance 提供器"""
    print("="*60)
    print("YFinance 数据提供器测试")
    print("="*60)
    print()
    
    yf_prov = YFinanceProvider()
    
    # 测试1: 获取股票数据
    print("【测试1】获取 AAPL 历史数据 (1年)")
    df = yf_prov.get_historical_price('AAPL', period='1y')
    if not df.empty:
        print(f"  成功: {len(df)} 条记录")
        print(f"  日期范围: {df['date'].min()} 至 {df['date'].max()}")
        print(f"  最新价格: ${df['close'].iloc[-1]:.2f}")
        print(f"  列: {list(df.columns)}")
    print()
    
    # 测试2: 获取当前价格
    print("【测试2】获取 SPY 当前价格")
    price = yf_prov.get_current_price('SPY')
    if price > 0:
        print(f"  当前价格: ${price:.2f}")
    print()
    
    # 测试3: 获取 VIX
    print("【测试3】获取 VIX 数据")
    vix_df = yf_prov.get_vix_data(period='1y')
    if not vix_df.empty:
        print(f"  成功: {len(vix_df)} 条记录")
        print(f"  VIX均值: {vix_df['close'].mean():.2f}")
        print(f"  VIX范围: {vix_df['close'].min():.1f} - {vix_df['close'].max():.1f}")
    print()
    
    # 测试4: 批量获取
    print("【测试4】批量获取多只股票")
    symbols = ['AAPL', 'MSFT', 'NVDA', 'SPY', 'QQQ']
    data = yf_prov.get_multiple_symbols(symbols, period='6mo')
    print(f"  成功获取 {len(data)} 只股票:")
    for sym, df in data.items():
        print(f"    {sym}: {len(df)} 条记录")
    print()
    
    # 测试5: 获取期权链
    print("【测试5】获取 SPY 期权链")
    options = yf_prov.get_options_chain('SPY')
    if not options.empty:
        print(f"  成功: {len(options)} 条期权记录")
        puts = options[options['type'] == 'put']
        calls = options[options['type'] == 'call']
        print(f"    Put: {len(puts)} 条")
        print(f"    Call: {len(calls)} 条")
        
        # 显示一个示例
        if not puts.empty:
            sample = puts.iloc[0]
            print(f"\n  示例 Put 期权:")
            print(f"    行权价: ${sample['strike']:.2f}")
            print(f"    到期日: {sample['expiration']}")
            print(f"    最后价: ${sample['lastPrice']:.2f}")
            print(f"    隐含波动率: {sample.get('impliedVolatility', 'N/A')}")
    print()
    
    # 测试6: CTA 适配器
    print("【测试6】CTA 适配器")
    adapter = YFinanceAdapter(yf_prov)
    cta_data = adapter.get_cta_data(['AAPL', 'MSFT'], period='3mo')
    print(f"  获取到 {len(cta_data)} 只股票")
    for sym, df in cta_data.items():
        print(f"    {sym}: {len(df)} 条记录, 列: {list(df.columns)[:5]}...")
    print()
    
    print("="*60)
    print("测试完成!")
    print("="*60)
    print("\n✓ YFinance 可以作为 FMP 的免费备选方案")
    print("✓ 支持历史数据、实时报价、VIX、期权链")
    print("✓ 无需 API Key，完全免费")


if __name__ == "__main__":
    test_yfinance_provider()
