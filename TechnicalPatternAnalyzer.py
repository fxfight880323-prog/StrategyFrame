"""
技术形态分析策略
================

基于路演PPT中的价格行为分析框架:
- Price Action Analysis: 好新闻坏反应 / 坏新闻好反应
- 趋势转换判断 (牛熊转换信号)
- 支撑/阻力位分析
- 经典技术形态识别 (头肩、双顶/底、三角形等)
- 背离检测 (价格与指标的背离)

适用标的: 美股101只核心股票
数据源: YFinance / AKShare / Tradier
"""

import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from enum import Enum
import logging

import yfinance as yf


# ============================================================
# 配置
# ============================================================
DEFAULT_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'AVGO', 'AMD', 'INTC',
    'NFLX', 'CRM', 'ADBE', 'ORCL', 'IBM', 'QCOM', 'TXN', 'AMAT', 'MU', 'LRCX',
    'PYPL', 'UBER', 'ABNB', 'SNOW', 'ZM', 'SHOP', 'SQ', 'ROKU', 'TWLO', 'DDOG',
    'MDB', 'CRWD', 'NET', 'FSLY', 'OKTA', 'PLTR', 'ASAN', 'MONDAY', 'SMAR', 'WORK',
    'SPY', 'QQQ', 'IWM', 'VTI', 'VOO', 'VUG', 'VTV', 'VYM', 'SCHD', 'DGRO',
    'JPM', 'BAC', 'WFC', 'GS', 'MS', 'C', 'USB', 'PNC', 'TFC', 'COF',
    'XOM', 'CVX', 'COP', 'EOG', 'SLB', 'OXY', 'MPC', 'VLO', 'PSX', 'KMI',
    'JNJ', 'PFE', 'UNH', 'ABBV', 'MRK', 'LLY', 'TMO', 'ABT', 'DHR', 'BMY',
    'HD', 'LOW', 'TGT', 'COST', 'WMT', 'NKE', 'MCD', 'SBUX', 'TJX', 'ROST',
    'DIS', 'NKE', 'VZ', 'T', 'CMCSA', 'CHTR', 'TMUS', 'NFLX', 'SPOT', 'LYV',
    'BA', 'LMT', 'RTX', 'NOC', 'GD', 'GE', 'HON', 'CAT', 'DE', 'MMM'
]


# ============================================================
# 日志设置
# ============================================================
def setup_logger(name: str = "pattern_analyzer") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# 枚举定义
# ============================================================
class PatternType(Enum):
    """技术形态类型"""
    # 反转形态
    HEAD_SHOULDERS_TOP = "头肩顶"
    HEAD_SHOULDERS_BOTTOM = "头肩底"
    DOUBLE_TOP = "双顶"
    DOUBLE_BOTTOM = "双底"
    TRIPLE_TOP = "三重顶"
    TRIPLE_BOTTOM = "三重底"
    
    # 持续形态
    ASCENDING_TRIANGLE = "上升三角形"
    DESCENDING_TRIANGLE = "下降三角形"
    SYMMETRIC_TRIANGLE = "对称三角形"
    FLAG_BULL = "牛市旗形"
    FLAG_BEAR = "熊市旗形"
    
    # 特殊形态
    CUP_HANDLE = "杯柄形态"
    ROUNDING_BOTTOM = "圆弧底"
    WEDGE_RISING = "上升楔形"
    WEDGE_FALLING = "下降楔形"
    
    UNKNOWN = "未知形态"


class TrendDirection(Enum):
    """趋势方向"""
    STRONG_UP = "强势上涨"
    UP = "上涨趋势"
    SIDEWAYS = "横盘整理"
    DOWN = "下跌趋势"
    STRONG_DOWN = "强势下跌"


class PriceActionSignal(Enum):
    """价格行为信号"""
    GOOD_NEWS_BAD_REACTION = "好新闻坏反应"  # 顶部信号
    BAD_NEWS_GOOD_REACTION = "坏新闻好反应"  # 底部信号
    BREAKOUT_STRONG = "强势突破"
    BREAKDOWN_STRONG = "强势跌破"
    FALSE_BREAKOUT = "假突破"
    ACCUMULATION = "吸筹阶段"
    DISTRIBUTION = "派发阶段"
    NO_SIGNAL = "无明确信号"


class SignalStrength(Enum):
    """信号强度"""
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    WEAK_BUY = "偏买入"
    NEUTRAL = "中性"
    WEAK_SELL = "偏卖出"
    SELL = "卖出"
    STRONG_SELL = "强烈卖出"


# ============================================================
# 数据模型
# ============================================================
@dataclass
class PatternSignal:
    """技术形态信号"""
    symbol: str
    date: date
    pattern: PatternType
    direction: TrendDirection
    price_action: PriceActionSignal
    signal_strength: SignalStrength
    entry_price: float
    target_price: float
    stop_loss: float
    confidence: float  # 0-1
    description: str
    
    # 支撑阻力位
    support_levels: List[float] = None
    resistance_levels: List[float] = None
    
    # 关键指标
    volume_ratio: float = 1.0
    rsi: float = 50.0
    macd_signal: str = "neutral"


@dataclass
class SupportResistance:
    """支撑阻力位"""
    level: float
    type: str  # 'support' or 'resistance'
    strength: int  # 触碰次数
    last_touch: date
    distance_pct: float  # 距当前价格百分比


# ============================================================
# 技术形态分析器
# ============================================================
class TechnicalPatternAnalyzer:
    """
    技术形态分析器
    
    基于PPT中的价格行为分析框架
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or setup_logger()
        self.cache = {}
    
    def get_stock_data(self, symbol: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
        """获取股票数据"""
        cache_key = f"{symbol}_{period}_{interval}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)
            if not df.empty:
                df = df.reset_index()
                if 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date'])
                elif 'Datetime' in df.columns:
                    df['Date'] = pd.to_datetime(df['Datetime'])
                self.cache[cache_key] = df
            return df
        except Exception as e:
            self.logger.error(f"获取 {symbol} 数据失败: {e}")
            return pd.DataFrame()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()
        
        # 价格变动
        df['Returns'] = df['Close'].pct_change()
        df['Log_Returns'] = np.log(df['Close'] / df['Close'].shift(1))
        
        # 移动平均线
        for period in [5, 10, 20, 50, 200]:
            df[f'MA_{period}'] = df['Close'].rolling(window=period).mean()
        
        # EMA
        df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # MACD
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
        
        # 布林带
        df['BB_Middle'] = df['Close'].rolling(window=20).mean()
        bb_std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)
        df['BB_Width'] = (df['BB_Upper'] - df['BB_Lower']) / df['BB_Middle']
        df['BB_Position'] = (df['Close'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'])
        
        # ATR (真实波幅)
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(14).mean()
        
        # 成交量指标
        df['Volume_MA'] = df['Volume'].rolling(20).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_MA']
        
        # 波动率
        df['Volatility'] = df['Returns'].rolling(20).std() * np.sqrt(252)
        
        return df
    
    def detect_support_resistance(self, df: pd.DataFrame, window: int = 10, 
                                   min_touches: int = 2) -> Tuple[List[SupportResistance], List[SupportResistance]]:
        """
        检测支撑阻力位
        
        使用局部极值点检测
        """
        if len(df) < window * 3:
            return [], []
        
        # 局部高点 (阻力位候选)
        highs = df['High'].values
        lows = df['Low'].values
        dates = df['Date'].values if 'Date' in df.columns else df.index
        
        resistance_levels = []
        support_levels = []
        
        # 寻找局部极值
        for i in range(window, len(df) - window):
            # 局部高点
            if highs[i] == max(highs[i-window:i+window+1]):
                level = highs[i]
                # 检查是否已存在相近水平
                exists = any(abs(r.level - level) / level < 0.02 for r in resistance_levels)
                if not exists:
                    touches = sum(1 for j in range(len(df)) if abs(highs[j] - level) / level < 0.01)
                    if touches >= min_touches:
                        resistance_levels.append(SupportResistance(
                            level=level,
                            type='resistance',
                            strength=touches,
                            last_touch=pd.Timestamp(dates[i]).date() if hasattr(dates[i], 'date') else dates[i],
                            distance_pct=(level - df['Close'].iloc[-1]) / df['Close'].iloc[-1] * 100
                        ))
            
            # 局部低点
            if lows[i] == min(lows[i-window:i+window+1]):
                level = lows[i]
                exists = any(abs(s.level - level) / level < 0.02 for s in support_levels)
                if not exists:
                    touches = sum(1 for j in range(len(df)) if abs(lows[j] - level) / level < 0.01)
                    if touches >= min_touches:
                        support_levels.append(SupportResistance(
                            level=level,
                            type='support',
                            strength=touches,
                            last_touch=pd.Timestamp(dates[i]).date() if hasattr(dates[i], 'date') else dates[i],
                            distance_pct=(df['Close'].iloc[-1] - level) / df['Close'].iloc[-1] * 100
                        ))
        
        # 按强度排序
        resistance_levels.sort(key=lambda x: x.strength, reverse=True)
        support_levels.sort(key=lambda x: x.strength, reverse=True)
        
        return support_levels[:5], resistance_levels[:5]
    
    def detect_head_shoulders(self, df: pd.DataFrame) -> Optional[PatternType]:
        """检测头肩顶/底形态"""
        if len(df) < 60:
            return None
        
        close = df['Close'].values
        
        # 简化检测：寻找三个峰值
        peaks = []
        for i in range(5, len(close) - 5):
            if close[i] > max(close[i-5:i]) and close[i] > max(close[i+1:i+5]):
                peaks.append((i, close[i]))
        
        if len(peaks) < 3:
            return None
        
        # 检查最后三个峰值是否形成头肩形态
        last_peaks = peaks[-3:]
        
        # 头肩顶: 中间峰值最高，两侧较低且相近
        if (last_peaks[1][1] > last_peaks[0][1] and 
            last_peaks[1][1] > last_peaks[2][1] and
            abs(last_peaks[0][1] - last_peaks[2][1]) / last_peaks[0][1] < 0.05):
            return PatternType.HEAD_SHOULDERS_TOP
        
        # 头肩底检测 (谷底)
        troughs = []
        for i in range(5, len(close) - 5):
            if close[i] < min(close[i-5:i]) and close[i] < min(close[i+1:i+5]):
                troughs.append((i, close[i]))
        
        if len(troughs) >= 3:
            last_troughs = troughs[-3:]
            if (last_troughs[1][1] < last_troughs[0][1] and 
                last_troughs[1][1] < last_troughs[2][1] and
                abs(last_troughs[0][1] - last_troughs[2][1]) / last_troughs[0][1] < 0.05):
                return PatternType.HEAD_SHOULDERS_BOTTOM
        
        return None
    
    def detect_double_top_bottom(self, df: pd.DataFrame) -> Optional[PatternType]:
        """检测双顶/双底形态"""
        if len(df) < 40:
            return None
        
        close = df['Close'].values
        high = df['High'].values
        low = df['Low'].values
        
        # 寻找近期两个相似的高点
        recent_highs = [(i, high[i]) for i in range(len(high)-20, len(high)-5) 
                        if high[i] == max(high[max(0,i-3):i+3])]
        
        if len(recent_highs) >= 2:
            h1, h2 = recent_highs[-2:]
            # 检查高度是否相近 (5%以内)
            if abs(h1[1] - h2[1]) / h1[1] < 0.05:
                # 检查中间是否有明显回调
                min_between = min(close[h1[0]:h2[0]])
                if min_between < h1[1] * 0.95:
                    return PatternType.DOUBLE_TOP
        
        # 双底检测
        recent_lows = [(i, low[i]) for i in range(len(low)-20, len(low)-5)
                       if low[i] == min(low[max(0,i-3):i+3])]
        
        if len(recent_lows) >= 2:
            l1, l2 = recent_lows[-2:]
            if abs(l1[1] - l2[1]) / l1[1] < 0.05:
                max_between = max(close[l1[0]:l2[0]])
                if max_between > l1[1] * 1.05:
                    return PatternType.DOUBLE_BOTTOM
        
        return None
    
    def detect_triangle(self, df: pd.DataFrame) -> Optional[PatternType]:
        """检测三角形形态"""
        if len(df) < 30:
            return None
        
        recent = df.tail(30)
        highs = recent['High'].values
        lows = recent['Low'].values
        
        # 线性回归拟合
        x = np.arange(len(highs))
        
        # 上轨趋势线 (连接高点)
        high_slope = np.polyfit(x[-15:], highs[-15:], 1)[0]
        
        # 下轨趋势线 (连接低点)
        low_slope = np.polyfit(x[-15:], lows[-15:], 1)[0]
        
        # 上升三角形: 上轨水平，下轨上升
        if abs(high_slope) < 0.001 and low_slope > 0:
            return PatternType.ASCENDING_TRIANGLE
        
        # 下降三角形: 下轨水平，上轨下降
        if abs(low_slope) < 0.001 and high_slope < 0:
            return PatternType.DESCENDING_TRIANGLE
        
        # 对称三角形: 两条线收敛
        if abs(high_slope + low_slope) < 0.001 and high_slope < 0:
            return PatternType.SYMMETRIC_TRIANGLE
        
        return None
    
    def analyze_trend(self, df: pd.DataFrame) -> TrendDirection:
        """分析趋势方向"""
        if len(df) < 50:
            return TrendDirection.SIDEWAYS
        
        close = df['Close'].iloc[-1]
        ma20 = df['MA_20'].iloc[-1]
        ma50 = df['MA_50'].iloc[-1]
        ma200 = df['MA_200'].iloc[-1] if 'MA_200' in df.columns and not pd.isna(df['MA_200'].iloc[-1]) else None
        
        # 短期趋势
        short_trend = 1 if close > ma20 else -1
        
        # 中期趋势
        medium_trend = 1 if close > ma50 else -1
        
        # 长期趋势
        if ma200:
            long_trend = 1 if close > ma200 else -1
        else:
            long_trend = 0
        
        # 综合判断
        trend_score = short_trend + medium_trend + long_trend
        
        # 均线排列
        ma_aligned = False
        if not pd.isna(ma20) and not pd.isna(ma50):
            if ma20 > ma50:
                ma_aligned = 1  # 多头排列
            elif ma20 < ma50:
                ma_aligned = -1  # 空头排列
        
        if trend_score >= 2 and ma_aligned == 1:
            return TrendDirection.STRONG_UP
        elif trend_score >= 1:
            return TrendDirection.UP
        elif trend_score <= -2 and ma_aligned == -1:
            return TrendDirection.STRONG_DOWN
        elif trend_score <= -1:
            return TrendDirection.DOWN
        else:
            return TrendDirection.SIDEWAYS
    
    def detect_divergence(self, df: pd.DataFrame) -> PriceActionSignal:
        """
        检测背离信号
        
        价格行为分析中的关键部分
        """
        if len(df) < 30:
            return PriceActionSignal.NO_SIGNAL
        
        close = df['Close'].values
        rsi = df['RSI'].values
        macd = df['MACD'].values
        
        # 近期高点和低点
        recent = 20
        
        # 顶背离: 价格新高，指标未新高
        if len(close) >= recent:
            price_high_idx = len(close) - recent + np.argmax(close[-recent:])
            price_high = close[price_high_idx]
            
            prev_period = close[max(0, price_high_idx-20):price_high_idx]
            if len(prev_period) > 0:
                prev_high = np.max(prev_period)
                
                if price_high > prev_high * 1.02:  # 价格创新高
                    rsi_high = rsi[price_high_idx]
                    prev_rsi_high = np.max(rsi[max(0, price_high_idx-20):price_high_idx])
                    
                    if rsi_high < prev_rsi_high * 0.98:  # RSI未创新高
                        return PriceActionSignal.GOOD_NEWS_BAD_REACTION
        
        # 底背离: 价格新低，指标未新低
        price_low_idx = len(close) - recent + np.argmin(close[-recent:])
        price_low = close[price_low_idx]
        
        prev_period = close[max(0, price_low_idx-20):price_low_idx]
        if len(prev_period) > 0:
            prev_low = np.min(prev_period)
            
            if price_low < prev_low * 0.98:  # 价格创新低
                rsi_low = rsi[price_low_idx]
                prev_rsi_low = np.min(rsi[max(0, price_low_idx-20):price_low_idx])
                
                if rsi_low > prev_rsi_low * 1.02:  # RSI未创新低
                    return PriceActionSignal.BAD_NEWS_GOOD_REACTION
        
        return PriceActionSignal.NO_SIGNAL
    
    def analyze_price_action(self, df: pd.DataFrame) -> PriceActionSignal:
        """
        价格行为分析
        
        基于PPT中的框架:
        - Good News, Bad Reaction -> 顶部信号
        - Bad News, Good Reaction -> 底部信号
        """
        if len(df) < 10:
            return PriceActionSignal.NO_SIGNAL
        
        # 检测背离
        divergence = self.detect_divergence(df)
        if divergence != PriceActionSignal.NO_SIGNAL:
            return divergence
        
        # 突破分析
        close = df['Close'].iloc[-1]
        volume_ratio = df['Volume_Ratio'].iloc[-1]
        
        support_levels, resistance_levels = self.detect_support_resistance(df)
        
        # 检查是否突破阻力位
        if resistance_levels:
            nearest_resistance = min(resistance_levels, key=lambda x: abs(x.level - close))
            if abs(close - nearest_resistance.level) / close < 0.01:
                if volume_ratio > 1.5:
                    return PriceActionSignal.BREAKOUT_STRONG
                else:
                    return PriceActionSignal.FALSE_BREAKOUT
        
        # 检查是否跌破支撑位
        if support_levels:
            nearest_support = min(support_levels, key=lambda x: abs(x.level - close))
            if abs(close - nearest_support.level) / close < 0.01:
                if volume_ratio > 1.5:
                    return PriceActionSignal.BREAKDOWN_STRONG
        
        return PriceActionSignal.NO_SIGNAL
    
    def generate_signal(self, symbol: str) -> Optional[PatternSignal]:
        """
        生成完整的技术形态交易信号
        """
        self.logger.info(f"分析 {symbol} 技术形态...")
        
        # 获取数据
        df = self.get_stock_data(symbol)
        if df.empty or len(df) < 50:
            self.logger.warning(f"  {symbol} 数据不足")
            return None
        
        # 计算指标
        df = self.calculate_indicators(df)
        
        # 获取最新数据
        latest = df.iloc[-1]
        current_price = latest['Close']
        current_date = latest['Date'].date() if hasattr(latest['Date'], 'date') else date.today()
        
        # 分析各维度
        trend = self.analyze_trend(df)
        price_action = self.analyze_price_action(df)
        
        # 检测经典形态
        pattern = self.detect_head_shoulders(df)
        if not pattern:
            pattern = self.detect_double_top_bottom(df)
        if not pattern:
            pattern = self.detect_triangle(df)
        if not pattern:
            pattern = PatternType.UNKNOWN
        
        # 支撑阻力
        support_levels, resistance_levels = self.detect_support_resistance(df)
        
        # 综合判断信号强度
        signal_strength = self._calculate_signal_strength(
            trend, price_action, pattern, latest
        )
        
        # 计算目标价和止损
        atr = latest['ATR'] if not pd.isna(latest['ATR']) else current_price * 0.02
        
        if signal_strength in [SignalStrength.BUY, SignalStrength.STRONG_BUY]:
            target_price = current_price + atr * 3
            stop_loss = current_price - atr * 2
        elif signal_strength in [SignalStrength.SELL, SignalStrength.STRONG_SELL]:
            target_price = current_price - atr * 3
            stop_loss = current_price + atr * 2
        else:
            target_price = current_price * 1.05
            stop_loss = current_price * 0.95
        
        # 计算置信度
        confidence = self._calculate_confidence(trend, price_action, pattern, latest)
        
        # 生成描述
        description = self._generate_description(
            symbol, trend, pattern, price_action, signal_strength
        )
        
        return PatternSignal(
            symbol=symbol,
            date=current_date,
            pattern=pattern,
            direction=trend,
            price_action=price_action,
            signal_strength=signal_strength,
            entry_price=round(current_price, 2),
            target_price=round(target_price, 2),
            stop_loss=round(stop_loss, 2),
            confidence=round(confidence, 2),
            description=description,
            support_levels=[s.level for s in support_levels[:3]],
            resistance_levels=[r.level for r in resistance_levels[:3]],
            volume_ratio=round(latest['Volume_Ratio'], 2) if not pd.isna(latest['Volume_Ratio']) else 1.0,
            rsi=round(latest['RSI'], 1) if not pd.isna(latest['RSI']) else 50.0,
            macd_signal="bullish" if latest['MACD'] > latest['MACD_Signal'] else "bearish"
        )
    
    def _calculate_signal_strength(self, trend: TrendDirection, 
                                    price_action: PriceActionSignal,
                                    pattern: PatternType, 
                                    latest: pd.Series) -> SignalStrength:
        """计算信号强度"""
        score = 0
        
        # 趋势得分
        if trend == TrendDirection.STRONG_UP:
            score += 2
        elif trend == TrendDirection.UP:
            score += 1
        elif trend == TrendDirection.STRONG_DOWN:
            score -= 2
        elif trend == TrendDirection.DOWN:
            score -= 1
        
        # 价格行为得分
        if price_action == PriceActionSignal.BAD_NEWS_GOOD_REACTION:
            score += 3  # 强底部信号
        elif price_action == PriceActionSignal.BREAKOUT_STRONG:
            score += 2
        elif price_action == PriceActionSignal.GOOD_NEWS_BAD_REACTION:
            score -= 3  # 强顶部信号
        elif price_action == PriceActionSignal.BREAKDOWN_STRONG:
            score -= 2
        
        # 形态得分
        bullish_patterns = [PatternType.HEAD_SHOULDERS_BOTTOM, PatternType.DOUBLE_BOTTOM,
                          PatternType.ASCENDING_TRIANGLE, PatternType.CUP_HANDLE,
                          PatternType.ROUNDING_BOTTOM]
        bearish_patterns = [PatternType.HEAD_SHOULDERS_TOP, PatternType.DOUBLE_TOP,
                          PatternType.DESCENDING_TRIANGLE]
        
        if pattern in bullish_patterns:
            score += 2
        elif pattern in bearish_patterns:
            score -= 2
        
        # RSI过滤
        rsi = latest['RSI'] if not pd.isna(latest['RSI']) else 50
        if rsi < 30:
            score += 1
        elif rsi > 70:
            score -= 1
        
        # 转换为信号强度
        if score >= 4:
            return SignalStrength.STRONG_BUY
        elif score >= 2:
            return SignalStrength.BUY
        elif score >= 1:
            return SignalStrength.WEAK_BUY
        elif score <= -4:
            return SignalStrength.STRONG_SELL
        elif score <= -2:
            return SignalStrength.SELL
        elif score <= -1:
            return SignalStrength.WEAK_SELL
        else:
            return SignalStrength.NEUTRAL
    
    def _calculate_confidence(self, trend: TrendDirection,
                              price_action: PriceActionSignal,
                              pattern: PatternType,
                              latest: pd.Series) -> float:
        """计算信号置信度"""
        confidence = 0.5  # 基础置信度
        
        # 趋势确认
        if trend in [TrendDirection.STRONG_UP, TrendDirection.STRONG_DOWN]:
            confidence += 0.15
        
        # 价格行为确认
        if price_action != PriceActionSignal.NO_SIGNAL:
            confidence += 0.2
        
        # 形态确认
        if pattern != PatternType.UNKNOWN:
            confidence += 0.1
        
        # 成交量确认
        volume_ratio = latest['Volume_Ratio'] if not pd.isna(latest['Volume_Ratio']) else 1
        if volume_ratio > 1.5:
            confidence += 0.05
        
        return min(confidence, 0.95)
    
    def _generate_description(self, symbol: str, trend: TrendDirection,
                             pattern: PatternType, price_action: PriceActionSignal,
                             signal: SignalStrength) -> str:
        """生成信号描述"""
        parts = [f"[{symbol}]"]
        
        # 趋势
        parts.append(f"趋势: {trend.value}")
        
        # 形态
        if pattern != PatternType.UNKNOWN:
            parts.append(f"形态: {pattern.value}")
        
        # 价格行为
        if price_action != PriceActionSignal.NO_SIGNAL:
            parts.append(f"信号: {price_action.value}")
        
        # 交易建议
        parts.append(f"建议: {signal.value}")
        
        return " | ".join(parts)


# ============================================================
# 批量分析
# ============================================================
class PatternBatchAnalyzer:
    """批量技术形态分析器"""
    
    def __init__(self, logger: logging.Logger = None):
        self.analyzer = TechnicalPatternAnalyzer(logger)
        self.logger = logger or setup_logger()
    
    def analyze_stocks(self, symbols: List[str] = None) -> pd.DataFrame:
        """批量分析股票"""
        symbols = symbols or DEFAULT_STOCKS
        
        self.logger.info("="*60)
        self.logger.info(f"批量技术形态分析: {len(symbols)} 只股票")
        self.logger.info("="*60)
        
        results = []
        for i, symbol in enumerate(symbols):
            try:
                signal = self.analyzer.generate_signal(symbol)
                if signal:
                    results.append({
                        'Symbol': signal.symbol,
                        'Date': signal.date,
                        'Signal': signal.signal_strength.value,
                        'Pattern': signal.pattern.value,
                        'Trend': signal.direction.value,
                        'Price_Action': signal.price_action.value,
                        'Price': signal.entry_price,
                        'Target': signal.target_price,
                        'Stop_Loss': signal.stop_loss,
                        'Confidence': signal.confidence,
                        'RSI': signal.rsi,
                        'Volume_Ratio': signal.volume_ratio,
                        'Description': signal.description
                    })
                
                if (i + 1) % 10 == 0:
                    self.logger.info(f"  进度: {i+1}/{len(symbols)}")
                    
            except Exception as e:
                self.logger.error(f"  {symbol} 分析失败: {e}")
        
        df = pd.DataFrame(results)
        
        # 排序: 买入信号在前
        signal_order = {
            '强烈买入': 0, '买入': 1, '偏买入': 2,
            '中性': 3,
            '偏卖出': 4, '卖出': 5, '强烈卖出': 6
        }
        df['Signal_Order'] = df['Signal'].map(signal_order)
        df = df.sort_values('Signal_Order').drop('Signal_Order', axis=1)
        
        self.logger.info(f"分析完成: {len(df)} 只股票")
        
        return df


# ============================================================
# 测试
# ============================================================
def test_pattern_analyzer():
    """测试技术形态分析器"""
    print("="*60)
    print("技术形态分析器测试")
    print("="*60)
    print()
    
    analyzer = TechnicalPatternAnalyzer()
    
    # 测试单只股票
    test_symbols = ['AAPL', 'NVDA', 'TSLA', 'SPY']
    
    for symbol in test_symbols:
        print(f"\n{'='*40}")
        signal = analyzer.generate_signal(symbol)
        
        if signal:
            print(f"股票: {signal.symbol}")
            print(f"日期: {signal.date}")
            print(f"当前价格: ${signal.entry_price}")
            print(f"趋势: {signal.direction.value}")
            print(f"形态: {signal.pattern.value}")
            print(f"价格行为: {signal.price_action.value}")
            print(f"信号强度: {signal.signal_strength.value}")
            print(f"目标价: ${signal.target_price}")
            print(f"止损价: ${signal.stop_loss}")
            print(f"置信度: {signal.confidence*100:.0f}%")
            print(f"RSI: {signal.rsi}")
            print(f"描述: {signal.description}")
            
            if signal.support_levels:
                print(f"支撑位: {signal.support_levels}")
            if signal.resistance_levels:
                print(f"阻力位: {signal.resistance_levels}")
    
    print("\n" + "="*60)
    print("批量分析测试")
    print("="*60)
    
    batch = PatternBatchAnalyzer()
    df = batch.analyze_stocks(['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA'])
    
    print("\n【分析结果汇总】")
    print(df[['Symbol', 'Signal', 'Pattern', 'Price', 'Confidence']].to_string(index=False))


if __name__ == "__main__":
    test_pattern_analyzer()
