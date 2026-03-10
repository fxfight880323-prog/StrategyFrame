import sys
import time
import math
import logging
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import akshare as ak
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay


# ============================================================
# USER CONFIG
# ============================================================
TICKERS = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA"]
START_DATE = "2025-01-01"
END_DATE = date.today().strftime("%Y-%m-%d")

OUTPUT_DIR = "."
OUTPUT_XLSX = "mag7_signal_pack_akshare.xlsx"

# 估值字段优先顺序：先 forwardPE，拿不到就 trailingPE
PE_FIELDS = ["forwardPE", "trailingPE"]

# 请求间隔（AkShare 对请求频率较宽松，但建议保持一定间隔）
SLEEP_SEC = 1.0

# 价格日期缓冲，方便拿到 PrevClose（周末/假期）
PRICE_BUFFER_DAYS = 10


# ============================================================
# Logging
# ============================================================
def setup_logger(name: str = "akshare_engine", level: int = logging.INFO) -> logging.Logger:
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

    # reaction score weights
    w_gap: float = 0.6
    w_intraday: float = 0.4

    # win-rate strong reaction threshold
    strong_reaction_th: float = 0.03

    # signal weights (robust)
    w_avg4: float = 0.45
    w_trend: float = 0.25
    w_surprise: float = 0.15
    w_winrate: float = 0.15

    # valuation sensitivity
    pe_high_pct: float = 0.7
    pe_low_pct: float = 0.3
    pe_high_penalty: float = -0.02
    pe_low_bonus: float = 0.01
    extra_penalty_gap_mult: float = 0.20

    # signal thresholds
    bullish_th: float = 0.05
    watch_th: float = 0.02
    bearish_th: float = -0.02

    # pacing
    sleep_sec: float = 1.0
    price_buffer_days: int = 10


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


def to_date(s: str) -> date:
    return pd.to_datetime(s).date()


def ymd(d: date) -> str:
    return d.strftime("%Y-%m-%d")


def make_key(ticker: str, d: date) -> str:
    return f"{ticker.upper()}|{ymd(d)}"


def next_us_business_day(d: date) -> date:
    """
    近似：US Federal holidays（不完全等价 NYSE 交易日）。
    如果你要 NYSE 精确交易日，我可以再给你 pandas_market_calendars 版本。
    """
    cbd = CustomBusinessDay(calendar=USFederalHolidayCalendar())
    return (pd.Timestamp(d) + 1 * cbd).date()


# ============================================================
# Data Source: AkShare
# ============================================================
class AkShareDataSource:
    def __init__(self, logger: logging.Logger, sleep_sec: float = 1.0):
        self.logger = logger
        self.sleep_sec = sleep_sec

    def fetch_prices_daily(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """
        使用 AkShare 的 stock_us_daily 获取美股历史数据
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # AkShare 获取美股数据
                time.sleep(self.sleep_sec + random.uniform(0, 0.5))
                df = ak.stock_us_daily(symbol=ticker, adjust="")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 3 + random.uniform(0, 2)
                    self.logger.warning(f"Download failed for {ticker}, retrying in {wait_time:.1f}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise DataSourceError(f"Price download failed for {ticker}: {e}")

        if df is None or df.empty:
            return pd.DataFrame(columns=["Ticker", "Date", "Open", "High", "Low", "Close"])

        # 重命名列名以匹配原有格式
        df = df.reset_index()
        if 'date' in df.columns:
            df = df.rename(columns={'date': 'Date'})
        
        # 转换日期格式
        df['Date'] = pd.to_datetime(df['Date']).dt.date
        
        # 过滤日期范围
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
        out = out.dropna(subset=["Close"]).copy()
        return out

    def fetch_earnings_events(self, ticker: str) -> pd.DataFrame:
        """
        AkShare 没有直接提供美股财报数据接口。
        这里返回空 DataFrame，需要通过其他方式获取财报数据。
        建议：使用已有的 Excel 文件中的财报数据，或接入 Finnhub API。
        """
        self.logger.warning(f"AkShare does not provide earnings data for US stocks. Skipping {ticker} earnings.")
        return pd.DataFrame(columns=["Ticker", "ReportDate", "EPS_Actual", "EPS_Estimate", "SurprisePct"])

    def fetch_valuation_snapshot(self, ticker: str, pe_fields: List[str]) -> Dict[str, Any]:
        """
        AkShare 没有直接提供美股估值数据接口。
        返回空值，需要通过其他方式获取估值数据。
        """
        return {
            "Ticker": ticker.upper(),
            "ValDate": date.today(),
            "ValMetric": None,
            "ValMetricField": None,
        }


# ============================================================
# Engine
# ============================================================
class EarningsSignalEngine:
    def __init__(self, cfg: EngineConfig, logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger
        self.ds = AkShareDataSource(logger, sleep_sec=cfg.sleep_sec)

    def run(self) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        self._validate()

        prices = self.build_prices_raw()
        earnings = self.build_earnings_raw(prices)
        valuation = self.build_valuation_raw()
        signals = self.make_signals(earnings, valuation)

        return prices, earnings, valuation, signals

    def _validate(self) -> None:
        if not self.cfg.tickers:
            raise DataValidationError("tickers 不能为空")
        to_date(self.cfg.start_date)
        to_date(self.cfg.end_date)

    # ---------- PricesRaw ----------
    def build_prices_raw(self) -> pd.DataFrame:
        self.logger.info("Building PricesRaw (AkShare)...")

        start = to_date(self.cfg.start_date) - timedelta(days=self.cfg.price_buffer_days)
        end = to_date(self.cfg.end_date) + timedelta(days=self.cfg.price_buffer_days)

        frames = []
        for t in self.cfg.tickers:
            try:
                df = self.ds.fetch_prices_daily(t, start, end)
                if df.empty:
                    self.logger.warning(f"No price rows for {t}")
                    continue
                frames.append(df)
            except Exception as e:
                self.logger.error(f"Failed to fetch prices for {t}: {e}")
                continue

        if not frames:
            raise DataValidationError("No price data returned for any tickers.")

        prices = pd.concat(frames, ignore_index=True).sort_values(["Ticker", "Date"]).reset_index(drop=True)

        # PrevClose per ticker
        prices["PrevClose"] = prices.groupby("Ticker")["Close"].shift(1)
        prices = prices.dropna(subset=["PrevClose", "Open", "Close"]).copy()

        prices["Key"] = prices.apply(lambda r: make_key(r["Ticker"], r["Date"]), axis=1)
        prices["GapPct"] = (prices["Open"] - prices["PrevClose"]) / prices["PrevClose"]
        prices["IntradayPct"] = (prices["Close"] - prices["Open"]) / prices["Open"]
        prices["ReactionScore"] = prices["GapPct"].abs() * self.cfg.w_gap + prices["IntradayPct"].abs() * self.cfg.w_intraday

        cols = ["Key", "Ticker", "Date", "Open", "High", "Low", "Close", "PrevClose",
                "GapPct", "IntradayPct", "ReactionScore"]
        self.logger.info(f"PricesRaw rows: {len(prices)}")
        return prices[cols]

    # ---------- EarningsRaw ----------
    def build_earnings_raw(self, prices_raw: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Building EarningsRaw...")
        
        # AkShare 不提供美股财报数据，这里从价格数据中计算模拟的反应分数
        # 实际应用中，建议从 Finnhub 或其他数据源获取真实财报数据
        
        price_map = prices_raw.set_index("Key")[["GapPct", "IntradayPct", "ReactionScore"]]
        
        # 创建一个简单的 earnings DataFrame，使用价格数据中的大幅波动作为"财报日"
        # 这是一种简化处理，实际应该使用真实的财报数据
        frames = []
        for ticker in self.cfg.tickers:
            ticker_prices = prices_raw[prices_raw["Ticker"] == ticker].copy()
            if ticker_prices.empty:
                continue
            
            # 取反应分数最大的几天作为"财报日"（简化处理）
            ticker_prices = ticker_prices.sort_values("ReactionScore", ascending=False).head(4)
            
            for _, row in ticker_prices.iterrows():
                frames.append({
                    "Ticker": ticker,
                    "ReportDate": row["Date"],
                    "EPS_Actual": None,
                    "EPS_Estimate": None,
                    "SurprisePct": None,
                    "ReactionDate": next_us_business_day(row["Date"]),
                    "ReactionKey": make_key(ticker, next_us_business_day(row["Date"])),
                    "GapPct": row["GapPct"],
                    "IntradayPct": row["IntradayPct"],
                    "ReactionScore": row["ReactionScore"],
                })
        
        if not frames:
            raise DataValidationError(
                "No earnings events available. "
                "AkShare does not provide US stock earnings data. "
                "Please use Finnhub or other data sources for earnings data."
            )
        
        earn = pd.DataFrame(frames)
        
        # 过滤时间范围
        sd, ed = to_date(self.cfg.start_date), to_date(self.cfg.end_date)
        earn = earn[(earn["ReportDate"] >= sd) & (earn["ReportDate"] <= ed)].copy()
        
        # 丢掉没有对齐到价格的事件
        earn = earn.dropna(subset=["ReactionScore"]).copy()
        
        # RankRecent：1=最新
        earn = earn.sort_values(["Ticker", "ReactionDate"], ascending=[True, False]).copy()
        earn["RankRecent"] = earn.groupby("Ticker").cumcount() + 1
        
        earn["Key"] = earn.apply(lambda r: make_key(r["Ticker"], r["ReportDate"]), axis=1)
        
        cols = ["Key", "Ticker", "ReportDate",
                "EPS_Actual", "EPS_Estimate", "SurprisePct",
                "ReactionDate", "ReactionKey",
                "GapPct", "IntradayPct", "ReactionScore",
                "RankRecent"]
        self.logger.info(f"EarningsRaw rows: {len(earn)}")
        return earn[cols]

    # ---------- ValuationRaw ----------
    def build_valuation_raw(self) -> pd.DataFrame:
        self.logger.info("Building ValuationRaw...")
        
        # AkShare 不提供美股估值数据，返回空值
        rows = []
        for t in self.cfg.tickers:
            rows.append(self.ds.fetch_valuation_snapshot(t, PE_FIELDS))
        
        val = pd.DataFrame(rows)
        self.logger.info(f"ValuationRaw rows: {len(val)} (Note: AkShare does not provide US stock valuation data)")
        return val

    # ---------- Signals ----------
    def make_signals(self, earnings_raw: pd.DataFrame, valuation_raw: pd.DataFrame) -> pd.DataFrame:
        self.logger.info("Building MAG7 Signals...")

        latest = (earnings_raw.sort_values(["Ticker", "ReactionDate"], ascending=[True, False])
                             .groupby("Ticker", as_index=False)
                             .head(1)
                             .copy())

        avg4 = (earnings_raw[earnings_raw["RankRecent"] <= 4]
                .groupby("Ticker")["ReactionScore"].mean().rename("AvgScore_4"))
        avg2 = (earnings_raw[earnings_raw["RankRecent"] <= 2]
                .groupby("Ticker")["ReactionScore"].mean().rename("AvgScore_2"))
        avg34 = (earnings_raw[(earnings_raw["RankRecent"] >= 3) & (earnings_raw["RankRecent"] <= 4)]
                 .groupby("Ticker")["ReactionScore"].mean().rename("AvgScore_34"))

        last8 = earnings_raw[earnings_raw["RankRecent"] <= 8].copy()
        denom = last8.groupby("Ticker")["ReactionScore"].apply(lambda s: (s > 0).sum()).rename("N8")
        numer = last8.groupby("Ticker")["ReactionScore"].apply(lambda s: (s >= self.cfg.strong_reaction_th).sum()).rename("N8Strong")
        winrate = (numer / denom.replace(0, pd.NA)).rename("WinRate_8")

        sig = (latest.merge(avg4, on="Ticker", how="left")
                     .merge(avg2, on="Ticker", how="left")
                     .merge(avg34, on="Ticker", how="left")
                     .merge(winrate, on="Ticker", how="left")
                     .merge(valuation_raw[["Ticker", "ValMetric"]], on="Ticker", how="left"))

        sig["Trend_2v34"] = sig["AvgScore_2"] - sig["AvgScore_34"]

        # base score（SurprisePct 缺失则当 0）
        sig["SignalScore"] = (
            self.cfg.w_avg4 * sig["AvgScore_4"].fillna(0.0)
            + self.cfg.w_trend * sig["Trend_2v34"].fillna(0.0)
            + self.cfg.w_surprise * sig["SurprisePct"].fillna(0.0).abs()
            + self.cfg.w_winrate * sig["WinRate_8"].fillna(0.0)
        )

        # risk brake：Surprise 与 Gap 方向相反 -> -0.02
        def risk_brake(row) -> float:
            sp, gp = row.get("SurprisePct"), row.get("GapPct")
            if pd.isna(sp) or pd.isna(gp):
                return 0.0
            if sp > 0 and gp < 0:
                return -0.02
            if sp < 0 and gp > 0:
                return -0.02
            return 0.0

        sig["RiskBrake"] = sig.apply(risk_brake, axis=1)

        # valuation sensitivity：横截面分位阈值
        pe_series = sig["ValMetric"].dropna()
        pe_high = pe_series.quantile(self.cfg.pe_high_pct) if len(pe_series) else None
        pe_low = pe_series.quantile(self.cfg.pe_low_pct) if len(pe_series) else None

        def val_penalty(row) -> float:
            pe = row.get("ValMetric")
            if pe is None or pd.isna(pe) or pe_high is None or pe_low is None:
                return 0.0
            if pe >= pe_high:
                extra = -self.cfg.extra_penalty_gap_mult * abs(float(row.get("GapPct") or 0.0))
                return self.cfg.pe_high_penalty + extra
            if pe <= pe_low:
                return self.cfg.pe_low_bonus
            return 0.0

        sig["ValPenalty"] = sig.apply(val_penalty, axis=1)
        sig["FinalScore"] = sig["SignalScore"] + sig["RiskBrake"] + sig["ValPenalty"]

        sig["Rank"] = sig["FinalScore"].rank(ascending=False, method="min").astype(int)

        def label(v: float) -> str:
            if v >= self.cfg.bullish_th:
                return "BULLISH"
            if v >= self.cfg.watch_th:
                return "WATCH"
            if v > self.cfg.bearish_th:
                return "NEUTRAL"
            return "BEARISH"

        sig["Signal"] = sig["FinalScore"].apply(label)

        def action(row) -> str:
            s = row["Signal"]
            gp = row.get("GapPct")
            if pd.isna(gp):
                return "No Trade"
            if s == "BULLISH":
                return "Follow-through Long" if gp > 0 else "Mean-revert Setup"
            if s == "BEARISH":
                return "Follow-through Short" if gp < 0 else "Fade Risk"
            return "No Trade"

        sig["Action"] = sig.apply(action, axis=1)

        out_cols = [
            "Ticker",
            "ReactionDate", "ReactionKey",
            "ReactionScore", "GapPct", "IntradayPct",
            "SurprisePct",
            "AvgScore_4", "AvgScore_2", "AvgScore_34",
            "Trend_2v34", "WinRate_8",
            "ValMetric", "ValPenalty",
            "RiskBrake",
            "SignalScore", "FinalScore",
            "Rank", "Signal", "Action",
        ]

        sig = sig.set_index("Ticker").reindex([t.upper() for t in self.cfg.tickers]).reset_index()
        self.logger.info("Signals built.")
        return sig[out_cols]


# ============================================================
# Output
# ============================================================
def save_outputs(prices: pd.DataFrame, earnings: pd.DataFrame, valuation: pd.DataFrame, signals: pd.DataFrame,
                 out_dir: str, xlsx_name: str, logger: logging.Logger) -> None:
    import os
    os.makedirs(out_dir, exist_ok=True)

    prices_csv = os.path.join(out_dir, "prices_raw_akshare.csv")
    earnings_csv = os.path.join(out_dir, "earnings_raw_akshare.csv")
    valuation_csv = os.path.join(out_dir, "valuation_raw_akshare.csv")
    signals_csv = os.path.join(out_dir, "mag7_signals_akshare.csv")
    xlsx_path = os.path.join(out_dir, xlsx_name)

    prices.to_csv(prices_csv, index=False)
    earnings.to_csv(earnings_csv, index=False)
    valuation.to_csv(valuation_csv, index=False)
    signals.to_csv(signals_csv, index=False)

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        prices.to_excel(w, sheet_name="PricesRaw", index=False)
        earnings.to_excel(w, sheet_name="EarningsRaw", index=False)
        valuation.to_excel(w, sheet_name="ValuationRaw", index=False)
        signals.to_excel(w, sheet_name="MAG7_Signals", index=False)

    logger.info(f"Saved: {prices_csv}")
    logger.info(f"Saved: {earnings_csv}")
    logger.info(f"Saved: {valuation_csv}")
    logger.info(f"Saved: {signals_csv}")
    logger.info(f"Saved: {xlsx_path}")


# ============================================================
# Main
# ============================================================
def main():
    logger = setup_logger(level=logging.INFO)
    
    logger.info("=" * 60)
    logger.info("MAG7 Tracker - AkShare Version")
    logger.info("Note: AkShare provides price data only.")
    logger.info("Earnings and valuation data require additional data sources.")
    logger.info("=" * 60)

    cfg = EngineConfig(
        tickers=TICKERS,
        start_date=START_DATE,
        end_date=END_DATE,
        sleep_sec=SLEEP_SEC,
        price_buffer_days=PRICE_BUFFER_DAYS,
    )

    try:
        engine = EarningsSignalEngine(cfg, logger)
        prices, earnings, valuation, signals = engine.run()

        logger.info("=== MAG7 Signals (sorted by Rank) ===")
        logger.info("\n" + signals.sort_values("Rank").to_string(index=False))

        save_outputs(prices, earnings, valuation, signals, OUTPUT_DIR, OUTPUT_XLSX, logger)

    except DataValidationError as e:
        logger.error(f"Config/Data error: {e}")
        sys.exit(2)
    except DataSourceError as e:
        logger.error(f"Data source error: {e}")
        sys.exit(3)
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
