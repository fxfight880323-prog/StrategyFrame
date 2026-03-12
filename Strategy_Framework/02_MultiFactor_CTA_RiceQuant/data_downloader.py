"""
数据下载与本地缓存
==================
Data Download & Local Cache Manager

数据源优先级:
1. RiceQuant (rqdatac) — A股专业数据源
2. AKShare — 免费开源备选数据源 (无需API Key)
3. 本地缓存 — 已下载的数据直接读取

下载内容:
- A股: 沪深300/中证500成份股、日线行情、因子数据
- 期货: 主要品种日线行情
- 美股: S&P500成份股、日线行情 (通过AKShare)

使用方法:
    # 1. 下载全量数据 (首次运行，需联网)
    python data_downloader.py --download-all

    # 2. 增量更新
    python data_downloader.py --update

    # 3. 在策略中使用本地数据
    from data_downloader import LocalDataProvider
    provider = LocalDataProvider()
    prices = provider.get_price_data(['000001.XSHE'], '2020-01-01', '2024-01-01')
"""

import pandas as pd
import numpy as np
import os
import json
import logging
import time
import argparse
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_cache')

DOWNLOAD_CONFIG = {
    # A股
    'a_stock': {
        'universes': {
            'hs300': '000300.XSHG',
            'zz500': '000905.XSHG',
            'zz800': '000906.XSHG',
        },
        'start_date': '2014-01-01',
        'factors': [
            'return_on_equity', 'return_on_asset',
            'gross_profit_margin', 'net_profit_margin',
            'pe_ratio', 'pb_ratio', 'ps_ratio',
            'market_cap', 'debt_to_asset_ratio',
        ],
    },
    # 期货
    'futures': {
        'symbols': {
            # 商品期货
            'RB': 'RB8888.XSGE',   # 螺纹钢
            'CU': 'CU8888.XSGE',   # 铜
            'AL': 'AL8888.XSGE',   # 铝
            'SC': 'SC8888.XINE',   # 原油
            'TA': 'TA8888.XZCE',   # PTA
            'M': 'M8888.XDCE',     # 豆粕
            'Y': 'Y8888.XDCE',     # 豆油
            'PP': 'PP8888.XDCE',   # 聚丙烯
            # 金融期货
            'IF': 'IF8888.CCFX',   # 沪深300期货
            'IC': 'IC8888.CCFX',   # 中证500期货
            'IH': 'IH8888.CCFX',   # 上证50期货
        },
        'start_date': '2014-01-01',
    },
    # 美股
    'us_stock': {
        'start_date': '2014-01-01',
    },
}


# ============================================================
# RiceQuant 数据下载器
# ============================================================
class RiceQuantDownloader:
    """
    RiceQuant数据下载器

    使用rqdatac下载A股和期货数据，保存为本地CSV/Parquet
    """

    def __init__(self, username: str = None, password: str = None, api_key: str = None):
        self.connected = False
        try:
            import rqdatac as rq
            self.rq = rq

            if api_key:
                rq.init(api_key)
            elif username and password:
                rq.init(username, password)
            else:
                from config import RQ_USERNAME, RQ_PASSWORD
                rq.init(RQ_USERNAME, RQ_PASSWORD)
            self.connected = True
            logger.info("RiceQuant 连接成功")
        except Exception as e:
            logger.warning(f"RiceQuant 连接失败: {e}")

    def download_index_components(self, save_dir: str) -> Dict[str, List[str]]:
        """下载指数成份股"""
        if not self.connected:
            return {}

        os.makedirs(save_dir, exist_ok=True)
        result = {}

        for name, index_code in DOWNLOAD_CONFIG['a_stock']['universes'].items():
            logger.info(f"下载 {name} ({index_code}) 成份股...")
            try:
                # 下载多个时间点的成份股 (用于survivorship-bias-free回测)
                dates = pd.date_range('2014-01-01', datetime.now().strftime('%Y-%m-%d'), freq='YS')
                all_components = {}

                for date in dates:
                    date_str = date.strftime('%Y-%m-%d')
                    try:
                        components = self.rq.index_components(index_code, date=date_str)
                        all_components[date_str] = list(components)
                        logger.info(f"  {date_str}: {len(components)} stocks")
                    except Exception as e:
                        logger.warning(f"  {date_str}: failed - {e}")

                # 当前成份股
                current = self.rq.index_components(index_code)
                all_components['current'] = list(current)
                result[name] = list(current)

                # 保存
                path = os.path.join(save_dir, f'{name}_components.json')
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(all_components, f, indent=2, ensure_ascii=False)
                logger.info(f"  保存: {path}")

            except Exception as e:
                logger.error(f"  下载失败: {e}")

        return result

    def download_stock_prices(self, symbols: List[str], save_dir: str, start_date: str = None):
        """下载A股日线行情"""
        if not self.connected:
            return

        os.makedirs(save_dir, exist_ok=True)
        start = start_date or DOWNLOAD_CONFIG['a_stock']['start_date']
        end = datetime.now().strftime('%Y-%m-%d')

        # 分批下载 (RiceQuant有频率限制)
        batch_size = 50
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            logger.info(f"下载A股行情: batch {i // batch_size + 1}, {len(batch)} stocks...")

            try:
                prices = self.rq.get_price(
                    batch,
                    start_date=start,
                    end_date=end,
                    frequency='1d',
                    fields=['open', 'high', 'low', 'close', 'volume', 'total_turnover'],
                    adjust_type='post',
                )

                if prices is not None and not prices.empty:
                    # 按股票分别保存
                    if isinstance(prices.index, pd.MultiIndex):
                        for sym in batch:
                            try:
                                sym_data = prices.xs(sym, level='order_book_id')
                                sym_safe = sym.replace('.', '_')
                                path = os.path.join(save_dir, f'{sym_safe}.csv')
                                sym_data.to_csv(path)
                            except (KeyError, Exception):
                                pass
                    else:
                        path = os.path.join(save_dir, f'batch_{i // batch_size}.csv')
                        prices.to_csv(path)

                    logger.info(f"  保存完成: {len(batch)} stocks")
                else:
                    logger.warning(f"  无数据返回")

            except Exception as e:
                logger.error(f"  下载失败: {e}")

            time.sleep(1)  # 限流

    def download_factor_data(self, symbols: List[str], save_dir: str, start_date: str = None):
        """下载A股因子数据"""
        if not self.connected:
            return

        os.makedirs(save_dir, exist_ok=True)
        start = start_date or DOWNLOAD_CONFIG['a_stock']['start_date']
        end = datetime.now().strftime('%Y-%m-%d')
        factors = DOWNLOAD_CONFIG['a_stock']['factors']

        # 按季度下载
        dates = pd.date_range(start, end, freq='QS')

        for i, date in enumerate(dates):
            date_end = min(date + pd.DateOffset(months=3), pd.to_datetime(end))
            logger.info(f"下载因子数据: {date.strftime('%Y-%m-%d')} to {date_end.strftime('%Y-%m-%d')} ({i + 1}/{len(dates)})")

            try:
                data = self.rq.get_factor(
                    symbols,
                    factors,
                    start_date=date.strftime('%Y-%m-%d'),
                    end_date=date_end.strftime('%Y-%m-%d'),
                )

                if data is not None and not data.empty:
                    quarter = date.strftime('%Y_Q%q') if hasattr(date, 'quarter') else date.strftime('%Y_%m')
                    path = os.path.join(save_dir, f'factors_{date.strftime("%Y_%m")}.csv')
                    data.to_csv(path)
                    logger.info(f"  保存: {path} ({len(data)} rows)")

            except Exception as e:
                logger.error(f"  下载失败: {e}")

            time.sleep(0.5)

    def download_futures_data(self, save_dir: str, start_date: str = None):
        """下载期货日线行情"""
        if not self.connected:
            return

        os.makedirs(save_dir, exist_ok=True)
        start = start_date or DOWNLOAD_CONFIG['futures']['start_date']
        end = datetime.now().strftime('%Y-%m-%d')

        for name, rq_code in DOWNLOAD_CONFIG['futures']['symbols'].items():
            logger.info(f"下载期货 {name} ({rq_code})...")

            try:
                data = self.rq.get_price(
                    rq_code,
                    start_date=start,
                    end_date=end,
                    frequency='1d',
                    fields=['open', 'high', 'low', 'close', 'volume', 'open_interest'],
                )

                if data is not None and not data.empty:
                    path = os.path.join(save_dir, f'{name}.csv')
                    data.to_csv(path)
                    logger.info(f"  保存: {path} ({len(data)} rows)")
                else:
                    logger.warning(f"  {name}: 无数据")

            except Exception as e:
                logger.error(f"  {name}: 下载失败 - {e}")

            time.sleep(0.5)


# ============================================================
# AKShare 数据下载器 (Plan B)
# ============================================================
class AKShareDownloader:
    """
    AKShare数据下载器 — 免费备选

    AKShare是开源金融数据接口，无需API Key:
    - A股日线行情
    - 期货日线行情
    - 美股日线行情
    - 指数成份股

    安装: pip install akshare
    文档: https://akshare.akfamily.xyz/
    """

    def __init__(self):
        self.available = False
        try:
            import akshare as ak
            self.ak = ak
            self.available = True
            logger.info("AKShare 可用")
        except ImportError:
            logger.warning("AKShare 未安装 (pip install akshare)")

    def download_a_stock_prices(self, symbols: List[str], save_dir: str, start_date: str = '20140101'):
        """
        下载A股日线行情 (通过AKShare)

        AKShare A股数据:
        - ak.stock_zh_a_hist(symbol, period='daily', start_date, end_date, adjust='hfq')
        - symbol格式: '000001' (不含交易所后缀)
        """
        if not self.available:
            return

        os.makedirs(save_dir, exist_ok=True)
        end = datetime.now().strftime('%Y%m%d')

        for i, sym in enumerate(symbols):
            # 转换代码格式: '000001.XSHE' -> '000001'
            code = sym.split('.')[0] if '.' in sym else sym
            logger.info(f"[AKShare] 下载A股 {code} ({i + 1}/{len(symbols)})...")

            try:
                df = self.ak.stock_zh_a_hist(
                    symbol=code,
                    period='daily',
                    start_date=start_date,
                    end_date=end,
                    adjust='hfq',  # 后复权
                )

                if df is not None and not df.empty:
                    # 标准化列名
                    df.columns = [c.lower().replace('日期', 'date').replace('开盘', 'open')
                                  .replace('收盘', 'close').replace('最高', 'high')
                                  .replace('最低', 'low').replace('成交量', 'volume')
                                  for c in df.columns]
                    if 'date' in df.columns:
                        df['date'] = pd.to_datetime(df['date'])
                        df = df.set_index('date')

                    sym_safe = sym.replace('.', '_')
                    path = os.path.join(save_dir, f'{sym_safe}.csv')
                    df.to_csv(path)
                    logger.info(f"  保存: {path} ({len(df)} rows)")

            except Exception as e:
                logger.warning(f"  {code}: 失败 - {e}")

            if i % 5 == 4:
                time.sleep(1)  # 限流

    def download_a_stock_financials(self, symbols: List[str], save_dir: str):
        """
        下载A股财务数据 (用于计算ROE/ROA等因子)

        AKShare方法:
        - ak.stock_financial_analysis_indicator(symbol)
        """
        if not self.available:
            return

        os.makedirs(save_dir, exist_ok=True)

        for i, sym in enumerate(symbols):
            code = sym.split('.')[0] if '.' in sym else sym
            logger.info(f"[AKShare] 下载财务数据 {code} ({i + 1}/{len(symbols)})...")

            try:
                df = self.ak.stock_financial_analysis_indicator(symbol=code)
                if df is not None and not df.empty:
                    sym_safe = sym.replace('.', '_')
                    path = os.path.join(save_dir, f'{sym_safe}_financials.csv')
                    df.to_csv(path, index=False)
                    logger.info(f"  保存: {path} ({len(df)} rows)")

            except Exception as e:
                logger.warning(f"  {code}: 失败 - {e}")

            if i % 3 == 2:
                time.sleep(1)

    def download_futures_data(self, save_dir: str, start_date: str = '20140101'):
        """
        下载期货日线行情 (通过AKShare)

        AKShare方法:
        - ak.futures_main_sina(symbol) — 主力合约
        - ak.futures_zh_daily_sina(symbol) — 指定合约
        """
        if not self.available:
            return

        os.makedirs(save_dir, exist_ok=True)

        futures_map = {
            'RB': 'RB0',  # 螺纹钢主力
            'CU': 'CU0',
            'AL': 'AL0',
            'SC': 'SC0',
            'TA': 'TA0',
            'M': 'M0',
            'Y': 'Y0',
            'PP': 'PP0',
            'IF': 'IF0',
            'IC': 'IC0',
            'IH': 'IH0',
        }

        for name, ak_code in futures_map.items():
            logger.info(f"[AKShare] 下载期货 {name}...")

            try:
                df = self.ak.futures_main_sina(symbol=ak_code)
                if df is not None and not df.empty:
                    path = os.path.join(save_dir, f'{name}.csv')
                    df.to_csv(path)
                    logger.info(f"  保存: {path} ({len(df)} rows)")

            except Exception as e:
                logger.warning(f"  {name}: 失败 - {e}")

            time.sleep(0.5)

    def download_us_stock_prices(self, symbols: List[str], save_dir: str):
        """
        下载美股日线行情 (通过AKShare)

        AKShare方法:
        - ak.stock_us_daily(symbol, adjust='qfq')
        - ak.stock_us_hist(symbol, period='daily', start_date, end_date, adjust='')
        """
        if not self.available:
            return

        os.makedirs(save_dir, exist_ok=True)

        for i, sym in enumerate(symbols):
            logger.info(f"[AKShare] 下载美股 {sym} ({i + 1}/{len(symbols)})...")

            try:
                # AKShare美股使用新浪财经接口
                df = self.ak.stock_us_daily(symbol=sym, adjust='qfq')
                if df is not None and not df.empty:
                    path = os.path.join(save_dir, f'{sym}.csv')
                    df.to_csv(path)
                    logger.info(f"  保存: {path} ({len(df)} rows)")

            except Exception as e:
                logger.warning(f"  {sym}: 失败 - {e}")

            if i % 5 == 4:
                time.sleep(1)

    def download_index_components(self, save_dir: str) -> Dict[str, List[str]]:
        """
        下载指数成份股 (通过AKShare)

        AKShare方法:
        - ak.index_stock_cons(symbol='000300')  # 沪深300
        """
        if not self.available:
            return {}

        os.makedirs(save_dir, exist_ok=True)
        result = {}

        index_map = {
            'hs300': '000300',
            'zz500': '000905',
        }

        for name, code in index_map.items():
            logger.info(f"[AKShare] 下载 {name} 成份股...")
            try:
                df = self.ak.index_stock_cons(symbol=code)
                if df is not None and not df.empty:
                    # 提取品种代码列
                    code_col = [c for c in df.columns if '代码' in c or 'code' in c.lower()]
                    if code_col:
                        stocks = df[code_col[0]].tolist()
                    else:
                        stocks = df.iloc[:, 0].tolist()

                    result[name] = stocks
                    path = os.path.join(save_dir, f'{name}_components_akshare.json')
                    with open(path, 'w') as f:
                        json.dump({'current': stocks}, f, indent=2)
                    logger.info(f"  {name}: {len(stocks)} stocks")

            except Exception as e:
                logger.warning(f"  {name}: 失败 - {e}")

        return result


# ============================================================
# 本地数据提供器 (供策略使用)
# ============================================================
class LocalDataProvider:
    """
    本地数据提供器

    从data_cache读取已下载的数据，接口与RiceQuantDataProvider一致
    可直接替换到策略中
    """

    def __init__(self, data_dir: str = None):
        self.data_dir = data_dir or DATA_DIR
        self.logger = logging.getLogger(__name__)

        # 缓存已加载的数据
        self._price_cache = {}
        self._factor_cache = {}
        self._universe_cache = {}

    def get_stock_universe(self, universe: str = 'hs300', date: str = None) -> List[str]:
        """获取股票池 (从本地缓存)"""
        if universe in self._universe_cache:
            return self._universe_cache[universe]

        # 尝试RiceQuant格式
        path = os.path.join(self.data_dir, 'components', f'{universe}_components.json')
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
            if date and date in data:
                stocks = data[date]
            else:
                stocks = data.get('current', list(data.values())[-1])
            self._universe_cache[universe] = stocks
            return stocks

        # 尝试AKShare格式
        path = os.path.join(self.data_dir, 'components', f'{universe}_components_akshare.json')
        if os.path.exists(path):
            with open(path, 'r') as f:
                data = json.load(f)
            stocks = data.get('current', [])
            self._universe_cache[universe] = stocks
            return stocks

        self.logger.warning(f"未找到{universe}成份股数据，请先运行 python data_downloader.py --download-all")
        return []

    def get_price_data(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """获取价格数据 (从本地缓存)"""
        prices = {}
        price_dir = os.path.join(self.data_dir, 'a_stock_prices')

        for sym in symbols:
            sym_safe = sym.replace('.', '_')
            path = os.path.join(price_dir, f'{sym_safe}.csv')

            if not os.path.exists(path):
                continue

            if sym not in self._price_cache:
                df = pd.read_csv(path, index_col=0, parse_dates=True)
                self._price_cache[sym] = df

            df = self._price_cache[sym]

            # 切片日期
            mask = (df.index >= start_date) & (df.index <= end_date)
            if mask.any():
                close_col = 'close' if 'close' in df.columns else df.columns[0]
                prices[sym] = df.loc[mask, close_col]

        if prices:
            return pd.DataFrame(prices)
        return pd.DataFrame()

    def get_factor_data(
        self,
        symbols: List[str],
        factors: List[str],
        date: str,
    ) -> pd.DataFrame:
        """获取因子数据 (从本地缓存)"""
        factor_dir = os.path.join(self.data_dir, 'a_stock_factors')
        if not os.path.exists(factor_dir):
            return pd.DataFrame()

        # 找到最近的因子文件
        target = pd.to_datetime(date)
        factor_files = sorted(Path(factor_dir).glob('factors_*.csv'))

        if not factor_files:
            return pd.DataFrame()

        # 加载最近的文件
        best_file = factor_files[-1]
        for f in factor_files:
            try:
                file_date = pd.to_datetime(f.stem.replace('factors_', ''), format='%Y_%m')
                if file_date <= target:
                    best_file = f
            except Exception:
                pass

        df = pd.read_csv(best_file, index_col=[0, 1] if 'order_book_id' not in str(best_file) else 0,
                         parse_dates=True)

        # 筛选目标股票
        result = pd.DataFrame(index=symbols)
        for factor in factors:
            if factor in df.columns:
                factor_data = df[factor]
                if isinstance(factor_data.index, pd.MultiIndex):
                    # 取最近日期
                    latest = factor_data.groupby(level=1).last()
                    result[factor] = latest.reindex(symbols)
                else:
                    result[factor] = factor_data.reindex(symbols)

        return result

    def get_futures_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取期货数据 (从本地缓存)"""
        futures_dir = os.path.join(self.data_dir, 'futures')
        path = os.path.join(futures_dir, f'{symbol}.csv')

        if not os.path.exists(path):
            return pd.DataFrame()

        df = pd.read_csv(path, index_col=0, parse_dates=True)
        mask = (df.index >= start_date) & (df.index <= end_date)
        return df.loc[mask] if mask.any() else pd.DataFrame()

    def get_us_stock_prices(self, symbols: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        """获取美股数据 (从本地缓存)"""
        us_dir = os.path.join(self.data_dir, 'us_stock_prices')
        prices = {}

        for sym in symbols:
            path = os.path.join(us_dir, f'{sym}.csv')
            if os.path.exists(path):
                df = pd.read_csv(path, index_col=0, parse_dates=True)
                mask = (df.index >= start_date) & (df.index <= end_date)
                if mask.any():
                    close_col = 'close' if 'close' in df.columns else df.columns[0]
                    prices[sym] = df.loc[mask, close_col]

        return pd.DataFrame(prices) if prices else pd.DataFrame()

    def check_data_status(self) -> Dict:
        """检查本地数据状态"""
        status = {}

        # 成份股
        comp_dir = os.path.join(self.data_dir, 'components')
        if os.path.exists(comp_dir):
            files = list(Path(comp_dir).glob('*.json'))
            status['components'] = len(files)
        else:
            status['components'] = 0

        # A股行情
        price_dir = os.path.join(self.data_dir, 'a_stock_prices')
        if os.path.exists(price_dir):
            files = list(Path(price_dir).glob('*.csv'))
            status['a_stock_prices'] = len(files)
        else:
            status['a_stock_prices'] = 0

        # 因子
        factor_dir = os.path.join(self.data_dir, 'a_stock_factors')
        if os.path.exists(factor_dir):
            files = list(Path(factor_dir).glob('*.csv'))
            status['a_stock_factors'] = len(files)
        else:
            status['a_stock_factors'] = 0

        # 期货
        futures_dir = os.path.join(self.data_dir, 'futures')
        if os.path.exists(futures_dir):
            files = list(Path(futures_dir).glob('*.csv'))
            status['futures'] = len(files)
        else:
            status['futures'] = 0

        # 美股
        us_dir = os.path.join(self.data_dir, 'us_stock_prices')
        if os.path.exists(us_dir):
            files = list(Path(us_dir).glob('*.csv'))
            status['us_stock_prices'] = len(files)
        else:
            status['us_stock_prices'] = 0

        return status


# ============================================================
# 全量下载编排
# ============================================================
def download_all(
    rq_username: str = None,
    rq_password: str = None,
    rq_api_key: str = None,
    use_akshare: bool = True,
    start_date: str = '2014-01-01',
):
    """
    下载全量数据

    优先级: RiceQuant > AKShare
    两个源都尝试，互相补充

    Args:
        rq_username: RiceQuant用户名 (默认用config.py)
        rq_password: RiceQuant密码
        rq_api_key: RiceQuant API Key
        use_akshare: 是否同时使用AKShare
        start_date: 数据起始日期
    """
    logger.info("=" * 70)
    logger.info("开始下载全量数据")
    logger.info(f"数据目录: {DATA_DIR}")
    logger.info("=" * 70)

    os.makedirs(DATA_DIR, exist_ok=True)
    all_symbols = []

    # ===== 1. RiceQuant 下载 =====
    rq_dl = RiceQuantDownloader(rq_username, rq_password, rq_api_key)

    if rq_dl.connected:
        logger.info("\n[1/5] 下载指数成份股 (RiceQuant)...")
        components = rq_dl.download_index_components(
            os.path.join(DATA_DIR, 'components')
        )

        # 收集所有股票代码
        for name, stocks in components.items():
            all_symbols.extend(stocks)
        all_symbols = list(set(all_symbols))
        logger.info(f"  总计 {len(all_symbols)} 只A股")

        logger.info("\n[2/5] 下载A股日线行情 (RiceQuant)...")
        rq_dl.download_stock_prices(
            all_symbols,
            os.path.join(DATA_DIR, 'a_stock_prices'),
            start_date,
        )

        logger.info("\n[3/5] 下载A股因子数据 (RiceQuant)...")
        rq_dl.download_factor_data(
            all_symbols,
            os.path.join(DATA_DIR, 'a_stock_factors'),
            start_date,
        )

        logger.info("\n[4/5] 下载期货日线行情 (RiceQuant)...")
        rq_dl.download_futures_data(
            os.path.join(DATA_DIR, 'futures'),
            start_date,
        )
    else:
        logger.warning("RiceQuant不可用，跳过")

    # ===== 2. AKShare 补充 =====
    if use_akshare:
        ak_dl = AKShareDownloader()

        if ak_dl.available:
            # 如果RiceQuant没有成份股数据，用AKShare下载
            if not all_symbols:
                logger.info("\n[AKShare] 下载指数成份股...")
                ak_components = ak_dl.download_index_components(
                    os.path.join(DATA_DIR, 'components')
                )
                for stocks in ak_components.values():
                    all_symbols.extend(stocks)
                all_symbols = list(set(all_symbols))

            # 下载缺失的A股行情
            price_dir = os.path.join(DATA_DIR, 'a_stock_prices')
            existing = set()
            if os.path.exists(price_dir):
                existing = {f.replace('.csv', '').replace('_', '.')
                            for f in os.listdir(price_dir) if f.endswith('.csv')}
            missing = [s for s in all_symbols if s not in existing]

            if missing:
                logger.info(f"\n[AKShare] 补充下载 {len(missing)} 只A股行情...")
                ak_dl.download_a_stock_prices(
                    missing[:200],  # 限制数量避免限流
                    price_dir,
                    start_date.replace('-', ''),
                )

            # 下载期货
            futures_dir = os.path.join(DATA_DIR, 'futures')
            if not os.path.exists(futures_dir) or len(os.listdir(futures_dir)) == 0:
                logger.info("\n[AKShare] 下载期货行情...")
                ak_dl.download_futures_data(futures_dir)

            # 下载美股
            logger.info("\n[5/5] 下载美股行情 (AKShare)...")
            us_symbols = [
                'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'NVDA', 'JPM',
                'JNJ', 'V', 'PG', 'UNH', 'HD', 'MA', 'BAC', 'XOM',
                'CRM', 'NFLX', 'CSCO', 'PFE', 'TMO', 'ABT', 'COST',
                'PEP', 'AVGO', 'ACN', 'MRK', 'NKE', 'LLY', 'WMT',
            ]
            ak_dl.download_us_stock_prices(
                us_symbols,
                os.path.join(DATA_DIR, 'us_stock_prices'),
            )

    # ===== 3. 状态汇总 =====
    provider = LocalDataProvider(DATA_DIR)
    status = provider.check_data_status()

    logger.info("\n" + "=" * 70)
    logger.info("下载完成! 数据状态:")
    logger.info("=" * 70)
    for k, v in status.items():
        logger.info(f"  {k}: {v} files")
    logger.info(f"\n数据目录: {DATA_DIR}")
    logger.info("在策略中使用: from data_downloader import LocalDataProvider")
    logger.info("=" * 70)

    return status


def update_data(
    rq_username: str = None,
    rq_password: str = None,
    use_akshare: bool = True,
):
    """增量更新 — 只下载最近数据"""
    # 找到已有数据的最新日期
    price_dir = os.path.join(DATA_DIR, 'a_stock_prices')
    latest_date = '2024-01-01'

    if os.path.exists(price_dir):
        csv_files = list(Path(price_dir).glob('*.csv'))
        if csv_files:
            df = pd.read_csv(csv_files[0], index_col=0, parse_dates=True)
            latest_date = df.index.max().strftime('%Y-%m-%d')
            logger.info(f"已有数据最新日期: {latest_date}")

    # 从最新日期开始更新
    download_all(
        rq_username=rq_username,
        rq_password=rq_password,
        use_akshare=use_akshare,
        start_date=latest_date,
    )


# ============================================================
# 命令行入口
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='数据下载与缓存管理')
    parser.add_argument('--download-all', action='store_true', help='下载全量数据')
    parser.add_argument('--update', action='store_true', help='增量更新')
    parser.add_argument('--status', action='store_true', help='检查数据状态')
    parser.add_argument('--rq-username', type=str, default=None, help='RiceQuant用户名')
    parser.add_argument('--rq-password', type=str, default=None, help='RiceQuant密码')
    parser.add_argument('--rq-api-key', type=str, default=None, help='RiceQuant API Key')
    parser.add_argument('--no-akshare', action='store_true', help='不使用AKShare')
    parser.add_argument('--start-date', type=str, default='2014-01-01', help='数据起始日期')

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
    )

    if args.status:
        provider = LocalDataProvider()
        status = provider.check_data_status()
        print("\n数据状态:")
        for k, v in status.items():
            print(f"  {k}: {v} files")

    elif args.download_all:
        download_all(
            rq_username=args.rq_username or '+8613810062394',
            rq_password=args.rq_password or 'Fox880323!',
            rq_api_key=args.rq_api_key,
            use_akshare=not args.no_akshare,
            start_date=args.start_date,
        )

    elif args.update:
        update_data(
            rq_username=args.rq_username or '+8613810062394',
            rq_password=args.rq_password or 'Fox880323!',
            use_akshare=not args.no_akshare,
        )

    else:
        parser.print_help()
        print("\n示例:")
        print("  # 下载全量数据 (RiceQuant + AKShare)")
        print("  python data_downloader.py --download-all")
        print("")
        print("  # 用自定义API Key")
        print("  python data_downloader.py --download-all --rq-api-key 'YOUR_KEY'")
        print("")
        print("  # 增量更新")
        print("  python data_downloader.py --update")
        print("")
        print("  # 只用AKShare (无需RiceQuant)")
        print("  python data_downloader.py --download-all --rq-username '' --rq-password ''")
