"""
CTA × 财报预期 综合分析系统
==============================
将技术分析（CTA）与财报预期分析结合，生成交叉策略信号

分析框架：
┌─────────────────────────────────────────────────────────────┐
│                    技术面 (CTA)                             │
│           强势           │           弱势                   │
├─────────────────────────┼───────────────────────────────────┤
│ 财报预期低 │   强力买入   │      观望/等待                 │
│ (被低估)   │  ★★★★★    │      ★★☆☆☆                   │
├─────────────────────────┼───────────────────────────────────┤
│ 财报预期高 │   谨慎持有   │      考虑卖出                  │
│ (已透支)   │   ★★★☆☆   │      ★☆☆☆☆                   │
└─────────────────────────┴───────────────────────────────────┘

输出：综合评分、策略建议、仓位配置、时间窗口
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
from pathlib import Path

import pandas as pd
import numpy as np


# ============================================================
# CONFIG
# ============================================================
# 输入文件配置
# 支持Excel和CSV两种格式
CTA_INPUT_FILE = "mag7_cta_analysis.xlsx"
CTA_INPUT_FILE_CSV = "mag7_cta_analysis.csv"
EARNINGS_INPUT_FILE = "us_stocks_earnings_expectation.xlsx"
EARNINGS_INPUT_FILE_CSV = "us_stocks_earnings_expectation.csv"

# 输出文件
OUTPUT_XLSX = "integrated_strategy_analysis.xlsx"
OUTPUT_DIR = "."

# 分析日期
END_DATE = "2026-02-23"

# 交叉分析权重
WEIGHT_TECHNICAL = 0.5      # 技术面权重
WEIGHT_EARNINGS = 0.3       # 财报预期权重  
WEIGHT_SYNERGY = 0.2        # 协同效应权重（信号一致性加分）

# 阈值配置
SCORE_THRESHOLD_STRONG_BUY = 85   # 强力买入阈值
SCORE_THRESHOLD_BUY = 70          # 买入阈值
SCORE_THRESHOLD_HOLD = 50         # 持有阈值
SCORE_THRESHOLD_SELL = 40         # 卖出阈值


# ============================================================
# 数据模型
# ============================================================
class StrategySignal(Enum):
    """策略信号"""
    STRONG_BUY = "强力买入"
    BUY = "买入"
    HOLD = "持有"
    REDUCE = "减仓"
    SELL = "卖出"
    AVOID = "回避"


@dataclass
class IntegratedAnalysis:
    """综合分析结果"""
    ticker: str
    
    # CTA技术面数据
    cta_score: float
    cta_signal: str
    cta_trend: str
    cta_rank: int
    
    # 财报预期数据
    earnings_expectation: str  # High/Low/Reasonable/Unknown
    eps_surprise_avg: float
    price_reaction_avg: float
    consistency_score: float   # 财报一致性评分
    
    # 交叉分析
    technical_score: float     # 技术面标准化分数 (0-100)
    fundamental_score: float   # 基本面标准化分数 (0-100)
    synergy_score: float       # 协同分数
    composite_score: float     # 综合评分
    
    # 策略输出
    signal: StrategySignal
    position_size: str         # 建议仓位
    time_horizon: str          # 时间窗口
    reasoning: str             # 逻辑说明
    risk_level: str            # 风险等级


# ============================================================
# Logging
# ============================================================
def setup_logger(name: str = "integrated_analyzer") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# 数据加载
# ============================================================
class DataLoader:
    """数据加载器"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def load_cta_data(self) -> pd.DataFrame:
        """加载CTA分析数据"""
        # 先尝试CSV格式
        if Path(CTA_INPUT_FILE_CSV).exists():
            try:
                df = pd.read_csv(CTA_INPUT_FILE_CSV)
                self.logger.info(f"加载CTA数据(CSV): {len(df)} 只股票")
                return df
            except Exception as e:
                self.logger.warning(f"CSV加载失败: {e}")
        
        # 再尝试Excel格式
        try:
            df = pd.read_excel(CTA_INPUT_FILE, sheet_name="CTA分析")
            self.logger.info(f"加载CTA数据(Excel): {len(df)} 只股票")
            return df
        except Exception as e:
            self.logger.error(f"加载CTA数据失败: {e}")
            return pd.DataFrame()
    
    def load_earnings_data(self) -> pd.DataFrame:
        """加载财报预期数据"""
        # 先尝试CSV格式
        if Path(EARNINGS_INPUT_FILE_CSV).exists():
            try:
                df = pd.read_csv(EARNINGS_INPUT_FILE_CSV)
                self.logger.info(f"加载财报数据(CSV): {len(df)} 只股票")
                return df
            except Exception as e:
                self.logger.warning(f"CSV加载失败: {e}")
        
        # 再尝试Excel格式
        try:
            sheets_to_try = ["财报预期", "预期分析", "earnings_expectation"]
            for sheet in sheets_to_try:
                try:
                    df = pd.read_excel(EARNINGS_INPUT_FILE, sheet_name=sheet)
                    self.logger.info(f"加载财报数据({sheet}): {len(df)} 只股票")
                    return df
                except:
                    continue
            df = pd.read_excel(EARNINGS_INPUT_FILE, sheet_name=0)
            self.logger.info(f"加载财报数据(默认sheet): {len(df)} 只股票")
            return df
        except Exception as e:
            self.logger.error(f"加载财报数据失败: {e}")
            return pd.DataFrame()


# ============================================================
# 交叉分析引擎
# ============================================================
class CrossAnalyzer:
    """交叉分析引擎"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def normalize_cta_score(self, cta_df: pd.DataFrame) -> Dict[str, float]:
        """将CTA评分标准化为0-100分"""
        scores = {}
        max_score = cta_df['总评分'].max() if '总评分' in cta_df.columns else 100
        min_score = cta_df['总评分'].min() if '总评分' in cta_df.columns else 0
        
        for _, row in cta_df.iterrows():
            ticker = row.get('Ticker', row.get('代码', ''))
            raw_score = row.get('总评分', 50)
            # 标准化到0-100
            normalized = (raw_score - min_score) / (max_score - min_score) * 100 if max_score > min_score else 50
            scores[ticker] = normalized
        
        return scores
    
    def calculate_fundamental_score(self, earnings_row: pd.Series) -> float:
        """计算基本面分数 (0-100)"""
        score = 50  # 基准分
        
        # 根据预期类型调整
        expectation = str(earnings_row.get('预期判断', '')).lower()
        if 'low' in expectation or '低' in expectation or '悲观' in expectation:
            score += 25  # 预期低 = 潜在上涨空间
        elif 'high' in expectation or '高' in expectation or '透支' in expectation:
            score -= 20  # 预期高 = 回调风险
        elif 'reasonable' in expectation or '合理' in expectation:
            score += 5   # 预期合理
        
        # 根据历史一致性调整
        consistency = earnings_row.get('一致性评分', 0.5)
        score += (consistency - 0.5) * 20  # -10 到 +10
        
        # 根据历史超预期概率调整
        eps_surprise = earnings_row.get('平均EPS惊喜', 0)
        if eps_surprise > 0.1:  # 经常超预期
            score += 10
        elif eps_surprise < -0.05:  # 经常低于预期
            score -= 10
        
        return max(0, min(100, score))
    
    def calculate_synergy_score(
        self, 
        tech_score: float, 
        fund_score: float,
        cta_signal: str,
        earnings_expectation: str
    ) -> float:
        """计算协同分数（信号一致性奖励/冲突惩罚）"""
        synergy = 0
        
        # 信号一致性判断
        tech_bullish = tech_score > 60 or cta_signal in ['BUY', '买入', '强力买入']
        tech_bearish = tech_score < 40 or cta_signal in ['SELL', '卖出', '卖出信号']
        
        fund_bullish = fund_score > 60  # 基本面好（预期低+超预期历史）
        fund_bearish = fund_score < 40  # 基本面差（预期高+低预期历史）
        
        # 同向信号奖励
        if tech_bullish and fund_bullish:
            synergy = 15  # 技术面+基本面双牛 = 强力买入
        elif tech_bearish and fund_bearish:
            synergy = 10  # 技术面+基本面双熊 = 确认卖出
        elif tech_bullish and fund_bearish:
            synergy = -10  # 技术面好但基本面差 = 冲突，谨慎
        elif tech_bearish and fund_bullish:
            synergy = -5   # 技术面差但基本面好 = 等待机会
        
        return synergy
    
    def determine_signal(self, composite_score: float, risk_factors: List[str]) -> StrategySignal:
        """确定最终信号"""
        if composite_score >= SCORE_THRESHOLD_STRONG_BUY:
            return StrategySignal.STRONG_BUY
        elif composite_score >= SCORE_THRESHOLD_BUY:
            return StrategySignal.BUY
        elif composite_score >= SCORE_THRESHOLD_HOLD:
            return StrategySignal.HOLD
        elif composite_score >= SCORE_THRESHOLD_SELL:
            return StrategySignal.REDUCE
        else:
            return StrategySignal.SELL
    
    def get_position_size(self, signal: StrategySignal, risk_level: str) -> str:
        """根据信号和风险确定仓位建议"""
        sizes = {
            (StrategySignal.STRONG_BUY, "Low"): "15-20%",
            (StrategySignal.STRONG_BUY, "Medium"): "10-15%",
            (StrategySignal.STRONG_BUY, "High"): "5-10%",
            (StrategySignal.BUY, "Low"): "10-15%",
            (StrategySignal.BUY, "Medium"): "8-12%",
            (StrategySignal.BUY, "High"): "5-8%",
            (StrategySignal.HOLD, "Low"): "维持现有",
            (StrategySignal.HOLD, "Medium"): "维持现有",
            (StrategySignal.HOLD, "High"): "适度减仓",
            (StrategySignal.REDUCE, "Low"): "减仓50%",
            (StrategySignal.REDUCE, "Medium"): "减仓50%",
            (StrategySignal.REDUCE, "High"): "减仓70%",
            (StrategySignal.SELL, "Low"): "清仓",
            (StrategySignal.SELL, "Medium"): "清仓",
            (StrategySignal.SELL, "High"): "清仓",
        }
        return sizes.get((signal, risk_level), "观望")
    
    def get_time_horizon(self, signal: StrategySignal, earnings_date: Optional[str]) -> str:
        """确定时间窗口"""
        if earnings_date:
            try:
                ed = pd.to_datetime(earnings_date)
                days_to_earnings = (ed - pd.Timestamp.now()).days
                if days_to_earnings <= 7:
                    return f"财报前{days_to_earnings}天 (事件驱动)"
                else:
                    return f"财报前持仓，目标日期: {earnings_date[:10]}"
            except:
                pass
        
        horizons = {
            StrategySignal.STRONG_BUY: "2-4周 (中期持有)",
            StrategySignal.BUY: "2-4周 (中期持有)",
            StrategySignal.HOLD: "维持现有仓位",
            StrategySignal.REDUCE: "1周内减仓",
            StrategySignal.SELL: "立即清仓",
        }
        return horizons.get(signal, "观望")
    
    def generate_reasoning(
        self,
        ticker: str,
        tech_score: float,
        fund_score: float,
        synergy: float,
        cta_signal: str,
        earnings_exp: str
    ) -> str:
        """生成分析逻辑说明"""
        parts = []
        
        # 技术面解读
        if tech_score >= 70:
            parts.append(f"技术面强势(评分{tech_score:.0f})")
        elif tech_score >= 50:
            parts.append(f"技术面中性(评分{tech_score:.0f})")
        else:
            parts.append(f"技术面弱势(评分{tech_score:.0f})")
        
        # 基本面解读
        if 'low' in str(earnings_exp).lower() or '低' in str(earnings_exp):
            parts.append("财报预期被低估")
        elif 'high' in str(earnings_exp).lower() or '高' in str(earnings_exp):
            parts.append("财报预期已透支")
        elif 'reasonable' in str(earnings_exp).lower() or '合理' in str(earnings_exp):
            parts.append("财报预期合理")
        
        # 协同解读
        if synergy > 10:
            parts.append("技术面与基本面共振")
        elif synergy < -5:
            parts.append("技术面与基本面背离，需谨慎")
        
        return "; ".join(parts) if parts else "数据不足"
    
    def analyze(
        self, 
        cta_df: pd.DataFrame, 
        earnings_df: pd.DataFrame
    ) -> List[IntegratedAnalysis]:
        """执行交叉分析"""
        self.logger.info("=" * 60)
        self.logger.info("开始CTA × 财报预期 交叉分析")
        self.logger.info("=" * 60)
        
        results = []
        
        # 标准化CTA评分
        tech_scores = self.normalize_cta_score(cta_df)
        
        # 构建财报数据字典
        earnings_dict = {}
        ticker_col = 'Ticker' if 'Ticker' in earnings_df.columns else earnings_df.columns[0]
        for _, row in earnings_df.iterrows():
            ticker = str(row.get(ticker_col, '')).strip().upper()
            if ticker:
                earnings_dict[ticker] = row
        
        self.logger.info(f"CTA数据覆盖: {len(tech_scores)} 只")
        self.logger.info(f"财报数据覆盖: {len(earnings_dict)} 只")
        
        # 遍历CTA数据进行交叉分析
        for ticker in tech_scores:
            tech_score = tech_scores[ticker]
            
            # 获取CTA详细信息
            cta_row = cta_df[cta_df['Ticker'] == ticker] if 'Ticker' in cta_df.columns else None
            if cta_row is None or cta_row.empty:
                continue
                
            cta_signal = cta_row.iloc[0].get('信号', 'HOLD')
            cta_trend = cta_row.iloc[0].get('趋势', 'Neutral')
            cta_rank = cta_row.iloc[0].get('排名', 999)
            
            # 获取财报数据
            earnings_row = earnings_dict.get(ticker)
            
            if earnings_row is not None:
                # 计算基本面分数
                fund_score = self.calculate_fundamental_score(earnings_row)
                earnings_exp = earnings_row.get('预期判断', 'Unknown')
                eps_surprise = earnings_row.get('平均EPS惊喜', 0)
                price_reaction = earnings_row.get('平均价格反应', 0)
                consistency = earnings_row.get('一致性评分', 0.5)
                earnings_date = earnings_row.get('下次财报日期', None)
            else:
                # 无财报数据，使用默认值
                fund_score = 50
                earnings_exp = "Unknown"
                eps_surprise = 0
                price_reaction = 0
                consistency = 0.5
                earnings_date = None
            
            # 计算协同分数
            synergy = self.calculate_synergy_score(
                tech_score, fund_score, cta_signal, earnings_exp
            )
            
            # 计算综合评分
            composite = (
                tech_score * WEIGHT_TECHNICAL +
                fund_score * WEIGHT_EARNINGS +
                (50 + synergy) * WEIGHT_SYNERGY  # 将synergy转换为0-100基准
            )
            
            # 风险因素
            risk_factors = []
            if tech_score < 40:
                risk_factors.append("技术面弱势")
            if 'high' in str(earnings_exp).lower() or '高' in str(earnings_exp):
                risk_factors.append("财报预期透支")
            if consistency < 0.3:
                risk_factors.append("财报表现不稳定")
            
            risk_level = "High" if len(risk_factors) >= 2 else ("Medium" if risk_factors else "Low")
            
            # 确定信号
            signal = self.determine_signal(composite, risk_factors)
            
            # 生成分析结果
            analysis = IntegratedAnalysis(
                ticker=ticker,
                cta_score=tech_score,
                cta_signal=str(cta_signal),
                cta_trend=str(cta_trend),
                cta_rank=int(cta_rank) if pd.notna(cta_rank) else 999,
                earnings_expectation=str(earnings_exp),
                eps_surprise_avg=float(eps_surprise) if pd.notna(eps_surprise) else 0,
                price_reaction_avg=float(price_reaction) if pd.notna(price_reaction) else 0,
                consistency_score=float(consistency) if pd.notna(consistency) else 0.5,
                technical_score=tech_score,
                fundamental_score=fund_score,
                synergy_score=synergy,
                composite_score=composite,
                signal=signal,
                position_size=self.get_position_size(signal, risk_level),
                time_horizon=self.get_time_horizon(signal, earnings_date),
                reasoning=self.generate_reasoning(
                    ticker, tech_score, fund_score, synergy, cta_signal, earnings_exp
                ),
                risk_level=risk_level
            )
            
            results.append(analysis)
        
        # 按综合评分排序
        results.sort(key=lambda x: x.composite_score, reverse=True)
        
        self.logger.info(f"✓ 交叉分析完成: {len(results)} 只股票")
        return results


# ============================================================
# 报告生成
# ============================================================
class ReportGenerator:
    """报告生成器"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def create_dataframe(self, analyses: List[IntegratedAnalysis]) -> pd.DataFrame:
        """创建分析结果DataFrame"""
        data = []
        for a in analyses:
            data.append({
                '代码': a.ticker,
                '综合评分': round(a.composite_score, 1),
                '策略信号': a.signal.value,
                '技术面评分': round(a.technical_score, 1),
                'CTA信号': a.cta_signal,
                'CTA排名': a.cta_rank,
                '基本面评分': round(a.fundamental_score, 1),
                '财报预期': a.earnings_expectation,
                '协同得分': round(a.synergy_score, 1),
                '建议仓位': a.position_size,
                '时间窗口': a.time_horizon,
                '风险等级': a.risk_level,
                '分析逻辑': a.reasoning,
                'EPS惊喜历史': round(a.eps_surprise_avg * 100, 1),
                '财报价格反应': round(a.price_reaction_avg * 100, 1),
            })
        
        return pd.DataFrame(data)
    
    def generate_excel(self, analyses: List[IntegratedAnalysis]) -> str:
        """生成Excel报告"""
        df = self.create_dataframe(analyses)
        
        output_path = Path(OUTPUT_DIR) / OUTPUT_XLSX
        
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 主分析表
            df.to_excel(writer, sheet_name='综合分析', index=False)
            
            # 按信号分类
            for signal in StrategySignal:
                subset = df[df['策略信号'] == signal.value]
                if not subset.empty:
                    sheet_name = signal.value[:10]  # Excel sheet名长度限制
                    subset.to_excel(writer, sheet_name=sheet_name, index=False)
            
            # 矩阵视图
            matrix_data = []
            for a in analyses[:50]:  # 前50只
                matrix_data.append({
                    '代码': a.ticker,
                    '技术面': '强势' if a.technical_score >= 60 else ('弱势' if a.technical_score < 40 else '中性'),
                    '基本面': a.earnings_expectation,
                    '信号': a.signal.value,
                    '评分': round(a.composite_score, 1),
                })
            pd.DataFrame(matrix_data).to_excel(writer, sheet_name='矩阵视图', index=False)
        
        self.logger.info(f"✓ 报告已保存: {output_path}")
        return str(output_path)
    
    def print_summary(self, analyses: List[IntegratedAnalysis]):
        """打印摘要"""
        print("\n" + "=" * 80)
        print("CTA × 财报预期 交叉分析摘要")
        print("=" * 80)
        
        # 信号统计
        signal_counts = {}
        for a in analyses:
            signal_counts[a.signal.value] = signal_counts.get(a.signal.value, 0) + 1
        
        print("\n【信号分布】")
        for signal, count in sorted(signal_counts.items(), key=lambda x: -x[1]):
            bar = "█" * (count * 2)
            print(f"  {signal:12s}: {count:3d}只 {bar}")
        
        # 强力买入推荐
        strong_buys = [a for a in analyses if a.signal == StrategySignal.STRONG_BUY]
        if strong_buys:
            print(f"\n【强力买入推荐】({len(strong_buys)}只)")
            for a in strong_buys[:5]:
                print(f"  #{a.cta_rank:2d} {a.ticker:6s} | 综合{a.composite_score:.0f}分 | {a.reasoning[:40]}...")
        
        # 卖出警告
        sells = [a for a in analyses if a.signal in [StrategySignal.SELL, StrategySignal.REDUCE]]
        if sells:
            print(f"\n【卖出/减仓警告】({len(sells)}只)")
            for a in sells[:5]:
                print(f"  #{a.cta_rank:2d} {a.ticker:6s} | 综合{a.composite_score:.0f}分 | {a.reasoning[:40]}...")
        
        # 重点关注（技术面与基本面背离）
        divergences = [a for a in analyses if abs(a.synergy_score) >= 10]
        if divergences:
            print(f"\n【重点关注】技术面与基本面背离 ({len(divergences)}只)")
            for a in divergences[:3]:
                direction = "共振" if a.synergy_score > 0 else "背离"
                print(f"  {a.ticker:6s} | {direction} (协同{a.synergy_score:+.0f}) | {a.reasoning[:35]}...")
        
        print("\n" + "=" * 80)


# ============================================================
# 主程序
# ============================================================
def main():
    logger = setup_logger()
    
    # 加载数据
    loader = DataLoader(logger)
    cta_df = loader.load_cta_data()
    earnings_df = loader.load_earnings_data()
    
    if cta_df.empty:
        logger.error("CTA数据为空，无法继续分析")
        return
    
    # 交叉分析
    analyzer = CrossAnalyzer(logger)
    results = analyzer.analyze(cta_df, earnings_df)
    
    if not results:
        logger.warning("分析结果为空")
        return
    
    # 生成报告
    generator = ReportGenerator(logger)
    output_path = generator.generate_excel(results)
    generator.print_summary(results)
    
    logger.info(f"分析完成！共处理 {len(results)} 只股票")


if __name__ == "__main__":
    main()
