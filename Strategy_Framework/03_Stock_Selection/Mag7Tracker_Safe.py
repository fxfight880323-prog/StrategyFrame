#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Mag7Tracker - 安全版 (带缓存和限流保护)
简化版Mag7分析器，使用缓存避免YFinance限流
"""

import sys
import time
import json
import logging
import random
from datetime import date, timedelta, datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import numpy as np

# 设置编码
sys.stdout = sys.__stdout__
sys.stderr = sys.__stderr__

# ============================================================
# CONFIG
# ============================================================
TICKERS = ["AAPL", "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA"]
CACHE_DIR = Path(__file__).parent / "cache"
CACHE_FILE = CACHE_DIR / "mag7_cache.json"
CACHE_TTL_HOURS = 24  # 缓存有效期24小时

OUTPUT_DIR = Path(__file__).parent.parent / "Results"

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("Mag7Safe")

# ============================================================
# Cache Management
# ============================================================
def ensure_cache_dir():
    """确保缓存目录存在"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

def is_cache_valid() -> bool:
    """检查缓存是否有效"""
    if not CACHE_FILE.exists():
        return False
    
    try:
        with open(CACHE_FILE, 'r') as f:
            cache = json.load(f)
        
        cache_time = datetime.fromisoformat(cache.get('timestamp', '2000-01-01'))
        age_hours = (datetime.now() - cache_time).total_seconds() / 3600
        
        return age_hours < CACHE_TTL_HOURS
    except:
        return False

def load_cache() -> Dict:
    """加载缓存数据"""
    if not is_cache_valid():
        return None
    
    try:
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    except:
        return None

def save_cache(data: Dict):
    """保存缓存数据"""
    ensure_cache_dir()
    cache = {
        'timestamp': datetime.now().isoformat(),
        'data': data
    }
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache, f, default=str)
        logger.info(f"缓存已保存: {CACHE_FILE}")
    except Exception as e:
        logger.warning(f"缓存保存失败: {e}")

# ============================================================
# Mock Data Generator (for fallback)
# ============================================================
def generate_mock_data() -> Dict:
    """生成模拟数据（当YFinance不可用时）"""
    logger.info("使用模拟数据模式")
    
    mock_signals = []
    for ticker in TICKERS:
        # 随机生成信号
        signal_score = random.uniform(-0.1, 0.15)
        
        if signal_score > 0.05:
            signal = "BULLISH"
        elif signal_score < -0.02:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"
        
        mock_signals.append({
            'Ticker': ticker,
            'Signal': signal,
            'Score': round(signal_score, 4),
            'Price': round(random.uniform(100, 500), 2),
            'PE_Ratio': round(random.uniform(15, 40), 2),
            'Trend_20D': round(random.uniform(-0.05, 0.1), 4),
            'Data_Source': 'MOCK'
        })
    
    return {
        'signals': mock_signals,
        'prices': [],
        'earnings': [],
        'valuation': []
    }

# ============================================================
# Safe YFinance Fetcher
# ============================================================
def fetch_with_retry(func, max_retries=3, sleep_base=2):
    """带重试的函数执行器"""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt < max_retries - 1:
                sleep_time = sleep_base * (2 ** attempt) + random.uniform(0, 1)
                logger.warning(f"请求失败，{sleep_time:.1f}秒后重试... ({attempt+1}/{max_retries})")
                time.sleep(sleep_time)
            else:
                raise e
    return None

def fetch_mag7_data(use_cache=True, use_mock_fallback=True) -> Dict:
    """获取Mag7数据（带缓存和降级）"""
    
    # 1. 尝试使用缓存
    if use_cache:
        cached = load_cache()
        if cached:
            logger.info("使用缓存数据")
            return cached['data']
    
    # 2. 尝试使用YFinance
    try:
        logger.info("从YFinance获取数据...")
        import yfinance as yf
        
        data = {
            'signals': [],
            'prices': [],
            'earnings': [],
            'valuation': [],
            'last_update': datetime.now().isoformat()
        }
        
        for i, ticker in enumerate(TICKERS):
            try:
                # 添加延迟避免限流 - 每个股票间隔5-8秒
                if i > 0:
                    sleep_time = 5 + random.uniform(0, 3)
                    logger.info(f"等待 {sleep_time:.1f} 秒...")
                    time.sleep(sleep_time)
                
                # 获取Ticker信息
                stock = yf.Ticker(ticker)
                info = stock.info or {}
                
                # 获取历史价格
                hist = stock.history(period="30d")
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
                    price_20d_ago = hist['Close'].iloc[0] if len(hist) >= 20 else hist['Close'].iloc[0]
                    trend_20d = (current_price - price_20d_ago) / price_20d_ago
                else:
                    current_price = info.get('currentPrice', 0)
                    trend_20d = 0
                
                # 获取估值数据
                pe_ratio = info.get('forwardPE') or info.get('trailingPE') or 0
                
                # 计算信号
                signal_score = trend_20d * 0.5
                if pe_ratio > 0:
                    if pe_ratio > 30:
                        signal_score -= 0.02
                    elif pe_ratio < 20:
                        signal_score += 0.02
                
                if signal_score > 0.05:
                    signal = "BULLISH"
                elif signal_score < -0.02:
                    signal = "BEARISH"
                else:
                    signal = "NEUTRAL"
                
                data['signals'].append({
                    'Ticker': ticker,
                    'Signal': signal,
                    'Score': round(signal_score, 4),
                    'Price': round(current_price, 2),
                    'PE_Ratio': round(pe_ratio, 2) if pe_ratio else None,
                    'Trend_20D': round(trend_20d, 4),
                    'Data_Source': 'YFINANCE'
                })
                
                logger.info(f"✓ {ticker}: {signal} (Score: {signal_score:.4f})")
                
            except Exception as e:
                logger.warning(f"✗ {ticker}: {str(e)[:80]}")
                # 检查是否是限流错误
                if "Rate limited" in str(e) or "Too Many Requests" in str(e):
                    logger.warning(f"YFinance限流，停止获取更多数据")
                    # 为剩余股票生成mock数据
                    for remaining_ticker in TICKERS[i:]:
                        signal_score = random.uniform(-0.05, 0.08)
                        signal = "BULLISH" if signal_score > 0.05 else ("BEARISH" if signal_score < -0.02 else "NEUTRAL")
                        data['signals'].append({
                            'Ticker': remaining_ticker,
                            'Signal': signal,
                            'Score': round(signal_score, 4),
                            'Price': round(random.uniform(150, 400), 2),
                            'PE_Ratio': round(random.uniform(20, 35), 2),
                            'Trend_20D': round(signal_score * 2, 4),
                            'Data_Source': 'MOCK_FALLBACK'
                        })
                        logger.info(f"✓ {remaining_ticker}: {signal} (Mock Fallback)")
                    break
                
                # 添加空数据
                data['signals'].append({
                    'Ticker': ticker,
                    'Signal': 'ERROR',
                    'Score': 0,
                    'Price': None,
                    'PE_Ratio': None,
                    'Trend_20D': 0,
                    'Data_Source': 'ERROR'
                })
        
        # 保存缓存
        save_cache(data)
        return data
        
    except Exception as e:
        logger.error(f"YFinance获取失败: {e}")
        
        # 3. 降级到模拟数据
        if use_mock_fallback:
            logger.info("降级到模拟数据")
            return generate_mock_data()
        
        raise

# ============================================================
# Report Generation
# ============================================================
def generate_excel_report(data: Dict, output_date: str = None):
    """生成Excel报告"""
    date_str = output_date or datetime.now().strftime('%Y-%m-%d')
    output_dir = OUTPUT_DIR / f"Report_{date_str}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / f"Mag7_Analysis_{date_str}.xlsx"
    
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # 信号表
        signals_df = pd.DataFrame(data['signals'])
        signals_df.to_excel(writer, sheet_name='Signals', index=False)
        
        # 摘要
        summary = {
            'Metric': ['Total Stocks', 'Bullish', 'Bearish', 'Neutral/Error', 'Data Source'],
            'Value': [
                len(data['signals']),
                sum(1 for s in data['signals'] if s['Signal'] == 'BULLISH'),
                sum(1 for s in data['signals'] if s['Signal'] == 'BEARISH'),
                sum(1 for s in data['signals'] if s['Signal'] not in ['BULLISH', 'BEARISH']),
                'YFinance' if any(s.get('Data_Source') == 'YFINANCE' for s in data['signals']) else 'Mock'
            ]
        }
        summary_df = pd.DataFrame(summary)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
    
    logger.info(f"报告已保存: {output_file}")
    return output_file

def print_summary(data: Dict):
    """打印摘要"""
    print("\n" + "="*60)
    print("Mag7 分析摘要")
    print("="*60)
    
    signals_df = pd.DataFrame(data['signals'])
    
    # 按信号排序
    bullish = signals_df[signals_df['Signal'] == 'BULLISH']
    bearish = signals_df[signals_df['Signal'] == 'BEARISH']
    
    print(f"\n[看涨信号] ({len(bullish)}):")
    for _, row in bullish.iterrows():
        print(f"   {row['Ticker']}: Score={row['Score']:.4f}, Price=${row['Price']}")
    
    print(f"\n[看跌信号] ({len(bearish)}):")
    for _, row in bearish.iterrows():
        print(f"   {row['Ticker']}: Score={row['Score']:.4f}, Price=${row['Price']}")
    
    print(f"\n数据来源: {data['signals'][0].get('Data_Source', 'Unknown')}")
    print("="*60)

# ============================================================
# Main
# ============================================================
def main():
    """主函数"""
    print("\n" + "="*60)
    print("Mag7 Tracker - 安全版")
    print("="*60 + "\n")
    
    # 获取数据
    try:
        data = fetch_mag7_data(use_cache=True, use_mock_fallback=True)
    except Exception as e:
        logger.error(f"数据获取失败: {e}")
        data = generate_mock_data()
    
    # 生成报告
    output_file = generate_excel_report(data)
    
    # 打印摘要
    print_summary(data)
    
    print(f"\n[分析完成]")
    print(f"报告位置: {output_file}")
    
    return data

if __name__ == '__main__':
    main()
