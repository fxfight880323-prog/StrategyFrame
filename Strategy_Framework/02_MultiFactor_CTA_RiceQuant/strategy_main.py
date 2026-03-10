"""
多因子选股 + CTA策略主程序
==========================

整合多因子选股和CTA信号的周度换仓策略

使用说明:
    1. 直接运行进行回测: python strategy_main.py
    2. 生成今日信号: python strategy_main.py --signal
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta

from config import StrategyConfig, CONFIG
from factor_model import quick_screen
from cta_signals import get_cta_signals
from ricequant_backtest import quick_backtest, print_backtest_report


# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def run_backtest_mode(start_date: str = None, end_date: str = None):
    """回测模式"""
    logger.info("启动回测模式")
    
    config = CONFIG
    start = start_date or config.START_DATE
    end = end_date or config.END_DATE
    
    result = quick_backtest(start, end, config)
    return result


def run_signal_mode():
    """信号生成模式"""
    logger.info("生成今日交易信号")
    
    config = CONFIG
    today = datetime.now().strftime('%Y-%m-%d')
    
    # 1. 多因子选股
    print("\n" + "=" * 70)
    print(f"多因子选股结果 - {today}")
    print("=" * 70)
    
    stock_scores = quick_screen(
        universe=config.STOCK_UNIVERSE,
        date=today,
        top_n=config.MAX_STOCK_HOLDINGS,
        api_key=config.RQ_API_KEY
    )
    
    print(f"\nTop {config.MAX_STOCK_HOLDINGS} Stocks:")
    print(stock_scores[['symbol', 'total_score', 'rank']].to_string())
    
    # 2. CTA信号
    print("\n" + "=" * 70)
    print(f"CTA交易信号 - {today}")
    print("=" * 70)
    
    cta_signals = get_cta_signals(
        symbols=config.CTA_SYMBOLS[:5],
        api_key=config.RQ_API_KEY
    )
    
    for sym, sig in cta_signals.items():
        direction = "LONG" if sig.signal.value == 1 else "SHORT" if sig.signal.value == -1 else "FLAT"
        print(f"{sym}: {direction} | Position: {sig.target_position:.2f} | Strength: {sig.strength:.2f}")
    
    # 3. 配置建议
    print("\n" + "=" * 70)
    print("组合配置建议")
    print("=" * 70)
    print(f"股票仓位: {config.STOCK_ALLOCATION*100:.0f}%")
    print(f"CTA仓位: {config.CTA_ALLOCATION*100:.0f}%")
    print(f"现金仓位: {(1-config.STOCK_ALLOCATION-config.CTA_ALLOCATION)*100:.0f}%")
    print(f"\n换仓频率: 每周{['一', '二', '三', '四', '五', '六', '日'][config.REBALANCE_DAY]}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='多因子选股 + CTA策略')
    parser.add_argument('--backtest', action='store_true', help='运行回测')
    parser.add_argument('--signal', action='store_true', help='生成今日信号')
    parser.add_argument('--start', type=str, default=None, help='回测开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, default=None, help='回测结束日期 (YYYY-MM-DD)')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("多因子选股 + CTA策略")
    print("=" * 70)
    
    if args.signal:
        run_signal_mode()
    elif args.backtest:
        run_backtest_mode(args.start, args.end)
    else:
        # 默认运行回测
        run_backtest_mode()


if __name__ == "__main__":
    main()
