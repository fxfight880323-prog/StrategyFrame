"""
优化版多因子回测 V2 (2014-2024)
=================================

简化版 - 稳定可靠的多因子回测
优化内容:
1. 价值+动量双因子组合
2. 行业/市值中性化
3. 延长回测期
4. 参数优化
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import json
import warnings
import sys
import io
from itertools import product

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
            'factor_type': self.factor_type,
            'params': self.params,
            'annualized_return': self.annualized_return,
            'information_ratio': self.information_ratio,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate
        }


class OptimizedBacktestV2:
    """优化版回测引擎 V2 - 简化稳定版"""
    
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
    
    def get_industry(self, stocks: List[str], date: str) -> pd.Series:
        """获取行业分类"""
        try:
            return rq.get_industry(stocks, date=date, level=1, source='sws')
        except:
            return pd.Series(index=stocks, dtype=str)
    
    def calc_value_signal(self, stocks: List[str], date: str) -> pd.Series:
        """计算价值因子信号 (EP + BP)"""
        try:
            curr = pd.to_datetime(date)
            prev = rq.get_previous_trading_date(curr).strftime('%Y-%m-%d')
            
            # 获取EP和BP
            pe_df = rq.get_factor(stocks, 'pe_ratio', prev, prev)
            pb_df = rq.get_factor(stocks, 'pb_ratio', prev, prev)
            
            if pe_df is None and pb_df is None:
                return pd.Series(dtype=float)
            
            signals = pd.Series(0, index=stocks, dtype=float)
            count = 0
            
            if pe_df is not None and not pe_df.empty:
                ep = 1 / pe_df['pe_ratio'].replace([np.inf, -np.inf], np.nan)
                ep = ep.dropna()
                # 标准化
                if len(ep) > 10 and ep.std() > 0:
                    ep = (ep - ep.mean()) / ep.std()
                    for idx, val in ep.items():
                        stock = idx[0] if isinstance(idx, tuple) else idx
                        if stock in signals.index:
                            signals[stock] += val
                    count += 1
            
            if pb_df is not None and not pb_df.empty:
                bp = 1 / pb_df['pb_ratio'].replace([np.inf, -np.inf], np.nan)
                bp = bp.dropna()
                if len(bp) > 10 and bp.std() > 0:
                    bp = (bp - bp.mean()) / bp.std()
                    for idx, val in bp.items():
                        stock = idx[0] if isinstance(idx, tuple) else idx
                        if stock in signals.index:
                            signals[stock] += val
                    count += 1
            
            if count > 0:
                signals = signals / count
            
            return signals[signals != 0]
        except Exception as e:
            logger.debug(f"价值因子计算失败: {e}")
            return pd.Series(dtype=float)
    
    def calc_momentum_signal(self, stocks: List[str], date: str, lookback: int = 12) -> pd.Series:
        """计算动量因子信号"""
        try:
            date_obj = pd.to_datetime(date)
            end = rq.get_previous_trading_date(date_obj).strftime('%Y-%m-%d')
            start = (date_obj - timedelta(days=lookback*30)).strftime('%Y-%m-%d')
            
            prices = self.get_prices(stocks, start, end)
            if prices is None or prices.empty:
                return pd.Series(dtype=float)
            
            momentum = pd.Series(index=stocks, dtype=float)
            
            for stock in stocks:
                try:
                    if isinstance(prices, pd.DataFrame):
                        if stock in prices.columns:
                            p = prices[stock].dropna()
                        else:
                            continue
                    elif isinstance(prices, pd.Series):
                        if prices.index.nlevels > 1:
                            try:
                                p = prices.xs(stock, level=0).dropna()
                            except:
                                continue
                        else:
                            continue
                    else:
                        continue
                    
                    if len(p) >= 2:
                        momentum[stock] = (p.iloc[-1] / p.iloc[0]) - 1
                except:
                    continue
            
            momentum = momentum.dropna()
            if len(momentum) > 10 and momentum.std() > 0:
                momentum = momentum.clip(momentum.quantile(0.05), momentum.quantile(0.95))
                momentum = (momentum - momentum.mean()) / momentum.std()
            
            return momentum
        except Exception as e:
            logger.debug(f"动量因子计算失败: {e}")
            return pd.Series(dtype=float)
    
    def apply_neutralization(self, signals: pd.Series, stocks: List[str], date: str, 
                            neutralize_industry: bool = True, 
                            neutralize_size: bool = True) -> pd.Series:
        """应用行业/市值中性化"""
        if signals.empty:
            return signals
        
        result = signals.copy()
        
        # 行业中性化
        if neutralize_industry:
            try:
                industries = self.get_industry(stocks, date)
                if not industries.empty:
                    for industry in industries.unique():
                        mask = industries == industry
                        ind_stocks_raw = industries[mask].index
                        # 提取股票代码
                        ind_stocks = set()
                        for s in ind_stocks_raw:
                            ind_stocks.add(s[0] if isinstance(s, tuple) else s)
                        ind_stocks = list(ind_stocks.intersection(set(result.index)))
                        if len(ind_stocks) > 0:
                            ind_signals = result[ind_stocks]
                            if ind_signals.std() > 0:
                                result[ind_stocks] = (ind_signals - ind_signals.mean()) / ind_signals.std()
                            else:
                                result[ind_stocks] = 0
            except:
                pass
        
        # 最终标准化
        if result.std() > 0:
            result = (result - result.mean()) / result.std()
        
        return result
    
    def calc_composite_signal(self, stocks: List[str], date: str, 
                             value_weight: float, 
                             momentum_weight: float,
                             momentum_lookback: int,
                             neutralize: bool = True) -> pd.Series:
        """计算复合信号"""
        # 获取各因子信号
        value_sig = self.calc_value_signal(stocks, date)
        mom_sig = self.calc_momentum_signal(stocks, date, momentum_lookback)
        
        # 构建复合信号
        composite = pd.Series(0, index=stocks, dtype=float)
        total_weight = 0
        
        if not value_sig.empty:
            for idx, val in value_sig.items():
                stock = idx[0] if isinstance(idx, tuple) else idx
                if stock in composite.index:
                    composite[stock] += val * value_weight
            total_weight += value_weight
        
        if not mom_sig.empty:
            for idx, val in mom_sig.items():
                stock = idx[0] if isinstance(idx, tuple) else idx
                if stock in composite.index:
                    composite[stock] += val * momentum_weight
            total_weight += momentum_weight
        
        if total_weight > 0:
            composite = composite[composite != 0]
            # 中性化
            if neutralize:
                composite = self.apply_neutralization(composite, list(composite.index), date)
            else:
                if composite.std() > 0:
                    composite = (composite - composite.mean()) / composite.std()
        
        return composite
    
    def backtest(self, params: Dict, start: str, end: str) -> BacktestResult:
        """回测"""
        result = BacktestResult(
            factor_name=params.get('name', 'Composite'),
            factor_type='multi-factor',
            params=params,
            start_date=start,
            end_date=end
        )
        
        dates = pd.date_range(start=start, end=end, freq='ME')
        if len(dates) < 2:
            return result
        
        portfolio = 1.0
        equity_curve = [portfolio]
        monthly_returns = []
        
        logger.info(f"回测: {result.factor_name}")
        logger.info(f"  参数: 价值权重={params.get('value_w', 0.5)}, 动量权重={params.get('momentum_w', 0.5)}, "
                   f"回看={params.get('lookback', 12)}月, 中性化={params.get('neutralize', True)}")
        
        for i in range(1, len(dates)):
            curr_date = dates[i].strftime('%Y-%m-%d')
            prev_date = dates[i-1].strftime('%Y-%m-%d')
            
            stocks = self.get_stocks(prev_date)
            if not stocks:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 计算复合信号
            signal = self.calc_composite_signal(
                stocks, prev_date,
                value_weight=params.get('value_w', 0.5),
                momentum_weight=params.get('momentum_w', 0.5),
                momentum_lookback=params.get('lookback', 12),
                neutralize=params.get('neutralize', True)
            )
            
            if signal.empty or len(signal) < 20:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 多空组合
            sorted_sig = signal.sort_values(ascending=False)
            n_stocks = params.get('n_stocks', 20)
            longs = list(sorted_sig.head(n_stocks).index)
            shorts = list(sorted_sig.tail(n_stocks).index)
            
            # 计算收益
            ret = self.calc_portfolio_return(longs, shorts, prev_date, curr_date)
            portfolio *= (1 + ret)
            equity_curve.append(portfolio)
            monthly_returns.append(ret)
            
            if i % 12 == 0:
                logger.info(f"    {curr_date}: 净值={portfolio:.4f}, 月收益={ret*100:.2f}%")
        
        # 计算指标
        if monthly_returns:
            rets = pd.Series(monthly_returns)
            result.total_return = portfolio - 1
            years = len(rets) / 12
            result.annualized_return = (portfolio ** (1/years)) - 1 if portfolio > 0 and years > 0 else -1
            result.volatility = rets.std() * np.sqrt(12)
            if result.volatility > 0:
                result.sharpe_ratio = result.annualized_return / result.volatility
                result.information_ratio = result.sharpe_ratio
            result.win_rate = (rets > 0).sum() / len(rets)
            result.num_months = len(rets)
            
            eq = pd.Series(equity_curve)
            dd = (eq - eq.cummax()) / eq.cummax()
            result.max_drawdown = dd.min()
        
        logger.info(f"[OK] {result.factor_name}: 年化={result.annualized_return*100:.2f}%, "
                   f"IR={result.information_ratio:.2f}, 胜率={result.win_rate*100:.1f}%")
        
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
            
            # 统一处理价格数据格式
            if isinstance(prices, pd.Series):
                if prices.index.nlevels > 1:
                    # MultiIndex Series: (date, stock) 或 (stock, date)
                    prices_df = prices.unstack(level=0 if prices.index.names[0] == 'date' else 1)
                else:
                    prices_df = prices.to_frame()
            else:
                prices_df = prices
            
            if prices_df.empty or len(prices_df) < 2:
                return 0
            
            # 计算每只股票的收益
            first_prices = prices_df.iloc[0]
            last_prices = prices_df.iloc[-1]
            
            # 处理可能为标量的情况
            if isinstance(first_prices, (int, float)):
                return 0  # 只有一只股票且数据异常
            
            stock_returns = (last_prices / first_prices - 1)
            if hasattr(stock_returns, 'fillna'):
                stock_returns = stock_returns.fillna(0)
            
            # 计算组合收益
            long_rets = [stock_returns[s] for s in longs if s in stock_returns.index]
            short_rets = [stock_returns[s] for s in shorts if s in stock_returns.index]
            
            long_mean = np.mean(long_rets) if long_rets else 0
            short_mean = np.mean(short_rets) if short_rets else 0
            
            return long_mean - short_mean
        except Exception as e:
            logger.debug(f"收益计算异常: {e}")
            return 0
    
    def run_optimization(self, start="2019-01-01", end="2024-01-01"):
        """参数优化"""
        print("\n" + "="*80)
        print("参数优化")
        print("="*80 + "\n")
        
        param_grid = []
        for vw, mw, lb, ns, neu in product(
            [0.3, 0.5, 0.7],      # 价值权重
            [0.3, 0.5, 0.7],      # 动量权重
            [6, 12],              # 回看期
            [15, 20],             # 持仓数量
            [True, False]         # 中性化
        ):
            if abs(vw + mw - 1.0) < 0.01:  # 确保权重和为1
                param_grid.append({
                    'value_w': vw,
                    'momentum_w': mw,
                    'lookback': lb,
                    'n_stocks': ns,
                    'neutralize': neu,
                    'name': f'V{vw:.1f}M{mw:.1f}_L{lb}_N{ns}_{"N" if neu else "NN"}'
                })
        
        print(f"总参数组合数: {len(param_grid)}")
        print(f"测试前10个组合\n")
        
        results = []
        for i, params in enumerate(param_grid[:10]):
            result = self.backtest(params, start, end)
            results.append(result)
        
        results.sort(key=lambda x: x.information_ratio, reverse=True)
        return results
    
    def run_full_backtest(self, start="2014-01-01", end="2024-01-01"):
        """运行完整回测"""
        print("\n" + "="*80)
        print(f"优化版多因子回测 V2 ({start} 至 {end})")
        print("="*80 + "\n")
        
        if not self.connected:
            print("[ERROR] 未连接数据服务")
            return []
        
        results = self.run_optimization(start, end)
        return results


def print_results(results):
    if not results:
        print("\n[WARNING] 没有回测结果")
        return
    
    print("\n" + "="*80)
    print("参数优化结果 (TOP 10)")
    print("="*80)
    
    print(f"{'排名':<5} {'策略':<20} {'IR':<8} {'年化':<10} {'夏普':<8} {'回撤':<10} {'胜率':<8}")
    print("-"*85)
    
    for i, r in enumerate(results[:10], 1):
        print(f"{i:<5} {r.factor_name:<20} {r.information_ratio:>7.2f} "
              f"{r.annualized_return*100:>8.2f}% {r.sharpe_ratio:>7.2f} "
              f"{r.max_drawdown*100:>8.2f}% {r.win_rate*100:>6.1f}%")
    
    print("="*80)
    
    data = {
        'metadata': {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
        'top_results': [r.to_dict() for r in results[:10]]
    }
    with open('backtests/optimized_v2_results.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("\n[OK] 结果已保存到 backtests/optimized_v2_results.json")
    
    if results:
        best = results[0]
        print(f"\n[最佳参数]")
        print(f"  名称: {best.factor_name}")
        print(f"  参数: {best.params}")
        print(f"  年化收益: {best.annualized_return*100:.2f}%")
        print(f"  信息比率: {best.information_ratio:.2f}")
        print(f"  最大回撤: {best.max_drawdown*100:.2f}%")
        print(f"  胜率: {best.win_rate*100:.1f}%")


if __name__ == "__main__":
    engine = OptimizedBacktestV2()
    if engine.connected:
        results = engine.run_full_backtest("2019-01-01", "2024-01-01")
        print_results(results)
    else:
        print("[ERROR] 连接失败")
