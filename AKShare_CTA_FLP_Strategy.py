"""
CTA + FLP 尾部风险对冲策略 - AKShare 版本
============================================

使用 AKShare 获取美股数据
优势:
- 无需 API Key
- 国内访问稳定
- 支持美股、期货、期权数据

策略组件:
1. CTA: 20/60日MA交叉 + 通道突破 + 波动率加权
2. FLP: 每周买入 Delta -0.07~-0.10 的 SPY Put
3. 风险平衡: CTA盈利时回哺15%增持FLP保护
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import akshare as ak
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import time
import logging


# ============================================================
# 配置
# ============================================================
CTA_CONFIG = {
    'fast_ma': 20,
    'slow_ma': 60,
    'channel_period': 20,
    'channel_width': 2.0,
    'symbols': ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'GLD', 'TLT']
}

FLP_CONFIG = {
    'underlying': 'SPY',
    'delta_target': (-0.10, -0.07),
    'vix_proxy': 'VIXY',  # AKShare 可能无法直接获取 VIX，使用 VIXY 作为代理
    'vix_low': 15,
    'vix_high': 30,
    'budget_increase': 0.20,
}

RISK_CONFIG = {
    'cta_base': 0.75,
    'flp_base': 0.05,
    'cash_base': 0.20,
    'profit_reinvest': 0.15,
    'max_flp': 0.10,
    'min_flp': 0.02,
}


# ============================================================
# 日志设置
# ============================================================
def setup_logger(name: str = "akshare_cta_flp") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# AKShare 数据提供器
# ============================================================
class AKShareDataProvider:
    """
    AKShare 数据提供器
    
    统一封装 AKShare 美股数据接口
    """
    
    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or setup_logger()
        self.cache = {}
    
    def get_us_stock(self, symbol: str, period: str = "3y") -> pd.DataFrame:
        """
        获取美股历史数据
        
        Args:
            symbol: 股票代码 (如 'AAPL', 'SPY')
            period: 时间周期 (1y, 3y, 5y, max)
        
        Returns:
            DataFrame with columns: date, open, high, low, close, volume
        """
        cache_key = f"stock_{symbol}_{period}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            self.logger.info(f"获取 {symbol} 数据...")
            
            # 使用 AKShare 美股日线接口
            df = ak.stock_us_daily(symbol=symbol, adjust="")
            
            if df is None or df.empty:
                self.logger.warning(f"  {symbol}: 无数据返回")
                return pd.DataFrame()
            
            # 标准化列名
            df = df.reset_index()
            
            # 确保列名正确
            column_map = {
                'date': 'date',
                'Date': 'date',
                'open': 'open',
                'Open': 'open',
                'high': 'high',
                'High': 'high',
                'low': 'low',
                'Low': 'low',
                'close': 'close',
                'Close': 'close',
                'volume': 'volume',
                'Volume': 'volume',
            }
            
            df = df.rename(columns=column_map)
            
            # 确保 date 列是 datetime
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])
            
            # 按日期排序
            df = df.sort_values('date')
            
            # 根据 period 筛选数据
            if period == '1y':
                cutoff = datetime.now() - timedelta(days=365)
            elif period == '3y':
                cutoff = datetime.now() - timedelta(days=365*3)
            elif period == '5y':
                cutoff = datetime.now() - timedelta(days=365*5)
            else:
                cutoff = datetime.now() - timedelta(days=365*10)
            
            df = df[df['date'] >= cutoff]
            
            self.cache[cache_key] = df
            self.logger.info(f"  ✓ 成功: {len(df)} 条记录")
            return df
            
        except Exception as e:
            self.logger.error(f"  ✗ 失败: {e}")
            return pd.DataFrame()
    
    def get_multiple_stocks(self, symbols: List[str], period: str = "3y") -> Dict[str, pd.DataFrame]:
        """批量获取多只股票"""
        results = {}
        
        for symbol in symbols:
            df = self.get_us_stock(symbol, period)
            if not df.empty:
                results[symbol] = df
            time.sleep(0.3)  # 限速
        
        return results
    
    def get_vix_proxy(self, period: str = "3y") -> pd.DataFrame:
        """
        获取 VIX 代理数据
        
        使用 VIXY (VIX 短期期货 ETF) 作为 VIX 的代理
        """
        return self.get_us_stock('VIXY', period)
    
    def estimate_vix_from_price(self, price_df: pd.DataFrame, window: int = 20) -> pd.Series:
        """
        从价格数据估算 VIX
        
        使用实现波动率的年化值作为 VIX 估算
        """
        returns = price_df['close'].pct_change()
        realized_vol = returns.rolling(window).std() * np.sqrt(252) * 100
        return realized_vol


# ============================================================
# CTA 趋势引擎 (AKShare 版本)
# ============================================================
class CTAKShareEngine:
    """CTA 趋势引擎 - AKShare 数据版本"""
    
    def __init__(self, config: Dict = CTA_CONFIG):
        self.config = config
        self.data_provider = AKShareDataProvider()
        self.logger = self.data_provider.logger
    
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
    
    def generate_signals(self) -> pd.DataFrame:
        """
        生成 CTA 信号
        
        Returns:
            DataFrame with signals for all symbols
        """
        self.logger.info("="*60)
        self.logger.info("CTA 趋势分析 (AKShare 数据)")
        self.logger.info("="*60)
        
        # 获取数据
        data = self.data_provider.get_multiple_stocks(
            self.config['symbols'], 
            period='3y'
        )
        
        results = []
        
        for symbol, df in data.items():
            try:
                # 计算指标
                df = self.calculate_indicators(df)
                
                # 获取最新数据
                latest = df.iloc[-1]
                
                # MA 信号
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
                if ma_signal == channel_signal:
                    final_signal = ma_signal
                else:
                    final_signal = 'FLAT'
                
                # 评分
                score = 50
                if final_signal == 'LONG':
                    score += 20
                    ma_diff = (latest['fast_ma'] / latest['slow_ma'] - 1) * 100
                    score += min(ma_diff * 10, 15)
                elif final_signal == 'SHORT':
                    score -= 20
                    ma_diff = (latest['slow_ma'] / latest['fast_ma'] - 1) * 100
                    score -= min(ma_diff * 10, 15)
                
                score = max(0, min(100, score))
                
                # 波动率权重
                vol = latest['volatility']
                position_size = 1.0 / (vol * 10) if vol > 0 else 0.1
                position_size = min(position_size, 1.0)
                
                results.append({
                    'symbol': symbol,
                    'date': str(latest['date'])[:10],
                    'price': round(latest['close'], 2),
                    'signal': final_signal,
                    'score': round(score, 1),
                    'fast_ma': round(latest['fast_ma'], 2),
                    'slow_ma': round(latest['slow_ma'], 2),
                    'volatility': round(vol * 100, 2),  # 转为百分比
                    'position_size': round(position_size, 2),
                })
                
                self.logger.info(f"{symbol:6s}: Signal={final_signal:5s}, Score={score:5.1f}, "
                               f"Vol={vol*100:5.2f}%")
                
            except Exception as e:
                self.logger.error(f"{symbol}: 分析失败 - {e}")
        
        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values('score', ascending=False)
        
        return df


# ============================================================
# FLP 保护引擎 (AKShare 版本)
# ============================================================
class FLPAKShareEngine:
    """FLP 保护引擎 - AKShare 数据版本"""
    
    def __init__(self, config: Dict = FLP_CONFIG):
        self.config = config
        self.data_provider = AKShareDataProvider()
        self.logger = self.data_provider.logger
    
    def get_next_friday(self, from_date: date = None) -> date:
        """获取下一个周五"""
        if from_date is None:
            from_date = date.today()
        
        days_ahead = 4 - from_date.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        return from_date + timedelta(days=days_ahead)
    
    def estimate_vix(self) -> float:
        """
        估算当前 VIX
        
        使用 SPY 的实现波动率作为 VIX 的估算
        """
        df = self.data_provider.get_us_stock('SPY', period='1y')
        
        if df.empty:
            return 20.0  # 默认值
        
        # 计算实现波动率
        df['returns'] = df['close'].pct_change()
        realized_vol = df['returns'].rolling(20).std().iloc[-1] * np.sqrt(252) * 100
        
        # 添加一些随机性模拟 VIX 的波动
        noise = np.random.normal(0, 2)
        vix_estimate = realized_vol + noise
        
        return max(10, min(50, vix_estimate))
    
    def execute_weekly_hedge(self, portfolio_value: float = 1_000_000,
                            trade_date: date = None) -> Optional[Dict]:
        """
        执行每周 FLP 对冲
        
        由于 AKShare 不直接提供期权数据，这里使用模拟逻辑
        """
        if trade_date is None:
            trade_date = date.today()
        
        # 只在周五执行
        if trade_date.weekday() != 4:
            return None
        
        self.logger.info("="*60)
        self.logger.info(f"执行 FLP 周度对冲 - {trade_date}")
        self.logger.info("="*60)
        
        # 获取 SPY 数据
        spy_df = self.data_provider.get_us_stock('SPY', period='1y')
        if spy_df.empty:
            self.logger.error("无法获取 SPY 数据")
            return None
        
        spy_price = spy_df['close'].iloc[-1]
        self.logger.info(f"SPY 价格: ${spy_price:.2f}")
        
        # 估算 VIX
        vix = self.estimate_vix()
        self.logger.info(f"估算 VIX: {vix:.2f}")
        
        # 确定模式
        if vix < self.config['vix_low']:
            mode = 'Long Put'
            budget_adj = 1 + self.config['budget_increase']
        elif vix > self.config['vix_high']:
            mode = 'Put Spread'
            budget_adj = 0.7
        else:
            mode = 'Long Put'
            budget_adj = 1.0
        
        self.logger.info(f"保护模式: {mode}")
        
        # 计算预算
        base_budget = portfolio_value * RISK_CONFIG['flp_base']
        budget = base_budget * budget_adj
        self.logger.info(f"保护预算: ${budget:,.2f}")
        
        # 模拟选择 Put (Delta -0.07 ~ -0.10)
        # 约 2% OTM
        put_strike = spy_price * 0.98
        put_delta = -0.085  # 中间值
        
        # 估算权利金 (简化 Black-Scholes)
        time_to_expiry = 7 / 365
        volatility = vix / 100
        premium = spy_price * volatility * np.sqrt(time_to_expiry) * 0.4
        
        # 计算合约数量
        contract_value = premium * 100  # 每手100股
        num_contracts = int(budget / contract_value)
        
        total_cost = contract_value * num_contracts
        
        self.logger.info(f"买入 Put: Strike=${put_strike:.2f}, Delta={put_delta:.3f}")
        self.logger.info(f"权利金: ${premium:.2f}, 合约数: {num_contracts}")
        self.logger.info(f"总成本: ${total_cost:.2f}")
        self.logger.info("="*60)
        
        return {
            'date': trade_date,
            'spy_price': spy_price,
            'vix': vix,
            'mode': mode,
            'put_strike': put_strike,
            'put_delta': put_delta,
            'premium': premium,
            'contracts': num_contracts,
            'total_cost': total_cost,
            'budget': budget,
        }


# ============================================================
# 整合策略
# ============================================================
class IntegratedAKShareStrategy:
    """CTA + FLP 整合策略 - AKShare 版本"""
    
    def __init__(self):
        self.cta_engine = CTAKShareEngine()
        self.flp_engine = FLPAKShareEngine()
        self.logger = self.cta_engine.logger
        
        self.portfolio_value = 1_000_000
        self.cta_pnl = 0
    
    def calculate_allocation(self) -> Dict[str, float]:
        """计算资金分配"""
        base_cta = RISK_CONFIG['cta_base']
        base_flp = RISK_CONFIG['flp_base']
        
        # 盈利回哺
        if self.cta_pnl > 0:
            profit_boost = min(
                self.cta_pnl * RISK_CONFIG['profit_reinvest'],
                self.portfolio_value * 0.05
            )
            cta_weight = base_cta - (profit_boost / self.portfolio_value)
            flp_weight = base_flp + (profit_boost / self.portfolio_value)
        else:
            cta_weight = base_cta
            flp_weight = base_flp
        
        # 边界检查
        flp_weight = max(min(flp_weight, RISK_CONFIG['max_flp']), RISK_CONFIG['min_flp'])
        cash_weight = 1 - cta_weight - flp_weight
        
        return {
            'cta': cta_weight,
            'flp': flp_weight,
            'cash': cash_weight
        }
    
    def run_strategy(self):
        """运行完整策略"""
        print("\n" + "="*70)
        print("CTA + FLP 整合策略 (AKShare 版本)")
        print("="*70)
        print()
        
        # 1. CTA 分析
        print("【1. CTA 趋势分析】")
        cta_signals = self.cta_engine.generate_signals()
        
        if not cta_signals.empty:
            print()
            print("Top 10 强势标的:")
            print(cta_signals.head(10)[['symbol', 'price', 'signal', 'score']].to_string(index=False))
        
        # 2. FLP 对冲
        print()
        print("【2. FLP 尾部保护】")
        
        today = date.today()
        if today.weekday() == 4:
            flp_trade = self.flp_engine.execute_weekly_hedge(self.portfolio_value)
        else:
            next_friday = self.flp_engine.get_next_friday()
            print(f"今天不是周五，下次对冲日期: {next_friday}")
            flp_trade = None
        
        # 3. 资金分配
        print()
        print("【3. 风险预算分配】")
        allocation = self.calculate_allocation()
        
        print(f"CTA 策略:  {allocation['cta']*100:5.1f}%  "
              f"(${self.portfolio_value * allocation['cta']:,.0f})")
        print(f"FLP 保护:  {allocation['flp']*100:5.1f}%  "
              f"(${self.portfolio_value * allocation['flp']:,.0f})")
        print(f"现金:      {allocation['cash']*100:5.1f}%  "
              f"(${self.portfolio_value * allocation['cash']:,.0f})")
        
        # 4. 保存结果
        print()
        print("【4. 保存结果】")
        
        if not cta_signals.empty:
            cta_signals.to_csv("cta_akshare_signals.csv", index=False)
            print("CTA 信号已保存: cta_akshare_signals.csv")
        
        print()
        print("="*70)
        print("策略运行完成")
        print("="*70)


# ============================================================
# 主函数
# ============================================================
def main():
    """主程序"""
    strategy = IntegratedAKShareStrategy()
    strategy.run_strategy()


if __name__ == "__main__":
    main()
