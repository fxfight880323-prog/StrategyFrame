#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中证A500技术形态分析系统 (RiceQuant数据版)
============================================

基于米筐(RiceQuant)数据，对中证A500成分股进行技术形态综合打分

功能:
- 使用RiceQuant获取中证A500成分股
- 批量技术形态分析
- 综合打分排序
- 生成Top20报告

数据源: RiceQuant (rqdatac)
"""

import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging
import time

# 米筐数据接口
try:
    import rqdatac as rq
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False


# ============================================================
# 配置
# ============================================================
# RiceQuant API Key (从环境变量或配置文件读取)
RQ_API_KEY = "Mg8lEL3dGgIyxrwc2rNsqVneytgqpSq4n0h4S8M-XQnZ9domysurqc3Lh1NlmAwAKSBTUr5qwFJ-aPEeFfR3L2rK5pq-HddOdS6vDBfDv187cVUdC9sejifx7V1lQjQWRm19YVrhx1poB-uThWtc3F6kzslu4cn9myNayWNzfo8="


# ============================================================
# 日志设置
# ============================================================
def setup_logger(name: str = "csi_a500_rq") -> logging.Logger:
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
# 数据模型
# ============================================================
@dataclass
class PatternScore:
    """技术形态评分"""
    symbol: str           # 股票代码
    name: str             # 股票名称
    score: float          # 综合得分 (0-100)
    
    # 各维度得分
    trend_score: float    # 趋势得分 (0-25)
    pattern_score: float  # 形态得分 (0-25)
    momentum_score: float # 动量得分 (0-25)
    volume_score: float   # 量能得分 (0-25)
    
    # 关键指标
    current_price: float
    ma20: float
    ma60: float
    rsi: float
    macd_signal: str
    pattern_type: str
    signal_type: str      # 买入/卖出/中性
    
    # 目标价和止损
    target_price: float
    stop_loss: float
    
    # 行业信息
    industry: str = ""
    market_cap: float = 0.0


# ============================================================
# RiceQuant A股数据提供器
# ============================================================
class RiceQuantAShareProvider:
    """RiceQuant A股数据提供器"""
    
    def __init__(self, api_key: str = RQ_API_KEY, logger: logging.Logger = None):
        self.logger = logger or setup_logger()
        self.api_key = api_key
        self.rq = None
        self.cache = {}
        
        # 初始化连接
        self._init_connection()
    
    def _init_connection(self):
        """初始化RiceQuant连接"""
        if not RQ_AVAILABLE:
            self.logger.error("rqdatac未安装，无法使用RiceQuant数据")
            return False
        
        try:
            rq.init(self.api_key)
            self.rq = rq
            self.logger.info("✓ RiceQuant连接成功")
            return True
        except Exception as e:
            self.logger.error(f"RiceQuant连接失败: {e}")
            return False
    
    def get_csi_a500_components(self) -> pd.DataFrame:
        """
        获取中证A500成分股
        
        Returns:
            DataFrame with columns: 代码, 名称
        """
        self.logger.info("获取中证A500成分股 (RiceQuant)...")
        
        if not self.rq:
            self.logger.error("RiceQuant未连接")
            return pd.DataFrame()
        
        try:
            # 获取中证A500指数成分股
            # 中证A500代码: 000510 (CSI)
            try:
                # 尝试获取中证A500
                constituents = rq.index_components('000510.XSHG')
                self.logger.info(f"  ✓ 成功获取中证A500成分股: {len(constituents)} 只")
            except:
                # 备选: 中证800去掉沪深300
                self.logger.info("  备选: 获取中证800成分股...")
                csi800 = rq.index_components('000906.XSHG')
                csi300 = set(rq.index_components('000300.XSHG'))
                # 中证500部分
                constituents = [s for s in csi800 if s not in csi300]
                self.logger.info(f"  ✓ 中证500部分: {len(constituents)} 只")
            
            # 获取股票名称
            stock_info = []
            for order_book_id in constituents:
                try:
                    inst = rq.instruments(order_book_id)
                    if inst:
                        stock_info.append({
                            '代码': order_book_id.split('.')[0],
                            '名称': inst.symbol,
                            'order_book_id': order_book_id
                        })
                except:
                    continue
            
            df = pd.DataFrame(stock_info)
            self.logger.info(f"  ✓ 成功获取 {len(df)} 只股票信息")
            return df
            
        except Exception as e:
            self.logger.error(f"  ✗ 获取成分股失败: {e}")
            # 返回一个默认列表用于测试
            return pd.DataFrame({
                '代码': ['000001', '000002', '000063', '000100', '000333'],
                '名称': ['平安银行', '万科A', '中兴通讯', 'TCL科技', '美的集团'],
                'order_book_id': ['000001.XSHE', '000002.XSHE', '000063.XSHE', '000100.XSHE', '000333.XSHE']
            })
    
    def get_stock_data(self, order_book_id: str, days: int = 120) -> pd.DataFrame:
        """
        获取股票历史数据 (RiceQuant)
        
        Args:
            order_book_id: 米筐代码 (如 '000001.XSHE')
            days: 获取天数
        
        Returns:
            DataFrame with OHLCV data
        """
        cache_key = f"{order_book_id}_{days}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        if not self.rq:
            return pd.DataFrame()
        
        try:
            # 计算日期范围
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            # 获取日线数据
            df = rq.get_price(
                order_book_ids=order_book_id,
                start_date=start_date,
                end_date=end_date,
                frequency='1d',
                fields=['open', 'high', 'low', 'close', 'volume']
            )
            
            if df.empty:
                return pd.DataFrame()
            
            # 重置索引，将日期变为列
            df = df.reset_index()
            
            # 标准化列名
            df = df.rename(columns={
                'date': 'Date',
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume'
            })
            
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.sort_values('Date').reset_index(drop=True)
            
            self.cache[cache_key] = df
            return df
            
        except Exception as e:
            self.logger.debug(f"  {order_book_id} 数据获取失败: {e}")
            return pd.DataFrame()
    
    def get_stock_info(self, order_book_id: str) -> Dict:
        """获取股票基本信息"""
        if not self.rq:
            return {'name': '', 'industry': '', 'market_cap': 0}
        
        try:
            inst = rq.instruments(order_book_id)
            if inst:
                # 获取行业信息
                try:
                    industry = rq.get_instrument_industry(order_book_id)
                except:
                    industry = ""
                
                return {
                    'name': inst.symbol,
                    'industry': industry if industry else '',
                    'market_cap': 0  # 可通过其他接口获取
                }
        except:
            pass
        
        return {'name': '', 'industry': '', 'market_cap': 0}


# ============================================================
# 技术形态评分器
# ============================================================
class ASharePatternScorer:
    """A股技术形态评分器"""
    
    def __init__(self, api_key: str = RQ_API_KEY, logger: logging.Logger = None):
        self.logger = logger or setup_logger()
        self.data_provider = RiceQuantAShareProvider(api_key, logger)
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()
        
        # 移动平均线
        for period in [5, 10, 20, 60]:
            df[f'MA_{period}'] = df['Close'].rolling(window=period).mean()
        
        # EMA
        df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
        
        # MACD
        df['MACD'] = df['EMA_12'] - df['EMA_26']
        df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # 布林带
        df['BB_Middle'] = df['Close'].rolling(window=20).mean()
        bb_std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)
        df['BB_Position'] = (df['Close'] - df['BB_Lower']) / (df['BB_Upper'] - df['BB_Lower'])
        
        # 成交量指标
        df['Volume_MA'] = df['Volume'].rolling(window=20).mean()
        df['Volume_Ratio'] = df['Volume'] / df['Volume_MA']
        
        # ATR
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(14).mean()
        
        # 波动率
        df['Returns'] = df['Close'].pct_change()
        df['Volatility'] = df['Returns'].rolling(20).std() * np.sqrt(252)
        
        return df
    
    def score_trend(self, df: pd.DataFrame) -> Tuple[float, str]:
        """
        趋势评分 (0-25分)
        """
        score = 0
        latest = df.iloc[-1]
        
        # 均线排列
        if (latest['MA_5'] > latest['MA_10'] > latest['MA_20'] > latest['MA_60']):
            score += 15
            trend_desc = "多头排列"
        elif (latest['MA_5'] > latest['MA_20'] > latest['MA_60']):
            score += 10
            trend_desc = "中期多头"
        elif (latest['Close'] > latest['MA_20'] > latest['MA_60']):
            score += 5
            trend_desc = "初步多头"
        elif (latest['Close'] < latest['MA_20'] < latest['MA_60']):
            score += 0
            trend_desc = "空头排列"
        else:
            score += 3
            trend_desc = "震荡"
        
        # 价格在均线上方加分
        if latest['Close'] > latest['MA_20']:
            score += 5
        if latest['Close'] > latest['MA_60']:
            score += 5
        
        return min(score, 25), trend_desc
    
    def score_pattern(self, df: pd.DataFrame) -> Tuple[float, str]:
        """
        形态评分 (0-25分)
        """
        score = 0
        pattern_name = "无明显形态"
        
        close = df['Close'].values
        high = df['High'].values
        low = df['Low'].values
        
        if len(close) < 60:
            return 12, "数据不足"
        
        # 寻找局部极值
        def find_peaks_prices(prices, window=5):
            peaks = []
            for i in range(window, len(prices) - window):
                if prices[i] == max(prices[i-window:i+window+1]):
                    peaks.append((i, prices[i]))
            return peaks
        
        def find_troughs_prices(prices, window=5):
            troughs = []
            for i in range(window, len(prices) - window):
                if prices[i] == min(prices[i-window:i+window+1]):
                    troughs.append((i, prices[i]))
            return troughs
        
        peaks = find_peaks_prices(high)
        troughs = find_troughs_prices(low)
        
        # 检测双底
        if len(troughs) >= 2:
            t1, t2 = troughs[-2], troughs[-1]
            if abs(t1[1] - t2[1]) / t1[1] < 0.03:
                if max(close[t1[0]:t2[0]]) > t1[1] * 1.05:
                    score += 20
                    pattern_name = "双底形态"
        
        # 检测双顶
        if len(peaks) >= 2 and score == 0:
            p1, p2 = peaks[-2], peaks[-1]
            if abs(p1[1] - p2[1]) / p1[1] < 0.03:
                if min(close[p1[0]:p2[0]]) < p1[1] * 0.95:
                    score += 5
                    pattern_name = "双顶形态"
        
        # 检测杯柄形态
        if score == 0 and len(close) >= 40:
            recent = close[-40:]
            if min(recent) < recent[0] * 0.9 and close[-1] > np.mean(recent[-10:]):
                score += 18
                pattern_name = "杯柄形态"
        
        # 检测三角形整理
        if score == 0 and len(close) >= 30:
            recent_high = high[-30:]
            recent_low = low[-30:]
            
            high_slope = np.polyfit(range(15), recent_high[-15:], 1)[0]
            low_slope = np.polyfit(range(15), recent_low[-15:], 1)[0]
            
            if abs(high_slope) < 0.001 and low_slope > 0:
                score += 16
                pattern_name = "上升三角形"
            elif high_slope < 0 and low_slope > 0:
                score += 14
                pattern_name = "对称三角形"
        
        if score == 0:
            latest = df.iloc[-1]
            if latest['Close'] > latest['MA_20']:
                score = 12
                pattern_name = "上升趋势"
            else:
                score = 8
                pattern_name = "调整中"
        
        return min(score, 25), pattern_name
    
    def score_momentum(self, df: pd.DataFrame) -> Tuple[float, str]:
        """
        动量评分 (0-25分)
        """
        score = 0
        latest = df.iloc[-1]
        
        # RSI评分
        rsi = latest['RSI']
        if 50 <= rsi <= 65:
            score += 10
            rsi_desc = "健康上涨"
        elif 40 <= rsi < 50:
            score += 8
            rsi_desc = "反弹初期"
        elif 65 < rsi <= 75:
            score += 6
            rsi_desc = "偏强"
        elif rsi > 75:
            score += 2
            rsi_desc = "超买"
        elif rsi < 30:
            score += 5
            rsi_desc = "超卖"
        else:
            score += 4
            rsi_desc = "弱势"
        
        # MACD评分
        if latest['MACD'] > latest['MACD_Signal'] and latest['MACD'] > 0:
            score += 10
            macd_desc = "金叉且正值"
        elif latest['MACD'] > latest['MACD_Signal']:
            score += 7
            macd_desc = "金叉"
        elif latest['MACD'] > 0:
            score += 4
            macd_desc = "正值"
        else:
            score += 1
            macd_desc = "死叉"
        
        # 近期涨幅 (5日)
        returns_5d = (latest['Close'] / df['Close'].iloc[-6] - 1) * 100 if len(df) >= 6 else 0
        if 0 < returns_5d <= 10:
            score += 5
        elif returns_5d > 10:
            score += 3
        elif -5 <= returns_5d <= 0:
            score += 3
        
        return min(score, 25), f"{rsi_desc}, {macd_desc}"
    
    def score_volume(self, df: pd.DataFrame) -> Tuple[float, str]:
        """
        量能评分 (0-25分)
        """
        score = 0
        latest = df.iloc[-1]
        
        # 成交量放大
        vol_ratio = latest['Volume_Ratio']
        if vol_ratio >= 2.0:
            score += 10
            vol_desc = "放量"
        elif vol_ratio >= 1.5:
            score += 8
            vol_desc = "明显放量"
        elif vol_ratio >= 1.0:
            score += 6
            vol_desc = "正常"
        elif vol_ratio >= 0.7:
            score += 4
            vol_desc = "缩量"
        else:
            score += 2
            vol_desc = "严重缩量"
        
        # 量价配合
        price_up = (latest['Close'] > df['Close'].iloc[-6]) if len(df) >= 6 else False
        vol_up = vol_ratio > 1.2
        
        if price_up and vol_up:
            score += 10
            vol_desc += ", 量价齐升"
        elif price_up and vol_ratio < 0.8:
            score += 3
            vol_desc += ", 上涨缩量(警惕)"
        elif not price_up and vol_up:
            score += 5
            vol_desc += ", 放量下跌"
        
        # 布林带位置
        bb_pos = latest['BB_Position']
        if 0.3 <= bb_pos <= 0.7:
            score += 5
        elif bb_pos > 0.8:
            score += 2
        elif bb_pos < 0.2:
            score += 3
        
        return min(score, 25), vol_desc
    
    def analyze_stock(self, order_book_id: str, name: str = "") -> Optional[PatternScore]:
        """
        分析单只股票的综合评分
        """
        try:
            # 获取数据
            df = self.data_provider.get_stock_data(order_book_id)
            if df.empty or len(df) < 60:
                return None
            
            # 计算指标
            df = self.calculate_indicators(df)
            latest = df.iloc[-1]
            
            # 各维度评分
            trend_score, trend_desc = self.score_trend(df)
            pattern_score, pattern_name = self.score_pattern(df)
            momentum_score, momentum_desc = self.score_momentum(df)
            volume_score, volume_desc = self.score_volume(df)
            
            # 综合得分
            total_score = trend_score + pattern_score + momentum_score + volume_score
            
            # 判断信号类型
            if total_score >= 80:
                signal_type = "强烈买入"
            elif total_score >= 65:
                signal_type = "买入"
            elif total_score >= 50:
                signal_type = "偏买入"
            elif total_score >= 40:
                signal_type = "中性"
            elif total_score >= 25:
                signal_type = "偏卖出"
            else:
                signal_type = "卖出"
            
            # 计算目标价和止损
            atr = latest['ATR'] if not pd.isna(latest['ATR']) else latest['Close'] * 0.02
            
            if signal_type in ["强烈买入", "买入"]:
                target_price = latest['Close'] + atr * 3
                stop_loss = latest['Close'] - atr * 2
            elif signal_type in ["卖出", "偏卖出"]:
                target_price = latest['Close'] - atr * 3
                stop_loss = latest['Close'] + atr * 2
            else:
                target_price = latest['Close'] * 1.05
                stop_loss = latest['Close'] * 0.95
            
            # 提取纯数字代码
            symbol = order_book_id.split('.')[0]
            
            return PatternScore(
                symbol=symbol,
                name=name,
                score=round(total_score, 1),
                trend_score=round(trend_score, 1),
                pattern_score=round(pattern_score, 1),
                momentum_score=round(momentum_score, 1),
                volume_score=round(volume_score, 1),
                current_price=round(latest['Close'], 2),
                ma20=round(latest['MA_20'], 2),
                ma60=round(latest['MA_60'], 2),
                rsi=round(latest['RSI'], 1),
                macd_signal="金叉" if latest['MACD'] > latest['MACD_Signal'] else "死叉",
                pattern_type=pattern_name,
                signal_type=signal_type,
                target_price=round(target_price, 2),
                stop_loss=round(stop_loss, 2)
            )
            
        except Exception as e:
            self.logger.debug(f"  {order_book_id} 分析失败: {e}")
            return None
    
    def batch_analyze(self, symbols_df: pd.DataFrame) -> pd.DataFrame:
        """
        批量分析股票
        """
        self.logger.info("="*60)
        self.logger.info("中证A500技术形态批量分析 (RiceQuant)")
        self.logger.info("="*60)
        
        results = []
        total = len(symbols_df)
        
        self.logger.info(f"分析标的: {total} 只股票")
        self.logger.info("评分维度: 趋势(25) + 形态(25) + 动量(25) + 量能(25) = 总分(100)")
        self.logger.info("")
        
        for idx, row in symbols_df.iterrows():
            order_book_id = row.get('order_book_id', '')
            if not order_book_id and '代码' in row:
                # 如果没有order_book_id，尝试构造
                code = str(row['代码']).zfill(6)
                if code.startswith('6'):
                    order_book_id = f"{code}.XSHG"
                else:
                    order_book_id = f"{code}.XSHE"
            
            name = row.get('名称', '')
            
            result = self.analyze_stock(order_book_id, name)
            if result:
                results.append(result)
            
            if (idx + 1) % 10 == 0 or idx == len(symbols_df) - 1:
                self.logger.info(f"  进度: {idx + 1}/{total} ({(idx+1)/total*100:.1f}%)")
            
            # 添加延迟避免请求过快
            time.sleep(0.1)
        
        # 转换为DataFrame
        if results:
            df = pd.DataFrame([
                {
                    '排名': i + 1,
                    '代码': r.symbol,
                    '名称': r.name,
                    '综合得分': r.score,
                    '趋势得分': r.trend_score,
                    '形态得分': r.pattern_score,
                    '动量得分': r.momentum_score,
                    '量能得分': r.volume_score,
                    '当前价格': r.current_price,
                    'MA20': r.ma20,
                    'MA60': r.ma60,
                    'RSI': r.rsi,
                    'MACD': r.macd_signal,
                    '技术形态': r.pattern_type,
                    '交易信号': r.signal_type,
                    '目标价': r.target_price,
                    '止损价': r.stop_loss,
                }
                for i, r in enumerate(sorted(results, key=lambda x: x.score, reverse=True))
            ])
            
            return df
        
        return pd.DataFrame()


# ============================================================
# 主函数
# ============================================================
def main():
    """主程序"""
    print("="*60)
    print("中证A500技术形态综合打分系统 (RiceQuant版)")
    print("="*60)
    print()
    
    # 检查rqdatac
    if not RQ_AVAILABLE:
        print("错误: 未安装rqdatac，请先运行: pip install rqdatac")
        return
    
    # 创建分析器
    analyzer = ASharePatternScorer()
    
    # 获取中证A500成分股
    components = analyzer.data_provider.get_csi_a500_components()
    
    print(f"成分股数量: {len(components)}")
    print()
    
    # 批量分析
    print("【分析配置】")
    analyze_count = min(len(components), 100)  # 分析前100只
    print(f"分析数量: {analyze_count} 只 (演示模式)")
    print("提示: 修改代码中的 analyze_count 可调整分析数量")
    print()
    
    sample = components.head(analyze_count)
    
    results_df = analyzer.batch_analyze(sample)
    
    if not results_df.empty:
        # 输出Top20
        print("\n" + "="*60)
        print("技术形态综合打分 - TOP 20")
        print("="*60)
        
        top20 = results_df.head(20)
        
        for idx, row in top20.iterrows():
            print(f"\n【排名 {row['排名']}】{row['代码']} {row['名称']}")
            print(f"  综合得分: {row['综合得分']:.1f}/100")
            print(f"  ├─ 趋势得分: {row['趋势得分']:.1f}")
            print(f"  ├─ 形态得分: {row['形态得分']:.1f} ({row['技术形态']})")
            print(f"  ├─ 动量得分: {row['动量得分']:.1f} (RSI: {row['RSI']}, MACD: {row['MACD']})")
            print(f"  └─ 量能得分: {row['量能得分']:.1f}")
            print(f"  当前价格: ¥{row['当前价格']:.2f} | 信号: {row['交易信号']}")
            print(f"  目标价: ¥{row['目标价']:.2f} | 止损价: ¥{row['止损价']:.2f}")
        
        # 保存结果
        output_file = f"CSI_A500_Pattern_Top20_{date.today().isoformat()}.csv"
        top20.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\nTop20结果已保存: {output_file}")
        
        # 保存完整结果
        full_output = f"CSI_A500_Pattern_Full_{date.today().isoformat()}.csv"
        results_df.to_csv(full_output, index=False, encoding='utf-8-sig')
        print(f"完整结果已保存: {full_output}")
        
        # 统计
        print("\n" + "="*60)
        print("统计分析")
        print("="*60)
        print(f"总分析数量: {len(results_df)}")
        print(f"平均得分: {results_df['综合得分'].mean():.1f}")
        print(f"得分分布:")
        print(f"  强烈买入(80+): {len(results_df[results_df['综合得分'] >= 80])} 只")
        print(f"  买入(65-80): {len(results_df[(results_df['综合得分'] >= 65) & (results_df['综合得分'] < 80)])} 只")
        print(f"  中性(40-65): {len(results_df[(results_df['综合得分'] >= 40) & (results_df['综合得分'] < 65)])} 只")
        print(f"  卖出(<40): {len(results_df[results_df['综合得分'] < 40])} 只")
    
    print("\n" + "="*60)
    print("分析完成")
    print("="*60)


if __name__ == "__main__":
    main()
