"""
技术形态策略主程序
==================

基于路演PPT中Price Action Analysis框架的完整技术形态分析系统

功能:
1. 批量分析美股技术形态
2. 生成买入/卖出信号
3. 执行策略回测
4. 生成可视化报告

使用方法:
    python PatternStrategy_Main.py

命令行参数:
    --mode: scan (扫描) / backtest (回测) / report (报告)
    --stocks: 股票列表 (默认101只美股)
    --output: 输出目录
"""

import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import List
import argparse
import logging
import os

from TechnicalPatternAnalyzer import (
    TechnicalPatternAnalyzer, 
    PatternBatchAnalyzer,
    DEFAULT_STOCKS,
    SignalStrength
)
from PatternStrategy_Backtest import PatternStrategyBacktest
from PatternStrategy_Visualizer import PatternVisualizer


# ============================================================
# 配置
# ============================================================
OUTPUT_DIR = f"Report_{date.today().isoformat()}"

# 股票池
STOCK_UNIVERSE = {
    'mag7': ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA'],
    'tech': ['AMD', 'INTC', 'NFLX', 'CRM', 'ADBE', 'ORCL', 'QCOM', 'TXN'],
    'etf': ['SPY', 'QQQ', 'IWM', 'VTI', 'VOO'],
    'all': DEFAULT_STOCKS
}


# ============================================================
# 日志
# ============================================================
def setup_logger() -> logging.Logger:
    logger = logging.getLogger("pattern_main")
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        
        # 控制台
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
        
        # 文件
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        fh = logging.FileHandler(f"{OUTPUT_DIR}/pattern_strategy.log", encoding='utf-8')
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    
    return logger


logger = setup_logger()


# ============================================================
# 功能模块
# ============================================================
class PatternStrategySystem:
    """技术形态策略系统"""
    
    def __init__(self, output_dir: str = OUTPUT_DIR):
        self.output_dir = output_dir
        self.analyzer = PatternBatchAnalyzer(logger)
        self.visualizer = PatternVisualizer(output_dir, logger)
        
        os.makedirs(output_dir, exist_ok=True)
    
    def scan_stocks(self, symbols: List[str] = None) -> pd.DataFrame:
        """
        扫描股票技术形态
        
        Args:
            symbols: 股票代码列表
        
        Returns:
            信号DataFrame
        """
        symbols = symbols or STOCK_UNIVERSE['mag7']
        
        logger.info("="*60)
        logger.info("技术形态扫描")
        logger.info("="*60)
        logger.info(f"扫描标的: {len(symbols)} 只")
        
        # 执行分析
        signals_df = self.analyzer.analyze_stocks(symbols)
        
        # 保存结果
        if not signals_df.empty:
            csv_path = f"{self.output_dir}/pattern_signals_{date.today().isoformat()}.csv"
            signals_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            logger.info(f"结果保存: {csv_path}")
            
            # 生成可视化
            logger.info("生成可视化图表...")
            self.visualizer.plot_signal_distribution(signals_df)
            self.visualizer.create_signal_heatmap(signals_df)
            
            # 生成HTML报告
            html_path = self.visualizer.create_html_report(signals_df)
            logger.info(f"HTML报告: {html_path}")
        
        # 输出重点推荐
        self._print_recommendations(signals_df)
        
        return signals_df
    
    def _print_recommendations(self, signals_df: pd.DataFrame):
        """输出重点推荐"""
        if signals_df.empty:
            return
        
        print("\n" + "="*60)
        print("重点推荐")
        print("="*60)
        
        # 强烈买入
        strong_buy = signals_df[signals_df['Signal'].isin(['强烈买入', '买入'])]
        if not strong_buy.empty:
            print("\n【买入信号】")
            for _, row in strong_buy.head(10).iterrows():
                print(f"  {row['Symbol']:6} | {row['Signal']:8} | "
                      f"形态: {row['Pattern']:12} | "
                      f"价格: ${row['Price']:.2f} | "
                      f"目标: ${row['Target']:.2f} | "
                      f"置信度: {row['Confidence']:.0%}")
        
        # 强烈卖出
        strong_sell = signals_df[signals_df['Signal'].isin(['强烈卖出', '卖出'])]
        if not strong_sell.empty:
            print("\n【卖出信号】")
            for _, row in strong_sell.head(10).iterrows():
                print(f"  {row['Symbol']:6} | {row['Signal']:8} | "
                      f"形态: {row['Pattern']:12} | "
                      f"价格: ${row['Price']:.2f}")
        
        print("\n" + "="*60)
    
    def run_backtest(self, symbols: List[str] = None, 
                    days: int = 90) -> pd.DataFrame:
        """
        执行策略回测
        
        Args:
            symbols: 股票代码列表
            days: 回测天数
        
        Returns:
            回测结果DataFrame
        """
        symbols = symbols or STOCK_UNIVERSE['mag7']
        
        logger.info("="*60)
        logger.info("技术形态策略回测")
        logger.info("="*60)
        
        end = date.today()
        start = end - timedelta(days=days)
        
        # 创建回测引擎
        backtest = PatternStrategyBacktest(
            initial_capital=1_000_000,
            max_positions=10,
            position_size=0.1,
            logger=logger
        )
        
        # 执行回测
        result = backtest.run_backtest(
            symbols=symbols,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            rebalance_freq=5
        )
        
        if not result.empty:
            # 保存结果
            csv_path = f"{self.output_dir}/backtest_result.csv"
            result.to_csv(csv_path, index=False, encoding='utf-8-sig')
            logger.info(f"回测结果: {csv_path}")
            
            # 获取交易记录
            trades_df = backtest.get_trade_summary()
            if not trades_df.empty:
                trades_path = f"{self.output_dir}/trade_records.csv"
                trades_df.to_csv(trades_path, index=False, encoding='utf-8-sig')
                logger.info(f"交易记录: {trades_path}")
            
            # 可视化
            self.visualizer.plot_backtest_performance(result, trades_df)
        
        return result
    
    def generate_full_report(self, symbols: List[str] = None):
        """生成完整分析报告"""
        symbols = symbols or STOCK_UNIVERSE['all'][:50]  # 默认分析前50只
        
        logger.info("="*60)
        logger.info("生成完整分析报告")
        logger.info("="*60)
        
        # 1. 扫描信号
        signals_df = self.scan_stocks(symbols)
        
        # 2. 回测 (使用subset)
        backtest_df = self.run_backtest(STOCK_UNIVERSE['mag7'], days=90)
        
        # 3. 生成综合HTML报告
        trades_df = None
        if not backtest_df.empty:
            trades_path = f"{self.output_dir}/trade_records.csv"
            if os.path.exists(trades_path):
                trades_df = pd.read_csv(trades_path)
        
        html_path = self.visualizer.create_html_report(
            signals_df, backtest_df, trades_df,
            title="技术形态策略完整分析报告"
        )
        
        logger.info(f"综合报告: {html_path}")
        
        return {
            'signals': signals_df,
            'backtest': backtest_df,
            'report_path': html_path
        }


# ============================================================
# 命令行入口
# ============================================================
def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='技术形态策略分析系统')
    
    parser.add_argument('--mode', type=str, default='scan',
                       choices=['scan', 'backtest', 'report'],
                       help='运行模式: scan(扫描), backtest(回测), report(完整报告)')
    
    parser.add_argument('--universe', type=str, default='mag7',
                       choices=['mag7', 'tech', 'etf', 'all'],
                       help='股票池选择')
    
    parser.add_argument('--stocks', type=str, default=None,
                       help='自定义股票列表，逗号分隔 (如: AAPL,MSFT,NVDA)')
    
    parser.add_argument('--days', type=int, default=90,
                       help='回测天数')
    
    parser.add_argument('--output', type=str, default=OUTPUT_DIR,
                       help='输出目录')
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    print("="*60)
    print("技术形态策略分析系统")
    print("基于Price Action Analysis框架")
    print("="*60)
    print()
    
    # 确定股票列表
    if args.stocks:
        symbols = [s.strip().upper() for s in args.stocks.split(',')]
    else:
        symbols = STOCK_UNIVERSE.get(args.universe, STOCK_UNIVERSE['mag7'])
    
    print(f"运行模式: {args.mode}")
    print(f"股票池: {args.universe if not args.stocks else '自定义'} ({len(symbols)}只)")
    if args.mode in ['backtest', 'report']:
        print(f"回测天数: {args.days}")
    print(f"输出目录: {args.output}")
    print()
    
    # 创建系统
    system = PatternStrategySystem(args.output)
    
    # 执行相应功能
    if args.mode == 'scan':
        system.scan_stocks(symbols)
    
    elif args.mode == 'backtest':
        system.run_backtest(symbols, args.days)
    
    elif args.mode == 'report':
        system.generate_full_report(symbols)
    
    print()
    print("="*60)
    print("分析完成")
    print(f"报告目录: {os.path.abspath(args.output)}")
    print("="*60)


# ============================================================
# 快速测试入口
# ============================================================
def quick_demo():
    """快速演示"""
    print("="*60)
    print("技术形态策略 - 快速演示")
    print("="*60)
    print()
    
    system = PatternStrategySystem()
    
    # 1. 扫描Mag7
    print("【1】扫描 Mag7 技术形态...")
    signals = system.scan_stocks(STOCK_UNIVERSE['mag7'])
    
    print("\n【2】回测演示 (最近30天)...")
    result = system.run_backtest(STOCK_UNIVERSE['mag7'], days=30)
    
    print("\n" + "="*60)
    print("演示完成")
    print(f"请查看报告目录: {OUTPUT_DIR}")
    print("="*60)


if __name__ == "__main__":
    # 如果有命令行参数，使用参数模式
    if len(sys.argv) > 1:
        main()
    else:
        # 否则运行快速演示
        quick_demo()
