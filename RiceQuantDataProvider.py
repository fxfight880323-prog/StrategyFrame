"""
米筐(RiceQuant) 数据提供模块
============================

API Key: Mg8lEL3dGgIyxrwc2rNsqVneytgqpSq4n0h4S8M-XQnZ9domysurqc3Lh1NlmAwAKSBTUr5qwFJ-aPEeFfR3L2rK5pq-HddOdS6vDBfDv187cVUdC9sejifx7V1lQjQWRm19YVrhx1poB-uThWtc3F6kzslu4cn9myNayWNzfo8=OPgej69FUSOnYfosbz62TAjuWXo_85kHZiUQUZCjXl78r0HUqN3HGJBXF7CIsXCHAAsQ7xieZzwD-_G8vn_3pkfFaAy2pLrhjk4BSLkVcNDwfPJovTa4hxIKfGAZ5G_HtNIHSUZcHnenxQnZljuvnzsixT3G-3Gr4UunAz9-72A=

文档: https://www.ricequant.com/doc/rqdata
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

# 尝试导入米筐SDK
try:
    import rqdatac as rq
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False
    print("⚠️ 米筐SDK未安装，尝试安装: pip install rqdatac")


# ============================================================
# 配置
# ============================================================
RQ_API_KEY = "Mg8lEL3dGgIyxrwc2rNsqVneytgqpSq4n0h4S8M-XQnZ9domysurqc3Lh1NlmAwAKSBTUr5qwFJ-aPEeFfR3L2rK5pq-HddOdS6vDBfDv187cVUdC9sejifx7V1lQjQWRm19YVrhx1poB-uThWtc3F6kzslu4cn9myNayWNzfo8=OPgej69FUSOnYfosbz62TAjuWXo_85kHZiUQUZCjXl78r0HUqN3HGJBXF7CIsXCHAAsQ7xieZzwD-_G8vn_3pkfFaAy2pLrhjk4BSLkVcNDwfPJovTa4hxIKfGAZ5G_HtNIHSUZcHnenxQnZljuvnzsixT3G-3Gr4UunAz9-72A="


# ============================================================
# 日志设置
# ============================================================
def setup_logger(name: str = "ricequant_provider") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# 米筐数据提供器
# ============================================================
class RiceQuantDataProvider:
    """
    米筐(RiceQuant) 数据提供器
    
    支持数据:
    - 股票日线/分钟线 (A股、港股、美股)
    - 期货数据 (商品期货、股指期货)
    - 期权数据 (50ETF、300ETF期权)
    - 财务数据、因子数据
    """
    
    def __init__(self, api_key: str = RQ_API_KEY, logger: logging.Logger = None):
        self.api_key = api_key
        self.logger = logger or setup_logger()
        self.connected = False
        
        if not RQ_AVAILABLE:
            self.logger.error("❌ 米筐SDK未安装，请先安装: pip install rqdatac")
            return
        
        self._connect()
    
    def _connect(self):
        """连接米筐数据服务"""
        try:
            self.logger.info("正在连接米筐数据服务...")
            rq.init(self.api_key)
            self.connected = True
            self.logger.info("✅ 米筐数据服务连接成功")
        except Exception as e:
            self.logger.error(f"❌ 连接失败: {e}")
            self.connected = False
    
    def get_stock_price(self, symbol: str, start_date: str, end_date: str, 
                       frequency: str = "1d") -> pd.DataFrame:
        """
        获取股票价格数据
        
        Args:
            symbol: 股票代码 (如 '000001.XSHE', 'AAPL.US')
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
            frequency: 频率 ('1d'=日线, '1m'=分钟线)
        
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        if not self.connected:
            self.logger.error("未连接到米筐服务")
            return pd.DataFrame()
        
        try:
            self.logger.info(f"获取 {symbol} 价格数据 ({start_date} ~ {end_date})...")
            
            df = rq.get_price(
                symbol,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency
            )
            
            if df is None or df.empty:
                self.logger.warning(f"  {symbol}: 无数据返回")
                return pd.DataFrame()
            
            # 标准化列名
            df = df.reset_index()
            df.columns = [c.lower() for c in df.columns]
            
            self.logger.info(f"  ✓ 成功: {len(df)} 条记录")
            return df
            
        except Exception as e:
            self.logger.error(f"  ✗ 失败: {e}")
            return pd.DataFrame()
    
    def get_future_price(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取期货价格数据
        
        Args:
            symbol: 期货代码 (如 'IF2312', 'RB2401')
        """
        if not self.connected:
            return pd.DataFrame()
        
        try:
            self.logger.info(f"获取期货 {symbol} 数据...")
            
            df = rq.futures.get_price(
                symbol,
                start_date=start_date,
                end_date=end_date
            )
            
            if df is not None and not df.empty:
                df = df.reset_index()
                df.columns = [c.lower() for c in df.columns]
                self.logger.info(f"  ✓ 成功: {len(df)} 条记录")
                return df
            
            return pd.DataFrame()
            
        except Exception as e:
            self.logger.error(f"  ✗ 失败: {e}")
            return pd.DataFrame()
    
    def get_option_chain(self, underlying: str, expiration_date: str) -> pd.DataFrame:
        """
        获取期权链数据
        
        Args:
            underlying: 标的代码 (如 '510050.XSHG' 为50ETF)
            expiration_date: 到期日 'YYYY-MM-DD'
        """
        if not self.connected:
            return pd.DataFrame()
        
        try:
            self.logger.info(f"获取期权链 {underlying} {expiration_date}...")
            
            # 获取期权列表
            options = rq.options.get_contracts(underlying, expiration_date)
            
            if options is None or len(options) == 0:
                self.logger.warning("  无期权数据")
                return pd.DataFrame()
            
            # 获取期权价格
            df = rq.options.get_price(options)
            
            self.logger.info(f"  ✓ 成功: {len(df)} 条期权记录")
            return df
            
        except Exception as e:
            self.logger.error(f"  ✗ 失败: {e}")
            return pd.DataFrame()
    
    def get_index_components(self, index_symbol: str) -> List[str]:
        """
        获取指数成分股
        
        Args:
            index_symbol: 指数代码 (如 '000001.XSHG' 上证指数, '000300.XSHG' 沪深300)
        
        Returns:
            成分股代码列表
        """
        if not self.connected:
            return []
        
        try:
            self.logger.info(f"获取指数 {index_symbol} 成分股...")
            
            components = rq.index_components(index_symbol)
            
            self.logger.info(f"  ✓ 成功: {len(components)} 只成分股")
            return components
            
        except Exception as e:
            self.logger.error(f"  ✗ 失败: {e}")
            return []
    
    def get_factor_data(self, symbol: str, factor: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取因子数据
        
        Args:
            symbol: 股票代码
            factor: 因子名称 (如 'market_cap', 'pe_ratio', 'pb_ratio')
        """
        if not self.connected:
            return pd.DataFrame()
        
        try:
            df = rq.get_factor(symbol, factor, start_date, end_date)
            return df
        except Exception as e:
            self.logger.error(f"获取因子数据失败: {e}")
            return pd.DataFrame()
    
    def get_trading_calendar(self, start_date: str, end_date: str, market: str = "cn") -> List[date]:
        """
        获取交易日历
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            market: 市场 ('cn'=中国, 'us'=美国)
        """
        if not self.connected:
            return []
        
        try:
            dates = rq.get_trading_dates(start_date, end_date)
            return dates
        except Exception as e:
            self.logger.error(f"获取交易日历失败: {e}")
            return []


# ============================================================
# CTA策略数据适配器
# ============================================================
class CTADataAdapterRQ:
    """CTA策略 - 米筐数据适配器"""
    
    def __init__(self, provider: RiceQuantDataProvider = None):
        self.provider = provider or RiceQuantDataProvider()
        self.logger = self.provider.logger
    
    def get_cta_data(self, symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """
        获取CTA分析所需数据
        
        Args:
            symbols: 标的代码列表 (如 ['000001.XSHE', 'IF2312'])
            start_date: 开始日期
            end_date: 结束日期
        
        Returns:
            Dict[symbol, DataFrame]
        """
        data = {}
        
        for symbol in symbols:
            df = self.provider.get_stock_price(symbol, start_date, end_date)
            
            if not df.empty:
                data[symbol] = df
            
            import time
            time.sleep(0.2)  # 限速
        
        return data


# ============================================================
# FLP策略数据适配器
# ============================================================
class FLPDataAdapterRQ:
    """FLP策略 - 米筐数据适配器"""
    
    def __init__(self, provider: RiceQuantDataProvider = None):
        self.provider = provider or RiceQuantDataProvider()
        self.logger = self.provider.logger
    
    def get_50etf_options(self, expiration_date: str) -> pd.DataFrame:
        """
        获取50ETF期权链
        
        用于国内版本的FLP策略
        """
        # 50ETF代码
        underlying = "510050.XSHG"
        
        return self.provider.get_option_chain(underlying, expiration_date)
    
    def get_300etf_options(self, expiration_date: str) -> pd.DataFrame:
        """获取300ETF期权链"""
        underlying = "510300.XSHG"
        
        return self.provider.get_option_chain(underlying, expiration_date)


# ============================================================
# 测试函数
# ============================================================
def test_ricequant():
    """测试米筐数据提供器"""
    print("="*60)
    print("米筐(RiceQuant) 数据提供器测试")
    print("="*60)
    print()
    
    if not RQ_AVAILABLE:
        print("❌ 请先安装米筐SDK:")
        print("   pip install rqdatac")
        return
    
    # 创建提供器
    provider = RiceQuantDataProvider()
    
    if not provider.connected:
        print("❌ 连接失败，请检查API Key")
        return
    
    print()
    
    # 测试1: 获取A股数据
    print("【测试1】获取平安银行(000001.XSHE)日线数据")
    df = provider.get_stock_price('000001.XSHE', '2024-01-01', '2024-02-01')
    if not df.empty:
        print(f"  最新价格: ¥{df['close'].iloc[-1]:.2f}")
    print()
    
    # 测试2: 获取指数成分股
    print("【测试2】获取沪深300成分股")
    components = provider.get_index_components('000300.XSHG')
    if components:
        print(f"  前5只: {', '.join(components[:5])}")
    print()
    
    # 测试3: 获取期货数据
    print("【测试3】获取沪深300期货(IF2403)数据")
    df = provider.get_future_price('IF2403', '2024-01-01', '2024-02-01')
    if not df.empty:
        print(f"  数据条数: {len(df)}")
    print()
    
    print("="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    test_ricequant()
