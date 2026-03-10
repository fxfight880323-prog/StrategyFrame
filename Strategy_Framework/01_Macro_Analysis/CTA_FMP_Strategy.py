"""
CTA 趋势策略 - FMP 数据版本
===========================

使用 Financial Modeling Prep API 获取实时数据
API Key: Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq

标的: AAPL, MSFT, NVDA, SPY 等美股核心个股
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Dict, List, Optional
import logging

# 路径设置
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', 'data_providers'))

# 导入 FMP 数据提供器
from FMPDataProvider import FMPDataProvider, CTADataAdapter


# ============================================================
# 配置
# ============================================================
CTA_CONFIG = {
    'fast_ma': 20,
    'slow_ma': 60,
    'channel_period': 20,
    'channel_width': 2.0,
}

# 分析标的 (美股核心个股)
DEFAULT_SYMBOLS = [
    'AAPL', 'MSFT', 'AMZN', 'NVDA', 'GOOGL', 'META', 'TSLA',  # Mag7
    'SPY', 'QQQ', 'IWM',  # 指数ETF
    'JPM', 'V', 'BAC',  # 金融
    'XOM', 'CVX',  # 能源
    'JNJ', 'UNH', 'PFE',  # 医药
    'WMT', 'HD', 'COST',  # 消费
]


# ============================================================
# CTA 趋势引擎 (FMP 版本)
# ============================================================
class CTAEngineFMP:
    """
    CTA 趋势引擎 - 使用 FMP 数据
    """
    
    def __init__(self, config: Dict = CTA_CONFIG):
        self.config = config
        self.fmp = FMPDataProvider()
        self.adapter = CTADataAdapter(self.fmp)
        self.logger = self.fmp.logger
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()
        
        # 移动平均线
        df['fast_ma'] = df['close'].rolling(self.config['fast_ma']).mean()
        df['slow_ma'] = df['close'].rolling(self.config['slow_ma']).mean()
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        df['tr'] = np.maximum(high_low, np.maximum(high_close, low_close))
        df['atr'] = df['tr'].rolling(self.config['channel_period']).mean()
        
        # 通道
        df['upper_channel'] = df['fast_ma'] + self.config['channel_width'] * df['atr']
        df['lower_channel'] = df['fast_ma'] - self.config['channel_width'] * df['atr']
        
        # 波动率
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(60).std() * np.sqrt(252)
        
        return df
    
    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Dict:
        """生成 CTA 信号"""
        df = self.calculate_indicators(df)
        
        # 获取最新数据
        latest = df.iloc[-1]
        
        # MA 交叉信号
        if latest['fast_ma'] > latest['slow_ma']:
            ma_signal = 'LONG'
        elif latest['fast_ma'] < latest['slow_ma']:
            ma_signal = 'SHORT'
        else:
            ma_signal = 'FLAT'
        
        # 通道信号
        if latest['close'] > latest['upper_channel']:
            channel_signal = 'LONG'
        elif latest['close'] < latest['lower_channel']:
            channel_signal = 'SHORT'
        else:
            channel_signal = 'FLAT'
        
        # 综合信号
        if ma_signal == channel_signal and ma_signal != 'FLAT':
            final_signal = ma_signal
        else:
            final_signal = 'FLAT'
        
        # 计算评分 (0-100)
        score = 50
        if final_signal == 'LONG':
            score += 20
            # 趋势强度加分
            ma_diff = (latest['fast_ma'] / latest['slow_ma'] - 1) * 100
            score += min(ma_diff * 10, 15)
        elif final_signal == 'SHORT':
            score -= 20
            ma_diff = (latest['slow_ma'] / latest['fast_ma'] - 1) * 100
            score -= min(ma_diff * 10, 15)
        
        score = max(0, min(100, score))
        
        return {
            'symbol': symbol,
            'date': df.index[-1] if isinstance(df.index[-1], str) else str(df.index[-1]),
            'price': latest['close'],
            'signal': final_signal,
            'score': round(score, 1),
            'fast_ma': latest['fast_ma'],
            'slow_ma': latest['slow_ma'],
            'atr': latest['atr'],
            'volatility': latest['volatility'],
        }
    
    def analyze_symbols(self, symbols: List[str] = None, 
                       lookback_days: int = 120) -> pd.DataFrame:
        """
        分析多个标的
        
        Args:
            symbols: 标的列表
            lookback_days: 回看天数
        
        Returns:
            DataFrame with signals for all symbols
        """
        if symbols is None:
            symbols = DEFAULT_SYMBOLS
        
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days + 60)  # 额外60天用于计算MA
        
        self.logger.info("="*60)
        self.logger.info("CTA 趋势分析 (FMP 数据)")
        self.logger.info("="*60)
        self.logger.info(f"分析标的: {len(symbols)} 只")
        self.logger.info(f"数据区间: {start_date} 至 {end_date}")
        
        results = []
        
        for symbol in symbols:
            try:
                # 获取数据
                df = self.fmp.get_historical_price(
                    symbol, 
                    start_date.isoformat(), 
                    end_date.isoformat()
                )
                
                if df.empty or len(df) < 60:
                    self.logger.warning(f"  {symbol}: 数据不足，跳过")
                    continue
                
                # 标准化列名
                df.columns = [c.lower() for c in df.columns]
                
                # 生成信号
                signal = self.generate_signal(df, symbol)
                results.append(signal)
                
                self.logger.info(f"  {symbol}: Signal={signal['signal']}, Score={signal['score']}")
                
            except Exception as e:
                self.logger.error(f"  {symbol}: 分析失败 - {e}")
        
        # 转换为 DataFrame 并排序
        results_df = pd.DataFrame(results)
        if not results_df.empty:
            results_df = results_df.sort_values('score', ascending=False)
        
        return results_df
    
    def get_top_picks(self, n: int = 10, min_score: float = 60.0) -> pd.DataFrame:
        """获取 top N 推荐"""
        results = self.analyze_symbols()
        
        # 筛选高评分标的
        top = results[results['score'] >= min_score].head(n)
        
        return top


# ============================================================
# 主函数
# ============================================================
def main():
    """主程序"""
    print("\n" + "="*70)
    print("CTA 趋势策略 - FMP 数据版本")
    print("="*70)
    print()
    
    # 创建引擎
    engine = CTAEngineFMP()
    
    # 运行分析
    results = engine.analyze_symbols(lookback_days=120)
    
    if results.empty:
        print("分析失败，无数据返回")
        return
    
    print()
    print("="*70)
    print("分析结果")
    print("="*70)
    print()
    
    # Top 10
    print("【Top 10 强势标的】")
    top10 = results.head(10)
    print(f"{'排名':<6} {'代码':<8} {'价格':<12} {'评分':<8} {'信号':<8}")
    print("-" * 50)
    for i, (_, row) in enumerate(top10.iterrows(), 1):
        print(f"{i:<6} {row['symbol']:<8} ${row['price']:<11.2f} {row['score']:<8.1f} {row['signal']:<8}")
    print()
    
    # 空头信号
    print("【空头信号】")
    shorts = results[results['signal'] == 'SHORT'].head(5)
    if not shorts.empty:
        print(f"{'代码':<8} {'价格':<12} {'评分':<8}")
        print("-" * 30)
        for _, row in shorts.iterrows():
            print(f"{row['symbol']:<8} ${row['price']:<11.2f} {row['score']:<8.1f}")
    else:
        print("  无空头信号")
    print()
    
    # 统计
    print("【统计摘要】")
    print(f"  分析标的: {len(results)} 只")
    print(f"  多头信号: {len(results[results['signal'] == 'LONG'])} 只")
    print(f"  空头信号: {len(results[results['signal'] == 'SHORT'])} 只")
    print(f"  中性信号: {len(results[results['signal'] == 'FLAT'])} 只")
    print(f"  平均评分: {results['score'].mean():.1f}")
    print()
    
    # 保存结果
    output_file = "cta_fmp_analysis.csv"
    results.to_csv(output_file, index=False)
    print(f"结果已保存: {output_file}")
    print()


if __name__ == "__main__":
    main()
