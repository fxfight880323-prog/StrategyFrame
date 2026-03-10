"""
CTA + FLP 策略 - 米筐(RiceQuant) 版本
========================================

使用米筐专业数据服务
API Key: 已配置

支持市场:
- A股 (股票、指数)
- 期货 (股指期货、商品期货)
- 期权 (50ETF期权、300ETF期权)
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Dict, List, Optional

# 导入米筐数据提供器
from RiceQuantDataProvider import RiceQuantDataProvider, CTADataAdapterRQ, FLPDataAdapterRQ


# ============================================================
# CTA 趋势引擎 (米筐版本)
# ============================================================
class CTARiceQuantEngine:
    """
    CTA 趋势引擎 - 米筐数据版本
    
    针对A股和期货市场优化
    """
    
    def __init__(self, symbols: List[str] = None):
        self.provider = RiceQuantDataProvider()
        self.adapter = CTADataAdapterRQ(self.provider)
        self.logger = self.provider.logger
        
        # 默认标的 - A股核心资产 + 股指期货
        self.symbols = symbols or [
            '000001.XSHE',  # 平安银行
            '000002.XSHE',  # 万科A
            '000333.XSHE',  # 美的集团
            '000858.XSHE',  # 五粮液
            '002415.XSHE',  # 海康威视
            '300750.XSHE',  # 宁德时代
            '600000.XSHG',  # 浦发银行
            '600519.XSHG',  # 贵州茅台
            '601318.XSHG',  # 中国平安
            '601888.XSHG',  # 中国中免
        ]
        
        # 期货标的 (如果连接成功)
        self.futures = [
            'IF2403',   # 沪深300指数期货
            'IC2403',   # 中证500指数期货
            'IH2403',   # 上证50指数期货
        ]
    
    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        df = df.copy()
        
        # 移动平均线
        df['fast_ma'] = df['close'].rolling(20).mean()
        df['slow_ma'] = df['close'].rolling(60).mean()
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        df['tr'] = np.maximum(high_low, np.maximum(high_close, low_close))
        df['atr'] = df['tr'].rolling(20).mean()
        
        # 通道
        df['upper_channel'] = df['fast_ma'] + 2.0 * df['atr']
        df['lower_channel'] = df['fast_ma'] - 2.0 * df['atr']
        
        # 波动率
        df['returns'] = df['close'].pct_change()
        df['volatility'] = df['returns'].rolling(60).std() * np.sqrt(252)
        
        return df
    
    def analyze_symbol(self, symbol: str, lookback_days: int = 120) -> Optional[Dict]:
        """
        分析单个标的
        
        Args:
            symbol: 股票/期货代码
            lookback_days: 回看天数
        
        Returns:
            分析结果字典
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=lookback_days + 60)
        
        # 获取数据
        df = self.provider.get_stock_price(
            symbol,
            start_date.isoformat(),
            end_date.isoformat()
        )
        
        if df.empty or len(df) < 60:
            return None
        
        # 计算指标
        df = self.calculate_indicators(df)
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
        
        return {
            'symbol': symbol,
            'name': self._get_symbol_name(symbol),
            'date': str(latest.get('date', df.index[-1]))[:10],
            'price': round(latest['close'], 2),
            'signal': final_signal,
            'score': round(score, 1),
            'fast_ma': round(latest['fast_ma'], 2),
            'slow_ma': round(latest['slow_ma'], 2),
            'volatility': round(latest['volatility'] * 100, 2),
        }
    
    def _get_symbol_name(self, symbol: str) -> str:
        """获取标的名称"""
        name_map = {
            '000001.XSHE': '平安银行',
            '000002.XSHE': '万科A',
            '000333.XSHE': '美的集团',
            '000858.XSHE': '五粮液',
            '002415.XSHE': '海康威视',
            '300750.XSHE': '宁德时代',
            '600000.XSHG': '浦发银行',
            '600519.XSHG': '贵州茅台',
            '601318.XSHG': '中国平安',
            '601888.XSHG': '中国中免',
        }
        return name_map.get(symbol, symbol)
    
    def run_analysis(self) -> pd.DataFrame:
        """运行完整分析"""
        self.logger.info("="*60)
        self.logger.info("CTA 趋势分析 (米筐数据)")
        self.logger.info("="*60)
        
        if not self.provider.connected:
            self.logger.error("❌ 未连接到米筐服务")
            return pd.DataFrame()
        
        results = []
        
        for symbol in self.symbols:
            result = self.analyze_symbol(symbol)
            if result:
                results.append(result)
                self.logger.info(f"{result['symbol']:15s} {result['name']:8s} "
                               f"Signal={result['signal']:5s} Score={result['score']:5.1f}")
        
        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values('score', ascending=False)
        
        return df


# ============================================================
# FLP 保护引擎 (米筐版本 - 50ETF期权)
# ============================================================
class FLPRiceQuantEngine:
    """
    FLP 保护引擎 - 米筐数据版本
    
    使用50ETF期权作为对冲工具
    """
    
    def __init__(self):
        self.provider = RiceQuantDataProvider()
        self.adapter = FLPDataAdapterRQ(self.provider)
        self.logger = self.provider.logger
    
    def get_next_expiry(self) -> date:
        """获取下一个期权到期日 (每月第四个周三)"""
        today = date.today()
        
        # 简化处理：取本月或下月的第四个周三
        from calendar import monthcalendar
        
        for month_offset in [0, 1]:
            year = today.year + (today.month + month_offset - 1) // 12
            month = (today.month + month_offset - 1) % 12 + 1
            
            cal = monthcalendar(year, month)
            wednesdays = [week[2] for week in cal if week[2] != 0]
            
            if len(wednesdays) >= 4:
                expiry = date(year, month, wednesdays[3])
                if expiry > today:
                    return expiry
        
        return today + timedelta(days=30)
    
    def select_put_option(self, expiry_date: date) -> Optional[Dict]:
        """
        选择合适的Put期权
        
        目标：Delta -0.07 ~ -0.10 的虚值Put
        """
        self.logger.info(f"选择 {expiry_date} 到期的Put期权...")
        
        # 获取50ETF期权链
        options_df = self.adapter.get_50etf_options(expiry_date.isoformat())
        
        if options_df is None or options_df.empty:
            self.logger.warning("  未获取到期权数据")
            return None
        
        # 筛选Put期权
        puts = options_df[options_df.get('option_type') == 'P'].copy()
        
        if puts.empty:
            self.logger.warning("  无Put期权")
            return None
        
        # 获取50ETF当前价格
        etf_price = self._get_50etf_price()
        
        # 计算Delta (简化估算)
        puts['delta_estimate'] = puts.apply(
            lambda row: self._estimate_delta(row, etf_price), axis=1
        )
        
        # 筛选目标Delta范围
        target_puts = puts[
            (puts['delta_estimate'] >= -0.10) & 
            (puts['delta_estimate'] <= -0.07)
        ]
        
        if target_puts.empty:
            # 找最接近的
            puts['delta_diff'] = abs(puts['delta_estimate'] - (-0.085))
            target_puts = puts.nsmallest(1, 'delta_diff')
        
        if not target_puts.empty:
            selected = target_puts.iloc[0]
            return {
                'code': selected.get('order_book_id', 'Unknown'),
                'strike': selected.get('strike_price', 0),
                'delta': selected.get('delta_estimate', -0.085),
                'price': selected.get('close', 0),
            }
        
        return None
    
    def _get_50etf_price(self) -> float:
        """获取50ETF当前价格"""
        df = self.provider.get_stock_price('510050.XSHG', 
                                           (date.today() - timedelta(days=5)).isoformat(),
                                           date.today().isoformat())
        if not df.empty:
            return df['close'].iloc[-1]
        return 2.5  # 默认值
    
    def _estimate_delta(self, row: pd.Series, spot_price: float) -> float:
        """
        估算期权Delta
        
        简化Black-Scholes模型
        """
        strike = row.get('strike_price', spot_price)
        
        # 简单的线性估算
        moneyness = strike / spot_price
        
        if moneyness < 0.95:  # 实值
            return -0.5 - (0.95 - moneyness) * 2
        elif moneyness > 1.05:  # 虚值
            return -0.05 - (moneyness - 1.05) * 0.5
        else:  # 平值附近
            return -0.5 + (moneyness - 1.0) * 2
    
    def execute_hedge(self, portfolio_value: float = 1_000_000) -> Optional[Dict]:
        """执行对冲"""
        self.logger.info("="*60)
        self.logger.info("执行 FLP 对冲 (50ETF期权)")
        self.logger.info("="*60)
        
        if not self.provider.connected:
            self.logger.error("❌ 未连接到米筐服务")
            return None
        
        # 获取到期日
        expiry = self.get_next_expiry()
        self.logger.info(f"目标到期日: {expiry}")
        
        # 选择期权
        option = self.select_put_option(expiry)
        
        if option:
            self.logger.info(f"选中期权: {option['code']}")
            self.logger.info(f"  行权价: ¥{option['strike']:.3f}")
            self.logger.info(f"  估算Delta: {option['delta']:.3f}")
            self.logger.info(f"  价格: ¥{option['price']:.4f}")
            
            # 计算合约数量
            budget = portfolio_value * 0.05  # 5%预算
            contract_value = option['price'] * 10000  # 50ETF期权每张10000份
            num_contracts = int(budget / contract_value)
            
            total_cost = contract_value * num_contracts
            
            self.logger.info(f"  预算: ¥{budget:,.0f}")
            self.logger.info(f"  合约数: {num_contracts}张")
            self.logger.info(f"  总成本: ¥{total_cost:,.0f}")
            
            return {
                'expiry': expiry,
                'option': option,
                'contracts': num_contracts,
                'total_cost': total_cost,
            }
        
        return None


# ============================================================
# 整合策略
# ============================================================
class IntegratedRiceQuantStrategy:
    """CTA + FLP 整合策略 - 米筐版本"""
    
    def __init__(self):
        self.cta_engine = CTARiceQuantEngine()
        self.flp_engine = FLPRiceQuantEngine()
    
    def run(self):
        """运行完整策略"""
        print("\n" + "="*70)
        print("CTA + FLP 整合策略 (米筐 RiceQuant 版本)")
        print("="*70)
        print()
        
        # 检查连接
        if not self.cta_engine.provider.connected:
            print("❌ 米筐服务未连接，请检查:")
            print("   1. 是否安装了 rqdatac: pip install rqdatac")
            print("   2. API Key 是否正确")
            return
        
        # 1. CTA分析
        print("【1. CTA 趋势分析】")
        cta_results = self.cta_engine.run_analysis()
        
        if not cta_results.empty:
            print()
            print("Top 10 标的:")
            print(cta_results.head(10)[['symbol', 'name', 'price', 'signal', 'score']].to_string(index=False))
            
            # 保存结果
            cta_results.to_csv("cta_ricequant_signals.csv", index=False)
            print()
            print("✓ 结果已保存: cta_ricequant_signals.csv")
        
        # 2. FLP对冲
        print()
        print("【2. FLP 期权对冲】")
        flp_result = self.flp_engine.execute_hedge()
        
        # 3. 总结
        print()
        print("="*70)
        print("策略运行完成")
        print("="*70)


# ============================================================
# 主函数
# ============================================================
def main():
    """主程序"""
    strategy = IntegratedRiceQuantStrategy()
    strategy.run()


if __name__ == "__main__":
    main()
