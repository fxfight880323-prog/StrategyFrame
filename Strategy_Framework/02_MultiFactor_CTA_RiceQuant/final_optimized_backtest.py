"""
最终优化版回测 (2014-2024)
================================

基于已验证的单因子回测，添加:
1. 参数优化
2. 更长的回测期
3. 详细的性能报告

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
    params: Dict
    start_date: str
    end_date: str
    total_return: float = 0
    annualized_return: float = 0
    volatility: float = 0
    information_ratio: float = 0
    sharpe_ratio: float = 0
    max_drawdown: float = 0
    win_rate: float = 0
    num_months: int = 0
    
    def to_dict(self):
        return {
            'factor_name': self.factor_name,
            'params': self.params,
            'annualized_return': self.annualized_return,
            'information_ratio': self.information_ratio,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate
        }


class FinalOptimizedBacktest:
    """最终优化版回测引擎"""
    
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
    
    def calc_factor_signal(self, stocks: List[str], date: str, factor: str) -> pd.Series:
        """计算因子信号"""
        date_obj = pd.to_datetime(date) - timedelta(days=1)
        trade_date = rq.get_previous_trading_date(date_obj).strftime('%Y-%m-%d')
        
        if factor in ['EP', 'BP', 'SP']:
            # 价值因子
            factor_map = {'EP': 'pe_ratio', 'BP': 'pb_ratio', 'SP': 'ps_ratio'}
            factor_code = factor_map[factor]
            
            try:
                df = rq.get_factor(stocks, factor_code, trade_date, trade_date)
                if df is None or df.empty:
                    return pd.Series(dtype=float)
                
                # 计算倒数
                values = 1 / df[factor_code].replace([np.inf, -np.inf], np.nan)
                values = values.dropna()
                
                # 重置索引只保留股票代码
                if values.index.nlevels > 1:
                    values.index = values.index.get_level_values(0)
                
                # 去极值标准化
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
    
    def backtest_factor(self, factor_name: str, factor_type: str, 
                        start: str, end: str, params: Dict = None) -> BacktestResult:
        """回测单个因子"""
        result = BacktestResult(
            factor_name=factor_name,
            factor_type=factor_type,
            params=params or {},
            start_date=start,
            end_date=end
        )
        
        dates = pd.date_range(start=start, end=end, freq='ME')
        if len(dates) < 2:
            return result
        
        n_long = params.get('n_long', 20) if params else 20
        n_short = params.get('n_short', 20) if params else 20
        
        portfolio = 1.0
        equity_curve = [portfolio]
        monthly_returns = []
        
        logger.info(f"回测: {factor_name} (多头{n_long}/空头{n_short})")
        
        for i in range(1, len(dates)):
            curr_date = dates[i].strftime('%Y-%m-%d')
            prev_date = dates[i-1].strftime('%Y-%m-%d')
            
            stocks = self.get_stocks(prev_date)
            if not stocks:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            signal = self.calc_factor_signal(stocks, prev_date, factor_name)
            
            if signal.empty or len(signal) < 20:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            sorted_sig = signal.sort_values(ascending=False)
            longs = list(sorted_sig.head(n_long).index)
            shorts = list(sorted_sig.tail(n_short).index)
            
            ret = self.calc_portfolio_return(longs, shorts, prev_date, curr_date)
            portfolio *= (1 + ret)
            equity_curve.append(portfolio)
            monthly_returns.append(ret)
            
            if i % 12 == 0:
                logger.info(f"    {curr_date}: 净值={portfolio:.4f}")
        
        if monthly_returns:
            rets = pd.Series(monthly_returns)
            result.total_return = portfolio - 1
            years = len(rets) / 12
            result.annualized_return = (portfolio ** (1/years)) - 1 if portfolio > 0 else -1
            result.volatility = rets.std() * np.sqrt(12)
            if result.volatility > 0:
                result.sharpe_ratio = result.annualized_return / result.volatility
                result.information_ratio = result.sharpe_ratio
            result.win_rate = (rets > 0).sum() / len(rets)
            result.num_months = len(rets)
            
            eq = pd.Series(equity_curve)
            dd = (eq - eq.cummax()) / eq.cummax()
            result.max_drawdown = dd.min()
        
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
            
            stock_returns = (last / first - 1).fillna(0) if hasattr(last, 'fillna') else (last / first - 1)
            
            long_rets = [stock_returns[s] for s in longs if s in stock_returns.index]
            short_rets = [stock_returns[s] for s in shorts if s in stock_returns.index]
            
            return np.mean(long_rets) if long_rets else 0 - np.mean(short_rets) if short_rets else 0
        except:
            return 0
    
    def parameter_optimization(self, start="2014-01-01", end="2024-01-01"):
        """参数优化"""
        print("\n" + "="*80)
        print("参数优化")
        print("="*80 + "\n")
        
        factors = ['EP', 'BP', 'SP', 'MOM_12_1', 'MOM_6_1']
        n_stocks_options = [15, 20, 25]
        
        all_results = []
        
        for factor in factors:
            factor_type = 'value' if factor in ['EP', 'BP', 'SP'] else 'momentum'
            for n_stocks in n_stocks_options:
                params = {'n_long': n_stocks, 'n_short': n_stocks}
                result = self.backtest_factor(factor, factor_type, start, end, params)
                result.params = params
                all_results.append(result)
                logger.info(f"[OK] {factor}_N{n_stocks}: 年化={result.annualized_return*100:.2f}%, IR={result.information_ratio:.2f}")
        
        all_results.sort(key=lambda x: x.information_ratio, reverse=True)
        return all_results
    
    def run(self, start="2014-01-01", end="2024-01-01"):
        """运行完整回测"""
        print("\n" + "="*80)
        print(f"最终优化版多因子回测 ({start} 至 {end})")
        print("="*80 + "\n")
        
        if not self.connected:
            print("[ERROR] 未连接数据服务")
            return []
        
        return self.parameter_optimization(start, end)


def print_results(results):
    if not results:
        return
    
    print("\n" + "="*80)
    print("参数优化结果 (TOP 15)")
    print("="*80)
    
    print(f"{'排名':<5} {'因子':<12} {'参数':<12} {'IR':<8} {'年化':<10} {'夏普':<8} {'回撤':<10} {'胜率':<8}")
    print("-"*90)
    
    for i, r in enumerate(results[:15], 1):
        params_str = f"N{r.params.get('n_long', 20)}"
        print(f"{i:<5} {r.factor_name:<12} {params_str:<12} {r.information_ratio:>7.2f} "
              f"{r.annualized_return*100:>8.2f}% {r.sharpe_ratio:>7.2f} "
              f"{r.max_drawdown*100:>8.2f}% {r.win_rate*100:>6.1f}%")
    
    print("="*80)
    
    # 按因子类型分组
    print("\n[按因子类型分组]")
    value_results = [r for r in results if r.factor_type == 'value'][:5]
    momentum_results = [r for r in results if r.factor_type == 'momentum'][:5]
    
    print("\n价值因子 TOP 5:")
    print(f"{'因子':<12} {'IR':<8} {'年化':<10}")
    print("-"*35)
    for r in value_results:
        print(f"{r.factor_name:<12} {r.information_ratio:>7.2f} {r.annualized_return*100:>8.2f}%")
    
    print("\n动量因子 TOP 5:")
    print(f"{'因子':<12} {'IR':<8} {'年化':<10}")
    print("-"*35)
    for r in momentum_results:
        print(f"{r.factor_name:<12} {r.information_ratio:>7.2f} {r.annualized_return*100:>8.2f}%")
    
    # 保存结果
    data = {
        'metadata': {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
        'all_results': [r.to_dict() for r in results]
    }
    with open('backtests/final_optimized_results.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("\n[OK] 结果已保存到 backtests/final_optimized_results.json")
    
    # 最佳参数
    if results:
        best = results[0]
        print(f"\n[最佳参数]")
        print(f"  因子: {best.factor_name}")
        print(f"  参数: {best.params}")
        print(f"  年化收益: {best.annualized_return*100:.2f}%")
        print(f"  信息比率: {best.information_ratio:.2f}")
        print(f"  夏普比率: {best.sharpe_ratio:.2f}")
        print(f"  最大回撤: {best.max_drawdown*100:.2f}%")
        print(f"  胜率: {best.win_rate*100:.1f}%")
        print(f"  回测月数: {best.num_months}")


if __name__ == "__main__":
    engine = FinalOptimizedBacktest()
    if engine.connected:
        # 先测试2019-2024 (5年)
        results = engine.run("2019-01-01", "2024-01-01")
        print_results(results)
    else:
        print("[ERROR] 连接失败")
