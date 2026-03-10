"""
ValMomEverywhere 回测运行脚本
==============================

运行 Value 和 Momentum 因子的单独回测，并计算 Information Ratio

使用方法:
    python run_valmom_backtest.py
    python run_valmom_backtest.py --start 2022-01-01 --end 2024-01-01
    python run_valmom_backtest.py --quick  # 快速测试模式
"""

import argparse
import sys
from datetime import datetime

from valmom_backtest import (
    run_valmom_backtests,
    quick_valmom_backtest,
    ValMomBacktester,
    print_backtest_summary
)
from config import CONFIG


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='ValMomEverywhere Factor Backtest',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 运行默认回测
  python run_valmom_backtest.py
  
  # 指定回测期间
  python run_valmom_backtest.py --start 2022-01-01 --end 2024-01-01
  
  # 快速测试 (3个月数据)
  python run_valmom_backtest.py --quick
  
  # 只回测特定因子
  python run_valmom_backtest.py --factor value
  python run_valmom_backtest.py --factor momentum
  python run_valmom_backtest.py --factor combo
        """
    )
    
    parser.add_argument(
        '--start',
        type=str,
        default=None,
        help='回测开始日期 (YYYY-MM-DD)，默认: 2022-01-01'
    )
    
    parser.add_argument(
        '--end',
        type=str,
        default=None,
        help='回测结束日期 (YYYY-MM-DD)，默认: 2024-12-31'
    )
    
    parser.add_argument(
        '--quick',
        action='store_true',
        help='快速测试模式 (使用3个月数据)'
    )
    
    parser.add_argument(
        '--factor',
        type=str,
        choices=['value', 'momentum', 'combo', 'all'],
        default='all',
        help='选择回测的因子，默认: all'
    )
    
    parser.add_argument(
        '--save',
        action='store_true',
        default=True,
        help='保存回测结果和图表'
    )
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    # 设置日期
    if args.quick:
        start_date = "2023-01-01"
        end_date = "2023-03-31"
        print("[快速测试模式] 使用2023年Q1数据")
    else:
        start_date = args.start or CONFIG.START_DATE
        end_date = args.end or CONFIG.END_DATE
    
    print("=" * 80)
    print("ValMomEverywhere Factor Backtest")
    print("=" * 80)
    print(f"\n论文参考:")
    print("  Asness, C.S., Moskowitz, T.J., & Pedersen, L.H. (2013)")
    print("  'Value and Momentum Everywhere'")
    print("  Journal of Finance, 68(3), 929-985")
    print(f"\n回测期间: {start_date} 至 {end_date}")
    print(f"股票池: {CONFIG.STOCK_UNIVERSE}")
    print(f"再平衡: 月度")
    print("=" * 80)
    
    # 运行回测
    if args.factor == 'all':
        results = run_valmom_backtests(start_date, end_date, args.save)
    else:
        # 单因子回测
        backtester = ValMomBacktester()
        result = backtester.backtest_factor(
            factor_name=args.factor,
            start_date=start_date,
            end_date=end_date,
            rebalance_freq='ME'
        )
        results = {args.factor.capitalize(): result}
        print_backtest_summary(results)
        
        # 保存单因子结果
        if args.save:
            from valmom_backtest import save_backtest_results
            save_backtest_results(
                results,
                f"backtests/valmom_{args.factor}_results.json"
            )
    
    # 打印关键发现
    print("\n" + "=" * 80)
    print("Key Findings (vs Paper)")
    print("=" * 80)
    print("\n论文发现:")
    print("  1. 价值和动量在全球多个市场和资产类别中都有显著溢价")
    print("  2. 价值和动量负相关 (相关系数约 -0.5)")
    print("  3. COMBO组合 (50/50) 可以平滑收益，提高夏普比率")
    print("\n本回测结果:")
    if len(results) >= 2:
        import pandas as pd
        returns_df = pd.DataFrame({
            name: result.returns_series for name, result in results.items()
        })
        corr = returns_df.corr()
        if 'Value' in corr.columns and 'Momentum' in corr.columns:
            corr_val = corr.loc['Value', 'Momentum']
            print(f"  Value-Momentum 相关系数: {corr_val:.2f} (论文: -0.5 左右)")
    
    print("\n" + "=" * 80)
    print("回测完成！")
    if args.save:
        print("结果保存在: backtests/")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断回测")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
