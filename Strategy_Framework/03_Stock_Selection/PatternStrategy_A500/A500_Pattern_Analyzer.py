#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中证A500技术形态分析与操作推荐系统
====================================

基于路演PPT中的Price Action Analysis框架，对中证A500成分股进行:
1. 技术形态识别与评分
2. 买卖信号生成
3. 推荐操作列表输出

数据源: AKShare (A股数据)
"""

import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import logging
import time
import json

# AKShare用于A股数据
try:
    import akshare as ak
except ImportError:
    print("警告: 未安装akshare，将使用模拟数据")
    ak = None


# ============================================================
# 配置参数
# ============================================================
class SignalType(Enum):
    STRONG_BUY = "强烈买入"
    BUY = "买入"
    WEAK_BUY = "偏买入"
    NEUTRAL = "中性"
    WEAK_SELL = "偏卖出"
    SELL = "卖出"
    STRONG_SELL = "强烈卖出"


@dataclass
class PatternAnalysis:
    """技术形态分析结果"""
    symbol: str               # 股票代码
    name: str                 # 股票名称
    industry: str            # 所属行业
    
    # 价格数据
    current_price: float
    prev_close: float
    price_change_pct: float
    
    # 均线系统
    ma5: float
    ma10: float
    ma20: float
    ma60: float
    ma120: float
    ma_trend: str           # 均线趋势描述
    
    # 技术指标
    rsi: float
    macd: float
    macd_signal: float
    macd_status: str        # 金叉/死叉
    bb_position: float      # 布林带位置
    atr: float             # 平均真实波幅
    
    # 量能指标
    volume: float
    volume_ma20: float
    volume_ratio: float     # 量比
    
    # 形态识别
    pattern_name: str       # 形态名称
    pattern_strength: int   # 形态强度 0-100
    
    # 趋势评分
    trend_score: int        # 0-25
    pattern_score: int      # 0-25
    momentum_score: int     # 0-25
    volume_score: int       # 0-25
    total_score: int        # 0-100
    
    # 信号与操作建议
    signal: str             # 交易信号
    action: str             # 推荐操作
    confidence: str         # 置信度
    
    # 目标价位
    target_price: float
    stop_loss: float
    risk_reward: float      # 盈亏比
    
    # 分析时间
    analysis_date: str


# ============================================================
# 日志设置
# ============================================================
def setup_logger(name: str = "a500_pattern") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    
    return logger


logger = setup_logger()


# ============================================================
# 数据提供器
# ============================================================
class A500DataProvider:
    """中证A500数据提供器"""
    
    def __init__(self):
        self.cache = {}
    
    def get_a500_components(self) -> pd.DataFrame:
        """获取中证A500成分股列表"""
        logger.info("获取中证A500成分股...")
        
        if ak is None:
            logger.warning("AKShare未安装，使用模拟数据")
            return self._get_mock_components()
        
        try:
            # 尝试获取中证A500 (代码000510)
            df = ak.index_stock_cons_weight_csindex(symbol="000510")
            logger.info(f"  ✓ 成功获取中证A500成分股: {len(df)} 只")
        except Exception as e:
            logger.warning(f"  获取A500失败，尝试中证500: {e}")
            try:
                df = ak.index_stock_cons_weight_csindex(symbol="000905")
                logger.info(f"  ✓ 成功获取中证500成分股: {len(df)} 只")
            except Exception as e2:
                logger.error(f"  获取成分股失败: {e2}")
                return self._get_mock_components()
        
        # 标准化列名
        df = df.rename(columns={
            '成分券代码': '代码',
            '成分券名称': '名称',
            '权重': '权重',
        })
        
        # 获取行业信息
        df['行业'] = df['名称'].apply(self._get_industry_by_name)
        
        return df
    
    def _get_industry_by_name(self, name: str) -> str:
        """根据名称推测行业"""
        industry_map = {
            '银行': '金融', '证券': '金融', '保险': '金融',
            '医药': '医药生物', '医疗': '医药生物', '生物': '医药生物',
            '科技': '科技', '电子': '科技', '半导体': '科技', '芯片': '科技',
            '汽车': '汽车', '新能源': '新能源', '锂电': '新能源', '光伏': '新能源',
            '酒': '消费', '食品': '消费', '饮料': '消费', '家电': '消费',
            '地产': '地产', '建筑': '建筑', '建材': '建筑',
            '化工': '化工', '材料': '化工', '有色': '有色', '钢铁': '钢铁',
            '传媒': '传媒', '游戏': '传媒', '影视': '传媒',
            '通信': '通信', '电信': '通信', '5G': '通信',
        }
        for keyword, industry in industry_map.items():
            if keyword in name:
                return industry
        return '其他'
    
    def _get_mock_components(self) -> pd.DataFrame:
        """模拟成分股数据（用于测试）"""
        logger.info("使用模拟A500成分股数据")
        mock_data = [
            ('000001', '平安银行', '金融'), ('000002', '万科A', '地产'),
            ('000063', '中兴通讯', '通信'), ('000100', 'TCL科技', '科技'),
            ('000333', '美的集团', '家电'), ('000538', '云南白药', '医药'),
            ('000568', '泸州老窖', '消费'), ('000651', '格力电器', '家电'),
            ('000725', '京东方A', '科技'), ('000768', '中航西飞', '军工'),
            ('000858', '五粮液', '消费'), ('002001', '新和成', '化工'),
            ('002007', '华兰生物', '医药'), ('002049', '紫光国微', '科技'),
            ('002120', '韵达股份', '物流'), ('002142', '宁波银行', '金融'),
            ('002230', '科大讯飞', '科技'), ('002271', '东方雨虹', '建材'),
            ('002311', '海大集团', '农业'), ('002415', '海康威视', '科技'),
            ('002460', '赣锋锂业', '新能源'), ('002594', '比亚迪', '汽车'),
            ('300014', '亿纬锂能', '新能源'), ('300124', '汇川技术', '科技'),
            ('300750', '宁德时代', '新能源'), ('600000', '浦发银行', '金融'),
            ('600009', '上海机场', '交通'), ('600016', '民生银行', '金融'),
            ('600028', '中国石化', '能源'), ('600030', '中信证券', '金融'),
            ('600031', '三一重工', '机械'), ('600036', '招商银行', '金融'),
            ('600048', '保利地产', '地产'), ('600050', '中国联通', '通信'),
            ('600104', '上汽集团', '汽车'), ('600196', '复星医药', '医药'),
            ('600276', '恒瑞医药', '医药'), ('600309', '万华化学', '化工'),
            ('600519', '贵州茅台', '消费'), ('600585', '海螺水泥', '建材'),
            ('600690', '海尔智家', '家电'), ('600745', '闻泰科技', '科技'),
            ('600809', '山西汾酒', '消费'), ('600887', '伊利股份', '消费'),
            ('601012', '隆基绿能', '新能源'), ('601066', '中信建投', '金融'),
            ('601088', '中国神华', '能源'), ('601166', '兴业银行', '金融'),
            ('601318', '中国平安', '金融'), ('601398', '工商银行', '金融'),
        ]
        return pd.DataFrame(mock_data, columns=['代码', '名称', '行业'])
    
    def get_stock_data(self, symbol: str, days: int = 120) -> pd.DataFrame:
        """获取股票历史数据"""
        cache_key = f"{symbol}_{days}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        if ak is None:
            return self._get_mock_stock_data(symbol, days)
        
        try:
            # 使用AKShare获取A股历史数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            df = ak.stock_zh_a_hist(
                symbol=symbol, 
                period="daily",
                start_date=start_date.strftime('%Y%m%d'),
                end_date=end_date.strftime('%Y%m%d'),
                adjust="qfq"  # 前复权
            )
            
            if df.empty or len(df) < 30:
                return self._get_mock_stock_data(symbol, days)
            
            # 标准化列名
            df = df.rename(columns={
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount',
            })
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').reset_index(drop=True)
            
            self.cache[cache_key] = df
            return df
            
        except Exception as e:
            logger.debug(f"  {symbol} 数据获取失败: {e}")
            return self._get_mock_stock_data(symbol, days)
    
    def _get_mock_stock_data(self, symbol: str, days: int) -> pd.DataFrame:
        """生成模拟股票数据"""
        np.random.seed(hash(symbol) % 10000)
        
        dates = pd.date_range(end=datetime.now(), periods=days, freq='B')
        base_price = np.random.uniform(10, 200)
        
        # 生成随机价格走势
        returns = np.random.normal(0.0005, 0.02, len(dates))
        prices = base_price * np.exp(np.cumsum(returns))
        
        df = pd.DataFrame({
            'date': dates,
            'open': prices * (1 + np.random.normal(0, 0.005, len(dates))),
            'close': prices,
            'high': prices * (1 + np.abs(np.random.normal(0, 0.015, len(dates)))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.015, len(dates)))),
            'volume': np.random.randint(1000000, 10000000, len(dates)),
        })
        
        # 确保价格逻辑
        df['high'] = df[['open', 'close', 'high']].max(axis=1)
        df['low'] = df[['open', 'close', 'low']].min(axis=1)
        
        return df


# ============================================================
# 技术形态分析器
# ============================================================
class PatternAnalyzer:
    """技术形态分析器 - 基于路演PPT框架"""
    
    def __init__(self):
        self.data_provider = A500DataProvider()
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()
        
        # 移动平均线
        for period in [5, 10, 20, 60, 120]:
            df[f'ma{period}'] = df['close'].rolling(window=period).mean()
        
        # EMA
        df['ema12'] = df['close'].ewm(span=12, adjust=False).mean()
        df['ema26'] = df['close'].ewm(span=26, adjust=False).mean()
        
        # MACD
        df['macd'] = df['ema12'] - df['ema26']
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 布林带
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        bb_std = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
        df['bb_lower'] = df['bb_middle'] - (bb_std * 2)
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
        
        # 成交量指标
        df['volume_ma20'] = df['volume'].rolling(window=20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma20']
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['atr'] = true_range.rolling(14).mean()
        
        return df
    
    def detect_patterns(self, df: pd.DataFrame) -> Tuple[str, int]:
        """
        检测技术形态
        
        Returns:
            (形态名称, 形态强度0-100)
        """
        close = df['close'].values
        high = df['high'].values
        low = df['low'].values
        volume = df['volume'].values
        
        if len(close) < 60:
            return "数据不足", 0
        
        latest = df.iloc[-1]
        
        # 寻找局部极值点
        def find_peaks(data, window=5):
            peaks = []
            for i in range(window, len(data) - window):
                if data[i] == max(data[i-window:i+window+1]):
                    peaks.append((i, data[i]))
            return peaks
        
        def find_troughs(data, window=5):
            troughs = []
            for i in range(window, len(data) - window):
                if data[i] == min(data[i-window:i+window+1]):
                    troughs.append((i, data[i]))
            return troughs
        
        peaks = find_peaks(high, window=3)
        troughs = find_troughs(low, window=3)
        
        # 1. 检测双底形态 (W底)
        if len(troughs) >= 2:
            t1, t2 = troughs[-2], troughs[-1]
            price_diff = abs(t1[1] - t2[1]) / t1[1]
            if price_diff < 0.03:  # 两个低点相近 (<3%)
                middle_peak = max(close[t1[0]:t2[0]]) if t2[0] > t1[0] else close[t1[0]]
                if middle_peak > t1[1] * 1.03:  # 中间有明显反弹
                    if close[-1] > middle_peak:  # 突破颈线
                        return "双底突破", 90
                    else:
                        return "双底形态", 80
        
        # 2. 检测双顶形态 (M头)
        if len(peaks) >= 2:
            p1, p2 = peaks[-2], peaks[-1]
            price_diff = abs(p1[1] - p2[1]) / p1[1]
            if price_diff < 0.03:
                middle_trough = min(close[p1[0]:p2[0]]) if p2[0] > p1[0] else close[p1[0]]
                if middle_trough < p1[1] * 0.97:
                    if close[-1] < middle_trough:
                        return "双顶跌破", 85
                    else:
                        return "双顶形态", 70
        
        # 3. 检测杯柄形态
        if len(close) >= 40:
            recent_40 = close[-40:]
            cup_bottom = min(recent_40)
            cup_start = recent_40[0]
            current = close[-1]
            
            # U型底部特征
            if cup_bottom < cup_start * 0.92 and current > np.mean(recent_40[-10:]):
                # 检测柄部整理
                handle = close[-15:]
                if max(handle) - min(handle) < (max(recent_40) - cup_bottom) * 0.3:
                    if current > max(handle[:-5]) * 0.98:
                        return "杯柄突破", 88
                    return "杯柄形态", 75
        
        # 4. 检测头肩底
        if len(troughs) >= 3:
            t1, t2, t3 = troughs[-3], troughs[-2], troughs[-1]
            # 中间谷底更低
            if t2[1] < t1[1] and t2[1] < t3[1]:
                if abs(t1[1] - t3[1]) / t1[1] < 0.05:  # 左右肩相近
                    if close[-1] > t1[1] * 1.05:
                        return "头肩底", 85
        
        # 5. 三角形整理
        if len(close) >= 30:
            recent_high = high[-30:]
            recent_low = low[-30:]
            
            # 计算趋势线斜率
            x = np.arange(15)
            high_slope = np.polyfit(x, recent_high[-15:], 1)[0]
            low_slope = np.polyfit(x, recent_low[-15:], 1)[0]
            
            if high_slope < 0 and low_slope > 0:
                if abs(high_slope) < abs(low_slope) * 2 and abs(high_slope) > abs(low_slope) * 0.5:
                    if close[-1] > recent_high[-5:].mean():
                        return "三角形突破", 82
                    return "对称三角形", 65
            
            if abs(high_slope) < 0.001 and low_slope > 0:
                if close[-1] > recent_high[-3:].mean():
                    return "上升三角突破", 85
                return "上升三角形", 70
        
        # 6. 旗形/楔形
        if len(close) >= 20:
            recent = close[-20:]
            trend_before = close[-40:-20]
            
            if max(recent) - min(recent) < (max(trend_before) - min(trend_before)) * 0.4:
                if trend_before[-1] > trend_before[0]:  # 前期上涨
                    if close[-1] > max(recent[-5:]):
                        return "旗形突破", 80
                    return "上涨旗形", 60
        
        # 7. 基于趋势的判断
        if latest['close'] > latest['ma20'] > latest['ma60']:
            if latest['volume_ratio'] > 1.2:
                return "上升趋势", 55
            return "温和上涨", 45
        elif latest['close'] < latest['ma20'] < latest['ma60']:
            return "下降趋势", 40
        else:
            return "震荡整理", 50
    
    def calculate_scores(self, df: pd.DataFrame, pattern_name: str) -> Dict[str, int]:
        """计算各维度评分"""
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        scores = {}
        
        # 1. 趋势评分 (0-25)
        trend_score = 0
        if latest['ma5'] > latest['ma10'] > latest['ma20'] > latest['ma60']:
            trend_score = 25  # 完美多头排列
        elif latest['ma10'] > latest['ma20'] > latest['ma60']:
            trend_score = 20
        elif latest['ma20'] > latest['ma60']:
            trend_score = 15
        elif latest['close'] > latest['ma20']:
            trend_score = 10
        elif latest['close'] < latest['ma20'] < latest['ma60']:
            trend_score = 5
        else:
            trend_score = 8
        scores['trend'] = trend_score
        
        # 2. 形态评分 (0-25)
        pattern_scores = {
            "双底突破": 25, "双底形态": 22,
            "杯柄突破": 24, "杯柄形态": 20,
            "头肩底": 23,
            "上升三角突破": 23, "上升三角形": 18,
            "三角形突破": 21, "对称三角形": 16,
            "旗形突破": 20, "上涨旗形": 15,
            "上升趋势": 15, "温和上涨": 12,
            "震荡整理": 10,
            "双顶跌破": 5, "双顶形态": 8,
            "下降趋势": 5,
            "数据不足": 0
        }
        scores['pattern'] = pattern_scores.get(pattern_name, 10)
        
        # 3. 动量评分 (0-25)
        momentum_score = 0
        rsi = latest['rsi']
        
        # RSI评分
        if 50 <= rsi <= 65:
            momentum_score += 12  # 健康上涨区间
        elif 40 <= rsi < 50:
            momentum_score += 10
        elif 65 < rsi <= 75:
            momentum_score += 8
        elif rsi < 30:
            momentum_score += 6   # 超卖可能反弹
        else:
            momentum_score += 4
        
        # MACD评分
        if latest['macd'] > latest['macd_signal'] and latest['macd'] > 0:
            momentum_score += 13  # 金叉且正值
        elif latest['macd'] > latest['macd_signal']:
            momentum_score += 10  # 金叉
        elif latest['macd'] > 0:
            momentum_score += 5
        else:
            momentum_score += 2
        
        scores['momentum'] = min(momentum_score, 25)
        
        # 4. 量能评分 (0-25)
        volume_score = 0
        vol_ratio = latest['volume_ratio']
        
        if vol_ratio >= 2.0:
            volume_score += 12
        elif vol_ratio >= 1.5:
            volume_score += 10
        elif vol_ratio >= 1.0:
            volume_score += 8
        elif vol_ratio >= 0.7:
            volume_score += 5
        else:
            volume_score += 3
        
        # 量价配合
        price_up = latest['close'] > prev['close']
        if price_up and vol_ratio > 1.2:
            volume_score += 10  # 上涨放量
        elif price_up and vol_ratio < 0.8:
            volume_score += 3   # 上涨缩量（警惕）
        elif not price_up and vol_ratio > 1.5:
            volume_score += 4   # 放量下跌
        else:
            volume_score += 5
        
        # 布林带位置
        bb_pos = latest['bb_position']
        if 0.3 <= bb_pos <= 0.7:
            volume_score += 3   # 健康区间
        elif bb_pos > 0.8:
            volume_score += 1   # 接近上轨
        elif bb_pos < 0.2:
            volume_score += 2   # 接近下轨
        
        scores['volume'] = min(volume_score, 25)
        
        return scores
    
    def determine_signal(self, total_score: int, pattern_name: str) -> Tuple[str, str, str]:
        """
        确定交易信号和操作建议
        
        Returns:
            (信号类型, 推荐操作, 置信度)
        """
        # 信号分级
        if total_score >= 85:
            signal = SignalType.STRONG_BUY
            confidence = "高"
        elif total_score >= 70:
            signal = SignalType.BUY
            confidence = "中高"
        elif total_score >= 55:
            signal = SignalType.WEAK_BUY
            confidence = "中等"
        elif total_score >= 40:
            signal = SignalType.NEUTRAL
            confidence = "低"
        elif total_score >= 25:
            signal = SignalType.WEAK_SELL
            confidence = "中等"
        elif total_score >= 15:
            signal = SignalType.SELL
            confidence = "中高"
        else:
            signal = SignalType.STRONG_SELL
            confidence = "高"
        
        # 生成操作建议
        action_map = {
            SignalType.STRONG_BUY: "积极建仓，分批买入",
            SignalType.BUY: "适量买入，关注突破",
            SignalType.WEAK_BUY: "轻仓试探，等待确认",
            SignalType.NEUTRAL: "观望为主，等待方向",
            SignalType.WEAK_SELL: "考虑减仓",
            SignalType.SELL: "适时卖出",
            SignalType.STRONG_SELL: "果断离场",
        }
        
        # 根据形态调整建议
        action = action_map[signal]
        if "突破" in pattern_name:
            action += "，突破确认后加仓"
        elif "形态" in pattern_name and signal in [SignalType.BUY, SignalType.STRONG_BUY]:
            action += "，形态完成度较高"
        
        return signal.value, action, confidence
    
    def analyze_stock(self, symbol: str, name: str = "", industry: str = "") -> Optional[PatternAnalysis]:
        """分析单只股票"""
        try:
            # 获取数据
            df = self.data_provider.get_stock_data(symbol)
            if df.empty or len(df) < 60:
                return None
            
            # 计算指标
            df = self.calculate_indicators(df)
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            
            # 检测形态
            pattern_name, pattern_strength = self.detect_patterns(df)
            
            # 计算评分
            scores = self.calculate_scores(df, pattern_name)
            total_score = sum(scores.values())
            
            # 确定信号
            signal, action, confidence = self.determine_signal(total_score, pattern_name)
            
            # 计算目标价和止损
            atr = latest['atr'] if not pd.isna(latest['atr']) else latest['close'] * 0.02
            
            if signal in ["强烈买入", "买入", "偏买入"]:
                target_price = latest['close'] + atr * 3
                stop_loss = latest['close'] - atr * 2
            elif signal in ["强烈卖出", "卖出", "偏卖出"]:
                target_price = latest['close'] - atr * 3
                stop_loss = latest['close'] + atr * 2
            else:
                target_price = latest['close'] * 1.05
                stop_loss = latest['close'] * 0.95
            
            risk_reward = abs(target_price - latest['close']) / abs(stop_loss - latest['close']) if stop_loss != latest['close'] else 1
            
            # 判断MACD状态
            macd_status = "金叉" if latest['macd'] > latest['macd_signal'] else "死叉"
            
            # 均线趋势描述
            if latest['ma5'] > latest['ma10'] > latest['ma20'] > latest['ma60']:
                ma_trend = "多头排列"
            elif latest['ma20'] > latest['ma60']:
                ma_trend = "中期多头"
            elif latest['close'] > latest['ma20']:
                ma_trend = "短期多头"
            else:
                ma_trend = "空头/震荡"
            
            return PatternAnalysis(
                symbol=symbol,
                name=name,
                industry=industry,
                current_price=round(latest['close'], 2),
                prev_close=round(prev['close'], 2),
                price_change_pct=round((latest['close'] / prev['close'] - 1) * 100, 2),
                ma5=round(latest['ma5'], 2),
                ma10=round(latest['ma10'], 2),
                ma20=round(latest['ma20'], 2),
                ma60=round(latest['ma60'], 2),
                ma120=round(latest.get('ma120', latest['ma60']), 2),
                ma_trend=ma_trend,
                rsi=round(latest['rsi'], 1),
                macd=round(latest['macd'], 3),
                macd_signal=round(latest['macd_signal'], 3),
                macd_status=macd_status,
                bb_position=round(latest['bb_position'], 2),
                atr=round(latest['atr'], 3),
                volume=int(latest['volume']),
                volume_ma20=int(latest['volume_ma20']),
                volume_ratio=round(latest['volume_ratio'], 2),
                pattern_name=pattern_name,
                pattern_strength=pattern_strength,
                trend_score=scores['trend'],
                pattern_score=scores['pattern'],
                momentum_score=scores['momentum'],
                volume_score=scores['volume'],
                total_score=total_score,
                signal=signal,
                action=action,
                confidence=confidence,
                target_price=round(target_price, 2),
                stop_loss=round(stop_loss, 2),
                risk_reward=round(risk_reward, 2),
                analysis_date=datetime.now().strftime('%Y-%m-%d')
            )
            
        except Exception as e:
            logger.debug(f"  {symbol} 分析失败: {e}")
            return None
    
    def batch_analyze(self, components: pd.DataFrame, max_stocks: int = None) -> pd.DataFrame:
        """批量分析A500成分股"""
        logger.info("="*60)
        logger.info("中证A500技术形态批量分析")
        logger.info("="*60)
        
        if max_stocks:
            components = components.head(max_stocks)
        
        total = len(components)
        logger.info(f"分析标的: {total} 只股票")
        logger.info("评分维度: 趋势(25) + 形态(25) + 动量(25) + 量能(25) = 总分(100)")
        logger.info("")
        
        results = []
        
        for idx, row in components.iterrows():
            symbol = str(row['代码']).zfill(6)
            name = row.get('名称', '')
            industry = row.get('行业', '')
            
            result = self.analyze_stock(symbol, name, industry)
            if result:
                results.append(result)
            
            if (idx + 1) % 10 == 0 or idx == len(components) - 1:
                logger.info(f"  进度: {idx + 1}/{total} ({(idx+1)/total*100:.1f}%)")
            
            # 延迟避免请求过快
            time.sleep(0.2)
        
        # 转换为DataFrame
        if results:
            df = pd.DataFrame([asdict(r) for r in results])
            df = df.sort_values('total_score', ascending=False).reset_index(drop=True)
            df.insert(0, 'rank', range(1, len(df) + 1))
            return df
        
        return pd.DataFrame()


# ============================================================
# 报告生成器
# ============================================================
class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, output_dir: str = None):
        self.output_dir = output_dir or f"Report_{date.today().isoformat()}"
        import os
        os.makedirs(self.output_dir, exist_ok=True)
    
    def generate_csv_report(self, df: pd.DataFrame, filename: str = None):
        """生成CSV报告"""
        if df.empty:
            return None
        
        filename = filename or f"A500_Pattern_Analysis_{date.today().isoformat()}.csv"
        filepath = f"{self.output_dir}/{filename}"
        
        # 选择关键列
        key_columns = [
            'rank', 'symbol', 'name', 'industry', 'total_score',
            'signal', 'action', 'confidence', 'pattern_name',
            'current_price', 'target_price', 'stop_loss', 'risk_reward',
            'trend_score', 'pattern_score', 'momentum_score', 'volume_score',
            'ma_trend', 'rsi', 'macd_status', 'volume_ratio'
        ]
        
        available_cols = [c for c in key_columns if c in df.columns]
        report_df = df[available_cols].copy()
        
        report_df.to_csv(filepath, index=False, encoding='utf-8-sig')
        logger.info(f"CSV报告已保存: {filepath}")
        return filepath
    
    def generate_recommendation_list(self, df: pd.DataFrame):
        """生成推荐操作列表（Markdown格式）"""
        if df.empty:
            return None
        
        filepath = f"{self.output_dir}/A500_Recommendation_List.md"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("# 中证A500 技术形态分析与操作推荐\n\n")
            f.write(f"**分析日期**: {datetime.now().strftime('%Y年%m月%d日')}\n\n")
            f.write("---\n\n")
            
            # 1. 强烈买入推荐
            strong_buy = df[df['signal'] == '强烈买入'].head(10)
            if not strong_buy.empty:
                f.write("## 一、强烈买入推荐 (综合得分 ≥85)\n\n")
                f.write("| 排名 | 代码 | 名称 | 行业 | 得分 | 形态 | 现价 | 目标价 | 止损价 | 盈亏比 | 建议操作 |\n")
                f.write("|------|------|------|------|------|------|------|--------|--------|--------|----------|\n")
                
                for _, row in strong_buy.iterrows():
                    f.write(f"| {row['rank']} | {row['symbol']} | {row['name']} | {row['industry']} | "
                           f"{row['total_score']} | {row['pattern_name']} | {row['current_price']:.2f} | "
                           f"{row['target_price']:.2f} | {row['stop_loss']:.2f} | {row['risk_reward']:.1f} | "
                           f"{row['action']} |\n")
                f.write("\n")
            
            # 2. 买入推荐
            buy = df[df['signal'] == '买入'].head(10)
            if not buy.empty:
                f.write("## 二、买入推荐 (综合得分 70-84)\n\n")
                f.write("| 排名 | 代码 | 名称 | 行业 | 得分 | 形态 | 现价 | 目标价 | 止损价 | 盈亏比 | 建议操作 |\n")
                f.write("|------|------|------|------|------|------|------|--------|--------|--------|----------|\n")
                
                for _, row in buy.iterrows():
                    f.write(f"| {row['rank']} | {row['symbol']} | {row['name']} | {row['industry']} | "
                           f"{row['total_score']} | {row['pattern_name']} | {row['current_price']:.2f} | "
                           f"{row['target_price']:.2f} | {row['stop_loss']:.2f} | {row['risk_reward']:.1f} | "
                           f"{row['action']} |\n")
                f.write("\n")
            
            # 3. 观望/中性
            neutral = df[df['signal'] == '中性'].head(5)
            if not neutral.empty:
                f.write("## 三、中性观望 (综合得分 40-54)\n\n")
                f.write("| 排名 | 代码 | 名称 | 行业 | 得分 | 形态 | 现价 | 建议 |\n")
                f.write("|------|------|------|------|------|------|------|------|\n")
                
                for _, row in neutral.iterrows():
                    f.write(f"| {row['rank']} | {row['symbol']} | {row['name']} | {row['industry']} | "
                           f"{row['total_score']} | {row['pattern_name']} | {row['current_price']:.2f} | "
                           f"{row['action']} |\n")
                f.write("\n")
            
            # 4. 卖出/减仓
            sell = df[df['signal'].isin(['卖出', '强烈卖出'])].head(5)
            if not sell.empty:
                f.write("## 四、卖出/减仓信号\n\n")
                f.write("| 排名 | 代码 | 名称 | 行业 | 得分 | 形态 | 现价 | 建议 |\n")
                f.write("|------|------|------|------|------|------|------|------|\n")
                
                for _, row in sell.iterrows():
                    f.write(f"| {row['rank']} | {row['symbol']} | {row['name']} | {row['industry']} | "
                           f"{row['total_score']} | {row['pattern_name']} | {row['current_price']:.2f} | "
                           f"{row['action']} |\n")
                f.write("\n")
            
            # 5. 统计汇总
            f.write("---\n\n")
            f.write("## 五、统计分析\n\n")
            f.write(f"- **总分析数量**: {len(df)} 只\n")
            f.write(f"- **平均得分**: {df['total_score'].mean():.1f}\n\n")
            
            f.write("### 信号分布\n\n")
            signal_counts = df['signal'].value_counts()
            for signal, count in signal_counts.items():
                pct = count / len(df) * 100
                f.write(f"- {signal}: {count} 只 ({pct:.1f}%)\n")
            
            f.write("\n### 行业分布 (Top10)\n\n")
            industry_counts = df['industry'].value_counts().head(10)
            for industry, count in industry_counts.items():
                f.write(f"- {industry}: {count} 只\n")
            
            f.write("\n---\n\n")
            f.write("## 六、评分标准说明\n\n")
            f.write("### 评分维度\n\n")
            f.write("| 维度 | 权重 | 说明 |\n")
            f.write("|------|------|------|\n")
            f.write("| 趋势评分 | 25分 | 均线排列、价格在均线上方 |\n")
            f.write("| 形态评分 | 25分 | 双底、杯柄、三角形等经典形态 |\n")
            f.write("| 动量评分 | 25分 | RSI、MACD、近期涨幅 |\n")
            f.write("| 量能评分 | 25分 | 成交量、量比、量价配合 |\n")
            f.write("| **总分** | **100分** | **综合评估** |\n\n")
            
            f.write("### 信号分级\n\n")
            f.write("| 信号 | 得分范围 | 操作建议 |\n")
            f.write("|------|----------|----------|\n")
            f.write("| 强烈买入 | ≥85分 | 积极建仓，分批买入 |\n")
            f.write("| 买入 | 70-84分 | 适量买入，关注突破 |\n")
            f.write("| 偏买入 | 55-69分 | 轻仓试探，等待确认 |\n")
            f.write("| 中性 | 40-54分 | 观望为主，等待方向 |\n")
            f.write("| 偏卖出 | 25-39分 | 考虑减仓 |\n")
            f.write("| 卖出 | <25分 | 果断离场 |\n\n")
            
            f.write("---\n\n")
            f.write("**免责声明**: 本报告基于技术分析生成，仅供参考，不构成投资建议。投资有风险，入市需谨慎。\n")
        
        logger.info(f"推荐列表已保存: {filepath}")
        return filepath


# ============================================================
# 主函数
# ============================================================
def main():
    """主程序"""
    print("="*60)
    print("中证A500 技术形态分析与操作推荐系统")
    print("="*60)
    print()
    
    # 创建分析器
    analyzer = PatternAnalyzer()
    
    # 获取A500成分股
    components = analyzer.data_provider.get_a500_components()
    print(f"成分股数量: {len(components)}")
    print()
    
    # 分析前N只（可以修改）
    MAX_STOCKS = 100  # 设置为None分析全部
    if MAX_STOCKS and len(components) > MAX_STOCKS:
        print(f"【演示模式】分析前 {MAX_STOCKS} 只股票")
        print("  如需分析全部成分股，请修改代码中的 MAX_STOCKS 参数")
        print()
    
    # 执行分析
    results_df = analyzer.batch_analyze(components, max_stocks=MAX_STOCKS)
    
    if not results_df.empty:
        # 生成报告
        report_gen = ReportGenerator()
        
        # 保存CSV
        csv_path = report_gen.generate_csv_report(results_df)
        
        # 生成推荐列表
        md_path = report_gen.generate_recommendation_list(results_df)
        
        # 控制台输出Top20
        print("\n" + "="*60)
        print("技术形态综合评分 - TOP 20")
        print("="*60)
        
        top20 = results_df.head(20)
        for _, row in top20.iterrows():
            print(f"\n【排名 {row['rank']}】{row['symbol']} {row['name']} ({row['industry']})")
            print(f"  综合得分: {row['total_score']}/100 | 信号: {row['signal']} | 置信度: {row['confidence']}")
            print(f"  ├─ 趋势: {row['trend_score']}分 ({row['ma_trend']})")
            print(f"  ├─ 形态: {row['pattern_score']}分 ({row['pattern_name']})")
            print(f"  ├─ 动量: {row['momentum_score']}分 (RSI:{row['rsi']}, MACD:{row['macd_status']})")
            print(f"  └─ 量能: {row['volume_score']}分 (量比:{row['volume_ratio']})")
            print(f"  价格: ¥{row['current_price']:.2f} → 目标: ¥{row['target_price']:.2f} | 止损: ¥{row['stop_loss']:.2f}")
            print(f"  建议: {row['action']}")
        
        # 保存Top20为单独文件
        top20_path = f"{report_gen.output_dir}/A500_Top20_{date.today().isoformat()}.csv"
        top20.to_csv(top20_path, index=False, encoding='utf-8-sig')
        
        print("\n" + "="*60)
        print("分析完成")
        print(f"报告目录: {report_gen.output_dir}")
        print(f"- CSV报告: {csv_path}")
        print(f"- 推荐列表: {md_path}")
        print(f"- Top20: {top20_path}")
        print("="*60)
    else:
        print("分析失败，无结果")


if __name__ == "__main__":
    main()
