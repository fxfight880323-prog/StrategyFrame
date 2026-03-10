"""
财报期权交易策略分析模块
==========================
基于IV、Straddle定价和市场预期，提供期权交易决策建议

核心逻辑：
1. 判断IV是否偏高 (IV Rank > 60%)
2. 计算市场预期波动 (Straddle%)
3. 对比实际预期 vs 市场预期
4. 给出买/卖波动策略建议

适用于: 财报季期权交易决策
"""

import sys
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

# 设置编码以支持Windows输出
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np


# ============================================================
# CONFIG
# ============================================================
# IV阈值
IV_RANK_HIGH = 60  # IV Rank高于60%视为偏高
IV_RANK_LOW = 40   # IV Rank低于40%视为偏低

# 波动率判断阈值
STRADDLE_PREMIUM_THRESHOLD = 0.08  # Straddle溢价8%作为判断基准

# 风险评估
HIGH_RISK_TICKERS = ['NVDA', 'TSLA', 'AMD', 'PLTR', 'COIN']  # 高风险标的


# ============================================================
# 数据模型
# ============================================================
class OptionsStrategy(Enum):
    """期权策略枚举"""
    SELL_STRADDLE = "卖跨式 (Short Straddle)"
    SELL_STRANGLE = "卖宽跨式 (Short Strangle)"
    IRON_CONDOR = " Iron Condor"
    BUY_STRADDLE = "买跨式 (Long Straddle)"
    BUY_STRANGLE = "买宽跨式 (Long Strangle)"
    VERTICAL_SPREAD = "垂直价差 (Vertical Spread)"
    NO_TRADE = "不交易 (No Trade)"


@dataclass
class EarningsOptionsAnalysis:
    """财报期权分析结果"""
    ticker: str
    earnings_date: date
    
    # IV数据
    iv_current: float
    iv_rank: float
    iv_percentile: float
    
    # Straddle数据
    atm_call_price: float
    atm_put_price: float
    stock_price: float
    straddle_price: float
    straddle_pct: float
    
    # 市场预期
    market_expected_move: float
    
    # 用户判断 (需要输入)
    user_expected_move: Optional[float] = None
    
    # IV状态标记 (带默认值)
    iv_high: bool = False
    iv_low: bool = False
    
    # 策略建议
    recommended_strategy: OptionsStrategy = OptionsStrategy.NO_TRADE
    strategy_logic: str = ""
    
    # 风险评估
    risk_level: str = "Medium"
    risk_factors: List[str] = None
    
    # 执行建议
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    
    def __post_init__(self):
        if self.risk_factors is None:
            self.risk_factors = []


# ============================================================
# 分析引擎
# ============================================================
class OptionsEarningsEngine:
    """财报期权分析引擎"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
    
    def calculate_straddle_metrics(self, 
                                   stock_price: float,
                                   atm_call_price: float, 
                                   atm_put_price: float) -> Dict[str, float]:
        """
        计算Straddle相关指标
        
        参数:
            stock_price: 当前股价
            atm_call_price: ATM看涨期权价格
            atm_put_price: ATM看跌期权价格
        
        返回:
            {
                'straddle_price': Straddle总价格,
                'straddle_pct': Straddle占股价百分比,
                'market_expected_move': 市场预期波动幅度
            }
        """
        straddle_price = atm_call_price + atm_put_price
        straddle_pct = straddle_price / stock_price
        
        # 市场预期波动 (Straddle% / 2 作为单方向预期)
        market_expected_move = straddle_pct / 2
        
        return {
            'straddle_price': straddle_price,
            'straddle_pct': straddle_pct,
            'market_expected_move': market_expected_move
        }
    
    def assess_iv_level(self, iv_rank: float) -> Tuple[bool, bool]:
        """
        评估IV水平
        
        返回: (is_high, is_low)
        """
        is_high = iv_rank > IV_RANK_HIGH
        is_low = iv_rank < IV_RANK_LOW
        return is_high, is_low
    
    def assess_risk_level(self, ticker: str, iv_rank: float, 
                         straddle_pct: float) -> Tuple[str, List[str]]:
        """
        评估交易风险等级
        
        返回: (risk_level, risk_factors)
        """
        risk_factors = []
        
        # 检查高风险标的
        if ticker in HIGH_RISK_TICKERS:
            risk_factors.append(f"{ticker}为高风险标的，过往财报波动极大")
        
        # IV过高风险
        if iv_rank > 80:
            risk_factors.append("IV Rank极高(>80%)，可能存在异常事件")
        
        # Straddle定价过高
        if straddle_pct > 0.15:
            risk_factors.append("Straddle定价过高(>15%)，卖波动风险大")
        
        # 确定风险等级
        if len(risk_factors) >= 2:
            risk_level = "High"
        elif len(risk_factors) == 1:
            risk_level = "Medium-High"
        else:
            risk_level = "Medium"
        
        return risk_level, risk_factors
    
    def determine_strategy(self, 
                          iv_high: bool,
                          market_expected: float,
                          user_expected: Optional[float],
                          risk_level: str) -> Tuple[OptionsStrategy, str]:
        """
        决策流程核心逻辑
        
        决策树:
        1. IV是否偏高? (IV Rank > 60%)
        2. 市场预期 vs 用户预期
        3. 风险评估
        """
        # 如果没有用户预期，基于IV和市场预期判断
        if user_expected is None:
            # 默认假设：如果IV高，市场预期可能被高估
            if iv_high:
                strategy = OptionsStrategy.SELL_STRANGLE
                logic = "IV偏高(>60%)，默认卖波动，收取时间价值"
            else:
                strategy = OptionsStrategy.NO_TRADE
                logic = "信息不足，建议观望"
            return strategy, logic
        
        # 核心决策逻辑
        expected_diff = user_expected - market_expected
        
        # Case 1: IV高 + 市场预期 > 用户预期 = 卖波动
        if iv_high and market_expected > user_expected * 1.2:  # 市场预期比用户高20%以上
            if risk_level == "High":
                strategy = OptionsStrategy.IRON_CONDOR
                logic = "IV高+市场预期过高，但风险高，用Iron Condor限险"
            else:
                strategy = OptionsStrategy.SELL_STRANGLE
                logic = "IV高+市场预期显著高于实际，卖宽跨式收时间价值"
        
        # Case 2: IV不高 + 用户预期 > 市场预期 = 买波动
        elif not iv_high and user_expected > market_expected * 1.3:  # 用户预期比市场高30%以上
            strategy = OptionsStrategy.BUY_STRANGLE
            logic = "市场预期过低，实际波动将更大，买宽跨式博波动"
        
        # Case 3: IV高 + 用户不确定 = 不做
        elif iv_high and user_expected is None:
            strategy = OptionsStrategy.NO_TRADE
            logic = "IV高但不确定方向，观望为主"
        
        # Case 4: 市场预期合理 = 不做
        elif abs(expected_diff) < 0.02:  # 差距小于2%
            strategy = OptionsStrategy.NO_TRADE
            logic = "市场预期与判断接近，无交易机会"
        
        # Default
        else:
            strategy = OptionsStrategy.NO_TRADE
            logic = "条件不满足，建议观望"
        
        return strategy, logic
    
    def calculate_position_size(self, 
                               account_size: float,
                               risk_per_trade: float = 0.02,
                               max_position_pct: float = 0.10) -> Dict[str, float]:
        """
        计算仓位大小
        
        参数:
            account_size: 账户总规模
            risk_per_trade: 单笔交易风险(默认2%)
            max_position_pct: 最大仓位(默认10%)
        """
        max_risk_amount = account_size * risk_per_trade
        max_position_amount = account_size * max_position_pct
        
        return {
            'max_risk_amount': max_risk_amount,
            'max_position_amount': max_position_amount,
            'suggested_contracts': int(max_position_amount / 5000)  # 假设每手约5000美元
        }
    
    def analyze_stock(self,
                     ticker: str,
                     earnings_date: date,
                     stock_price: float,
                     atm_call_price: float,
                     atm_put_price: float,
                     iv_current: float,
                     iv_rank: float,
                     iv_percentile: float,
                     user_expected_move: Optional[float] = None,
                     account_size: float = 100000) -> EarningsOptionsAnalysis:
        """
        分析单只股票的财报期权策略
        """
        # 1. 计算Straddle指标
        straddle_metrics = self.calculate_straddle_metrics(
            stock_price, atm_call_price, atm_put_price
        )
        
        # 2. 评估IV水平
        iv_high, iv_low = self.assess_iv_level(iv_rank)
        
        # 3. 评估风险
        risk_level, risk_factors = self.assess_risk_level(
            ticker, iv_rank, straddle_metrics['straddle_pct']
        )
        
        # 4. 确定策略
        strategy, logic = self.determine_strategy(
            iv_high,
            straddle_metrics['market_expected_move'],
            user_expected_move,
            risk_level
        )
        
        # 5. 计算仓位
        position = self.calculate_position_size(account_size)
        
        # 6. 创建分析结果
        analysis = EarningsOptionsAnalysis(
            ticker=ticker,
            earnings_date=earnings_date,
            iv_current=iv_current,
            iv_rank=iv_rank,
            iv_percentile=iv_percentile,
            iv_high=iv_high,
            iv_low=iv_low,
            atm_call_price=atm_call_price,
            atm_put_price=atm_put_price,
            stock_price=stock_price,
            straddle_price=straddle_metrics['straddle_price'],
            straddle_pct=straddle_metrics['straddle_pct'],
            market_expected_move=straddle_metrics['market_expected_move'],
            user_expected_move=user_expected_move,
            recommended_strategy=strategy,
            strategy_logic=logic,
            risk_level=risk_level,
            risk_factors=risk_factors
        )
        
        return analysis


# ============================================================
# 示例数据和演示
# ============================================================
def create_sample_analysis():
    """创建示例分析"""
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)
    
    engine = OptionsEarningsEngine(logger)
    
    # 示例1: NVDA (高风险，谨慎卖波动)
    nvda = engine.analyze_stock(
        ticker="NVDA",
        earnings_date=date(2026, 2, 26),
        stock_price=191.55,
        atm_call_price=12.50,
        atm_put_price=11.80,
        iv_current=65.0,
        iv_rank=75.0,
        iv_percentile=80.0,
        user_expected_move=0.06,  # 用户预期6%波动
        account_size=100000
    )
    
    # 示例2: AAPL (适中风险)
    aapl = engine.analyze_stock(
        ticker="AAPL",
        earnings_date=date(2026, 2, 27),
        stock_price=266.18,
        atm_call_price=8.20,
        atm_put_price=7.80,
        iv_current=35.0,
        iv_rank=55.0,
        iv_percentile=55.0,
        user_expected_move=0.04,  # 用户预期4%波动
        account_size=100000
    )
    
    # 示例3: JPM (低风险，适合卖波动)
    jpm = engine.analyze_stock(
        ticker="JPM",
        earnings_date=date(2026, 2, 28),
        stock_price=245.0,
        atm_call_price=5.50,
        atm_put_price=5.20,
        iv_current=28.0,
        iv_rank=65.0,
        iv_percentile=70.0,
        user_expected_move=0.025,  # 用户预期2.5%波动
        account_size=100000
    )
    
    return [nvda, aapl, jpm]


def print_analysis_report(analyses: List[EarningsOptionsAnalysis]):
    """打印分析报告"""
    print("\n" + "="*100)
    print("财报期权交易策略分析报告")
    print("="*100)
    
    for analysis in analyses:
        print(f"\n【{analysis.ticker}】财报日期: {analysis.earnings_date}")
        print("-"*100)
        
        # 基本信息
        print(f"股价: ${analysis.stock_price:.2f}")
        print(f"ATM Call: ${analysis.atm_call_price:.2f} | ATM Put: ${analysis.atm_put_price:.2f}")
        print(f"Straddle价格: ${analysis.straddle_price:.2f} ({analysis.straddle_pct:.1%})")
        
        # IV分析
        iv_status = "偏高" if analysis.iv_high else ("偏低" if analysis.iv_low else "正常")
        print(f"\nIV分析:")
        print(f"  当前IV: {analysis.iv_current:.1f}% | IV Rank: {analysis.iv_rank:.0f}% | 百分位: {analysis.iv_percentile:.0f}%")
        print(f"  IV状态: {iv_status}")
        
        # 市场预期
        print(f"\n市场预期:")
        print(f"  隐含波动: ±{analysis.market_expected_move:.1%}")
        if analysis.user_expected_move:
            print(f"  你的预期: ±{analysis.user_expected_move:.1%}")
            diff = analysis.user_expected_move - analysis.market_expected_move
            print(f"  差异: {diff:+.1%} ({'市场预期过高' if diff < 0 else '市场预期过低'})")
        
        # 策略建议
        print(f"\n策略建议: {analysis.recommended_strategy.value}")
        print(f"逻辑: {analysis.strategy_logic}")
        
        # 风险评估
        print(f"\n风险等级: {analysis.risk_level}")
        if analysis.risk_factors:
            print("风险因素:")
            for factor in analysis.risk_factors:
                print(f"  ⚠️ {factor}")
        
        print("-"*100)


# ============================================================
# 快速判断工具
# ============================================================
def quick_decision_tool():
    """交互式快速判断工具"""
    print("\n" + "="*80)
    print("财报期权交易快速判断工具")
    print("="*80)
    print("\n请回答以下问题:")
    
    # 问题1
    ticker = input("\n1. 股票代码: ").upper().strip()
    
    # 问题2
    iv_rank = float(input("2. IV Rank (0-100): "))
    
    # 问题3
    stock_price = float(input("3. 当前股价: $"))
    call_price = float(input("4. ATM Call价格: $"))
    put_price = float(input("5. ATM Put价格: $"))
    
    # 计算Straddle%
    straddle_price = call_price + put_price
    straddle_pct = straddle_price / stock_price
    market_expected = straddle_pct / 2
    
    print(f"\n6. 计算结果:")
    print(f"   Straddle价格: ${straddle_price:.2f}")
    print(f"   Straddle占比: {straddle_pct:.1%}")
    print(f"   市场预期波动: ±{market_expected:.1%}")
    
    # 问题4
    user_expected = float(input(f"\n7. 你判断的实际波动 (如6%输入0.06): "))
    
    # 判断
    print("\n" + "="*80)
    print("决策分析")
    print("="*80)
    
    if iv_rank > 60:
        print(f"✓ IV Rank {iv_rank:.0f}% > 60%, IV偏高")
        
        if market_expected > user_expected * 1.2:
            print(f"✓ 市场预期({market_expected:.1%}) > 你的预期({user_expected:.1%})")
            print("\n" + "="*80)
            print("🎯 策略建议: 卖波动 (SELL VOLATILITY)")
            print("="*80)
            print("推荐策略:")
            if ticker in HIGH_RISK_TICKERS:
                print("  • Iron Condor (风险限制)")
            else:
                print("  • 卖宽跨式 (Short Strangle)")
                print("  • 或卖跨式 (Short Straddle)")
            print("\n逻辑: 市场预期过高，实际波动将小于预期，收取时间价值")
        else:
            print(f"✗ 市场预期({market_expected:.1%}) <= 你的预期({user_expected:.1%})")
            print("\n不建议卖波动")
    else:
        print(f"✗ IV Rank {iv_rank:.0f}% <= 60%, IV不高")
        
        if user_expected > market_expected * 1.3:
            print(f"✓ 你的预期({user_expected:.1%}) > 市场预期({market_expected:.1%})")
            print("\n" + "="*80)
            print("🎯 策略建议: 买波动 (BUY VOLATILITY)")
            print("="*80)
            print("推荐策略:")
            print("  • 买宽跨式 (Long Strangle)")
            print("  • 或买跨式 (Long Straddle)")
            print("\n逻辑: 市场预期过低，实际波动将大于预期，博取波动收益")
        else:
            print("\n" + "="*80)
            print("🎯 策略建议: 不交易 (NO TRADE)")
            print("="*80)
            print("逻辑: 市场预期合理，无明显机会")
    
    # 风险提示
    print("\n" + "="*80)
    print("⚠️ 风险提示")
    print("="*80)
    if ticker in HIGH_RISK_TICKERS:
        print(f"• {ticker}是高风险标的，过往财报经常超预期")
        print("• 卖波动风险极高，建议严格控制仓位")
    if iv_rank > 80:
        print("• IV Rank极高，可能存在未公开信息")
        print("• 建议观望或小额试水")
    
    print("\n" + "="*80)


# ============================================================
# Main
# ============================================================
def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='财报期权交易策略分析')
    parser.add_argument('--demo', action='store_true', help='运行示例分析')
    parser.add_argument('--interactive', action='store_true', help='交互式快速判断')
    
    args = parser.parse_args()
    
    if args.interactive:
        quick_decision_tool()
    elif args.demo:
        analyses = create_sample_analysis()
        print_analysis_report(analyses)
    else:
        print("财报期权交易策略分析工具")
        print("\n使用方法:")
        print("  python OptionsEarningsAnalyzer.py --demo        # 运行示例")
        print("  python OptionsEarningsAnalyzer.py --interactive # 交互式判断")


if __name__ == "__main__":
    main()
