"""
Quality+LowVol 双市场回测
=========================
A股 (RiceQuant API) + 美股 (Tushare API) 对比回测

功能:
1. A股数据源: RiceQuant (rqdatac) — 沪深300/中证500
2. 美股数据源: Tushare Pro — S&P500/Nasdaq100
3. 相同策略逻辑，不同市场对比
4. 生成跨市场对比报告

使用方法:
    # 快速回测 (使用模拟数据)
    >>> results = run_dual_market_backtest()

    # 连接真实API
    >>> results = run_dual_market_backtest(
    ...     rq_username='+8613810062394',
    ...     rq_password='Fox880323!',
    ...     tushare_token='your_tushare_token',
    ... )
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import json
import os

logger = logging.getLogger(__name__)

# ============================================================
# 尝试导入SDK
# ============================================================
try:
    import rqdatac as rq
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False
    logger.warning("rqdatac 未安装，A股将使用模拟数据")

try:
    import tushare as ts
    TS_AVAILABLE = True
except ImportError:
    TS_AVAILABLE = False
    logger.warning("tushare 未安装，美股将使用模拟数据")

from config import StrategyConfig, RQ_USERNAME, RQ_PASSWORD
from valmom_backtest import FactorBacktestResult, ValMomVisualizer


# ============================================================
# 市场定义
# ============================================================
class Market(Enum):
    A_STOCK = "A-Stock"
    US_STOCK = "US-Stock"


@dataclass
class MarketConfig:
    """市场级别配置"""
    market: Market
    universe_name: str          # 'hs300', 'sp500' 等
    benchmark_name: str         # 基准名称
    currency: str               # 'CNY', 'USD'
    trading_days_per_year: int  # 年交易日数
    commission_rate: float      # 佣金率
    slippage: float             # 滑点
    quality_factors: List[str]  # 可用质量因子
    start_date: str
    end_date: str


# 预设市场配置
A_STOCK_CONFIG = MarketConfig(
    market=Market.A_STOCK,
    universe_name='hs300',
    benchmark_name='沪深300',
    currency='CNY',
    trading_days_per_year=244,
    commission_rate=0.0003,
    slippage=0.001,
    quality_factors=['roe', 'roa', 'gross_profit_margin'],
    start_date='2018-01-01',
    end_date='2024-12-31',
)

US_STOCK_CONFIG = MarketConfig(
    market=Market.US_STOCK,
    universe_name='sp500',
    benchmark_name='S&P 500',
    currency='USD',
    trading_days_per_year=252,
    commission_rate=0.0001,
    slippage=0.0005,
    quality_factors=['roe', 'roa', 'grossmargin'],
    start_date='2018-01-01',
    end_date='2024-12-31',
)


# ============================================================
# A股数据提供器 (RiceQuant)
# ============================================================
class RiceQuantDataProvider:
    """
    A股数据提供器 — 基于RiceQuant API

    API文档: https://www.ricequant.com/doc/rqdata/python/

    核心方法:
    - rq.init(): 初始化连接
    - rq.index_components(): 获取指数成份股
    - rq.get_factor(): 获取因子数据
    - rq.get_price(): 获取价格数据
    - rq.get_fundamentals(): 获取财务数据
    """

    def __init__(self, username: str = None, password: str = None, api_key: str = None):
        self.connected = False
        self.username = username
        self.password = password
        self.api_key = api_key
        self._connect()

    def _connect(self):
        """连接RiceQuant数据服务"""
        if not RQ_AVAILABLE:
            logger.info("RiceQuant SDK未安装，使用模拟数据")
            return

        try:
            if self.api_key:
                rq.init(self.api_key)
            elif self.username and self.password:
                rq.init(self.username, self.password)
            else:
                rq.init(RQ_USERNAME, RQ_PASSWORD)
            self.connected = True
            logger.info("RiceQuant 连接成功")
        except Exception as e:
            logger.warning(f"RiceQuant 连接失败: {e}，使用模拟数据")
            self.connected = False

    def get_stock_universe(self, universe: str = 'hs300', date: str = None) -> List[str]:
        """
        获取A股股票池

        Args:
            universe: 'hs300' / 'zz500' / 'zz800'
            date: 截止日期

        Returns:
            股票代码列表 (RQ格式: '000001.XSHE')
        """
        if self.connected:
            index_map = {
                'hs300': '000300.XSHG',
                'zz500': '000905.XSHG',
                'zz800': '000906.XSHG',
            }
            index_code = index_map.get(universe, '000300.XSHG')
            try:
                components = rq.index_components(index_code, date=date)
                return list(components)
            except Exception as e:
                logger.warning(f"获取成份股失败: {e}")

        # 模拟数据: 返回沪深300部分股票代码
        return self._mock_universe(universe)

    def get_factor_data(
        self,
        symbols: List[str],
        factors: List[str],
        date: str,
    ) -> pd.DataFrame:
        """
        获取因子数据

        支持的因子:
        - roe: 净资产收益率
        - roa: 总资产收益率
        - gross_profit_margin: 毛利率
        - net_profit_margin: 净利率
        - debt_to_asset_ratio: 资产负债率
        """
        if self.connected:
            try:
                # RiceQuant因子名称映射
                rq_factors = self._map_factors_to_rq(factors)
                start = (pd.to_datetime(date) - timedelta(days=5)).strftime('%Y-%m-%d')
                data = rq.get_factor(symbols, rq_factors, start_date=start, end_date=date)
                if data is not None and not data.empty:
                    # 取最新一天的数据
                    if isinstance(data.index, pd.MultiIndex):
                        latest = data.groupby(level=1).last()
                    else:
                        latest = data
                    latest.columns = factors[:len(latest.columns)]
                    return latest
            except Exception as e:
                logger.warning(f"获取因子数据失败: {e}")

        return self._mock_factor_data(symbols, factors, date)

    def get_price_data(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """获取A股价格数据 (复权收盘价)"""
        if self.connected:
            try:
                prices = rq.get_price(
                    symbols,
                    start_date=start_date,
                    end_date=end_date,
                    frequency='1d',
                    fields=['close'],
                    adjust_type='post',
                )
                if prices is not None and not prices.empty:
                    if isinstance(prices, pd.Panel if hasattr(pd, 'Panel') else type(None)):
                        prices = prices['close']
                    elif 'close' in prices.columns:
                        prices = prices.pivot(columns='order_book_id', values='close')
                    return prices
            except Exception as e:
                logger.warning(f"获取价格数据失败: {e}")

        return self._mock_price_data(symbols, start_date, end_date)

    def _map_factors_to_rq(self, factors: List[str]) -> List[str]:
        """映射通用因子名到RiceQuant因子名"""
        mapping = {
            'roe': 'return_on_equity',
            'roa': 'return_on_asset',
            'gross_profit_margin': 'gross_profit_margin',
            'net_profit_margin': 'net_profit_margin',
            'debt_to_asset_ratio': 'debt_to_asset_ratio',
        }
        return [mapping.get(f, f) for f in factors]

    def _mock_universe(self, universe: str) -> List[str]:
        """模拟A股股票池"""
        np.random.seed(42)
        exchanges = ['XSHE', 'XSHG']
        stocks = []
        n = {'hs300': 300, 'zz500': 500, 'zz800': 800}.get(universe, 300)
        for i in range(n):
            code = f"{np.random.randint(1, 699999):06d}"
            ex = exchanges[0] if int(code) < 400000 else exchanges[1]
            stocks.append(f"{code}.{ex}")
        return stocks[:n]

    def _mock_factor_data(self, symbols, factors, date) -> pd.DataFrame:
        np.random.seed(hash(date) % 2**31)
        data = {}
        for f in factors:
            if f in ('roe', 'roa'):
                data[f] = np.random.normal(0.10, 0.08, len(symbols))
            elif f == 'gross_profit_margin':
                data[f] = np.random.normal(0.30, 0.15, len(symbols))
            else:
                data[f] = np.random.normal(0, 1, len(symbols))
        return pd.DataFrame(data, index=symbols)

    def _mock_price_data(self, symbols, start_date, end_date) -> pd.DataFrame:
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        prices = pd.DataFrame(index=dates)
        for sym in symbols[:100]:  # 限制模拟数量
            # 每只股票独立seed，避免跨截面伪相关
            np.random.seed(hash(sym + start_date) % 2**31)
            ret = np.random.normal(0.0003, 0.018, len(dates))
            prices[sym] = 100 * np.cumprod(1 + ret)
        return prices


# ============================================================
# 美股数据提供器 (Tushare)
# ============================================================
class TushareUSDataProvider:
    """
    美股数据提供器 — 基于Tushare Pro API

    API文档: https://tushare.pro/document/2

    核心方法:
    - ts.pro_api(token): 初始化
    - pro.us_daily(): 美股日线行情
    - pro.us_basic(): 美股基本信息
    - pro.us_tradecal(): 美股交易日历

    Tushare美股因子数据有限，需要基于价格/财报自行计算:
    - 质量因子: 通过财报数据计算ROE/ROA
    - 波动率: 通过价格数据计算
    """

    def __init__(self, token: str = None):
        self.pro = None
        self.connected = False
        self.token = token
        self._connect()

    def _connect(self):
        """连接Tushare Pro"""
        if not TS_AVAILABLE:
            logger.info("Tushare 未安装，使用模拟数据")
            return

        try:
            if self.token:
                ts.set_token(self.token)
                self.pro = ts.pro_api(self.token)
            else:
                self.pro = ts.pro_api()
            self.connected = True
            logger.info("Tushare Pro 连接成功")
        except Exception as e:
            logger.warning(f"Tushare 连接失败: {e}，使用模拟数据")
            self.connected = False

    def get_stock_universe(self, universe: str = 'sp500', date: str = None) -> List[str]:
        """
        获取美股股票池

        Args:
            universe: 'sp500' / 'nasdaq100' / 'djia'

        Returns:
            Tushare美股代码列表
        """
        if self.connected and self.pro:
            try:
                # Tushare美股列表
                df = self.pro.us_basic(
                    classify=universe.upper() if universe != 'sp500' else 'SP500',
                    fields='ts_code,name,classify'
                )
                if df is not None and not df.empty:
                    return df['ts_code'].tolist()
            except Exception as e:
                logger.warning(f"获取美股股票池失败: {e}")

        return self._mock_universe(universe)

    def get_factor_data(
        self,
        symbols: List[str],
        factors: List[str],
        date: str,
    ) -> pd.DataFrame:
        """
        获取美股因子数据

        由于Tushare美股财务数据有限，使用以下方法:
        - ROE: 通过 us_income + us_balancesheet 计算
        - ROA: 通过 us_income + us_balancesheet 计算
        - Gross Margin: 通过 us_income 计算

        当API不可用时使用模拟数据
        """
        if self.connected and self.pro:
            try:
                return self._fetch_us_factors(symbols, factors, date)
            except Exception as e:
                logger.warning(f"获取美股因子数据失败: {e}")

        return self._mock_factor_data(symbols, factors, date)

    def _fetch_us_factors(self, symbols, factors, date) -> pd.DataFrame:
        """
        从Tushare获取美股财务因子

        使用 pro.us_income() 和 pro.us_balancesheet() 计算
        """
        result = pd.DataFrame(index=symbols)

        for sym in symbols[:50]:  # Tushare限流，分批取
            try:
                # 获取利润表
                income = self.pro.us_income(
                    ts_code=sym,
                    period=date.replace('-', '')[:6],
                    fields='ts_code,net_income,total_revenue,total_cogs'
                )

                # 获取资产负债表
                balance = self.pro.us_balancesheet(
                    ts_code=sym,
                    period=date.replace('-', '')[:6],
                    fields='ts_code,total_assets,total_equity'
                )

                if income is not None and not income.empty and balance is not None and not balance.empty:
                    net_income = income['net_income'].iloc[0]
                    revenue = income['total_revenue'].iloc[0]
                    cogs = income['total_cogs'].iloc[0] if 'total_cogs' in income.columns else 0
                    total_assets = balance['total_assets'].iloc[0]
                    total_equity = balance['total_equity'].iloc[0]

                    if 'roe' in factors and total_equity and total_equity != 0:
                        result.loc[sym, 'roe'] = net_income / total_equity
                    if 'roa' in factors and total_assets and total_assets != 0:
                        result.loc[sym, 'roa'] = net_income / total_assets
                    if 'grossmargin' in factors and revenue and revenue != 0:
                        result.loc[sym, 'grossmargin'] = (revenue - cogs) / revenue

            except Exception:
                continue

        return result

    def get_price_data(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        获取美股价格数据

        使用 pro.us_daily() 获取日线行情
        """
        if self.connected and self.pro:
            try:
                return self._fetch_us_prices(symbols, start_date, end_date)
            except Exception as e:
                logger.warning(f"获取美股价格失败: {e}")

        return self._mock_price_data(symbols, start_date, end_date)

    def _fetch_us_prices(self, symbols, start_date, end_date) -> pd.DataFrame:
        """从Tushare获取美股日线"""
        all_prices = {}
        start_fmt = start_date.replace('-', '')
        end_fmt = end_date.replace('-', '')

        for sym in symbols[:100]:
            try:
                df = self.pro.us_daily(
                    ts_code=sym,
                    start_date=start_fmt,
                    end_date=end_fmt,
                    fields='trade_date,close'
                )
                if df is not None and not df.empty:
                    df['trade_date'] = pd.to_datetime(df['trade_date'])
                    df = df.set_index('trade_date').sort_index()
                    all_prices[sym] = df['close']
            except Exception:
                continue

        if all_prices:
            return pd.DataFrame(all_prices)
        return self._mock_price_data(symbols, start_date, end_date)

    def _mock_universe(self, universe: str) -> List[str]:
        """模拟美股股票池"""
        sp500_sample = [
            'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'NVDA', 'BRK.B', 'JPM',
            'JNJ', 'V', 'PG', 'UNH', 'HD', 'MA', 'DIS', 'BAC', 'XOM', 'ADBE',
            'CRM', 'NFLX', 'CSCO', 'PFE', 'TMO', 'ABT', 'COST', 'PEP', 'AVGO',
            'ACN', 'MRK', 'NKE', 'LLY', 'WMT', 'DHR', 'TXN', 'NEE', 'MDT',
            'HON', 'UNP', 'AMGN', 'LIN', 'LOW', 'PM', 'QCOM', 'ORCL', 'RTX',
            'INTC', 'UPS', 'IBM', 'CVX', 'BA', 'SBUX', 'CAT', 'GS', 'BLK',
            'ISRG', 'GILD', 'AXP', 'DE', 'MMM', 'MO', 'NOW', 'INTU', 'BKNG',
            'SYK', 'ZTS', 'MDLZ', 'CI', 'TGT', 'SPGI', 'ADP', 'CB', 'SCHW',
            'PLD', 'CME', 'TJX', 'BDX', 'CL', 'SO', 'DUK', 'ICE', 'AON',
            'FIS', 'NSC', 'REGN', 'SHW', 'ITW', 'MU', 'APD', 'ATVI', 'FCX',
            'ETN', 'LRCX', 'GD', 'FISV', 'HUM', 'EW', 'EMR', 'KLAC', 'PH',
            'PSA', 'ADI', 'MCO', 'KMB', 'WM', 'AFL', 'AEP', 'D', 'EXC',
        ]
        n = {'sp500': 100, 'nasdaq100': 50, 'djia': 30}.get(universe, 100)
        return sp500_sample[:n]

    def _mock_factor_data(self, symbols, factors, date) -> pd.DataFrame:
        np.random.seed(hash(date) % 2**31)
        data = {}
        for f in factors:
            if f in ('roe', 'roa'):
                # 美股ROE/ROA略高于A股
                data[f] = np.random.normal(0.15, 0.10, len(symbols))
            elif f in ('grossmargin', 'gross_profit_margin'):
                data[f] = np.random.normal(0.40, 0.18, len(symbols))
            else:
                data[f] = np.random.normal(0, 1, len(symbols))
        return pd.DataFrame(data, index=symbols)

    def _mock_price_data(self, symbols, start_date, end_date) -> pd.DataFrame:
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        prices = pd.DataFrame(index=dates)
        for sym in symbols[:100]:
            # 每只股票独立seed，避免跨截面伪相关
            np.random.seed(hash(sym + start_date) % 2**31)
            # 美股长期正漂移略高
            ret = np.random.normal(0.0004, 0.015, len(dates))
            prices[sym] = 100 * np.cumprod(1 + ret)
        return prices


# ============================================================
# 通用数据接口 (适配器模式)
# ============================================================
class UnifiedDataProvider:
    """
    统一数据接口

    将不同市场的数据提供器统一为相同接口
    QualityLowVolFactorBuilder 通过此接口获取数据
    """

    def __init__(self, provider, market_config: MarketConfig):
        self.provider = provider
        self.market_config = market_config

    def get_stock_universe(self, universe: str = None, date: str = None) -> List[str]:
        uni = universe or self.market_config.universe_name
        return self.provider.get_stock_universe(uni, date)

    def get_factor_data(self, symbols, factors, date) -> pd.DataFrame:
        return self.provider.get_factor_data(symbols, factors, date)

    def get_price_data(self, symbols, start_date, end_date) -> pd.DataFrame:
        return self.provider.get_price_data(symbols, start_date, end_date)


# ============================================================
# 质量+低波动因子构建 (市场无关)
# ============================================================
class DualMarketQualityLowVolBuilder:
    """
    跨市场质量+低波动因子构建器

    与 QualityLowVolFactorBuilder 逻辑一致，
    但通过 UnifiedDataProvider 支持不同市场
    """

    QUALITY_WEIGHTS = {'roe': 0.30, 'roa': 0.25, 'gross_margin': 0.25, 'low_leverage': 0.20}
    LOWVOL_WEIGHTS = {'inv_vol_60': 0.50, 'inv_vol_120': 0.50}
    COMPOSITE_WEIGHTS = {'quality': 0.60, 'lowvol': 0.40}

    def __init__(self, data_provider: UnifiedDataProvider):
        self.data_provider = data_provider
        self.market_config = data_provider.market_config

    def build_quality_signal(self, symbols: List[str], date: str) -> pd.Series:
        """构建质量因子信号"""
        factors = self.market_config.quality_factors
        factor_data = self.data_provider.get_factor_data(symbols, factors, date)

        scores = pd.DataFrame(index=symbols)

        # ROE
        for col in ['roe', 'return_on_equity']:
            if col in factor_data.columns:
                scores['roe'] = self._zscore(factor_data[col])
                break

        # ROA
        for col in ['roa', 'return_on_asset']:
            if col in factor_data.columns:
                scores['roa'] = self._zscore(factor_data[col])
                break

        # 毛利率
        for col in ['gross_profit_margin', 'grossmargin']:
            if col in factor_data.columns:
                scores['gross_margin'] = self._zscore(factor_data[col])
                break

        # 低杠杆 (ROA/ROE比值)
        if 'roe' in scores.columns and 'roa' in scores.columns:
            roe_vals = factor_data.iloc[:, 0].replace(0, np.nan)
            roa_vals = factor_data.iloc[:, 1] if factor_data.shape[1] > 1 else roe_vals
            leverage_inv = roa_vals / roe_vals
            scores['low_leverage'] = self._zscore(leverage_inv)

        quality_signal = pd.Series(0.0, index=symbols)
        for factor, weight in self.QUALITY_WEIGHTS.items():
            if factor in scores.columns:
                quality_signal += scores[factor].fillna(0) * weight

        return quality_signal.dropna()

    def build_lowvol_signal(self, symbols: List[str], date: str) -> pd.Series:
        """构建低波动因子信号"""
        end_dt = pd.to_datetime(date)
        start_dt = end_dt - timedelta(days=180)

        prices = self.data_provider.get_price_data(
            symbols, start_dt.strftime('%Y-%m-%d'), date
        )

        if prices.empty:
            return pd.Series(dtype=float)

        returns = prices.pct_change().dropna()
        ann_factor = np.sqrt(self.market_config.trading_days_per_year)
        scores = pd.DataFrame(index=prices.columns)

        if len(returns) >= 60:
            vol_60 = returns.iloc[-60:].std() * ann_factor
            scores['inv_vol_60'] = self._zscore(1.0 / vol_60.replace(0, np.nan))

        if len(returns) >= 120:
            vol_120 = returns.iloc[-120:].std() * ann_factor
            scores['inv_vol_120'] = self._zscore(1.0 / vol_120.replace(0, np.nan))

        lowvol_signal = pd.Series(0.0, index=prices.columns)
        for factor, weight in self.LOWVOL_WEIGHTS.items():
            if factor in scores.columns:
                lowvol_signal += scores[factor].fillna(0) * weight

        return lowvol_signal.dropna()

    def build_composite_signal(self, quality: pd.Series, lowvol: pd.Series) -> pd.Series:
        """构建复合信号"""
        common = quality.index.intersection(lowvol.index)
        if len(common) == 0:
            return pd.Series(dtype=float)
        q = self._zscore(quality.loc[common])
        lv = self._zscore(lowvol.loc[common])
        return self.COMPOSITE_WEIGHTS['quality'] * q + self.COMPOSITE_WEIGHTS['lowvol'] * lv

    def _zscore(self, series: pd.Series) -> pd.Series:
        s = series.copy().dropna()
        if len(s) == 0:
            return s
        lower, upper = s.quantile(0.01), s.quantile(0.99)
        s = s.clip(lower, upper)
        std = s.std()
        if std > 0:
            s = (s - s.mean()) / std
        return s


# ============================================================
# 单市场回测引擎
# ============================================================
class SingleMarketBacktester:
    """单一市场回测引擎"""

    def __init__(
        self,
        data_provider: UnifiedDataProvider,
        factor_builder: DualMarketQualityLowVolBuilder,
        market_config: MarketConfig,
    ):
        self.data_provider = data_provider
        self.factor_builder = factor_builder
        self.market_config = market_config
        self.logger = logging.getLogger(__name__)

    def backtest_factor(
        self,
        factor_name: str,  # 'quality', 'lowvol', 'composite'
        start_date: str = None,
        end_date: str = None,
        rebalance_freq: str = 'ME',
        top_n: int = 30,
        bottom_n: int = 30,
        signal_weighted: bool = True,
    ) -> FactorBacktestResult:
        """运行单因子回测"""
        start = start_date or self.market_config.start_date
        end = end_date or self.market_config.end_date
        market_label = self.market_config.market.value

        self.logger.info(
            f"[{market_label}] 回测 {factor_name}: {start} 至 {end}"
        )

        dates = pd.date_range(start=start, end=end, freq=rebalance_freq)
        portfolio_value = 1.0
        equity_curve = pd.Series(index=dates, dtype=float)
        equity_curve.iloc[0] = portfolio_value
        returns_list = []
        prev_weights = None
        turnover_list = []

        for i in range(1, len(dates)):
            current_date = dates[i]
            prev_date = dates[i - 1]

            universe = self.data_provider.get_stock_universe(
                date=prev_date.strftime('%Y-%m-%d')
            )

            signal = self._build_signal(factor_name, universe, prev_date)

            if signal.empty:
                equity_curve.iloc[i] = equity_curve.iloc[i - 1]
                continue

            weights = self._construct_weights(signal, top_n, bottom_n, signal_weighted)

            if prev_weights is not None:
                all_idx = prev_weights.index.union(weights.index)
                turnover = np.abs(
                    weights.reindex(all_idx, fill_value=0)
                    - prev_weights.reindex(all_idx, fill_value=0)
                ).sum() / 2
                turnover_list.append(turnover)
            prev_weights = weights.copy()

            # 计算组合收益
            symbols = weights[weights != 0].index.tolist()
            prices = self.data_provider.get_price_data(
                symbols,
                prev_date.strftime('%Y-%m-%d'),
                current_date.strftime('%Y-%m-%d'),
            )
            if prices.empty or len(prices) < 2:
                period_return = 0.0
            else:
                stock_returns = (prices.iloc[-1] / prices.iloc[0] - 1).fillna(0)
                period_return = (weights.reindex(stock_returns.index, fill_value=0) * stock_returns).sum()

            # 扣除交易成本
            tc = turnover_list[-1] * self.market_config.commission_rate if turnover_list else 0
            period_return -= tc

            portfolio_value *= (1 + period_return)
            equity_curve.iloc[i] = portfolio_value
            returns_list.append(period_return)

        returns_series = pd.Series(returns_list, index=dates[1:len(returns_list) + 1])
        label = f"{market_label}_{factor_name}"

        return self._calc_metrics(label, start, end, equity_curve, returns_series, turnover_list)

    def _build_signal(self, factor_name, universe, date):
        date_str = date.strftime('%Y-%m-%d')
        if factor_name == 'quality':
            return self.factor_builder.build_quality_signal(universe, date_str)
        elif factor_name == 'lowvol':
            return self.factor_builder.build_lowvol_signal(universe, date_str)
        elif factor_name == 'composite':
            q = self.factor_builder.build_quality_signal(universe, date_str)
            lv = self.factor_builder.build_lowvol_signal(universe, date_str)
            if q.empty or lv.empty:
                return pd.Series(dtype=float)
            return self.factor_builder.build_composite_signal(q, lv)
        else:
            raise ValueError(f"Unknown factor: {factor_name}")

    def _construct_weights(self, signal, top_n, bottom_n, signal_weighted):
        weights = pd.Series(0.0, index=signal.index)
        if signal_weighted:
            pos = signal[signal > 0]
            neg = signal[signal < 0]
            if len(pos) > 0:
                weights.loc[pos.index] = pos / pos.sum() * 0.5
            if len(neg) > 0:
                weights.loc[neg.index] = neg / neg.abs().sum() * (-0.5)
        else:
            sorted_sig = signal.sort_values(ascending=False)
            weights.loc[sorted_sig.head(top_n).index] = 0.5 / top_n
            weights.loc[sorted_sig.tail(bottom_n).index] = -0.5 / bottom_n
        return weights

    def _calc_metrics(self, factor_name, start_date, end_date,
                      equity_curve, returns_series, turnover_list):
        ec = equity_curve.dropna()
        total_return = ec.iloc[-1] / ec.iloc[0] - 1
        years = len(ec) / 12
        ann_ret = (1 + total_return) ** (1 / max(years, 0.01)) - 1
        vol = returns_series.std() * np.sqrt(12) if len(returns_series) > 0 else 0
        sharpe = ann_ret / vol if vol > 0 else 0
        downside = returns_series[returns_series < 0]
        ds_std = downside.std() * np.sqrt(12) if len(downside) > 0 else 0.0001
        sortino = ann_ret / ds_std if ds_std > 0 else 0
        cummax = ec.cummax()
        dd = (ec - cummax) / cummax
        max_dd = dd.min()
        calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0

        return FactorBacktestResult(
            factor_name=factor_name,
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            annualized_return=ann_ret,
            volatility=vol,
            sharpe_ratio=sharpe,
            information_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            calmar_ratio=calmar,
            turnover=np.mean(turnover_list) if turnover_list else 0,
            equity_curve=equity_curve,
            returns_series=returns_series,
        )


# ============================================================
# 跨市场对比报告
# ============================================================
class CrossMarketReporter:
    """跨市场对比报告生成器"""

    @staticmethod
    def print_comparison(
        a_stock_results: Dict[str, FactorBacktestResult],
        us_stock_results: Dict[str, FactorBacktestResult],
    ):
        """打印跨市场对比报告"""
        print("\n" + "=" * 110)
        print("Quality + Low Volatility: A-Stock vs US-Stock Cross-Market Comparison")
        print("=" * 110)

        factors = ['quality', 'lowvol', 'composite']
        header = (f"{'Factor':<12} | {'Market':<10} | {'Ann Ret':<10} | {'Vol':<10} | "
                  f"{'Sharpe':<8} | {'Sortino':<9} | {'Max DD':<10} | {'Calmar':<8} | {'Turnover':<8}")
        print(header)
        print("-" * 110)

        for factor in factors:
            a_key = f"A-Stock_{factor}"
            us_key = f"US-Stock_{factor}"

            if a_key in a_stock_results:
                r = a_stock_results[a_key]
                print(f"{factor:<12} | {'A-Stock':<10} | {r.annualized_return*100:>8.2f}% | "
                      f"{r.volatility*100:>8.2f}% | {r.sharpe_ratio:>7.2f} | {r.sortino_ratio:>8.2f} | "
                      f"{r.max_drawdown*100:>8.2f}% | {r.calmar_ratio:>7.2f} | {r.turnover:>7.2f}")

            if us_key in us_stock_results:
                r = us_stock_results[us_key]
                print(f"{'':>12} | {'US-Stock':<10} | {r.annualized_return*100:>8.2f}% | "
                      f"{r.volatility*100:>8.2f}% | {r.sharpe_ratio:>7.2f} | {r.sortino_ratio:>8.2f} | "
                      f"{r.max_drawdown*100:>8.2f}% | {r.calmar_ratio:>7.2f} | {r.turnover:>7.2f}")
            print("-" * 110)

        # 关键差异
        print("\n【关键差异分析】")
        for factor in factors:
            a_key = f"A-Stock_{factor}"
            us_key = f"US-Stock_{factor}"
            if a_key in a_stock_results and us_key in us_stock_results:
                a = a_stock_results[a_key]
                u = us_stock_results[us_key]
                print(f"\n  {factor.upper()}:")
                print(f"    夏普差异:    A={a.sharpe_ratio:.2f}  US={u.sharpe_ratio:.2f}  "
                      f"(差值: {a.sharpe_ratio - u.sharpe_ratio:+.2f})")
                print(f"    年化收益差异: A={a.annualized_return*100:.2f}%  US={u.annualized_return*100:.2f}%  "
                      f"(差值: {(a.annualized_return - u.annualized_return)*100:+.2f}pp)")
                print(f"    最大回撤差异: A={a.max_drawdown*100:.2f}%  US={u.max_drawdown*100:.2f}%  "
                      f"(差值: {(a.max_drawdown - u.max_drawdown)*100:+.2f}pp)")

        print("\n" + "=" * 110)

    @staticmethod
    def save_comparison(
        a_stock_results: Dict[str, FactorBacktestResult],
        us_stock_results: Dict[str, FactorBacktestResult],
        save_dir: str = "backtests",
    ):
        """保存跨市场对比结果"""
        os.makedirs(save_dir, exist_ok=True)

        data = {
            'A-Stock': {k: v.to_dict() for k, v in a_stock_results.items()},
            'US-Stock': {k: v.to_dict() for k, v in us_stock_results.items()},
        }

        path = os.path.join(save_dir, 'quality_lowvol_dual_market.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"跨市场对比结果已保存: {path}")


# ============================================================
# 便捷入口
# ============================================================
def run_dual_market_backtest(
    start_date: str = "2018-01-01",
    end_date: str = "2024-12-31",
    rq_username: str = None,
    rq_password: str = None,
    tushare_token: str = None,
    save_results: bool = True,
) -> Dict[str, Dict[str, FactorBacktestResult]]:
    """
    运行A股 + 美股双市场 Quality+LowVol 回测

    Args:
        start_date: 起始日期
        end_date: 结束日期
        rq_username: RiceQuant用户名 (默认使用config.py配置)
        rq_password: RiceQuant密码
        tushare_token: Tushare Pro token
        save_results: 是否保存结果

    Returns:
        {'A-Stock': {...}, 'US-Stock': {...}}
    """
    logger.info("=" * 70)
    logger.info("Quality+LowVol Dual Market Backtest")
    logger.info(f"Period: {start_date} to {end_date}")
    logger.info("=" * 70)

    factors = ['quality', 'lowvol', 'composite']

    # ===== A股回测 (RiceQuant) =====
    logger.info("\n[A-Stock] 初始化 RiceQuant 数据源...")
    a_config = MarketConfig(
        market=Market.A_STOCK,
        universe_name='hs300',
        benchmark_name='沪深300',
        currency='CNY',
        trading_days_per_year=244,
        commission_rate=0.0003,
        slippage=0.001,
        quality_factors=['roe', 'roa', 'gross_profit_margin'],
        start_date=start_date,
        end_date=end_date,
    )

    rq_provider = RiceQuantDataProvider(
        username=rq_username,
        password=rq_password,
    )
    a_unified = UnifiedDataProvider(rq_provider, a_config)
    a_builder = DualMarketQualityLowVolBuilder(a_unified)
    a_backtester = SingleMarketBacktester(a_unified, a_builder, a_config)

    a_results = {}
    for i, factor in enumerate(factors, 1):
        logger.info(f"\n[A-Stock {i}/{len(factors)}] 回测 {factor.upper()}...")
        result = a_backtester.backtest_factor(factor, start_date, end_date)
        a_results[result.factor_name] = result

    # ===== 美股回测 (Tushare) =====
    logger.info("\n[US-Stock] 初始化 Tushare 数据源...")
    us_config = MarketConfig(
        market=Market.US_STOCK,
        universe_name='sp500',
        benchmark_name='S&P 500',
        currency='USD',
        trading_days_per_year=252,
        commission_rate=0.0001,
        slippage=0.0005,
        quality_factors=['roe', 'roa', 'grossmargin'],
        start_date=start_date,
        end_date=end_date,
    )

    ts_provider = TushareUSDataProvider(token=tushare_token)
    us_unified = UnifiedDataProvider(ts_provider, us_config)
    us_builder = DualMarketQualityLowVolBuilder(us_unified)
    us_backtester = SingleMarketBacktester(us_unified, us_builder, us_config)

    us_results = {}
    for i, factor in enumerate(factors, 1):
        logger.info(f"\n[US-Stock {i}/{len(factors)}] 回测 {factor.upper()}...")
        result = us_backtester.backtest_factor(factor, start_date, end_date)
        us_results[result.factor_name] = result

    # ===== 跨市场对比 =====
    reporter = CrossMarketReporter()
    reporter.print_comparison(a_results, us_results)

    if save_results:
        reporter.save_comparison(a_results, us_results)

        # 绘制对比图
        all_results = {}
        for k, v in a_results.items():
            all_results[f"A_{k.split('_')[-1]}"] = v
        for k, v in us_results.items():
            all_results[f"US_{k.split('_')[-1]}"] = v

        viz = ValMomVisualizer()
        viz.plot_equity_curves(all_results, "backtests/dual_market_equity.png")
        viz.plot_drawdown(all_results, "backtests/dual_market_drawdown.png")

    return {'A-Stock': a_results, 'US-Stock': us_results}


def run_astock_only(
    start_date: str = "2018-01-01",
    end_date: str = "2024-12-31",
    universe: str = 'hs300',
) -> Dict[str, FactorBacktestResult]:
    """
    仅运行A股回测

    Example:
        >>> results = run_astock_only('2020-01-01', '2024-12-31', 'zz500')
    """
    config = MarketConfig(
        market=Market.A_STOCK, universe_name=universe,
        benchmark_name='沪深300' if universe == 'hs300' else '中证500',
        currency='CNY', trading_days_per_year=244,
        commission_rate=0.0003, slippage=0.001,
        quality_factors=['roe', 'roa', 'gross_profit_margin'],
        start_date=start_date, end_date=end_date,
    )
    provider = UnifiedDataProvider(RiceQuantDataProvider(), config)
    builder = DualMarketQualityLowVolBuilder(provider)
    bt = SingleMarketBacktester(provider, builder, config)

    results = {}
    for factor in ['quality', 'lowvol', 'composite']:
        results[factor] = bt.backtest_factor(factor, start_date, end_date)
    return results


def run_usstock_only(
    start_date: str = "2018-01-01",
    end_date: str = "2024-12-31",
    universe: str = 'sp500',
    tushare_token: str = None,
) -> Dict[str, FactorBacktestResult]:
    """
    仅运行美股回测

    Example:
        >>> results = run_usstock_only('2020-01-01', '2024-12-31', tushare_token='your_token')
    """
    config = MarketConfig(
        market=Market.US_STOCK, universe_name=universe,
        benchmark_name='S&P 500', currency='USD',
        trading_days_per_year=252, commission_rate=0.0001,
        slippage=0.0005, quality_factors=['roe', 'roa', 'grossmargin'],
        start_date=start_date, end_date=end_date,
    )
    provider = UnifiedDataProvider(TushareUSDataProvider(tushare_token), config)
    builder = DualMarketQualityLowVolBuilder(provider)
    bt = SingleMarketBacktester(provider, builder, config)

    results = {}
    for factor in ['quality', 'lowvol', 'composite']:
        results[factor] = bt.backtest_factor(factor, start_date, end_date)
    return results


def run_with_local_data(
    start_date: str = "2018-01-01",
    end_date: str = "2024-12-31",
    universe: str = 'hs300',
    save_results: bool = True,
) -> Dict[str, FactorBacktestResult]:
    """
    使用本地缓存数据回测 (先运行 data_downloader.py --download-all)

    数据源优先级:
    1. 本地缓存 (data_cache/) — 来自RiceQuant或AKShare
    2. 模拟数据 (当缓存不存在时)

    Example:
        # 先下载数据
        # python data_downloader.py --download-all

        # 然后回测
        >>> results = run_with_local_data('2018-01-01', '2024-12-31')
    """
    from data_downloader import LocalDataProvider

    logger.info("=" * 70)
    logger.info("Quality+LowVol Backtest (Local Data)")
    logger.info("=" * 70)

    local = LocalDataProvider()
    status = local.check_data_status()
    logger.info(f"本地数据: {status}")

    if status.get('a_stock_prices', 0) == 0:
        logger.warning("未找到本地A股数据! 请先运行: python data_downloader.py --download-all")
        logger.warning("将使用模拟数据...")

    config = MarketConfig(
        market=Market.A_STOCK, universe_name=universe,
        benchmark_name='沪深300' if universe == 'hs300' else '中证500',
        currency='CNY', trading_days_per_year=244,
        commission_rate=0.0003, slippage=0.001,
        quality_factors=['roe', 'roa', 'gross_profit_margin'],
        start_date=start_date, end_date=end_date,
    )

    unified = UnifiedDataProvider(local, config)
    builder = DualMarketQualityLowVolBuilder(unified)
    bt = SingleMarketBacktester(unified, builder, config)

    results = {}
    for factor in ['quality', 'lowvol', 'composite']:
        logger.info(f"回测 {factor.upper()}...")
        results[factor] = bt.backtest_factor(factor, start_date, end_date)

    # 打印结果
    print("\n" + "=" * 90)
    print(f"Quality+LowVol on {universe.upper()} (Local Data)")
    print("=" * 90)
    print(f"{'Factor':<12} {'Ann Return':<12} {'Vol':<12} {'Sharpe':<10} {'Max DD':<10} {'Calmar':<10}")
    print("-" * 90)
    for name, r in results.items():
        print(f"{name:<12} {r.annualized_return*100:>10.2f}% {r.volatility*100:>10.2f}% "
              f"{r.sharpe_ratio:>9.2f} {r.max_drawdown*100:>9.2f}% {r.calmar_ratio:>9.2f}")
    print("=" * 90)

    if save_results:
        os.makedirs("backtests", exist_ok=True)
        data = {name: r.to_dict() for name, r in results.items()}
        with open("backtests/quality_lowvol_local_data.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        viz = ValMomVisualizer()
        viz.plot_equity_curves(results, "backtests/quality_lowvol_local_equity.png")
        viz.plot_drawdown(results, "backtests/quality_lowvol_local_drawdown.png")

    return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
    )

    # 双市场回测 (无API凭证时使用模拟数据)
    results = run_dual_market_backtest(
        start_date="2018-01-01",
        end_date="2024-12-31",
    )
