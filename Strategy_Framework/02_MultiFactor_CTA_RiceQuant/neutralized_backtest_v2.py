"""
市值中性化多因子回测 V2 (2019-2024)
=====================================

优化内容:
1. 市值中性化 - 对log(市值)回归取残差
2. 简化行业分类 - 按股票代码前缀（主板/创业板/科创板）
3. 原始 vs 中性化 对比

作者: AI Assistant
日期: 2026-03-06
"""

import pandas as pd
import numpy as np
from typing import List, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import json
import warnings
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

try:
    import rqdatac as rq
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False

try:
    from config import RQ_USERNAME, RQ_PASSWORD
except ImportError:
    RQ_USERNAME = '+8613810062394'
    RQ_PASSWORD = 'Fox880323!'


@dataclass
class BacktestResult:
    factor_name: str
    factor_type: str
    neutralized: bool
    start_date: str
    end_date: str
    annualized_return: float = 0
    information_ratio: float = 0
    sharpe_ratio: float = 0
    max_drawdown: float = 0
    win_rate: float = 0
    
    def to_dict(self):
        return {
            'factor_name': self.factor_name,
            'neutralized': self.neutralized,
            'annualized_return': self.annualized_return,
            'information_ratio': self.information_ratio,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate
        }


class NeutralizedBacktestV2:
    """市值中性化回测引擎 V2"""
    
    def __init__(self):
        self.connected = False
        self._connect()
    
    def _connect(self):
        try:
            logger.info("[INFO] 连接米筐...")
            try:
                rq.deinit()
            except:
                pass
            rq.init(RQ_USERNAME, RQ_PASSWORD)
            
            test = rq.index_components('000300.XSHG', '2024-01-01')
            if test is not None and len(test) > 0:
                self.connected = True
                logger.info(f"[OK] 连接成功！沪深300: {len(test)}只")
                return True
        except Exception as e:
            logger.error(f"[ERROR] 连接失败: {e}")
        return False
    
    def get_stocks(self, date: str) -> List[str]:
        try:
            return rq.index_components('000300.XSHG', date).tolist()
        except:
            return []
    
    def get_prices(self, stocks: List[str], start: str, end: str) -> pd.DataFrame:
        if not stocks:
            return pd.DataFrame()
        try:
            prices = rq.get_price(stocks, start, end, frequency='1d', fields=['close'])
            if isinstance(prices, pd.DataFrame) and 'close' in prices.columns:
                return prices['close']
            return prices
        except:
            return pd.DataFrame()
    
    def get_market_cap(self, stocks: List[str], date: str) -> pd.Series:
        """获取市值数据"""
        try:
            date_obj = pd.to_datetime(date)
            prev = rq.get_previous_trading_date(date_obj).strftime('%Y-%m-%d')
            cap = rq.get_factor(stocks, 'market_cap', prev, prev)
            if cap is not None and not cap.empty:
                series = cap['market_cap']
                if series.index.nlevels > 1:
                    series.index = series.index.get_level_values(0)
                return series
        except:
            pass
        return pd.Series(dtype=float)
    
    def get_simple_industry(self, stocks: List[str]) -> pd.Series:
        """简化行业分类：按股票代码前缀"""
        industries = pd.Series(index=stocks, dtype=str)
        for stock in stocks:
            if '.XSHE' in stock:
                code = stock.split('.')[0]
                if code.startswith('000') or code.startswith('001'):
                    industries[stock] = 'SZ_MAIN'  # 深圳主板
                elif code.startswith('002'):
                    industries[stock] = 'SZ_SMEB'  # 中小板
                elif code.startswith('300'):
                    industries[stock] = 'SZ_CHIN'  # 创业板
                elif code.startswith('301'):
                    industries[stock] = 'SZ_CHIN2' # 创业板2
                else:
                    industries[stock] = 'SZ_OTHER'
            elif '.XSHG' in stock:
                code = stock.split('.')[0]
                if code.startswith('600') or code.startswith('601') or code.startswith('603') or code.startswith('605'):
                    industries[stock] = 'SH_MAIN'  # 上海主板
                elif code.startswith('688'):
                    industries[stock] = 'SH_KCB'   # 科创板
                elif code.startswith('689'):
                    industries[stock] = 'SH_KCB2'  # 科创板2
                else:
                    industries[stock] = 'SH_OTHER'
            else:
                industries[stock] = 'OTHER'
        return industries
    
    def simple_industry_neutralize(self, signals: pd.Series, industries: pd.Series) -> pd.Series:
        """简化行业中性化"""
        if industries.empty or signals.empty:
            return signals
        
        neutralized = pd.Series(index=signals.index, dtype=float)
        
        for industry in industries.unique():
            ind_stocks = industries[industries == industry].index.intersection(signals.index)
            if len(ind_stocks) > 0:
                ind_signals = signals[ind_stocks]
                if len(ind_signals) > 1 and ind_signals.std() > 0:
                    neutralized[ind_stocks] = (ind_signals - ind_signals.mean()) / ind_signals.std()
                else:
                    neutralized[ind_stocks] = 0
        
        return neutralized.dropna()
    
    def size_neutralize(self, signals: pd.Series, market_caps: pd.Series) -> pd.Series:
        """市值中性化：对log(市值)回归取残差"""
        if market_caps.empty or signals.empty:
            return signals
        
        common_stocks = signals.index.intersection(market_caps.index)
        if len(common_stocks) < 10:
            return signals
        
        sig = signals[common_stocks]
        cap = np.log(market_caps[common_stocks].replace(0, np.nan).dropna())
        
        common_stocks = sig.index.intersection(cap.index)
        if len(common_stocks) < 10:
            return signals
        
        sig = sig[common_stocks]
        cap = cap[common_stocks]
        
        try:
            # 计算回归系数
            cov = np.cov(sig, cap)[0, 1]
            var = np.var(cap)
            beta = cov / var if var > 0 else 0
            
            # 计算残差
            residual = sig - beta * cap
            
            # 标准化
            if residual.std() > 0:
                residual = (residual - residual.mean()) / residual.std()
            
            return residual
        except:
            return signals
    
    def calc_factor_signal(self, stocks: List[str], date: str, factor: str) -> pd.Series:
        """计算因子信号"""
        date_obj = pd.to_datetime(date) - timedelta(days=1)
        trade_date = rq.get_previous_trading_date(date_obj).strftime('%Y-%m-%d')
        
        if factor in ['EP', 'BP', 'SP']:
            factor_map = {'EP': 'pe_ratio', 'BP': 'pb_ratio', 'SP': 'ps_ratio'}
            factor_code = factor_map[factor]
            
            try:
                df = rq.get_factor(stocks, factor_code, trade_date, trade_date)
                if df is None or df.empty:
                    return pd.Series(dtype=float)
                
                values = 1 / df[factor_code].replace([np.inf, -np.inf], np.nan)
                values = values.dropna()
                
                if values.index.nlevels > 1:
                    values.index = values.index.get_level_values(0)
                
                if len(values) > 10:
                    values = values.clip(values.quantile(0.05), values.quantile(0.95))
                    if values.std() > 0:
                        values = (values - values.mean()) / values.std()
                
                return values
            except:
                return pd.Series(dtype=float)
        
        else:  # 动量因子
            lookback = 12 if '12' in factor else 6
            end = (date_obj - timedelta(days=30)).strftime('%Y-%m-%d')
            start = (date_obj - timedelta(days=(lookback + 1) * 30)).strftime('%Y-%m-%d')
            
            prices = self.get_prices(stocks, start, end)
            if prices is None or prices.empty:
                return pd.Series(dtype=float)
            
            momentum = pd.Series(index=stocks, dtype=float)
            for stock in stocks:
                try:
                    if isinstance(prices, pd.DataFrame) and stock in prices.columns:
                        p = prices[stock].dropna()
                    elif isinstance(prices, pd.Series) and prices.index.nlevels > 1:
                        try:
                            p = prices.xs(stock, level=0).dropna()
                        except:
                            continue
                    else:
                        continue
                    
                    if len(p) >= 2:
                        momentum[stock] = (p.iloc[-1] / p.iloc[0]) - 1
                except:
                    continue
            
            momentum = momentum.dropna()
            if len(momentum) > 10:
                momentum = momentum.clip(momentum.quantile(0.05), momentum.quantile(0.95))
                if momentum.std() > 0:
                    momentum = (momentum - momentum.mean()) / momentum.std()
            
            return momentum
    
    def apply_neutralization(self, signals: pd.Series, stocks: List[str], date: str,
                            industry_neutral: bool = True, 
                            size_neutral: bool = True) -> pd.Series:
        """应用中性化处理"""
        if signals.empty:
            return signals
        
        result = signals.copy()
        
        # 简化行业中性化
        if industry_neutral:
            industries = self.get_simple_industry(list(result.index))
            result = self.simple_industry_neutralize(result, industries)
        
        # 市值中性化
        if size_neutral:
            market_caps = self.get_market_cap(list(result.index), date)
            if not market_caps.empty:
                result = self.size_neutralize(result, market_caps)
        
        # 最终标准化
        result = result.dropna()
        if len(result) > 10 and result.std() > 0:
            result = (result - result.mean()) / result.std()
        
        return result
    
    def backtest(self, factor_name: str, factor_type: str, 
                 start: str, end: str, neutralized: bool = False) -> BacktestResult:
        """回测"""
        result = BacktestResult(
            factor_name=factor_name,
            factor_type=factor_type,
            neutralized=neutralized,
            start_date=start,
            end_date=end
        )
        
        dates = pd.date_range(start=start, end=end, freq='ME')
        if len(dates) < 2:
            return result
        
        portfolio = 1.0
        equity_curve = [portfolio]
        monthly_returns = []
        
        mode = "中性化" if neutralized else "原始"
        logger.info(f"回测: {factor_name} ({mode})")
        
        for i in range(1, len(dates)):
            curr_date = dates[i].strftime('%Y-%m-%d')
            prev_date = dates[i-1].strftime('%Y-%m-%d')
            
            stocks = self.get_stocks(prev_date)
            if not stocks:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 计算原始信号
            signal = self.calc_factor_signal(stocks, prev_date, factor_name)
            
            if signal.empty or len(signal) < 20:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 应用中性化
            if neutralized:
                signal = self.apply_neutralization(signal, list(signal.index), prev_date)
            
            if signal.empty or len(signal) < 20:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 多空组合
            sorted_sig = signal.sort_values(ascending=False)
            longs = list(sorted_sig.head(20).index)
            shorts = list(sorted_sig.tail(20).index)
            
            ret = self.calc_portfolio_return(longs, shorts, prev_date, curr_date)
            portfolio *= (1 + ret)
            equity_curve.append(portfolio)
            monthly_returns.append(ret)
            
            if i % 12 == 0:
                logger.info(f"    {curr_date}: 净值={portfolio:.4f}")
        
        # 计算指标
        if monthly_returns:
            rets = pd.Series(monthly_returns)
            result.annualized_return = (portfolio ** (12/len(rets))) - 1 if portfolio > 0 else -1
            result.volatility = rets.std() * np.sqrt(12)
            if result.volatility > 0:
                result.sharpe_ratio = result.annualized_return / result.volatility
                result.information_ratio = result.sharpe_ratio
            result.win_rate = (rets > 0).sum() / len(rets)
            
            eq = pd.Series(equity_curve)
            dd = (eq - eq.cummax()) / eq.cummax()
            result.max_drawdown = dd.min()
        
        logger.info(f"[OK] {mode} {factor_name}: 年化={result.annualized_return*100:.2f}%, "
                   f"IR={result.information_ratio:.2f}")
        
        return result
    
    def calc_portfolio_return(self, longs, shorts, start, end):
        """计算组合收益"""
        all_stocks = list(set(longs + shorts))
        if not all_stocks:
            return 0
        
        try:
            prices = self.get_prices(all_stocks, start, end)
            if prices is None or prices.empty:
                return 0
            
            if isinstance(prices, pd.Series):
                prices_df = prices.unstack(level=0) if prices.index.nlevels > 1 else prices.to_frame()
            else:
                prices_df = prices
            
            if prices_df.empty or len(prices_df) < 2:
                return 0
            
            first = prices_df.iloc[0]
            last = prices_df.iloc[-1]
            
            if isinstance(first, (int, float, np.number)):
                return 0
            
            stock_returns = (last / first - 1)
            if hasattr(stock_returns, 'fillna'):
                stock_returns = stock_returns.fillna(0)
            
            long_rets = [stock_returns[s] for s in longs if s in stock_returns.index]
            short_rets = [stock_returns[s] for s in shorts if s in stock_returns.index]
            
            long_mean = np.mean(long_rets) if long_rets else 0
            short_mean = np.mean(short_rets) if short_rets else 0
            
            return long_mean - short_mean
        except:
            return 0
    
    def compare(self, start="2019-01-01", end="2024-01-01"):
        """对比原始 vs 中性化"""
        print("\n" + "="*80)
        print("市值中性化效果对比测试")
        print("="*80 + "\n")
        
        factors = ['EP', 'BP', 'SP', 'MOM_12_1', 'MOM_6_1']
        results = []
        
        for factor in factors:
            factor_type = 'value' if factor in ['EP', 'BP', 'SP'] else 'momentum'
            
            # 原始
            result_raw = self.backtest(factor, factor_type, start, end, neutralized=False)
            results.append(result_raw)
            
            # 中性化
            result_neu = self.backtest(factor, factor_type, start, end, neutralized=True)
            results.append(result_neu)
        
        return results
    
    def run(self, start="2019-01-01", end="2024-01-01"):
        print("\n" + "="*80)
        print(f"市值中性化多因子回测 ({start} 至 {end})")
        print("="*80 + "\n")
        
        if not self.connected:
            print("[ERROR] 未连接数据服务")
            return []
        
        return self.compare(start, end)


def print_comparison(results):
    if not results:
        return
    
    print("\n" + "="*100)
    print("中性化效果对比")
    print("="*100)
    
    print(f"{'因子':<12} {'处理方式':<10} {'IR':<8} {'年化':<10} {'夏普':<8} {'回撤':<10} {'胜率':<8} {'改善':<8}")
    print("-"*100)
    
    factor_names = sorted(set(r.factor_name for r in results))
    
    for factor in factor_names:
        raw = next((r for r in results if r.factor_name == factor and not r.neutralized), None)
        neu = next((r for r in results if r.factor_name == factor and r.neutralized), None)
        
        if raw and neu:
            ir_improve = neu.information_ratio - raw.information_ratio
            ir_improve_str = f"+{ir_improve:.2f}" if ir_improve >= 0 else f"{ir_improve:.2f}"
            
            print(f"{factor:<12} {'原始':<10} {raw.information_ratio:>7.2f} {raw.annualized_return*100:>8.2f}% "
                  f"{raw.sharpe_ratio:>7.2f} {raw.max_drawdown*100:>8.2f}% {raw.win_rate*100:>6.1f}% {'-':<8}")
            
            print(f"{'':<12} {'中性化':<10} {neu.information_ratio:>7.2f} {neu.annualized_return*100:>8.2f}% "
                  f"{neu.sharpe_ratio:>7.2f} {neu.max_drawdown*100:>8.2f}% {neu.win_rate*100:>6.1f}% {ir_improve_str:<8}")
            print("-"*100)
    
    print("="*100)
    
    data = {'comparison': [r.to_dict() for r in results]}
    with open('backtests/neutralized_v2_comparison.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("\n[OK] 结果已保存到 backtests/neutralized_v2_comparison.json")


if __name__ == "__main__":
    engine = NeutralizedBacktestV2()
    if engine.connected:
        results = engine.run("2019-01-01", "2024-01-01")
        print_comparison(results)
    else:
        print("[ERROR] 连接失败")
