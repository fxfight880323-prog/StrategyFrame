"""
美股财报预期分析系统
========================
基于真实财报披露时间，分析市场对个股的预期高低。
覆盖范围：美股核心100+个股（与CTA技术分析相同的标的范围）

核心逻辑：
- 当业绩超预期但股价下跌 → 市场预期已被透支（预期过高）
- 当业绩低于预期但股价上涨 → 市场预期过于悲观（预期过低）
- 当业绩和股价同向反应 → 市场预期与实际情况一致
"""

import sys
import time
import math
import logging
import random
import os
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Any, Dict, List, Optional, Tuple
from functools import lru_cache

import pandas as pd
import requests
import akshare as ak
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay


# ============================================================
# USER CONFIG
# ============================================================
# 美股核心个股 (与CTA技术分析相同的标的范围)
TICKERS = [
    # 科技巨头 (Mag7)
    "AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA",
    # 其他科技
    "AMD", "CRM", "ORCL", "NFLX", "AVGO", "QCOM", "ADBE", 
    "INTC", "CSCO", "IBM", "UBER", "ABNB", "PYPL", "SQ",
    # 金融
    "JPM", "BAC", "GS", "MS", "WFC", "BLK", "C",
    # 消费
    "WMT", "COST", "HD", "NKE", "DIS", "MCD", "SBUX", "TJX",
    # 医药
    "JNJ", "UNH", "LLY", "PFE", "MRK", "ABBV", "TMO",
    # 工业
    "CAT", "BA", "GE", "HON", "UPS", "FDX", "MMM",
    # 能源
    "XOM", "CVX", "COP", "SLB", "EOG",
    # 通信
    "VZ", "T", "TMUS", "CMCSA",
    # 其他龙头
    "V", "MA", "UNP", "LOW", "BMY", "DHR", "SPGI", "ACN",
    "TXN", "PM", "RTX", "HDB", "AXP", "PGR", "SYK", "BKNG",
    "ELV", "LIN", "AMT", "NOW", "ISRG", "LRCX", "MU", "KLAC",
    "PANW", "SNOW", "ZM", "ROKU", "PLTR", "CRWD", "MDB", "NET",
    "ZS", "OKTA", "DDOG", "SPLK", "TWLO", "ASML", "SHOP", "FTNT",
    # 用户重仓股
    "SNDK",  # SanDisk 闪迪
    "TSM",   # 台积电
]
START_DATE = "2024-01-01"
END_DATE = "2026-02-23"

OUTPUT_DIR = "."
OUTPUT_XLSX = "us_stocks_earnings_expectation.xlsx"

# Finnhub API Key（免费版每分钟60次调用）
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "d65ul8pr01qiish14p3gd65ul8pr01qiish14p40")

SLEEP_SEC = 0.5  # 扩大标的范围后适当降低sleep时间
PRICE_BUFFER_DAYS = 5


# ============================================================
# Logging
# ============================================================
def setup_logger(name: str = "earnings_expectation", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# Exceptions
# ============================================================
class DataValidationError(RuntimeError):
    pass


class DataSourceError(RuntimeError):
    pass


# ============================================================
# Config
# ============================================================
@dataclass(frozen=True)
class EngineConfig:
    tickers: List[str]
    start_date: str
    end_date: str
    finnhub_api_key: str
    sleep_sec: float = 1.0
    price_buffer_days: int = 5
    
    # 信号阈值
    bullish_th: float = 0.03
    watch_th: float = 0.015
    bearish_th: float = -0.015
    
    # 超预期阈值
    strong_beat_th: float = 0.10
    beat_th: float = 0.05
    miss_th: float = -0.05
    strong_miss_th: float = -0.10


# ============================================================
# Utils
# ============================================================
def safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if math.isfinite(v):
            return v
        return None
    except Exception:
        return None


def to_date(s: Any) -> date:
    if isinstance(s, date):
        return s
    if isinstance(s, datetime):
        return s.date()
    return pd.to_datetime(s).date()


def ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def make_key(ticker: str, d: date) -> str:
    return f"{ticker.upper()}|{ymd(d)}"


def next_us_business_day(d: date) -> date:
    """获取下一个美股交易日（近似）"""
    cbd = CustomBusinessDay(calendar=USFederalHolidayCalendar())
    return (pd.Timestamp(d) + 1 * cbd).date()


# ============================================================
# Finnhub 数据源 - 获取真实财报数据
# ============================================================
class FinnhubDataSource:
    """使用 Finnhub API 获取美股财报数据"""
    
    BASE_URL = "https://finnhub.io/api/v1"
    
    def __init__(self, api_key: str, logger: logging.Logger, sleep_sec: float = 1.0):
        self.api_key = api_key
        self.logger = logger
        self.sleep_sec = sleep_sec
        self.cache_dir = "_finnhub_cache"
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def _get_cache_path(self, ticker: str) -> str:
        return os.path.join(self.cache_dir, f"{ticker}_earnings.csv")
    
    def _load_cache(self, ticker: str) -> Optional[pd.DataFrame]:
        cache_path = self._get_cache_path(ticker)
        if os.path.exists(cache_path):
            try:
                df = pd.read_csv(cache_path)
                df['date'] = pd.to_datetime(df['date']).dt.date
                return df
            except Exception:
                return None
        return None
    
    def _save_cache(self, ticker: str, df: pd.DataFrame):
        cache_path = self._get_cache_path(ticker)
        df.to_csv(cache_path, index=False)
    
    def _estimate_report_date(self, period_date: date) -> date:
        """
        估算财报发布日期
        美股通常规律：
        - Q1 (1-3月): 4月中下旬发布
        - Q2 (4-6月): 7月中下旬发布  
        - Q3 (7-9月): 10月中下旬发布
        - Q4 (10-12月): 1月中下旬发布（次年）
        """
        month = period_date.month
        year = period_date.year
        
        # 根据季度结束月份确定发布月份
        if month == 3:    # Q1
            return date(year, 4, 25)
        elif month == 6:  # Q2
            return date(year, 7, 25)
        elif month == 9:  # Q3
            return date(year, 10, 25)
        elif month == 12: # Q4
            return date(year + 1, 1, 25)
        else:
            # 其他情况，默认一个月后
            return date(year, month + 1, 15) if month < 12 else date(year + 1, 1, 15)
    
    def fetch_earnings(self, ticker: str, from_date: str, end_date: str) -> pd.DataFrame:
        """获取财报数据"""
        # 先尝试读取缓存
        cache_df = self._load_cache(ticker)
        if cache_df is not None and not cache_df.empty:
            sd, ed = to_date(from_date), to_date(end_date)
            return cache_df[(cache_df['date'] >= sd) & (cache_df['date'] <= ed)].copy()
        
        if not self.api_key:
            self.logger.warning(f"No Finnhub API key provided")
            return pd.DataFrame()
        
        url = f"{self.BASE_URL}/stock/earnings"
        params = {
            "symbol": ticker,
            "from": from_date,
            "to": end_date,
            "token": self.api_key
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                time.sleep(self.sleep_sec)
                response = requests.get(url, params=params, timeout=30)
                
                if response.status_code == 429:
                    self.logger.warning(f"Rate limited, waiting 10s...")
                    time.sleep(10)
                    continue
                
                response.raise_for_status()
                data = response.json()
                
                if not data:
                    return pd.DataFrame()
                
                df = pd.DataFrame(data)
                if df.empty:
                    return df
                
                # Finnhub 使用 'period' 作为财报期（季度结束日期）
                # 需要估算财报发布日期（通常为季度结束后 4-6 周）
                df['period_date'] = pd.to_datetime(df['period']).dt.date
                df['report_date'] = df['period_date'].apply(self._estimate_report_date)
                df['date'] = df['report_date']  # 用于后续匹配的字段
                df['ticker'] = ticker.upper()
                
                # 添加财报期数字段 (如 "2025 Q1")
                df['FiscalPeriod'] = df['year'].astype(str) + ' Q' + df['quarter'].astype(str)
                
                # 重命名 EPS 字段以便后续使用
                if 'actual' in df.columns:
                    df['epsActual'] = df['actual']
                if 'estimate' in df.columns:
                    df['epsEstimate'] = df['estimate']
                
                # 保存缓存
                self._save_cache(ticker, df)
                
                return df[(df['date'] >= to_date(from_date)) & (df['date'] <= to_date(end_date))].copy()
                
            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"Retry {attempt + 1} for {ticker}: {e}")
                    time.sleep(5)
                else:
                    self.logger.error(f"Failed to fetch earnings for {ticker}: {e}")
                    return pd.DataFrame()
        
        return pd.DataFrame()


# ============================================================
# AkShare 数据源 - 获取价格数据
# ============================================================
class AkShareDataSource:
    def __init__(self, logger: logging.Logger, sleep_sec: float = 1.0):
        self.logger = logger
        self.sleep_sec = sleep_sec
    
    def fetch_prices_daily(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """获取美股历史价格"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                time.sleep(self.sleep_sec + random.uniform(0, 0.5))
                df = ak.stock_us_daily(symbol=ticker, adjust="")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 3 + random.uniform(0, 2)
                    self.logger.warning(f"Retry {attempt + 1} for {ticker}")
                    time.sleep(wait_time)
                else:
                    raise DataSourceError(f"Price download failed: {e}")
        
        if df is None or df.empty:
            return pd.DataFrame(columns=["Ticker", "Date", "Open", "High", "Low", "Close"])
        
        df = df.reset_index()
        if 'date' in df.columns:
            df = df.rename(columns={'date': 'Date'})
        
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        df = df[(df['Date'] >= start) & (df['Date'] <= end)].copy()
        
        if df.empty:
            return pd.DataFrame(columns=["Ticker", "Date", "Open", "High", "Low", "Close"])
        
        out = pd.DataFrame({
            "Ticker": ticker.upper(),
            "Date": df["Date"],
            "Open": pd.to_numeric(df.get("open"), errors="coerce"),
            "High": pd.to_numeric(df.get("high"), errors="coerce"),
            "Low": pd.to_numeric(df.get("low"), errors="coerce"),
            "Close": pd.to_numeric(df.get("close"), errors="coerce"),
        })
        return out.dropna(subset=["Close"]).copy()


# ============================================================
# 财报预期分析引擎
# ============================================================
class EarningsExpectationEngine:
    """
    分析财报后的市场反应，判断市场预期高低
    """
    
    def __init__(self, cfg: EngineConfig, logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger
        self.finnhub = FinnhubDataSource(cfg.finnhub_api_key, logger, cfg.sleep_sec)
        self.akshare = AkShareDataSource(logger, cfg.sleep_sec)
    
    def run(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """运行分析流程"""
        self.logger.info("=" * 60)
        self.logger.info("MAG7 财报预期分析系统")
        self.logger.info("=" * 60)
        
        # 1. 获取财报数据
        earnings = self.fetch_earnings_data()
        if earnings.empty:
            raise DataValidationError("未获取到财报数据，请检查 Finnhub API Key")
        
        # 2. 获取价格数据
        prices = self.fetch_prices_data()
        
        # 3. 计算财报后的市场反应
        reactions = self.calculate_reactions(earnings, prices)
        
        # 4. 分析市场预期
        analysis = self.analyze_expectations(reactions)
        
        return earnings, reactions, analysis
    
    def fetch_earnings_data(self) -> pd.DataFrame:
        """获取所有股票的财报数据"""
        self.logger.info("获取财报数据...")
        frames = []
        
        for ticker in self.cfg.tickers:
            df = self.finnhub.fetch_earnings(ticker, self.cfg.start_date, self.cfg.end_date)
            if not df.empty:
                frames.append(df)
                self.logger.info(f"  {ticker}: {len(df)} 条财报记录")
        
        if not frames:
            return pd.DataFrame()
        
        return pd.concat(frames, ignore_index=True)
    
    def fetch_prices_data(self) -> pd.DataFrame:
        """获取所有股票的价格数据"""
        self.logger.info("获取价格数据...")
        
        # 扩大日期范围以覆盖财报前后
        start = to_date(self.cfg.start_date) - timedelta(days=self.cfg.price_buffer_days * 10)
        end = to_date(self.cfg.end_date) + timedelta(days=self.cfg.price_buffer_days)
        
        frames = []
        for ticker in self.cfg.tickers:
            try:
                df = self.akshare.fetch_prices_daily(ticker, start, end)
                if not df.empty:
                    # 计算 PrevClose
                    df["PrevClose"] = df["Close"].shift(1)
                    df = df.dropna(subset=["PrevClose"]).copy()
                    
                    # 计算涨跌幅
                    df["GapPct"] = (df["Open"] - df["PrevClose"]) / df["PrevClose"]
                    df["IntradayPct"] = (df["Close"] - df["Open"]) / df["Open"]
                    df["DayChange"] = (df["Close"] - df["PrevClose"]) / df["PrevClose"]
                    
                    frames.append(df)
                    self.logger.info(f"  {ticker}: {len(df)} 条价格记录")
            except Exception as e:
                self.logger.error(f"  {ticker} 获取失败: {e}")
        
        if not frames:
            raise DataSourceError("未获取到价格数据")
        
        return pd.concat(frames, ignore_index=True)
    
    def calculate_reactions(self, earnings: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
        """
        计算财报发布后的市场反应
        
        逻辑：
        - 盘前发布(bmo) → 反应当天(同一天)
        - 盘后发布(amc) → 反应次日
        """
        self.logger.info("计算市场反应...")
        
        # 构建价格查找表
        price_map = prices.set_index(["Ticker", "Date"])
        
        results = []
        for _, row in earnings.iterrows():
            ticker = row['ticker']
            report_date = row['date']
            hour = row.get('hour', 'amc')  # 默认盘后
            
            # 确定反应日期
            if hour == 'bmo':  # 盘前发布
                reaction_date = report_date
            else:  # 盘后发布（默认）
                reaction_date = next_us_business_day(report_date)
            
            # 查找价格数据
            try:
                if (ticker, reaction_date) in price_map.index:
                    price_row = price_map.loc[(ticker, reaction_date)]
                    prev_row = price_map.loc[(ticker, reaction_date - timedelta(days=1))] \
                        if (ticker, reaction_date - timedelta(days=1)) in price_map.index else None
                    
                    result = {
                        'Ticker': ticker,
                        'FiscalPeriod': row.get('FiscalPeriod'),  # 财报期数 (如 2025 Q1)
                        'PeriodEndDate': row.get('period_date'),  # 财季结束日期
                        'ReportDate': report_date,                # 财报发布日期(估算)
                        'Hour': hour,
                        'ReactionDate': reaction_date,
                        'EPS_Actual': row.get('epsActual'),
                        'EPS_Estimate': row.get('epsEstimate'),
                        'SurprisePct': safe_float(row.get('surprisePercent')) / 100 
                            if pd.notna(row.get('surprisePercent')) else None,
                        'Open': price_row['Open'],
                        'High': price_row['High'],
                        'Low': price_row['Low'],
                        'Close': price_row['Close'],
                        'PrevClose': price_row['PrevClose'],
                        'GapPct': price_row['GapPct'],
                        'IntradayPct': price_row['IntradayPct'],
                        'DayChange': price_row['DayChange'],
                    }
                    results.append(result)
            except Exception as e:
                self.logger.warning(f"  无法匹配 {ticker} {report_date} 的价格: {e}")
        
        df = pd.DataFrame(results)
        self.logger.info(f"成功匹配 {len(df)} 条财报-价格数据")
        return df


    def analyze_expectations(self, reactions: pd.DataFrame) -> pd.DataFrame:
        """
        分析市场预期
        
        核心判断逻辑：
        1. Surprise% > 0 (业绩超预期) + GapPct > 0 (股价上涨) → 预期合理/低估
        2. Surprise% > 0 (业绩超预期) + GapPct < 0 (股价下跌) → 预期过高（已被透支）
        3. Surprise% < 0 (低于预期) + GapPct < 0 (股价下跌) → 预期合理/高估
        4. Surprise% < 0 (低于预期) + GapPct > 0 (股价上涨) → 预期过低（利空出尽）
        """
        self.logger.info("分析市场预期...")
        
        df = reactions.copy()
        
        # 分类业绩 Surprise
        def classify_surprise(sp):
            if pd.isna(sp):
                return "Unknown"
            if sp >= self.cfg.strong_beat_th:
                return "Strong Beat"
            if sp >= self.cfg.beat_th:
                return "Beat"
            if sp <= self.cfg.strong_miss_th:
                return "Strong Miss"
            if sp <= self.cfg.miss_th:
                return "Miss"
            return "Inline"
        
        # 分类市场反应
        def classify_reaction(gap):
            if pd.isna(gap):
                return "Unknown"
            if gap >= self.cfg.bullish_th:
                return "Positive"
            if gap <= self.cfg.bearish_th:
                return "Negative"
            return "Neutral"
        
        # 判断预期高低
        def judge_expectation(row):
            sp = row['SurprisePct']
            gap = row['GapPct']
            
            if pd.isna(sp) or pd.isna(gap):
                return "Unknown", "N/A"
            
            # 情况1: 业绩超预期
            if sp > 0:
                if gap > 0:
                    # 好事+上涨 = 预期合理或略低
                    if gap > sp * 0.5:  # 涨幅超过惊喜的一半
                        return "Expectation Low", "市场可能过于保守，仍有上涨空间"
                    else:
                        return "Expectation Reasonable", "市场预期与业绩匹配"
                else:
                    # 好事+下跌 = 预期已被透支（买预期卖事实）
                    return "Expectation High", "业绩已被Price In，预期过高"
            
            # 情况2: 业绩低于预期
            elif sp < 0:
                if gap < 0:
                    # 坏事+下跌 = 预期合理或略高
                    if abs(gap) > abs(sp) * 0.5:
                        return "Expectation High", "市场反应过度，可能过度悲观"
                    else:
                        return "Expectation Reasonable", "市场预期与业绩匹配"
                else:
                    # 坏事+上涨 = 预期过低（利空出尽）
                    return "Expectation Low", "市场已充分消化利空，或有反弹"
            
            # 情况3: 业绩符合预期
            else:
                if abs(gap) < 0.01:
                    return "Expectation Accurate", "市场预测精准"
                elif gap > 0:
                    return "Slight Optimistic", "市场略偏乐观"
                else:
                    return "Slight Pessimistic", "市场略偏悲观"
        
        df['SurpriseClass'] = df['SurprisePct'].apply(classify_surprise)
        df['ReactionClass'] = df['GapPct'].apply(classify_reaction)
        
        expectation_results = df.apply(judge_expectation, axis=1)
        df['ExpectationLevel'] = [r[0] for r in expectation_results]
        df['ExpectationComment'] = [r[1] for r in expectation_results]
        
        # 计算综合得分
        df['SignalScore'] = df.apply(self._calculate_signal_score, axis=1)
        
        # 排序
        df = df.sort_values(['Ticker', 'ReportDate'], ascending=[True, False])
        
        return df
    
    def _calculate_signal_score(self, row) -> float:
        """计算综合信号得分"""
        sp = row['SurprisePct'] if pd.notna(row['SurprisePct']) else 0
        gap = row['GapPct'] if pd.notna(row['GapPct']) else 0
        
        # 基础分：业绩 Surprise
        score = sp * 0.5
        
        # 市场反应分
        score += gap * 0.3
        
        # 日内走势分
        intraday = row['IntradayPct'] if pd.notna(row['IntradayPct']) else 0
        score += intraday * 0.2
        
        return round(score, 4)


# ============================================================
# 输出和可视化
# ============================================================
def save_outputs(earnings: pd.DataFrame, reactions: pd.DataFrame, analysis: pd.DataFrame,
                 out_dir: str, xlsx_name: str, logger: logging.Logger):
    """保存结果到文件"""
    import os
    os.makedirs(out_dir, exist_ok=True)
    
    # 生成摘要报告
    summary = generate_summary(analysis)
    
    xlsx_path = os.path.join(out_dir, xlsx_name)
    
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        analysis.to_excel(w, sheet_name="ExpectationAnalysis", index=False)
        reactions.to_excel(w, sheet_name="RawReactions", index=False)
        earnings.to_excel(w, sheet_name="EarningsData", index=False)
        summary.to_excel(w, sheet_name="Summary", index=False)
    
    # 同时保存 CSV
    analysis.to_csv(os.path.join(out_dir, "expectation_analysis.csv"), index=False)
    summary.to_csv(os.path.join(out_dir, "summary.csv"), index=False)
    
    logger.info(f"结果已保存: {xlsx_path}")
    
    # 打印摘要
    print_summary(summary, logger)


def generate_summary(analysis: pd.DataFrame) -> pd.DataFrame:
    """生成每只股票最新的预期分析摘要"""
    # 取每只股票最新的财报
    latest = analysis.sort_values('ReportDate', ascending=False).groupby('Ticker').first().reset_index()
    
    summary = latest[['Ticker', 'FiscalPeriod', 'PeriodEndDate', 'ReportDate', 
                     'EPS_Actual', 'EPS_Estimate', 'SurprisePct',
                     'GapPct', 'DayChange', 'SurpriseClass', 'ReactionClass', 
                     'ExpectationLevel', 'ExpectationComment', 'SignalScore']].copy()
    
    # 保持原始数值，在打印时再格式化
    
    # 按 SignalScore 排序
    summary = summary.sort_values('SignalScore', ascending=False)
    
    return summary


def print_summary(summary: pd.DataFrame, logger: logging.Logger):
    """打印摘要到日志"""
    logger.info("\n" + "=" * 80)
    logger.info("MAG7 财报预期分析摘要（按信号强度排序）")
    logger.info("=" * 80)
    
    for _, row in summary.iterrows():
        logger.info(f"\n[{row['Ticker']}]")
        fiscal_period = row['FiscalPeriod'] if pd.notna(row['FiscalPeriod']) else 'N/A'
        period_end = row['PeriodEndDate'] if pd.notna(row['PeriodEndDate']) else 'N/A'
        report_date = row['ReportDate'] if pd.notna(row['ReportDate']) else 'N/A'
        logger.info(f"  财报期数: {fiscal_period} (财季截止: {period_end})")
        logger.info(f"  发布日期: {report_date} (估算)")
        eps_actual = row['EPS_Actual'] if pd.notna(row['EPS_Actual']) else 0
        eps_estimate = row['EPS_Estimate'] if pd.notna(row['EPS_Estimate']) else 0
        surprise = row['SurprisePct'] if pd.notna(row['SurprisePct']) else 0
        logger.info(f"  EPS: 实际 ${eps_actual:.2f} vs 预期 ${eps_estimate:.2f} -> Surprise: {surprise:.1%}")
        gap = row['GapPct'] if pd.notna(row['GapPct']) else 0
        day_change = row['DayChange'] if pd.notna(row['DayChange']) else 0
        logger.info(f"  股价反应: 跳空 {gap:.2%}, 全天 {day_change:.2%}")
        logger.info(f"  分类: {row['SurpriseClass']} + {row['ReactionClass']}")
        logger.info(f"  [判断] 预期: {row['ExpectationLevel']}")
        logger.info(f"  [解读] {row['ExpectationComment']}")
        score = row['SignalScore'] if pd.notna(row['SignalScore']) else 0
        logger.info(f"  [得分] 信号: {score:.4f}")
    
    logger.info("\n" + "=" * 80)


# ============================================================
# Main
# ============================================================
def main():
    logger = setup_logger(level=logging.INFO)
    
    # 检查 API Key
    api_key = FINNHUB_API_KEY
    if not api_key:
        logger.error("请设置 Finnhub API Key!")
        logger.error("方式1: 设置环境变量 FINNHUB_API_KEY")
        logger.error("方式2: 修改代码中的 FINNHUB_API_KEY 变量")
        logger.error("获取免费 API Key: https://finnhub.io/register")
        sys.exit(1)
    
    cfg = EngineConfig(
        tickers=TICKERS,
        start_date=START_DATE,
        end_date=END_DATE,
        finnhub_api_key=api_key,
        sleep_sec=SLEEP_SEC,
        price_buffer_days=PRICE_BUFFER_DAYS,
    )
    
    try:
        engine = EarningsExpectationEngine(cfg, logger)
        earnings, reactions, analysis = engine.run()
        
        save_outputs(earnings, reactions, analysis, OUTPUT_DIR, OUTPUT_XLSX, logger)
        
        logger.info("\n分析完成！")
        
    except DataValidationError as e:
        logger.error(f"数据验证错误: {e}")
        sys.exit(2)
    except DataSourceError as e:
        logger.error(f"数据源错误: {e}")
        sys.exit(3)
    except Exception as e:
        logger.exception(f"未知错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
