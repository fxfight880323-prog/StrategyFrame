"""
美股核心个股 CTA 技术分析系统
=============================
利用短期和中期技术指标，对美股大盘股进行强弱分析和走势预期

分析维度：
1. 短期指标 (1-20日): RSI, 价格动量, 突破信号
2. 中期指标 (20-200日): 均线系统, MACD, 趋势强度
3. 综合评分: 多因子加权排名
"""

import sys
import time
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
import akshare as ak


# ============================================================
# CONFIG
# ============================================================
# 美股核心个股 (标普100主要成分股 + 科技龙头)
CORE_TICKERS = [
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

# 分析日期
END_DATE = "2026-02-23"
START_DATE = "2024-01-01"  # 需要足够历史数据计算200日均线

OUTPUT_DIR = "."
OUTPUT_XLSX = "mag7_cta_analysis.xlsx"


# ============================================================
# Logging
# ============================================================
def setup_logger(name: str = "cta_analyzer", level: int = logging.INFO) -> logging.Logger:
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
# Data Source
# ============================================================
class StockDataSource:
    """股票数据源 - 使用 AkShare"""
    
    def __init__(self, logger: logging.Logger, sleep_sec: float = 0.5):
        self.logger = logger
        self.sleep_sec = sleep_sec
    
    def fetch_prices(self, ticker: str, start: date, end: date) -> pd.DataFrame:
        """获取股票历史价格"""
        import random
        max_retries = 3
        for attempt in range(max_retries):
            try:
                time.sleep(self.sleep_sec + random.uniform(0, 0.3))
                df = ak.stock_us_daily(symbol=ticker, adjust="")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                else:
                    return pd.DataFrame()
        
        if df is None or df.empty:
            return pd.DataFrame()
        
        df = df.reset_index()
        df['Date'] = pd.to_datetime(df['Date'] if 'Date' in df.columns else df['date']).dt.date
        df = df[(df['Date'] >= start) & (df['Date'] <= end)].copy()
        
        if df.empty:
            return pd.DataFrame()
        
        # 标准化列名
        df = df.rename(columns={
            'open': 'Open', 'high': 'High', 'low': 'Low', 
            'close': 'Close', 'volume': 'Volume'
        })
        
        df['Ticker'] = ticker.upper()
        return df[['Ticker', 'Date', 'Open', 'High', 'Low', 'Close', 'Volume']].copy()
    
    def fetch_all_prices(self, tickers: List[str], start: date, end: date) -> pd.DataFrame:
        """获取多只股票数据"""
        self.logger.info("=" * 60)
        self.logger.info("获取美股核心个股数据...")
        self.logger.info("=" * 60)
        
        frames = []
        success_count = 0
        for ticker in tickers:
            df = self.fetch_prices(ticker, start, end)
            if not df.empty and len(df) >= 50:  # 至少50个交易日
                frames.append(df)
                success_count += 1
                if success_count % 10 == 0:
                    self.logger.info(f"  已获取 {success_count}/{len(tickers)} 只股票")
            else:
                self.logger.debug(f"  跳过 {ticker}: 数据不足")
        
        if not frames:
            return pd.DataFrame()
        
        result = pd.concat(frames, ignore_index=True)
        self.logger.info(f"成功获取 {success_count} 只股票数据")
        return result.sort_values(['Ticker', 'Date']).reset_index(drop=True)


# ============================================================
# Technical Indicators
# ============================================================
class TechnicalIndicators:
    """技术指标计算"""
    
    @staticmethod
    def calculate_all(df: pd.DataFrame) -> pd.DataFrame:
        """计算所有技术指标"""
        df = df.copy()
        
        # 价格变化
        df['Daily_Return'] = df['Close'].pct_change()
        df['Daily_Return_Pct'] = df['Daily_Return'] * 100
        
        # ========== 短期指标 (1-20日) ==========
        
        # 1. RSI (14日)
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI_14'] = 100 - (100 / (1 + rs))
        
        # 2. 短期动量 (5日, 10日, 20日)
        df['Momentum_5'] = df['Close'].pct_change(periods=5) * 100
        df['Momentum_10'] = df['Close'].pct_change(periods=10) * 100
        df['Momentum_20'] = df['Close'].pct_change(periods=20) * 100
        
        # 3. 波动率 (10日)
        df['Volatility_10'] = df['Daily_Return'].rolling(window=10).std() * np.sqrt(252) * 100
        
        # 4. 成交量趋势 (5日)
        df['Volume_MA5'] = df['Volume'].rolling(window=5).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_MA5']
        
        # ========== 中期指标 (20-200日) ==========
        
        # 1. 移动平均线
        df['MA_20'] = df['Close'].rolling(window=20).mean()
        df['MA_50'] = df['Close'].rolling(window=50).mean()
        df['MA_200'] = df['Close'].rolling(window=200).mean()
        
        # 2. 均线位置 (股价相对均线的百分比)
        df['MA20_Dist'] = (df['Close'] - df['MA_20']) / df['MA_20'] * 100
        df['MA50_Dist'] = (df['Close'] - df['MA_50']) / df['MA_50'] * 100
        df['MA200_Dist'] = (df['Close'] - df['MA_200']) / df['MA_200'] * 100
        
        # 3. 均线排列 (趋势强度)
        df['MA_Trend_Score'] = (
            (df['MA_20'] > df['MA_50']).astype(int) +
            (df['MA_50'] > df['MA_200']).astype(int) +
            (df['Close'] > df['MA_20']).astype(int) +
            (df['Close'] > df['MA_50']).astype(int) +
            (df['Close'] > df['MA_200']).astype(int)
        )
        
        # 4. MACD
        ema_12 = df['Close'].ewm(span=12).mean()
        ema_26 = df['Close'].ewm(span=26).mean()
        df['MACD'] = ema_12 - ema_26
        df['MACD_Signal'] = df['MACD'].ewm(span=9).mean()
        df['MACD_Histogram'] = df['MACD'] - df['MACD_Signal']
        df['MACD_Bullish'] = (df['MACD'] > df['MACD_Signal']).astype(int)
        
        # 5. 布林带 (20日)
        df['BB_Middle'] = df['MA_20']
        bb_std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)
        df['BB_Position'] = (df['Close'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'])
        
        # 6. ATR (14日)
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR_14'] = true_range.rolling(window=14).mean()
        df['ATR_Pct'] = df['ATR_14'] / df['Close'] * 100
        
        return df
    
    @staticmethod
    def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
        """生成交易信号"""
        df = df.copy()
        
        # 短期信号 (0-20分)
        df['RSI_Signal'] = np.where(df['RSI_14'] > 70, -1, 
                           np.where(df['RSI_14'] < 30, 1, 0))
        df['Momentum_Signal'] = np.where(df['Momentum_10'] > 5, 1,
                                np.where(df['Momentum_10'] < -5, -1, 0))
        
        # 中期信号 (0-30分)
        df['Trend_Signal'] = np.where(df['MA_Trend_Score'] >= 4, 1,
                             np.where(df['MA_Trend_Score'] <= 2, -1, 0))
        df['MACD_Signal'] = np.where(df['MACD_Histogram'] > 0, 1, -1)
        
        # 突破信号
        df['Breakout_20D'] = df['Close'] > df['High'].rolling(20).max().shift(1)
        df['Breakdown_20D'] = df['Close'] < df['Low'].rolling(20).min().shift(1)
        
        return df


# ============================================================
# CTA Analysis Engine
# ============================================================
class CTAAnalysisEngine:
    """CTA分析引擎"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def analyze_stock(self, df: pd.DataFrame) -> Dict[str, Any]:
        """分析单只股票"""
        if df.empty or len(df) < 200:
            return {}
        
        latest = df.iloc[-1]
        prev_month = df.iloc[-22] if len(df) >= 22 else df.iloc[0]
        
        # 基础信息
        result = {
            'Ticker': latest['Ticker'],
            'Date': latest['Date'],
            'Price': latest['Close'],
            'Price_MA20': latest['MA_20'],
            'Price_MA50': latest['MA_50'],
            'Price_MA200': latest['MA_200'],
        }
        
        # ========== 短期指标评分 (满分 30) ==========
        short_score = 0
        
        # RSI (10分) - 中性区域较好，极端区域反转信号
        rsi = latest['RSI_14']
        if 40 <= rsi <= 60:
            short_score += 10  # 健康区间
        elif 30 <= rsi < 40 or 60 < rsi <= 70:
            short_score += 5   # 警戒区间
        elif rsi < 30:
            short_score += 7   # 超卖，潜在反弹
        else:
            short_score += 3   # 超买
        result['RSI'] = rsi
        result['RSI_Score'] = short_score
        
        # 短期动量 (10分)
        mom_5 = latest['Momentum_5']
        mom_10 = latest['Momentum_10']
        if mom_5 > 0 and mom_10 > 0:
            short_score += 10
        elif mom_5 > 0 or mom_10 > 0:
            short_score += 5
        elif mom_5 < -5 and mom_10 < -5:
            short_score += 2  # 下跌过快
        else:
            short_score += 3
        result['Momentum_5'] = mom_5
        result['Momentum_10'] = mom_10
        result['Momentum_Score'] = 10 if mom_5 > 0 and mom_10 > 0 else (5 if mom_5 > 0 or mom_10 > 0 else 3)
        
        # 成交量 (10分)
        vol_ratio = latest['Volume_Ratio']
        if vol_ratio > 1.5 and latest['Daily_Return'] > 0:
            short_score += 10  # 放量上涨
        elif vol_ratio > 1.2 and latest['Daily_Return'] > 0:
            short_score += 7   # 温和放量
        elif vol_ratio < 0.8 and latest['Daily_Return'] < 0:
            short_score += 3   # 缩量下跌 (还好)
        else:
            short_score += 5
        result['Volume_Ratio'] = vol_ratio
        result['Volume_Score'] = 10 if vol_ratio > 1.5 and latest['Daily_Return'] > 0 else 5
        
        result['Short_Score'] = short_score
        result['Short_Rating'] = '强' if short_score >= 25 else ('中' if short_score >= 18 else '弱')
        
        # ========== 中期指标评分 (满分 40) ==========
        mid_score = 0
        
        # 均线排列 (15分)
        ma_trend = int(latest['MA_Trend_Score'])
        mid_score += ma_trend * 3  # 每个条件3分
        result['MA_Trend_Score'] = ma_trend
        result['MA_Trend_Score_Points'] = ma_trend * 3
        
        # 均线距离 (10分)
        ma20_dist = latest['MA20_Dist']
        ma50_dist = latest['MA50_Dist']
        if ma20_dist > 0 and ma50_dist > 0:
            mid_score += min(abs(ma20_dist), 10)  # 最多10分
        elif ma20_dist > 0 or ma50_dist > 0:
            mid_score += 5
        else:
            mid_score += max(-10, ma20_dist) + 10  # 负数时减少
        result['MA20_Dist'] = ma20_dist
        result['MA50_Dist'] = ma50_dist
        result['MA_Dist_Score'] = min(abs(ma20_dist), 10) if ma20_dist > 0 and ma50_dist > 0 else 5
        
        # MACD (10分)
        macd_hist = latest['MACD_Histogram']
        macd_bull = latest['MACD_Bullish']
        if macd_bull and macd_hist > 0:
            mid_score += 10
        elif macd_bull:
            mid_score += 7
        elif macd_hist < 0:
            mid_score += 3
        else:
            mid_score += 5
        result['MACD_Histogram'] = macd_hist
        result['MACD_Score'] = 10 if macd_bull and macd_hist > 0 else (7 if macd_bull else 3)
        
        # 波动率调整 (5分)
        volatility = latest['Volatility_10']
        if 15 <= volatility <= 35:
            mid_score += 5  # 正常波动
        elif volatility < 15:
            mid_score += 3  # 低波动
        else:
            mid_score += 2  # 高波动
        result['Volatility_10'] = volatility
        result['Vol_Score'] = 5 if 15 <= volatility <= 35 else 3
        
        result['Mid_Score'] = min(mid_score, 40)
        result['Mid_Rating'] = '强' if mid_score >= 30 else ('中' if mid_score >= 22 else '弱')
        
        # ========== 趋势强度评分 (满分 30) ==========
        trend_score = 0
        
        # 20日新高/新低
        high_20d = df['High'].rolling(20).max().iloc[-1]
        low_20d = df['Low'].rolling(20).min().iloc[-1]
        price_position = (latest['Close'] - low_20d) / (high_20d - low_20d) * 100 if high_20d != low_20d else 50
        
        if price_position > 80:
            trend_score += 30  # 强势
        elif price_position > 60:
            trend_score += 22
        elif price_position > 40:
            trend_score += 15  # 中性
        elif price_position > 20:
            trend_score += 8
        else:
            trend_score += 3   # 弱势
        
        result['Price_Position_20D'] = price_position
        result['Trend_Score'] = trend_score
        result['Trend_Rating'] = '强' if trend_score >= 25 else ('中' if trend_score >= 15 else '弱')
        
        # ========== 综合评分 ==========
        total_score = result['Short_Score'] + result['Mid_Score'] + result['Trend_Score']
        result['Total_Score'] = total_score
        result['Max_Score'] = 100
        result['Score_Pct'] = total_score / 100 * 100
        
        # 评级
        if total_score >= 80:
            rating = '强烈看涨'
            signal = 'BUY'
        elif total_score >= 65:
            rating = '看涨'
            signal = 'BUY'
        elif total_score >= 50:
            rating = '中性偏强'
            signal = 'HOLD'
        elif total_score >= 35:
            rating = '中性偏弱'
            signal = 'HOLD'
        elif total_score >= 20:
            rating = '看跌'
            signal = 'SELL'
        else:
            rating = '强烈看跌'
            signal = 'SELL'
        
        result['Rating'] = rating
        result['Signal'] = signal
        
        # 近期表现
        result['Return_1D'] = latest['Daily_Return_Pct']
        result['Return_5D'] = latest['Momentum_5']
        result['Return_20D'] = latest['Momentum_20']
        
        return result
    
    def rank_stocks(self, prices_df: pd.DataFrame) -> pd.DataFrame:
        """对所有股票进行排名"""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("计算技术指标并排名...")
        self.logger.info("=" * 60)
        
        # 计算技术指标
        calculator = TechnicalIndicators()
        prices_with_indicators = []
        
        tickers = prices_df['Ticker'].unique()
        for ticker in tickers:
            ticker_df = prices_df[prices_df['Ticker'] == ticker].copy()
            if len(ticker_df) >= 200:
                ticker_df = calculator.calculate_all(ticker_df)
                ticker_df = calculator.generate_signals(ticker_df)
                prices_with_indicators.append(ticker_df)
        
        if not prices_with_indicators:
            return pd.DataFrame()
        
        all_data = pd.concat(prices_with_indicators, ignore_index=True)
        
        # 分析每只股票
        results = []
        for ticker in tickers:
            ticker_df = all_data[all_data['Ticker'] == ticker].copy()
            analysis = self.analyze_stock(ticker_df)
            if analysis:
                results.append(analysis)
        
        if not results:
            return pd.DataFrame()
        
        result_df = pd.DataFrame(results)
        result_df = result_df.sort_values('Total_Score', ascending=False).reset_index(drop=True)
        result_df['Rank'] = range(1, len(result_df) + 1)
        
        return result_df


# ============================================================
# Output
# ============================================================
def save_outputs(ranked_df: pd.DataFrame, out_dir: str, xlsx_name: str, logger: logging.Logger):
    """保存分析结果"""
    import os
    os.makedirs(out_dir, exist_ok=True)
    
    xlsx_path = os.path.join(out_dir, xlsx_name)
    
    # 分类
    strong_buy = ranked_df[ranked_df['Signal'] == 'BUY'].head(20)
    sell = ranked_df[ranked_df['Signal'] == 'SELL'].tail(20)
    tech_stocks = ranked_df[ranked_df['Ticker'].isin(['AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'TSLA', 'AMD', 'NFLX', 'CRM'])]
    
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        ranked_df.to_excel(w, sheet_name="All_Rankings", index=False)
        strong_buy.to_excel(w, sheet_name="Strong_Buy", index=False)
        sell.to_excel(w, sheet_name="Sell", index=False)
        tech_stocks.to_excel(w, sheet_name="Tech_Stocks", index=False)
    
    ranked_df.to_csv(os.path.join(out_dir, "cta_rankings.csv"), index=False)
    
    logger.info(f"\n结果已保存: {xlsx_path}")
    
    # 打印摘要
    print_summary(ranked_df, logger)


def print_summary(df: pd.DataFrame, logger: logging.Logger):
    """打印分析摘要"""
    logger.info("\n" + "=" * 80)
    logger.info("CTA 技术分析排名摘要")
    logger.info("=" * 80)
    
    # TOP 10 强势
    logger.info("\n🏆 TOP 10 强势个股 (强烈看涨):")
    logger.info("-" * 80)
    top10 = df.head(10)
    logger.info(f"{'排名':<4} {'代码':<8} {'价格':<10} {'总分':<8} {'短期':<6} {'中期':<6} {'趋势':<6} {'信号':<8}")
    logger.info("-" * 80)
    for _, row in top10.iterrows():
        logger.info(f"{row['Rank']:<4} {row['Ticker']:<8} ${row['Price']:<9.2f} "
                   f"{row['Total_Score']:<7.0f} {row['Short_Rating']:<6} "
                   f"{row['Mid_Rating']:<6} {row['Trend_Rating']:<6} {row['Signal']:<8}")
    
    # 科技巨头
    logger.info("\n🚀 科技巨头排名:")
    logger.info("-" * 80)
    mag7 = df[df['Ticker'].isin(['AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'TSLA'])]
    mag7 = mag7.sort_values('Rank')
    logger.info(f"{'排名':<4} {'代码':<8} {'价格':<10} {'总分':<8} {'RSI':<8} {'20日距':<8} {'评级':<12}")
    logger.info("-" * 80)
    for _, row in mag7.iterrows():
        logger.info(f"{row['Rank']:<4} {row['Ticker']:<8} ${row['Price']:<9.2f} "
                   f"{row['Total_Score']:<7.0f} {row['RSI']:<7.1f} "
                   f"{row['MA20_Dist']:<+7.1f}% {row['Rating']:<12}")
    
    # 弱势个股
    logger.info("\n⚠️ 弱势个股 (建议回避):")
    logger.info("-" * 80)
    bottom10 = df.tail(10)
    for _, row in bottom10.iterrows():
        logger.info(f"{row['Rank']:<4} {row['Ticker']:<8} ${row['Price']:<9.2f} "
                   f"{row['Total_Score']:<7.0f} - {row['Rating']}")
    
    # 统计
    logger.info("\n" + "=" * 80)
    logger.info("统计摘要")
    logger.info("=" * 80)
    buy_count = len(df[df['Signal'] == 'BUY'])
    hold_count = len(df[df['Signal'] == 'HOLD'])
    sell_count = len(df[df['Signal'] == 'SELL'])
    
    logger.info(f"看涨 (BUY): {buy_count} 只 ({buy_count/len(df)*100:.1f}%)")
    logger.info(f"中性 (HOLD): {hold_count} 只 ({hold_count/len(df)*100:.1f}%)")
    logger.info(f"看跌 (SELL): {sell_count} 只 ({sell_count/len(df)*100:.1f}%)")
    logger.info(f"平均得分: {df['Total_Score'].mean():.1f}")
    logger.info(f"中位数得分: {df['Total_Score'].median():.1f}")
    logger.info("=" * 80)


# ============================================================
# Main
# ============================================================
def main():
    logger = setup_logger(level=logging.INFO)
    
    logger.info("=" * 60)
    logger.info("美股核心个股 CTA 技术分析系统")
    logger.info(f"分析日期: {END_DATE}")
    logger.info("=" * 60)
    
    try:
        # 1. 获取数据
        ds = StockDataSource(logger)
        start = pd.to_datetime(START_DATE).date()
        end = pd.to_datetime(END_DATE).date()
        
        prices_df = ds.fetch_all_prices(CORE_TICKERS, start, end)
        if prices_df.empty:
            logger.error("未能获取价格数据")
            sys.exit(1)
        
        # 2. CTA分析
        engine = CTAAnalysisEngine(logger)
        ranked_df = engine.rank_stocks(prices_df)
        
        if ranked_df.empty:
            logger.error("分析失败")
            sys.exit(1)
        
        # 3. 保存结果
        save_outputs(ranked_df, OUTPUT_DIR, OUTPUT_XLSX, logger)
        
        logger.info("\n分析完成！")
        
    except Exception as e:
        logger.exception(f"分析失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
