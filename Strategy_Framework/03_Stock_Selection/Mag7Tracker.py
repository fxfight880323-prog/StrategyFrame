import sys
import time
import math
import logging
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yfinance as yf
from pandas.tseries.holiday import USFederalHolidayCalendar
from pandas.tseries.offsets import CustomBusinessDay


# ============================================================
# USER CONFIG
# ============================================================
TICKERS = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA"]
START_DATE = "2025-01-01"
END_DATE = date.today().strftime("%Y-%m-%d")

OUTPUT_DIR = "."
OUTPUT_XLSX = "mag7_signal_pack_yfinance.xlsx"

# 估值字段优先顺序：先 forwardPE，拿不到就 trailingPE
PE_FIELDS = ["forwardPE", "trailingPE"]

# yfinance 限流时可加大一点
SLEEP_SEC = 6.0

# 价格日期缓冲，方便拿到 PrevClose（周末/假期）
PRICE_BUFFER_DAYS = 10


# ============================================================
# Logging
# ============================================================
def setup_logger(name: str = "yfinance_engine", level: int = logging.INFO) -> logging.Logger:
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
    sleep_sec: float = 0.25
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
# Data Source: yfinance
# ============================================================
class YahooDataSource:
    def __init__(self, logger: logging.Logger, sleep_sec: float = 0.25):
        self.logger = logger
        self.sleep_sec = sleep_sec

    def fetch_prices_daily(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Add jitter to avoid synchronized requests
                time.sleep(self.sleep_sec + random.uniform(0, 2))
                df = yf.download(
                    tickers=ticker,
                    start=ymd(start),
                    end=ymd(end + timedelta(days=1)),
                    interval="1d",
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 5 + random.uniform(0, 3)
                    self.logger.warning(f"Download failed for {ticker}, retrying in {wait_time:.1f}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    raise DataSourceError(f"Price download failed for {ticker}: {e}")

        if df is None or df.empty:
            return pd.DataFrame(columns=["Ticker", "Date", "Open", "High", "Low", "Close"])

        df = df.reset_index()
        if "Date" not in df.columns and "Datetime" in df.columns:
            df = df.rename(columns={"Datetime": "Date"})

        out = pd.DataFrame({
            "Ticker": ticker.upper(),
            "Date": pd.to_datetime(df["Date"]).dt.date,
            "Open": df.get("Open"),
            "High": df.get("High"),
            "Low": df.get("Low"),
            "Close": df.get("Close"),
        })
        out = out.dropna(subset=["Close"]).copy()
        return out

    def fetch_earnings_events(self, ticker: str) -> pd.DataFrame:
        """
        尝试用 yfinance 的 earnings_dates（若可用）：
        返回 ReportDate + EPS Actual/Estimate + SurprisePct(若能算出来)
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                time.sleep(self.sleep_sec + random.uniform(0, 2))
                t = yf.Ticker(ticker)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 5 + random.uniform(0, 3)
                    self.logger.warning(f"Ticker init failed for {ticker}, retrying... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    return pd.DataFrame(columns=["Ticker", "ReportDate", "EPS_Actual", "EPS_Estimate", "SurprisePct"])

        try:
            ed = getattr(t, "earnings_dates", None)
            if ed is None:
                return pd.DataFrame(columns=["Ticker", "ReportDate", "EPS_Actual", "EPS_Estimate", "SurprisePct"])
            df = ed.copy()
        except Exception:
            return pd.DataFrame(columns=["Ticker", "ReportDate", "EPS_Actual", "EPS_Estimate", "SurprisePct"])

        if df is None or df.empty:
            return pd.DataFrame(columns=["Ticker", "ReportDate", "EPS_Actual", "EPS_Estimate", "SurprisePct"])

        df = df.reset_index().rename(columns={"index": "EarningsDate"})
        df["ReportDate"] = pd.to_datetime(df["EarningsDate"]).dt.date

        col_map = {c.lower(): c for c in df.columns}

        def pick(*names: str) -> Optional[str]:
            for n in names:
                c = col_map.get(n.lower())
                if c is not None:
                    return c
            return None

        c_est = pick("EPS Estimate", "Eps Estimate", "epsEstimate")
        c_act = pick("Reported EPS", "reportedEPS", "EPS Actual", "Eps Actual")
        c_sur = pick("Surprise(%)", "surprise(%)", "surprisePercent", "Surprise (%)")

        eps_est = pd.to_numeric(df[c_est], errors="coerce") if c_est else pd.Series([pd.NA] * len(df))
        eps_act = pd.to_numeric(df[c_act], errors="coerce") if c_act else pd.Series([pd.NA] * len(df))

        if c_sur:
            s = pd.to_numeric(df[c_sur], errors="coerce")
            # 若是 12.3(%) 这种，转成 0.123
            s = s.apply(lambda x: x / 100.0 if pd.notna(x) and abs(x) > 1 else x)
        else:
            if c_est and c_act:
                # (actual - estimate) / estimate
                s = (eps_act - eps_est) / eps_est
            else:
                s = pd.Series([pd.NA] * len(df))

        out = pd.DataFrame({
            "Ticker": ticker.upper(),
            "ReportDate": df["ReportDate"],
            "EPS_Actual": eps_act,
            "EPS_Estimate": eps_est,
            "SurprisePct": s,
        })
        out = out.dropna(subset=["ReportDate"]).copy()
        return out

    def fetch_valuation_snapshot(self, ticker: str, pe_fields: List[str]) -> Dict[str, Any]:
        """
        从 yfinance Ticker.info 抓估值字段（可能缺失）。
        """
        max_retries = 3
        info = {}
        for attempt in range(max_retries):
            try:
                time.sleep(self.sleep_sec + random.uniform(0, 2))
                t = yf.Ticker(ticker)
                info = t.info or {}
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = (2 ** attempt) * 5 + random.uniform(0, 3)
                    self.logger.warning(f"Valuation fetch failed for {ticker}, retrying... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                else:
                    self.logger.warning(f"Failed to get valuation for {ticker} after {max_retries} attempts")

        val = None
        used = None
        for f in pe_fields:
            v = safe_float(info.get(f))
            if v is not None:
                val = v
                used = f
                break

        return {
            "Ticker": ticker.upper(),
            "ValDate": date.today(),
            "ValMetric": val,
            "ValMetricField": used,
        }


# ============================================================
# Engine
# ============================================================
class EarningsSignalEngine:
    def __init__(self, cfg: EngineConfig, logger: logging.Logger):
        self.cfg = cfg
        self.logger = logger
        self.ds = YahooDataSource(logger, sleep_sec=cfg.sleep_sec)

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
        self.logger.info("Building PricesRaw (yfinance)...")

        start = to_date(self.cfg.start_date) - timedelta(days=self.cfg.price_buffer_days)
        end = to_date(self.cfg.end_date) + timedelta(days=self.cfg.price_buffer_days)

        frames = []
        for t in self.cfg.tickers:
            df = self.ds.fetch_prices_daily(t, start, end)
            if df.empty:
                self.logger.warning(f"No price rows for {t}")
                continue
            frames.append(df)

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
        self.logger.info("Building EarningsRaw (yfinance)...")

        price_map = prices_raw.set_index("Key")[["GapPct", "IntradayPct", "ReactionScore"]]

        frames = []
        for t in self.cfg.tickers:
            df = self.ds.fetch_earnings_events(t)
            if df.empty:
                self.logger.warning(f"No earnings events for {t} (will still rank by price reactions if any later).")
                continue
            frames.append(df)

        if not frames:
            raise DataValidationError(
                "No earnings events returned by yfinance for any tickers. "
                "你可以：1) 放宽时间范围；2) 或改用其它 earnings 数据源。"
            )

        earn = pd.concat(frames, ignore_index=True)

        # 过滤时间范围
        sd, ed = to_date(self.cfg.start_date), to_date(self.cfg.end_date)
        earn = earn[(earn["ReportDate"] >= sd) & (earn["ReportDate"] <= ed)].copy()

        # ReactionDate：默认盘后 -> 次日（若你后续能拿到盘前/盘后时间，我可以改成分流）
        earn["ReactionDate"] = earn["ReportDate"].apply(next_us_business_day)
        earn["ReactionKey"] = earn.apply(lambda r: make_key(r["Ticker"], r["ReactionDate"]), axis=1)

        pulled = price_map.reindex(earn["ReactionKey"]).reset_index(drop=True)
        earn["GapPct"] = pulled["GapPct"].values
        earn["IntradayPct"] = pulled["IntradayPct"].values
        earn["ReactionScore"] = pulled["ReactionScore"].values

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
        self.logger.info("Building ValuationRaw (yfinance)...")

        rows = []
        for t in self.cfg.tickers:
            rows.append(self.ds.fetch_valuation_snapshot(t, PE_FIELDS))

        val = pd.DataFrame(rows)
        self.logger.info(f"ValuationRaw rows: {len(val)}")
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

    prices_csv = os.path.join(out_dir, "prices_raw_yfinance.csv")
    earnings_csv = os.path.join(out_dir, "earnings_raw_yfinance.csv")
    valuation_csv = os.path.join(out_dir, "valuation_raw_yfinance.csv")
    signals_csv = os.path.join(out_dir, "mag7_signals_yfinance.csv")
    xlsx_path = os.path.join(out_dir, xlsx_name)

    prices.to_csv(prices_csv, index=False)
    earnings.to_csv(earnings_csv, index=False)
    valuation.to_csv(valuation_csv, index=False)
    signals.to_csv(signals_csv, index=False)

    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        prices.to_excel(w, "PricesRaw", index=False)
        earnings.to_excel(w, "EarningsRaw", index=False)
        valuation.to_excel(w, "ValuationRaw", index=False)
        signals.to_excel(w, "MAG7_Signals", index=False)

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