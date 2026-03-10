"""
MAG7 财报预期分析系统 - 演示版本
==============================
使用模拟数据展示系统输出格式
"""

import pandas as pd
from datetime import date, timedelta
import random

# 模拟数据生成
def generate_demo_data():
    """生成模拟财报数据用于演示"""
    tickers = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA"]
    data = []
    
    # 为每只股票生成最近2-3次财报
    base_dates = {
        "AAPL": ["2025-01-30", "2024-10-31", "2024-08-01"],
        "MSFT": ["2025-01-30", "2024-10-30", "2024-07-30"],
        "AMZN": ["2025-02-06", "2024-10-31", "2024-08-01"],
        "NVDA": ["2025-02-26", "2024-11-20", "2024-08-28"],
        "GOOGL": ["2025-02-04", "2024-10-29", "2024-07-23"],
        "META": ["2025-01-29", "2024-10-30", "2024-07-31"],
        "TSLA": ["2025-01-29", "2024-10-23", "2024-07-23"],
    }
    
    scenarios = [
        # (Surprise%, Gap%, 场景说明)
        (0.15, -0.02, "超预期但下跌 - 预期过高"),
        (-0.10, 0.03, "低于预期但上涨 - 预期过低"),
        (0.08, 0.05, "超预期且大涨 - 预期合理"),
        (-0.05, -0.03, "低于预期且下跌 - 预期合理"),
        (0.02, 0.01, "符合预期微涨 - 预期精准"),
        (0.20, 0.08, "大幅超预期大涨 - 预期偏低"),
        (-0.15, -0.05, "大幅低于预期大跌 - 预期偏高"),
    ]
    
    for ticker in tickers:
        for i, report_date in enumerate(base_dates[ticker]):
            # 为每次财报随机选择一个场景
            scenario = scenarios[(hash(ticker) + i) % len(scenarios)]
            surprise, gap, comment = scenario
            
            # 添加一些随机扰动
            surprise += random.uniform(-0.02, 0.02)
            gap += random.uniform(-0.01, 0.01)
            intraday = random.uniform(-0.02, 0.04)
            
            eps_estimate = random.uniform(0.5, 5.0)
            eps_actual = eps_estimate * (1 + surprise)
            
            prev_close = random.uniform(100, 500)
            open_price = prev_close * (1 + gap)
            close_price = open_price * (1 + intraday)
            day_change = (close_price - prev_close) / prev_close
            
            # 判断预期
            if surprise > 0 and gap < 0:
                expectation = "Expectation High"
                detail = "业绩超预期但股价下跌，预期已被透支"
            elif surprise < 0 and gap > 0:
                expectation = "Expectation Low"
                detail = "业绩低于预期但股价上涨，利空出尽"
            elif surprise > 0 and gap > surprise * 0.5:
                expectation = "Expectation Low"
                detail = "业绩超预期且涨幅更大，市场此前保守"
            elif surprise < 0 and abs(gap) > abs(surprise) * 0.5:
                expectation = "Expectation High"
                detail = "业绩低于预期且跌幅更大，过度悲观"
            else:
                expectation = "Expectation Reasonable"
                detail = "市场预期与业绩基本匹配"
            
            # 计算信号得分
            signal_score = surprise * 0.5 + gap * 0.3 + intraday * 0.2
            
            data.append({
                'Ticker': ticker,
                'ReportDate': report_date,
                'Hour': 'amc' if i % 2 == 0 else 'bmo',
                'EPS_Actual': round(eps_actual, 2),
                'EPS_Estimate': round(eps_estimate, 2),
                'SurprisePct': surprise,
                'GapPct': gap,
                'IntradayPct': intraday,
                'DayChange': day_change,
                'PrevClose': round(prev_close, 2),
                'Open': round(open_price, 2),
                'Close': round(close_price, 2),
                'SurpriseClass': 'Strong Beat' if surprise > 0.1 else 'Beat' if surprise > 0.05 else 'Inline' if surprise > -0.05 else 'Miss',
                'ReactionClass': 'Positive' if gap > 0.03 else 'Negative' if gap < -0.03 else 'Neutral',
                'ExpectationLevel': expectation,
                'ExpectationComment': detail,
                'SignalScore': round(signal_score, 4),
            })
    
    return pd.DataFrame(data)


def print_analysis(df: pd.DataFrame):
    """打印分析结果"""
    print("\n" + "=" * 100)
    print("MAG7 财报预期分析结果（演示数据）")
    print("=" * 100)
    
    # 按股票分组显示
    for ticker in df['Ticker'].unique():
        ticker_data = df[df['Ticker'] == ticker].sort_values('ReportDate', ascending=False)
        latest = ticker_data.iloc[0]
        
        print(f"\n{'─' * 100}")
        print(f"【{ticker}】最新财报: {latest['ReportDate']}")
        print(f"{'─' * 100}")
        
        for _, row in ticker_data.iterrows():
            emoji = {
                "Expectation High": "[高]",
                "Expectation Low": "[低]",
                "Expectation Reasonable": "[合理]"
            }.get(row['ExpectationLevel'], "[?]")
            
            print(f"\n  财报日期: {row['ReportDate']} ({row['Hour']})")
            print(f"  EPS: 实际 ${row['EPS_Actual']:.2f} vs 预期 ${row['EPS_Estimate']:.2f} "
                  f"→ Surprise: {row['SurprisePct']:+.1%}")
            print(f"  股价: 跳空 {row['GapPct']:+.2%} | 日内 {row['IntradayPct']:+.2%} | "
                  f"全天 {row['DayChange']:+.2%}")
            print(f"  {emoji} 预期判断: {row['ExpectationLevel']}")
            print(f"       -> {row['ExpectationComment']}")
            print(f"  [信号] 得分: {row['SignalScore']:+.4f}")
    
    print("\n" + "=" * 100)
    
    # 汇总表
    print("\n[汇总表] 按最新信号得分排序:")
    print("-" * 100)
    summary = df.sort_values('ReportDate', ascending=False).groupby('Ticker').first()
    summary = summary.sort_values('SignalScore', ascending=False)
    
    print(f"{'排名':<4} {'股票':<8} {'日期':<12} {'Surprise':<10} {'跳空':<10} {'预期判断':<20} {'得分':<8}")
    print("-" * 100)
    
    for rank, (ticker, row) in enumerate(summary.iterrows(), 1):
        marker = {"Expectation High": "[高]", "Expectation Low": "[低]", "Expectation Reasonable": "[合理]"}.get(row['ExpectationLevel'], "[?]")
        print(f"{rank:<4} {ticker:<8} {row['ReportDate']:<12} "
              f"{row['SurprisePct']:>+8.1%}  {row['GapPct']:>+8.1%}  "
              f"{marker} {row['ExpectationLevel']:<18} {row['SignalScore']:>+6.4f}")
    
    print("-" * 100)


def main():
    print("\n" + "=" * 100)
    print("MAG7 财报预期分析系统 - 演示模式")
    print("=" * 100)
    print("\n本演示使用模拟数据展示系统输出格式")
    print("实际使用时请运行: Mag7Tracker_EarningsExpectation.py")
    print("需要 Finnhub API Key 获取真实财报数据")
    print("\n" + "=" * 100)
    
    df = generate_demo_data()
    print_analysis(df)
    
    # 保存示例
    df.to_csv("demo_expectation_analysis.csv", index=False)
    print(f"\n💾 演示数据已保存: demo_expectation_analysis.csv")
    
    # 输出解释
    print("\n" + "=" * 100)
    print("[说明] 如何判断市场预期:")
    print("=" * 100)
    print("""
    [高] Expectation High (预期过高):
       → 业绩超预期但股价下跌，或低于预期且大跌
       → 说明业绩已被Price In，机构借利好出货
       -> 操作建议: 短期回避，等待回调
    
    [低] Expectation Low (预期过低):
       → 业绩低于预期但股价上涨，或超预期且大涨
       → 说明市场此前过度悲观，或预期保守
       → 操作建议: 关注买入机会，利空出尽
    
    [合理] Expectation Reasonable (预期合理):
       → 业绩和股价反应方向一致，幅度匹配
       → 说明市场定价效率较高
       → 操作建议: 按趋势操作，顺势而为
    """)
    print("=" * 100)


if __name__ == "__main__":
    main()
