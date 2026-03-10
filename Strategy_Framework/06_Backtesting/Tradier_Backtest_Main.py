"""
Tradier 完整回测系统
=====================

整合 Tradier API 进行完整的量化策略回测:
- CTA 趋势策略
- FLP 期权对冲
- PB-ROE A股策略 (通过RiceQuant)
- 组合分析与报告生成

运行方式:
    python Tradier_Backtest_Main.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List
import logging
import os

# 路径设置
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', 'data_providers'))
sys.path.insert(0, os.path.join(_DIR, '..', '04_Strategy_Execution'))

from TradierDataProvider import TradierDataProvider
from CTA_FLP_Strategy_Tradier import CTAFLPBacktest
from OptionsBacktest_Tradier import OptionsStrategyBacktest, OptionsStrategy


# ============================================================
# 配置
# ============================================================
REPORT_DIR = f"Report_{date.today().isoformat()}"
INITIAL_CAPITAL = 1_000_000

# 策略配置
STRATEGY_CONFIG = {
    'cta_enabled': True,
    'flp_enabled': True,
    'options_hedge_enabled': True,
    'lookback_days': 90,
}


# ============================================================
# 日志
# ============================================================
def setup_logger() -> logging.Logger:
    logger = logging.getLogger("tradier_main")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        # 控制台输出
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(sh)
        
        # 文件输出
        os.makedirs(REPORT_DIR, exist_ok=True)
        fh = logging.FileHandler(f"{REPORT_DIR}/backtest_log.txt", encoding='utf-8')
        fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(fh)
    
    return logger


logger = setup_logger()


# ============================================================
# 回测控制器
# ============================================================
class TradierBacktestController:
    """Tradier 回测主控制器"""
    
    def __init__(self, api_key: str = None, sandbox: bool = True):
        self.data_provider = TradierDataProvider(
            api_key=api_key or TradierDataProvider.TRADIER_API_KEY,
            sandbox=sandbox,
            logger=logger
        )
        self.results = {}
        
    def run_cta_backtest(self, symbol: str = 'SPY', days: int = 90) -> pd.DataFrame:
        """运行CTA趋势策略回测"""
        logger.info("="*60)
        logger.info("【策略1】CTA趋势跟踪回测")
        logger.info("="*60)
        
        end = date.today()
        start = end - timedelta(days=days)
        
        # 获取数据
        df = self.data_provider.get_historical_data(symbol, start.isoformat(), end.isoformat())
        if df.empty:
            logger.error("无法获取数据")
            return pd.DataFrame()
        
        # 生成信号
        from CTA_FLP_Strategy_Tradier import CTATrendEngine
        cta = CTATrendEngine()
        signals_df = cta.generate_signals(df)
        
        # 计算策略表现
        signals_df['cumulative_strategy'] = (1 + signals_df['strategy_return'].fillna(0)).cumprod()
        signals_df['cumulative_buyhold'] = (1 + signals_df['returns'].fillna(0)).cumprod()
        
        # 绩效统计
        total_return = signals_df['cumulative_strategy'].iloc[-1] - 1
        buyhold_return = signals_df['cumulative_buyhold'].iloc[-1] - 1
        
        # 信号统计
        signal_counts = signals_df['signal'].value_counts()
        
        logger.info(f"回测区间: {start} ~ {end}")
        logger.info(f"总收益率: {total_return*100:.2f}%")
        logger.info(f"买入持有: {buyhold_return*100:.2f}%")
        logger.info(f"超额收益: {(total_return - buyhold_return)*100:.2f}%")
        logger.info(f"信号统计: {dict(signal_counts)}")
        
        self.results['cta'] = {
            'df': signals_df,
            'total_return': total_return,
            'buyhold_return': buyhold_return,
            'excess_return': total_return - buyhold_return,
        }
        
        return signals_df
    
    def run_flp_backtest(self, symbol: str = 'SPY', days: int = 90) -> pd.DataFrame:
        """运行FLP尾部风险对冲回测"""
        logger.info("")
        logger.info("="*60)
        logger.info("【策略2】FLP尾部风险对冲回测")
        logger.info("="*60)
        
        end = date.today()
        start = end - timedelta(days=days)
        
        backtest = CTAFLPBacktest(
            initial_capital=INITIAL_CAPITAL,
            data_provider=self.data_provider,
            logger=logger
        )
        
        result = backtest.run_backtest(start.isoformat(), end.isoformat())
        
        if not result.empty:
            self.results['flp'] = {
                'df': result,
                'put_trades': len(backtest.put_history),
                'final_value': result['Total_Value'].iloc[-1],
            }
        
        return result
    
    def run_options_hedge_backtest(self, symbol: str = 'SPY', 
                                   days: int = 90,
                                   strategy: OptionsStrategy = OptionsStrategy.PROTECTIVE_PUT) -> pd.DataFrame:
        """运行期权对冲回测"""
        logger.info("")
        logger.info("="*60)
        logger.info(f"【策略3】期权对冲策略回测 - {strategy.value}")
        logger.info("="*60)
        
        end = date.today()
        start = end - timedelta(days=days)
        
        backtest = OptionsStrategyBacktest(
            initial_capital=INITIAL_CAPITAL,
            strategy=strategy,
            data_provider=self.data_provider,
            logger=logger
        )
        
        result = backtest.run_backtest(symbol, start.isoformat(), end.isoformat())
        
        if not result.empty:
            self.results['options_hedge'] = {
                'df': result,
                'strategy': strategy.value,
            }
        
        return result
    
    def run_full_backtest(self, symbols: List[str] = None) -> Dict:
        """运行完整回测套件"""
        symbols = symbols or ['SPY']
        
        logger.info("\n" + "="*60)
        logger.info("Tradier 完整回测系统启动")
        logger.info("="*60)
        logger.info(f"标的: {symbols}")
        logger.info(f"报告目录: {REPORT_DIR}")
        
        # 1. CTA 趋势策略
        for sym in symbols:
            self.run_cta_backtest(sym, days=STRATEGY_CONFIG['lookback_days'])
        
        # 2. FLP 对冲策略
        if STRATEGY_CONFIG['flp_enabled']:
            self.run_flp_backtest('SPY', days=STRATEGY_CONFIG['lookback_days'])
        
        # 3. 期权对冲策略
        if STRATEGY_CONFIG['options_hedge_enabled']:
            self.run_options_hedge_backtest('SPY', days=60, 
                                           strategy=OptionsStrategy.PROTECTIVE_PUT)
            self.run_options_hedge_backtest('SPY', days=60,
                                           strategy=OptionsStrategy.BEAR_PUT_SPREAD)
        
        # 4. 生成报告
        self.generate_report()
        
        return self.results
    
    def generate_report(self):
        """生成回测报告"""
        logger.info("")
        logger.info("="*60)
        logger.info("生成回测报告")
        logger.info("="*60)
        
        os.makedirs(REPORT_DIR, exist_ok=True)
        
        # 保存各策略结果
        for name, data in self.results.items():
            if 'df' in data:
                csv_path = f"{REPORT_DIR}/{name}_backtest.csv"
                data['df'].to_csv(csv_path, index=False, encoding='utf-8-sig')
                logger.info(f"  ✓ {name} 结果: {csv_path}")
        
        # 生成汇总报告
        summary = []
        
        if 'cta' in self.results:
            summary.append({
                'Strategy': 'CTA Trend',
                'Total_Return_%': f"{self.results['cta']['total_return']*100:.2f}",
                'BuyHold_Return_%': f"{self.results['cta']['buyhold_return']*100:.2f}",
                'Excess_Return_%': f"{self.results['cta']['excess_return']*100:.2f}",
            })
        
        if 'flp' in self.results:
            summary.append({
                'Strategy': 'CTA+FLP',
                'Total_Return_%': f"{(self.results['flp']['final_value']/INITIAL_CAPITAL - 1)*100:.2f}",
                'BuyHold_Return_%': '-',
                'Excess_Return_%': '-',
            })
        
        if summary:
            summary_df = pd.DataFrame(summary)
            summary_path = f"{REPORT_DIR}/backtest_summary.csv"
            summary_df.to_csv(summary_path, index=False, encoding='utf-8-sig')
            logger.info(f"  ✓ 汇总报告: {summary_path}")
        
        logger.info("报告生成完成")


# ============================================================
# 主函数
# ============================================================
def main():
    """主入口"""
    print("="*60)
    print("Tradier 量化回测系统")
    print("="*60)
    print()
    
    # 检查 API Key
    if TradierDataProvider.TRADIER_API_KEY == "YOUR_TRADIER_API_KEY_HERE":
        print("⚠️  请先配置 Tradier API Key")
        print()
        print("获取步骤:")
        print("1. 访问 https://developer.tradier.com/")
        print("2. 注册开发者账号")
        print("3. 创建应用获取 API Key")
        print("4. 将 API Key 填入 TradierDataProvider.py 中的 TRADIER_API_KEY 变量")
        print()
        print("注意: 建议使用沙盒环境(sandbox=True)进行测试")
        print()
        return
    
    # 创建控制器并运行
    controller = TradierBacktestController(sandbox=True)
    
    # 交互式选择
    print("选择回测策略:")
    print("1. CTA趋势策略")
    print("2. FLP尾部风险对冲")
    print("3. 期权保险策略")
    print("4. 全部运行")
    print()
    
    try:
        choice = input("输入选项 (1-4) [默认4]: ").strip() or "4"
    except:
        choice = "4"
    
    if choice == "1":
        controller.run_cta_backtest('SPY', days=90)
    elif choice == "2":
        controller.run_flp_backtest('SPY', days=90)
    elif choice == "3":
        controller.run_options_hedge_backtest('SPY', days=60)
    elif choice == "4":
        controller.run_full_backtest(['SPY'])
    else:
        print("无效选项，运行全部策略")
        controller.run_full_backtest(['SPY'])
    
    print()
    print("="*60)
    print("回测完成，请查看报告目录:", REPORT_DIR)
    print("="*60)


if __name__ == "__main__":
    main()
