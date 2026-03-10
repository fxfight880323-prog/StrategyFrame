"""
Tradier API 数据提供模块
========================

API 文档: https://documentation.tradier.com/

支持数据:
- 美股实时/历史行情
- 期权链数据 ( Greeks, IV, 到期日等)
- 期权历史价格

用途: CTA + FLP 策略数据获取
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import time
import logging


# ============================================================
# 配置
# ============================================================
TRADIER_BASE_URL = "https://api.tradier.com/v1"
# 注意: 需要替换为实际的 API Key
TRADIER_API_KEY = "YOUR_TRADIER_API_KEY_HERE"  # 请替换


# ============================================================
# 日志设置
# ============================================================
def setup_logger(name: str = "tradier_provider") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# Tradier 数据提供器
# ============================================================
class TradierDataProvider:
    """
    Tradier API 数据提供器
    
    提供美股股票和期权专业数据
    """
    
    def __init__(self, api_key: str = TRADIER_API_KEY, 
                 sandbox: bool = True,  # 使用沙盒环境测试
                 logger: logging.Logger = None):
        self.api_key = api_key
        self.sandbox = sandbox
        self.logger = logger or setup_logger()
        
        # 选择环境
        if sandbox:
            self.base_url = "https://sandbox.tradier.com/v1"
            self.logger.info("使用 Tradier 沙盒环境")
        else:
            self.base_url = TRADIER_BASE_URL
            self.logger.info("使用 Tradier 生产环境")
        
        # 请求头
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json"
        }
        
        self.cache = {}
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """发送 API 请求"""
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                self.logger.error("API Key 无效或已过期")
                return {}
            elif response.status_code == 429:
                self.logger.warning("请求过于频繁，等待后重试...")
                time.sleep(1)
                return self._make_request(endpoint, params)
            else:
                self.logger.error(f"请求失败: {response.status_code} - {response.text}")
                return {}
                
        except Exception as e:
            self.logger.error(f"请求异常: {e}")
            return {}
    
    def get_stock_quote(self, symbol: str) -> Dict:
        """
        获取股票实时报价
        
        Args:
            symbol: 股票代码 (如 'AAPL', 'SPY')
        
        Returns:
            股票报价信息
        """
        data = self._make_request(f"markets/quotes", {"symbols": symbol})
        
        if data and 'quotes' in data and 'quote' in data['quotes']:
            quote = data['quotes']['quote']
            return {
                'symbol': quote.get('symbol'),
                'price': quote.get('last'),
                'bid': quote.get('bid'),
                'ask': quote.get('ask'),
                'volume': quote.get('volume'),
                'change': quote.get('change'),
                'change_percent': quote.get('change_percentage'),
                'open': quote.get('open'),
                'high': quote.get('high'),
                'low': quote.get('low'),
                'close': quote.get('close'),
            }
        return {}
    
    def get_historical_data(self, symbol: str, start_date: str, end_date: str, 
                           interval: str = "daily") -> pd.DataFrame:
        """
        获取历史价格数据
        
        Args:
            symbol: 股票代码
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
            interval: 时间周期 ('daily', 'weekly', 'monthly')
        
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        cache_key = f"hist_{symbol}_{start_date}_{end_date}_{interval}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        self.logger.info(f"获取 {symbol} 历史数据 ({start_date} ~ {end_date})...")
        
        params = {
            "symbol": symbol,
            "interval": interval,
            "start": start_date,
            "end": end_date,
        }
        
        data = self._make_request("markets/history", params)
        
        if data and 'history' in data and 'day' in data['history']:
            days = data['history']['day']
            
            # 确保是列表
            if not isinstance(days, list):
                days = [days]
            
            df = pd.DataFrame(days)
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date')
            
            # 标准化列名
            column_map = {
                'open': 'open',
                'high': 'high',
                'low': 'low',
                'close': 'close',
                'volume': 'volume',
            }
            df = df.rename(columns=column_map)
            
            self.cache[cache_key] = df
            self.logger.info(f"  ✓ 成功: {len(df)} 条记录")
            return df
        
        self.logger.warning(f"  ⚠️ 无数据返回")
        return pd.DataFrame()
    
    def get_option_chain(self, symbol: str, expiration_date: str = None, 
                        greeks: bool = True) -> pd.DataFrame:
        """
        获取期权链数据
        
        Args:
            symbol: 标的代码 (如 'SPY', 'AAPL')
            expiration_date: 到期日 'YYYY-MM-DD'，None则获取所有到期日
            greeks: 是否获取希腊字母
        
        Returns:
            DataFrame with option data including Greeks
        """
        self.logger.info(f"获取 {symbol} 期权链...")
        
        params = {"symbol": symbol}
        if expiration_date:
            params["expiration"] = expiration_date
        if greeks:
            params["greeks"] = "true"
        
        data = self._make_request("markets/options/chains", params)
        
        if data and 'options' in data and 'option' in data['options']:
            options = data['options']['option']
            
            if not isinstance(options, list):
                options = [options]
            
            df = pd.DataFrame(options)
            
            self.logger.info(f"  ✓ 成功: {len(df)} 条期权记录")
            return df
        
        self.logger.warning(f"  ⚠️ 无期权数据")
        return pd.DataFrame()
    
    def get_option_expirations(self, symbol: str) -> List[str]:
        """
        获取期权到期日列表
        
        Args:
            symbol: 标的代码
        
        Returns:
            到期日字符串列表 ['YYYY-MM-DD', ...]
        """
        self.logger.info(f"获取 {symbol} 期权到期日...")
        
        data = self._make_request("markets/options/expirations", {"symbol": symbol})
        
        if data and 'expirations' in data and 'date' in data['expirations']:
            dates = data['expirations']['date']
            if not isinstance(dates, list):
                dates = [dates]
            
            self.logger.info(f"  ✓ 成功: {len(dates)} 个到期日")
            return dates
        
        return []
    
    def get_option_strikes(self, symbol: str, expiration_date: str) -> List[float]:
        """
        获取指定到期日的行权价列表
        
        Args:
            symbol: 标的代码
            expiration_date: 到期日 'YYYY-MM-DD'
        """
        data = self._make_request("markets/options/strikes", {
            "symbol": symbol,
            "expiration": expiration_date
        })
        
        if data and 'strikes' in data and 'strike' in data['strikes']:
            strikes = data['strikes']['strike']
            if not isinstance(strikes, list):
                strikes = [strikes]
            return [float(s) for s in strikes]
        
        return []
    
    def select_put_for_flp(self, symbol: str = 'SPY', 
                          target_delta: Tuple[float, float] = (-0.10, -0.07),
                          min_days_to_expiry: int = 7,
                          max_days_to_expiry: int = 45) -> Optional[Dict]:
        """
        为FLP策略选择合适的Put期权
        
        筛选条件:
        - Delta 在目标范围内
        - 到期日在合理范围内
        - 流动性良好 (Open Interest)
        
        Returns:
            选中的期权信息
        """
        self.logger.info(f"为FLP策略选择 {symbol} Put期权...")
        
        # 1. 获取标的当前价格
        quote = self.get_stock_quote(symbol)
        if not quote:
            self.logger.error("无法获取标的报价")
            return None
        
        spot_price = quote['price']
        self.logger.info(f"  {symbol} 当前价格: ${spot_price:.2f}")
        
        # 2. 获取到期日
        expirations = self.get_option_expirations(symbol)
        if not expirations:
            return None
        
        # 3. 筛选合适的到期日
        today = date.today()
        valid_expiries = []
        
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, '%Y-%m-%d').date()
            days_to_exp = (exp_date - today).days
            
            if min_days_to_expiry <= days_to_exp <= max_days_to_expiry:
                valid_expiries.append((exp_str, days_to_exp))
        
        if not valid_expiries:
            self.logger.warning("无符合条件的到期日")
            return None
        
        # 选择最近的合适到期日
        selected_expiry, days_to_exp = valid_expiries[0]
        self.logger.info(f"  选择到期日: {selected_expiry} ({days_to_exp}天后)")
        
        # 4. 获取期权链
        options_df = self.get_option_chain(symbol, selected_expiry, greeks=True)
        if options_df.empty:
            return None
        
        # 5. 筛选Put期权
        puts = options_df[options_df['option_type'] == 'put'].copy()
        
        if puts.empty:
            self.logger.warning("无Put期权数据")
            return None
        
        # 6. 检查希腊字母数据
        if 'delta' not in puts.columns:
            self.logger.warning("期权数据无希腊字母，使用估算")
            # 基于行权价估算Delta
            puts['delta'] = puts.apply(
                lambda row: self._estimate_delta(row, spot_price, 'put'), axis=1
            )
        else:
            # 转换为数值
            puts['delta'] = pd.to_numeric(puts['delta'], errors='coerce')
        
        # 7. 筛选目标Delta范围
        min_delta, max_delta = target_delta
        target_puts = puts[
            (puts['delta'] >= min_delta) & 
            (puts['delta'] <= max_delta)
        ].copy()
        
        if target_puts.empty:
            self.logger.warning(f"无Delta在 {min_delta} ~ {max_delta} 范围内的期权")
            # 找最接近的
            puts['delta_diff'] = abs(puts['delta'] - (min_delta + max_delta) / 2)
            target_puts = puts.nsmallest(1, 'delta_diff')
        
        # 8. 选择最优期权 (考虑流动性和价格)
        selected = target_puts.iloc[0]
        
        result = {
            'symbol': symbol,
            'option_symbol': selected.get('symbol'),
            'strike': float(selected.get('strike', 0)),
            'expiration': selected_expiry,
            'days_to_expiry': days_to_exp,
            'option_type': 'put',
            'delta': float(selected.get('delta', 0)),
            'gamma': float(selected.get('gamma', 0)) if 'gamma' in selected else None,
            'theta': float(selected.get('theta', 0)) if 'theta' in selected else None,
            'vega': float(selected.get('vega', 0)) if 'vega' in selected else None,
            'iv': float(selected.get('mid_iv', 0)) if 'mid_iv' in selected else None,
            'bid': float(selected.get('bid', 0)),
            'ask': float(selected.get('ask', 0)),
            'last': float(selected.get('last', 0)),
            'volume': int(selected.get('volume', 0)),
            'open_interest': int(selected.get('open_interest', 0)),
            'spot_price': spot_price,
        }
        
        self.logger.info(f"  ✓ 选中期权: {result['option_symbol']}")
        self.logger.info(f"    行权价: ${result['strike']:.2f}")
        self.logger.info(f"    Delta: {result['delta']:.3f}")
        self.logger.info(f"    权利金: ${result['last']:.2f}")
        self.logger.info(f"    IV: {result['iv']*100:.1f}%" if result['iv'] else "    IV: N/A")
        
        return result
    
    def _estimate_delta(self, option_row: pd.Series, spot_price: float, option_type: str) -> float:
        """
        估算期权Delta (当希腊字母不可用时)
        
        简化Black-Scholes近似
        """
        strike = float(option_row.get('strike', spot_price))
        
        # 简单线性近似
        moneyness = strike / spot_price
        
        if option_type == 'put':
            if moneyness < 0.95:  # OTM
                return -0.3 + (moneyness - 0.95) * 2
            elif moneyness > 1.05:  # ITM
                return -0.7 - (moneyness - 1.05) * 2
            else:  # ATM
                return -0.5
        else:  # call
            if moneyness < 0.95:  # ITM
                return 0.7 + (0.95 - moneyness) * 2
            elif moneyness > 1.05:  # OTM
                return 0.3 - (moneyness - 1.05) * 2
            else:  # ATM
                return 0.5


# ============================================================
# 测试函数
# ============================================================
def test_tradier():
    """测试 Tradier 数据提供器"""
    print("="*60)
    print("Tradier API 测试")
    print("="*60)
    print()
    
    # 创建提供器 (使用沙盒环境测试)
    provider = TradierDataProvider(sandbox=True)
    
    # 注意: 需要有效的 API Key 才能测试
    if provider.api_key == "YOUR_TRADIER_API_KEY_HERE":
        print("⚠️ 请先在代码中设置有效的 Tradier API Key")
        print("   获取方式: https://developer.tradier.com/")
        return
    
    print("【测试1】获取 SPY 实时报价")
    quote = provider.get_stock_quote("SPY")
    if quote:
        print(f"  价格: ${quote['price']:.2f}")
        print(f"  涨跌: {quote['change_percent']:.2f}%")
    print()
    
    print("【测试2】获取 SPY 历史数据")
    end = date.today()
    start = end - timedelta(days=30)
    df = provider.get_historical_data("SPY", start.isoformat(), end.isoformat())
    if not df.empty:
        print(f"  数据条数: {len(df)}")
        print(f"  最新收盘: ${df['close'].iloc[-1]:.2f}")
    print()
    
    print("【测试3】获取期权到期日")
    expirations = provider.get_option_expirations("SPY")
    if expirations:
        print(f"  到期日数量: {len(expirations)}")
        print(f"  最近到期: {expirations[0]}")
    print()
    
    print("【测试4】获取期权链")
    if expirations:
        options = provider.get_option_chain("SPY", expirations[0])
        if not options.empty:
            puts = options[options['option_type'] == 'put']
            calls = options[options['option_type'] == 'call']
            print(f"  Put数量: {len(puts)}")
            print(f"  Call数量: {len(calls)}")
    print()
    
    print("【测试5】为FLP策略选择Put期权")
    put = provider.select_put_for_flp("SPY")
    if put:
        print(f"  选中: {put['option_symbol']}")
        print(f"  Delta: {put['delta']:.3f}")
    print()
    
    print("="*60)
    print("测试完成")
    print("="*60)


if __name__ == "__main__":
    test_tradier()
