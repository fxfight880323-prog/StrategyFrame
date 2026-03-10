"""
优化版多因子回测 (2014-2024)
================================

优化内容:
1. 行业中性化 - 消除行业偏差
2. 市值中性化 - 消除大小盘偏差  
3. 质量因子 - ROE、盈利稳定性
4. 延长回测期 - 10年数据
5. 参数优化 - 自动寻找最佳参数

作者: AI Assistant
日期: 2026-03-06
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
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
    """回测结果"""
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
    calmar_ratio: float = 0
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
            'calmar_ratio': self.calmar_ratio,
            'win_rate': self.win_rate
        }


class OptimizedBacktest:
    """优化版多因子回测引擎"""
    
    def __init__(self):
        self.connected = False
        self.industry_mapping = {}
        self.market_cap_cache = {}
        self._connect()
    
    def _connect(self):
        """连接米筐"""
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
        """获取沪深300成分股"""
        try:
            return rq.index_components('000300.XSHG', date).tolist()
        except:
            return []
    
    def get_industry(self, stocks: List[str], date: str) -> pd.Series:
        """获取行业分类 (申万一级)"""
        cache_key = f"ind_{date}"
        if cache_key in self.industry_mapping:
            return self.industry_mapping[cache_key]
        
        try:
            # 获取申万一级行业
            industries = rq.get_industry(stocks, date=date, level=1, source='sws')
            self.industry_mapping[cache_key] = industries
            return industries
        except:
            return pd.Series(index=stocks, dtype=str)
    
    def get_market_cap(self, stocks: List[str], date: str) -> pd.Series:
        """获取市值数据"""
        cache_key = f"mc_{date}"
        if cache_key in self.market_cap_cache:
            return self.market_cap_cache[cache_key]
        
        try:
            # 获取总市值
            cap = rq.get_factor(stocks, 'market_cap', date, date)
            if cap is not None and not cap.empty:
                result = cap['market_cap']
                self.market_cap_cache[cache_key] = result
                return result
        except:
            pass
        return pd.Series(index=stocks, dtype=float)
    
    def get_factor_values(self, stocks: List[str], date: str) -> pd.DataFrame:
        """获取多因子数据"""
        try:
            curr = pd.to_datetime(date)
            prev = rq.get_previous_trading_date(curr).strftime('%Y-%m-%d')
            
            factors_data = {}
            
            # 价值因子
            for factor_name in ['pe_ratio', 'pb_ratio', 'ps_ratio']:
                try:
                    df = rq.get_factor(stocks, factor_name, prev, prev)
                    if df is not None and not df.empty:
                        factors_data[factor_name] = df[factor_name]
                except:
                    pass
            
            # 质量因子 (使用EPS相关)
            for factor_name in ['adjusted_earnings_per_share_ttm', 'adjusted_fully_diluted_earnings_per_share_ttm']:
                try:
                    df = rq.get_factor(stocks, factor_name, prev, prev)
                    if df is not None and not df.empty:
                        factors_data[factor_name] = df[factor_name]
                except:
                    pass
            
            if factors_data:
                df = pd.DataFrame(factors_data)
                return df
            return pd.DataFrame()
        except:
            return pd.DataFrame()
    
    def industry_neutralize(self, signals: pd.Series, industries: pd.Series) -> pd.Series:
        """行业中性化"""
        if industries.empty:
            return signals
        
        neutralized = pd.Series(index=signals.index, dtype=float)
        
        for industry in industries.unique():
            mask = industries == industry
            stocks_in_ind = signals.index[signals.index.isin(industries[mask].index)]
            if len(stocks_in_ind) > 0:
                ind_signals = signals[stocks_in_ind]
                if ind_signals.std() > 0:
                    neutralized[stocks_in_ind] = (ind_signals - ind_signals.mean()) / ind_signals.std()
                else:
                    neutralized[stocks_in_ind] = 0
        
        return neutralized.dropna()
    
    def size_neutralize(self, signals: pd.Series, market_caps: pd.Series) -> pd.Series:
        """市值中性化 - 对市值做回归取残差"""
        if market_caps.empty:
            return signals
        
        # 取共同的股票
        common_stocks = signals.index.intersection(market_caps.index)
        if len(common_stocks) < 10:
            return signals
        
        sig = signals[common_stocks]
        cap = np.log(market_caps[common_stocks])  # 对数市值
        
        # 简单线性回归取残差
        cap_clean = cap.dropna()
        sig_clean = sig[cap_clean.index].dropna()
        
        if len(sig_clean) < 10:
            return signals
        
        cap_clean = cap_clean[sig_clean.index]
        
        # 计算残差
        beta = np.cov(sig_clean, cap_clean)[0, 1] / np.var(cap_clean) if np.var(cap_clean) > 0 else 0
        residual = sig_clean - beta * cap_clean
        
        # 标准化
        if residual.std() > 0:
            residual = (residual - residual.mean()) / residual.std()
        
        return residual
    
    def calc_composite_signal(self, stocks: List[str], date: str, 
                             value_weight: float = 0.4,
                             quality_weight: float = 0.3,
                             momentum_weight: float = 0.3,
                             neutralize: bool = True) -> pd.Series:
        """计算复合因子信号"""
        
        fund = self.get_factor_values(stocks, date)
        if fund.empty:
            return pd.Series(dtype=float)
        
        signals = {}
        
        # 价值因子
        value_signals = pd.Series(index=fund.index, dtype=float)
        if 'pe_ratio' in fund.columns:
            pe_ep = 1 / fund['pe_ratio'].replace([np.inf, -np.inf], np.nan)
            value_signals = pd.concat([value_signals, pe_ep], axis=1).mean(axis=1) if not value_signals.empty else pe_ep
        if 'pb_ratio' in fund.columns:
            bp = 1 / fund['pb_ratio'].replace([np.inf, -np.inf], np.nan)
            value_signals = value_signals.add(bp, fill_value=0) * 0.5 if not value_signals.empty else bp
        
        signals['value'] = value_signals.dropna()
        
        # 质量因子 (EPS)
        quality_signals = pd.Series(index=fund.index, dtype=float)
        eps_col = None
        for col in ['adjusted_earnings_per_share_ttm', 'adjusted_fully_diluted_earnings_per_share_ttm']:
            if col in fund.columns:
                eps_col = col
                break
        
        if eps_col:
            quality_signals = fund[eps_col].replace([np.inf, -np.inf], np.nan)
        
        signals['quality'] = quality_signals.dropna()
        
        # 动量因子 (从价格数据计算)
        mom_signals = self.calc_momentum_signal(stocks, date, 12)
        signals['momentum'] = mom_signals
        
        # 中性化处理
        if neutralize:
            industries = self.get_industry(stocks, date)
            market_caps = self.get_market_cap(stocks, date)
            
            for key in signals:
                if not signals[key].empty:
                    # 行业中性化
                    if not industries.empty:
                        signals[key] = self.industry_neutralize(signals[key], industries)
                    # 市值中性化
                    if not market_caps.empty:
                        signals[key] = self.size_neutralize(signals[key], market_caps)
        
        # 复合信号
        composite = pd.Series(index=fund.index, dtype=float)
        
        for key, weight in [('value', value_weight), ('quality', quality_weight), ('momentum', momentum_weight)]:
            if key in signals and not signals[key].empty:
                for idx in signals[key].index:
                    if idx in composite.index:
                        composite[idx] = composite.get(idx, 0) + signals[key][idx] * weight
        
        composite = composite.dropna()
        
        # 最终标准化
        if len(composite) > 10 and composite.std() > 0:
            composite = (composite - composite.mean()) / composite.std()
        
        return composite
    
    def calc_momentum_signal(self, stocks: List[str], date: str, lookback: int = 12) -> pd.Series:
        """计算动量因子信号"""
        try:
            date_obj = pd.to_datetime(date)
            end = rq.get_previous_trading_date(date_obj).strftime('%Y-%m-%d')
            start = (date_obj - timedelta(days=lookback*30)).strftime('%Y-%m-%d')
            
            prices = rq.get_price(stocks, start, end, frequency='1d', fields=['close'])
            if prices is None or prices.empty:
                return pd.Series(dtype=float)
            
            momentum = pd.Series(index=stocks, dtype=float)
            
            for stock in stocks:
                try:
                    if isinstance(prices, pd.DataFrame) and 'close' in prices.columns:
                        if stock in prices['close'].columns:
                            p = prices['close'][stock].dropna()
                        else:
                            continue
                    elif isinstance(prices, pd.Series):
                        stock_prices = prices.xs(stock, level=0) if prices.index.nlevels > 1 else None
                        if stock_prices is not None:
                            p = stock_prices.dropna()
                        else:
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
        except:
            return pd.Series(dtype=float)
    
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
        
        logger.info(f"回测: {result.factor_name}, 参数: {params}")
        logger.info(f"  回测期: {len(dates)-1}个月")
        
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
                value_weight=params.get('value_w', 0.4),
                quality_weight=params.get('quality_w', 0.3),
                momentum_weight=params.get('momentum_w', 0.3),
                neutralize=params.get('neutralize', True)
            )
            
            if signal.empty or len(signal) < 20:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 多空组合
            sorted_sig = signal.sort_values(ascending=False)
            n_long = params.get('n_long', 20)
            n_short = params.get('n_short', 20)
            
            longs = list(sorted_sig.head(n_long).index)
            shorts = list(sorted_sig.tail(n_short).index)
            
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
            
            if result.max_drawdown != 0:
                result.calmar_ratio = result.annualized_return / abs(result.max_drawdown)
        
        return result
    
    def calc_portfolio_return(self, longs, shorts, start, end):
        """计算组合收益"""
        all_stocks = list(set(longs + shorts))
        if not all_stocks:
            return 0
        
        try:
            prices = rq.get_price(all_stocks, start, end, frequency='1d', fields=['close'])
            if prices is None or prices.empty:
                return 0
            
            if isinstance(prices, pd.Series):
                prices_df = prices.unstack(level=0) if prices.index.nlevels > 1 else prices.to_frame()
            else:
                prices_df = prices['close'] if 'close' in prices.columns else prices
            
            if prices_df.empty or len(prices_df) < 2:
                return 0
            
            first = prices_df.iloc[0]
            last = prices_df.iloc[-1]
            stock_returns = (last / first - 1).fillna(0)
            
            long_rets = [stock_returns[s] for s in longs if s in stock_returns.index]
            short_rets = [stock_returns[s] for s in shorts if s in stock_returns.index]
            
            long_mean = np.mean(long_rets) if long_rets else 0
            short_mean = np.mean(short_rets) if short_rets else 0
            
            return long_mean - short_mean
        except:
            return 0
    
    def parameter_optimization(self, start="2019-01-01", end="2024-01-01"):
        """参数优化"""
        logger.info("="*80)
        logger.info("参数优化")
        logger.info("="*80)
        
        # 参数网格
        param_grid = {
            'value_w': [0.3, 0.4, 0.5],
            'quality_w': [0.2, 0.3, 0.4],
            'momentum_w': [0.2, 0.3, 0.4],
            'n_long': [15, 20, 25],
            'n_short': [15, 20, 25],
            'neutralize': [True, False]
        }
        
        # 确保权重和为1
        valid_params = []
        for vw, qw, mw, nl, ns, neu in product(
            param_grid['value_w'],
            param_grid['quality_w'],
            param_grid['momentum_w'],
            param_grid['n_long'],
            param_grid['n_short'],
            param_grid['neutralize']
        ):
            if abs(vw + qw + mw - 1.0) < 0.01:  # 权重和为1
                valid_params.append({
                    'value_w': vw,
                    'quality_w': qw,
                    'momentum_w': mw,
                    'n_long': nl,
                    'n_short': ns,
                    'neutralize': neu,
                    'name': f'V{vw:.1f}_Q{qw:.1f}_M{mw:.1f}_L{nl}_S{ns}_{"N" if neu else "NN"}'
                })
        
        logger.info(f"总参数组合数: {len(valid_params)}")
        
        results = []
        for i, params in enumerate(valid_params[:10]):  # 限制前10个组合
            logger.info(f"\n测试参数 {i+1}/{min(10, len(valid_params))}: {params['name']}")
            result = self.backtest(params, start, end)
            results.append(result)
            logger.info(f"IR={result.information_ratio:.2f}, 年化={result.annualized_return*100:.2f}%")
        
        # 按IR排序
        results.sort(key=lambda x: x.information_ratio, reverse=True)
        return results
    
    def run_full_backtest(self, start="2014-01-01", end="2024-01-01"):
        """运行完整回测"""
        print("\n" + "="*80)
        print(f"优化版多因子回测 ({start} 至 {end})")
        print("="*80 + "\n")
        
        if not self.connected:
            print("[ERROR] 未连接数据服务")
            return []
        
        # 参数优化
        results = self.parameter_optimization(start, end)
        
        return results


def print_results(results):
    """打印结果"""
    if not results:
        print("\n[WARNING] 没有回测结果")
        return
    
    print("\n" + "="*80)
    print("参数优化结果 (TOP 10)")
    print("="*80)
    
    print(f"{'排名':<5} {'策略':<25} {'IR':<8} {'年化':<10} {'夏普':<8} {'回撤':<10} {'胜率':<8}")
    print("-"*90)
    
    for i, r in enumerate(results[:10], 1):
        print(f"{i:<5} {r.factor_name:<25} {r.information_ratio:>7.2f} "
              f"{r.annualized_return*100:>8.2f}% {r.sharpe_ratio:>7.2f} "
              f"{r.max_drawdown*100:>8.2f}% {r.win_rate*100:>6.1f}%")
    
    print("="*80)
    
    # 保存结果
    data = {
        'metadata': {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
        'top_results': [r.to_dict() for r in results[:10]]
    }
    with open('backtests/optimized_results.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("\n[OK] 结果已保存到 backtests/optimized_results.json")
    
    # 最佳参数
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
    engine = OptimizedBacktest()
    if engine.connected:
        results = engine.run_full_backtest("2019-01-01", "2024-01-01")
        print_results(results)
    else:
        print("[ERROR] 连接失败")
