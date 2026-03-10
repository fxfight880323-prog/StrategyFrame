"""
快速运行 AKShare CTA + FLP 策略
================================

简化版入口，方便日常使用
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 路径设置
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', '..', 'Strategy_Framework', '01_Macro_Analysis'))

from AKShare_CTA_FLP_Strategy import IntegratedAKShareStrategy
import pandas as pd
from datetime import date


def main():
    print("="*70)
    print("CTA + FLP 策略快速运行 (AKShare)")
    print("="*70)
    print()
    
    # 运行策略
    strategy = IntegratedAKShareStrategy()
    strategy.run_strategy()
    
    print()
    print("="*70)
    print("交易建议")
    print("="*70)
    
    # 读取生成的信号
    try:
        signals = pd.read_csv("cta_akshare_signals.csv")
        
        # 买入建议
        longs = signals[signals['signal'] == 'LONG']
        if not longs.empty:
            print("\n【买入标的】")
            for _, row in longs.iterrows():
                print(f"  {row['symbol']:6s} 价格:${row['price']:8.2f} "
                      f"评分:{row['score']:5.1f} 仓位:{row['position_size']*100:5.1f}%")
        else:
            print("\n【买入标的】无")
        
        # 回避标的
        shorts = signals[signals['signal'] == 'SHORT']
        if not shorts.empty:
            print("\n【回避标的】")
            for _, row in shorts.iterrows():
                print(f"  {row['symbol']:6s} 价格:${row['price']:8.2f} 评分:{row['score']:5.1f}")
        
        # FLP 提醒
        today = date.today()
        if today.weekday() == 4:
            print("\n【FLP 对冲】今天是周五，已执行周度对冲")
        else:
            from datetime import timedelta
            days_to_friday = (4 - today.weekday()) % 7
            next_friday = today + timedelta(days=days_to_friday)
            print(f"\n【FLP 对冲】下次对冲日期: {next_friday} ({days_to_friday}天后)")
        
        # 资金分配
        print("\n【资金分配建议】")
        allocation = strategy.calculate_allocation()
        print(f"  CTA 策略: {allocation['cta']*100:5.1f}%")
        print(f"  FLP 保护: {allocation['flp']*100:5.1f}%")
        print(f"  现金:     {allocation['cash']*100:5.1f}%")
        
    except Exception as e:
        print(f"读取信号文件失败: {e}")
    
    print()
    print("="*70)
    print("完成! 详细数据请查看: cta_akshare_signals.csv")
    print("="*70)


if __name__ == "__main__":
    main()
