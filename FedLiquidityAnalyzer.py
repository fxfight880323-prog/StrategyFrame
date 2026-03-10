"""
美联储流动性分析系统
========================
通过 FRED API 获取宏观数据，分析货币和财政政策的宽松/紧缩状态

核心指标：
1. WALCL - 美联储资产负债表总资产 (Fed Balance Sheet)
2. WTREGEN - 财政部一般账户 (TGA)
3. RRPONTSYD - 隔夜逆回购 (RRP)
4. DFII10 - 10年期TIPS收益率 (实际利率)

净流动性公式：Net Liquidity = WALCL - TGA - RRP
"""

import sys
import time
import logging
from dataclasses import dataclass
from datetime import date, timedelta, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import requests
import numpy as np


# ============================================================
# CONFIG
# ============================================================
FRED_API_KEY = "216cc2c0220dedeb572e8649f7a0ff0a"
FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

# 关键指标代码
SERIES_CODES = {
    "WALCL": "美联储资产负债表总资产 (Fed Balance Sheet)",
    "WTREGEN": "财政部一般账户 (TGA)",
    "RRPONTSYD": "隔夜逆回购 (RRP)",
    "DFII10": "10年期TIPS收益率 (实际利率)",
    "DFF": "联邦基金利率 (Fed Funds Rate)",
    "TOTRESNS": "总储备金 (Total Reserves)",
}

OUTPUT_DIR = "."
OUTPUT_XLSX = "fed_liquidity_analysis.xlsx"


# ============================================================
# Logging
# ============================================================
def setup_logger(name: str = "fed_liquidity", level: int = logging.INFO) -> logging.Logger:
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
# FRED Data Source
# ============================================================
class FREDDataSource:
    """美联储 FRED 数据源"""
    
    def __init__(self, api_key: str, logger: logging.Logger):
        self.api_key = api_key
        self.logger = logger
    
    def fetch_series(self, series_id: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取 FRED 数据序列
        
        Parameters:
            series_id: FRED 指标代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
        """
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start_date,
            "observation_end": end_date,
            # 不指定 frequency，使用原始频率
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                time.sleep(0.5)  # 避免频率限制
                response = requests.get(FRED_BASE_URL, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
                
                if "observations" not in data or not data["observations"]:
                    self.logger.warning(f"No data returned for {series_id}")
                    return pd.DataFrame()
                
                df = pd.DataFrame(data["observations"])
                df["date"] = pd.to_datetime(df["date"]).dt.date
                df["value"] = pd.to_numeric(df["value"], errors="coerce")
                df = df.dropna(subset=["value"])
                df["series_id"] = series_id
                df["series_name"] = SERIES_CODES.get(series_id, series_id)
                
                return df[["date", "series_id", "series_name", "value"]]
                
            except Exception as e:
                if attempt < max_retries - 1:
                    self.logger.warning(f"Retry {attempt + 1} for {series_id}: {e}")
                    time.sleep(2)
                else:
                    self.logger.error(f"Failed to fetch {series_id}: {e}")
                    return pd.DataFrame()
        
        return pd.DataFrame()
    
    def fetch_all_series(self, start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """获取所有关键指标"""
        self.logger.info("=" * 60)
        self.logger.info("获取美联储流动性数据...")
        self.logger.info("=" * 60)
        
        results = {}
        for series_id in SERIES_CODES.keys():
            self.logger.info(f"  获取 {series_id} - {SERIES_CODES[series_id]}")
            df = self.fetch_series(series_id, start_date, end_date)
            if not df.empty:
                results[series_id] = df
                self.logger.info(f"    成功: {len(df)} 条数据, 最新值: {df['value'].iloc[-1]:.2f}")
            else:
                self.logger.warning(f"    失败: 无数据")
        
        return results


# ============================================================
# Liquidity Analysis Engine
# ============================================================
class LiquidityAnalysisEngine:
    """流动性分析引擎"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def calculate_net_liquidity(self, data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """
        计算净流动性
        Net Liquidity = WALCL (Fed Balance Sheet) - WTREGEN (TGA) - RRPONTSYD (RRP)
        """
        self.logger.info("\n计算净流动性 (Net Liquidity)...")
        
        # 检查必需的数据
        required = ["WALCL", "WTREGEN", "RRPONTSYD"]
        for r in required:
            if r not in data:
                self.logger.error(f"缺少必需数据: {r}")
                return pd.DataFrame()
        
        # 合并数据
        walcl = data["WALCL"].set_index("date")["value"].rename("WALCL")
        tga = data["WTREGEN"].set_index("date")["value"].rename("TGA")
        rrp = data["RRPONTSYD"].set_index("date")["value"].rename("RRP")
        
        # 对齐日期（使用周频，因为TGA是周数据）
        df = pd.concat([walcl, tga, rrp], axis=1)
        df = df.dropna()
        
        # 计算净流动性（单位：十亿美元）
        df["NetLiquidity"] = df["WALCL"] - df["TGA"] - df["RRP"]
        
        # 计算变化率
        df["NetLiquidity_MoM"] = df["NetLiquidity"].pct_change(periods=30) * 100  # 月度变化
        df["NetLiquidity_QoQ"] = df["NetLiquidity"].pct_change(periods=90) * 100  # 季度变化
        
        self.logger.info(f"  最新净流动性: ${df['NetLiquidity'].iloc[-1]:,.0f} B")
        self.logger.info(f"  月度变化: {df['NetLiquidity_MoM'].iloc[-1]:+.2f}%")
        self.logger.info(f"  季度变化: {df['NetLiquidity_QoQ'].iloc[-1]:+.2f}%")
        
        return df.reset_index()
    
    def analyze_liquidity_regime(self, net_liquidity: pd.DataFrame, tips_data: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
        """
        分析流动性环境
        
        判断标准：
        1. 净流动性趋势（上升=宽松，下降=紧缩）
        2. TGA水平（高=财政抽水，低=财政放水）
        3. RRP水平（高=资金充裕但不愿投资，低=资金紧张）
        4. 实际利率（高=紧缩，低=宽松）
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("流动性环境分析")
        self.logger.info("=" * 60)
        
        latest = net_liquidity.iloc[-1]
        prev_month = net_liquidity.iloc[-30] if len(net_liquidity) >= 30 else net_liquidity.iloc[0]
        prev_quarter = net_liquidity.iloc[-90] if len(net_liquidity) >= 90 else net_liquidity.iloc[0]
        
        analysis = {
            "date": latest["date"],
            "net_liquidity": latest["NetLiquidity"],
            "walcl": latest["WALCL"],
            "tga": latest["TGA"],
            "rrp": latest["RRP"],
        }
        
        # 1. 净流动性趋势判断
        nl_change_1m = latest["NetLiquidity"] - prev_month["NetLiquidity"]
        nl_change_3m = latest["NetLiquidity"] - prev_quarter["NetLiquidity"]
        
        if nl_change_1m > 100:  # 月度增加超过100B
            liquidity_trend = "大幅宽松"
            liquidity_score = 2
        elif nl_change_1m > 0:
            liquidity_trend = "适度宽松"
            liquidity_score = 1
        elif nl_change_1m > -100:
            liquidity_trend = "适度紧缩"
            liquidity_score = -1
        else:
            liquidity_trend = "大幅紧缩"
            liquidity_score = -2
        
        analysis["liquidity_trend"] = liquidity_trend
        analysis["liquidity_score"] = liquidity_score
        analysis["nl_change_1m"] = nl_change_1m
        analysis["nl_change_3m"] = nl_change_3m
        
        self.logger.info(f"\n[净流动性趋势]")
        self.logger.info(f"  当前: ${latest['NetLiquidity']:,.0f} B")
        self.logger.info(f"  1个月变化: ${nl_change_1m:,.0f} B ({nl_change_1m/prev_month['NetLiquidity']*100:+.2f}%)")
        self.logger.info(f"  3个月变化: ${nl_change_3m:,.0f} B ({nl_change_3m/prev_quarter['NetLiquidity']*100:+.2f}%)")
        self.logger.info(f"  判断: {liquidity_trend}")
        
        # 2. 财政政策判断 (TGA)
        tga_level = latest["TGA"]
        if tga_level > 800:
            fiscal_stance = "财政抽水 (TGA高位)"
            fiscal_score = -2
        elif tga_level > 500:
            fiscal_stance = "财政中性偏紧"
            fiscal_score = -1
        elif tga_level > 200:
            fiscal_stance = "财政中性"
            fiscal_score = 0
        else:
            fiscal_stance = "财政放水 (TGA低位)"
            fiscal_score = 1
        
        analysis["fiscal_stance"] = fiscal_stance
        analysis["fiscal_score"] = fiscal_score
        analysis["tga_level"] = tga_level
        
        self.logger.info(f"\n[财政政策 - TGA]")
        self.logger.info(f"  当前: ${tga_level:,.0f} B")
        self.logger.info(f"  判断: {fiscal_stance}")
        
        # 3. 货币政策判断 (RRP)
        rrp_level = latest["RRP"]
        if rrp_level > 2000:
            monetary_stance = "资金充裕但需求不足 (RRP高位)"
            monetary_score = 1
        elif rrp_level > 1000:
            monetary_stance = "资金适中"
            monetary_score = 0
        elif rrp_level > 500:
            monetary_stance = "资金偏紧"
            monetary_score = -1
        else:
            monetary_stance = "资金紧张 (RRP低位)"
            monetary_score = -2
        
        analysis["monetary_stance"] = monetary_stance
        analysis["monetary_score"] = monetary_score
        analysis["rrp_level"] = rrp_level
        
        self.logger.info(f"\n[货币政策 - RRP]")
        self.logger.info(f"  当前: ${rrp_level:,.0f} B")
        self.logger.info(f"  判断: {monetary_stance}")
        
        # 4. 实际利率判断
        if tips_data is not None and not tips_data.empty:
            tips_rate = tips_data.iloc[-1]["value"]
            analysis["tips_rate"] = tips_rate
            
            if tips_rate > 2.0:
                real_rate_stance = "实际利率过高 (紧缩)"
                real_rate_score = -2
            elif tips_rate > 1.0:
                real_rate_stance = "实际利率适中偏紧"
                real_rate_score = -1
            elif tips_rate > 0:
                real_rate_stance = "实际利率适中"
                real_rate_score = 0
            else:
                real_rate_stance = "实际利率为负 (宽松)"
                real_rate_score = 2
            
            analysis["real_rate_stance"] = real_rate_stance
            analysis["real_rate_score"] = real_rate_score
            
            self.logger.info(f"\n[实际利率 - 10Y TIPS]")
            self.logger.info(f"  当前: {tips_rate:.2f}%")
            self.logger.info(f"  判断: {real_rate_stance}")
        
        # 5. 综合判断
        total_score = liquidity_score + fiscal_score + monetary_score
        if "real_rate_score" in analysis:
            total_score += analysis["real_rate_score"]
        
        analysis["total_score"] = total_score
        
        if total_score >= 3:
            overall_regime = "全面宽松 (Goldilocks)"
        elif total_score >= 1:
            overall_regime = "偏宽松"
        elif total_score >= -1:
            overall_regime = "中性"
        elif total_score >= -3:
            overall_regime = "偏紧缩"
        else:
            overall_regime = "全面紧缩 (Liquidity Squeeze)"
        
        analysis["overall_regime"] = overall_regime
        
        self.logger.info(f"\n[综合判断]")
        self.logger.info(f"  总得分: {total_score}")
        self.logger.info(f"  流动性环境: {overall_regime}")
        
        return analysis
    
    def generate_historical_context(self, net_liquidity: pd.DataFrame) -> pd.DataFrame:
        """生成历史背景分析"""
        df = net_liquidity.copy()
        
        # 计算历史分位数
        df["NL_Percentile"] = df["NetLiquidity"].rank(pct=True) * 100
        
        # 计算滚动标准差（波动率）
        df["NL_Volatility_30D"] = df["NetLiquidity"].rolling(30).std()
        
        # 计算趋势（20日移动平均）
        df["NL_MA20"] = df["NetLiquidity"].rolling(20).mean()
        df["NL_Trend"] = np.where(df["NetLiquidity"] > df["NL_MA20"], "上升", "下降")
        
        return df


# ============================================================
# Output
# ============================================================
def save_outputs(data: Dict[str, pd.DataFrame], net_liquidity: pd.DataFrame, 
                 analysis: Dict[str, Any], out_dir: str, xlsx_name: str, logger: logging.Logger):
    """保存分析结果"""
    import os
    os.makedirs(out_dir, exist_ok=True)
    
    xlsx_path = os.path.join(out_dir, xlsx_name)
    
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as w:
        # 原始数据
        for series_id, df in data.items():
            df.to_excel(w, sheet_name=series_id, index=False)
        
        # 净流动性
        net_liquidity.to_excel(w, sheet_name="NetLiquidity", index=False)
        
        # 分析报告
        analysis_df = pd.DataFrame([analysis])
        analysis_df.to_excel(w, sheet_name="Analysis", index=False)
    
    # CSV 输出
    net_liquidity.to_csv(os.path.join(out_dir, "net_liquidity.csv"), index=False)
    
    logger.info(f"\n结果已保存: {xlsx_path}")


# ============================================================
# Main
# ============================================================
def main():
    logger = setup_logger(level=logging.INFO)
    
    # 日期范围（获取最近2年数据）
    end_date = "2026-02-23"
    start_date = "2024-01-01"
    
    logger.info("=" * 60)
    logger.info("美联储流动性分析系统")
    logger.info(f"分析日期: {start_date} 至 {end_date}")
    logger.info("=" * 60)
    
    try:
        # 1. 获取数据
        fred = FREDDataSource(FRED_API_KEY, logger)
        data = fred.fetch_all_series(start_date, end_date)
        
        if not data:
            logger.error("未能获取任何数据")
            sys.exit(1)
        
        # 2. 计算净流动性
        engine = LiquidityAnalysisEngine(logger)
        net_liquidity = engine.calculate_net_liquidity(data)
        
        if net_liquidity.empty:
            logger.error("净流动性计算失败")
            sys.exit(1)
        
        # 3. 分析流动性环境
        tips_data = data.get("DFII10")
        analysis = engine.analyze_liquidity_regime(net_liquidity, tips_data)
        
        # 4. 历史背景
        net_liquidity = engine.generate_historical_context(net_liquidity)
        
        # 5. 保存结果
        save_outputs(data, net_liquidity, analysis, OUTPUT_DIR, OUTPUT_XLSX, logger)
        
        logger.info("\n分析完成！")
        
    except Exception as e:
        logger.exception(f"分析失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
