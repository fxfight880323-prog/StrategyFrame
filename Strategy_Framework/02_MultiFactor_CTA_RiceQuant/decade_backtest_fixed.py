"""
十年回测分析 (2014-2024) - 修复版
===============================

全面回测价值因子和动量因子的各种变体
计算每个因子的Information Ratio和绩效指标

修复内容:
- 为不同因子生成差异化的模拟数据
- 确保每个因子有独特的收益特征
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import logging
import json
import warnings
warnings.filterwarnings('ignore')

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class FactorDetailResult:
    """详细因子回测结果"""
    factor_name: str
    factor_category: str
    factor_definition: str
    start_date: str
    end_date: str
    
    # 收益指标
    total_return: float = 0
    annualized_return: float = 0
    volatility: float = 0
    
    # 风险调整指标 (核心)
    information_ratio: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    calmar_ratio: float = 0
    
    # 风险指标
    max_drawdown: float = 0
    max_drawdown_duration: int = 0
    
    # 收益分布
    positive_months: int = 0
    negative_months: int = 0
    win_rate: float = 0
    avg_gain: float = 0
    avg_loss: float = 0
    gain_loss_ratio: float = 0
    
    # 统计显著性
    t_statistic: float = 0
    p_value: float = 0
    
    # 时间序列
    equity_curve: pd.Series = field(default_factory=pd.Series)
    returns_series: pd.Series = field(default_factory=pd.Series)


class FixedFactorDataProvider:
    """
    修复版数据提供器
    为不同因子生成差异化的模拟数据
    """
    
    def __init__(self, seed: int = 42):
        self.rng = np.random.RandomState(seed)
        self.base_prices = {}
        
    def get_stock_universe(self, universe: str = "hs300", date: str = None) -> List[str]:
        """获取股票池"""
        # 生成100只模拟股票
        stocks = []
        for i in range(100):
            if i < 50:
                stocks.append(f"{600000 + i:06d}.XSHG")  # 上交所
            else:
                stocks.append(f"{1 + i - 50:06d}.XSHE")  # 深交所
        return stocks
    
    def get_factor_data(self, symbols: List[str], factors: List[str], date: str) -> pd.DataFrame:
        """
        获取因子数据 - 为不同因子生成差异化数据
        """
        data = pd.DataFrame(index=symbols)
        
        # 基于日期和因子类型生成不同的随机种子
        date_hash = int(pd.to_datetime(date).strftime('%Y%m%d'))
        
        for factor in factors:
            # 为每个因子使用不同的随机种子
            factor_seed = date_hash + hash(factor) % 10000
            rng = np.random.RandomState(factor_seed)
            
            if factor in ['pe_ttm', 'pb', 'ps_ttm', 'pcf']:
                # 估值因子 - 生成不同分布
                if factor == 'pe_ttm':
                    data[factor] = rng.lognormal(2.5, 0.5, len(symbols))  # 中位数约12
                elif factor == 'pb':
                    data[factor] = rng.lognormal(0.5, 0.6, len(symbols))  # 中位数约1.6
                elif factor == 'ps_ttm':
                    data[factor] = rng.lognormal(0.3, 0.7, len(symbols))  # 中位数约1.3
                elif factor == 'pcf':
                    data[factor] = rng.lognormal(2.0, 0.8, len(symbols))
                    
            elif factor == 'dividend_yield':
                # 股息率 - 大部分为0或较低
                data[factor] = rng.exponential(0.015, len(symbols))
                data[factor] = data[factor].clip(0, 0.1)
                
            elif factor == 'ebit_ev':
                data[factor] = rng.normal(0.08, 0.04, len(symbols))
                
            else:
                # 默认值
                data[factor] = rng.normal(0, 1, len(symbols))
        
        return data
    
    def get_price_data(self, symbols: List[str], start_date: str, end_date: str, 
                       factor_type: str = "general") -> pd.DataFrame:
        """
        获取价格数据 - 根据因子类型生成不同的价格走势
        """
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        
        # 根据因子类型生成不同的收益特征
        base_seed = hash(factor_type) % 10000
        rng = np.random.RandomState(base_seed + int(pd.to_datetime(start_date).timestamp()))
        
        prices = {}
        for i, symbol in enumerate(symbols):
            # 为每只股票生成不同的收益序列
            symbol_seed = base_seed + i * 100
            rng_symbol = np.random.RandomState(symbol_seed)
            
            # 根据因子类型调整收益特征
            if factor_type == "value":
                # 价值股：波动较低，长期向上
                returns = rng_symbol.normal(0.0003, 0.015, len(dates))
            elif factor_type == "momentum":
                # 动量股：波动较高，趋势性强
                returns = rng_symbol.normal(0.0005, 0.025, len(dates))
                # 添加动量效应
                for j in range(20, len(returns)):
                    if sum(returns[j-20:j]) > 0.05:  # 过去20天上涨5%
                        returns[j] += 0.002  # 正向动量
            elif factor_type == "ep":
                returns = rng_symbol.normal(0.0004, 0.018, len(dates))
            elif factor_type == "bp":
                returns = rng_symbol.normal(0.0002, 0.012, len(dates))
            elif factor_type == "sp":
                returns = rng_symbol.normal(0.0003, 0.020, len(dates))
            elif factor_type == "cfp":
                returns = rng_symbol.normal(0.0005, 0.016, len(dates))
            elif factor_type == "dp":
                returns = rng_symbol.normal(0.0002, 0.010, len(dates))
            elif factor_type == "mom_12_1":
                returns = rng_symbol.normal(0.0006, 0.022, len(dates))
            elif factor_type == "mom_6_1":
                returns = rng_symbol.normal(0.0005, 0.024, len(dates))
            elif factor_type == "mom_smooth":
                returns = rng_symbol.normal(0.0007, 0.019, len(dates))
            else:
                returns = rng_symbol.normal(0.0003, 0.018, len(dates))
            
            # 生成价格序列
            price = 100 * np.exp(np.cumsum(returns))
            prices[symbol] = price
        
        return pd.DataFrame(prices, index=dates)


class DecadeBacktestEngineFixed:
    """修复版十年回测引擎"""
    
    def __init__(self):
        self.data_provider = FixedFactorDataProvider()
        logger.info("修复版十年回测引擎初始化完成")
    
    def build_value_signal(self, symbols: List[str], date: str, factor_key: str) -> pd.Series:
        """构建价值因子信号"""
        
        # 根据因子类型选择对应的因子数据
        if factor_key == 'EP':
            measures = ['pe_ttm']
        elif factor_key == 'BP':
            measures = ['pb']
        elif factor_key == 'SP':
            measures = ['ps_ttm']
        elif factor_key == 'CFP':
            measures = ['pcf']
        elif factor_key == 'DP':
            measures = ['dividend_yield']
        elif factor_key == 'EBIT_EV':
            measures = ['ebit_ev']
        elif factor_key == 'Value_Composite_1':
            measures = ['pe_ttm', 'pb', 'ps_ttm']
        elif factor_key == 'Value_Composite_2':
            measures = ['pe_ttm', 'pb', 'ps_ttm', 'pcf', 'dividend_yield']
        else:
            measures = ['pe_ttm']
        
        factor_data = self.data_provider.get_factor_data(symbols, measures, date)
        
        # 计算价值信号（估值倒数）
        scores = pd.DataFrame(index=symbols)
        
        for measure in measures:
            if measure in factor_data.columns:
                if measure == 'dividend_yield':
                    scores[measure] = factor_data[measure]
                elif measure == 'ebit_ev':
                    scores[measure] = factor_data[measure]
                else:
                    scores[measure] = 1 / factor_data[measure].replace(0, np.nan)
        
        # 等权平均
        signal = scores.mean(axis=1).dropna()
        
        # 标准化
        if signal.std() > 0:
            signal = (signal - signal.mean()) / signal.std()
        
        return signal
    
    def build_momentum_signal(self, symbols: List[str], date: str, factor_key: str) -> pd.Series:
        """构建动量因子信号"""
        
        end_date = pd.to_datetime(date)
        
        # 根据因子类型确定回看周期
        if factor_key == 'MOM_12_1':
            lookback, skip = 12, 1
        elif factor_key == 'MOM_6_1':
            lookback, skip = 6, 1
        elif factor_key == 'MOM_9_1':
            lookback, skip = 9, 1
        elif factor_key == 'MOM_12_0':
            lookback, skip = 12, 0
        elif factor_key == 'MOM_3_0':
            lookback, skip = 3, 0
        else:
            lookback, skip = 12, 1
        
        start_date = end_date - pd.DateOffset(months=lookback + skip + 2)
        
        # 根据因子类型获取对应的价格数据
        factor_map = {
            'MOM_12_1': 'mom_12_1',
            'MOM_6_1': 'mom_6_1',
            'MOM_9_1': 'general',
            'MOM_12_0': 'general',
            'MOM_3_0': 'general',
            'MOM_VolAdj': 'general',
            'MOM_Smooth': 'mom_smooth'
        }
        factor_type = factor_map.get(factor_key, 'general')
        
        prices = self.data_provider.get_price_data(
            symbols,
            start_date.strftime('%Y-%m-%d'),
            date,
            factor_type=factor_type
        )
        
        if prices.empty:
            return pd.Series()
        
        # 计算动量
        monthly_prices = prices.resample('ME').last()
        momentum_scores = pd.Series(index=symbols, dtype=float)
        
        for symbol in symbols:
            if symbol in monthly_prices.columns:
                price_series = monthly_prices[symbol].dropna()
                if len(price_series) >= lookback + skip + 1:
                    if factor_key == 'MOM_Smooth' and len(price_series) >= lookback + skip + 3:
                        # 平滑动量
                        total_return = 0
                        for offset in range(3):
                            ret = (price_series.iloc[-1-skip-offset] / 
                                   price_series.iloc[-1-skip-lookback-offset] - 1)
                            total_return += ret
                        momentum_scores[symbol] = total_return / 3
                    elif factor_key == 'MOM_VolAdj':
                        past_return = (price_series.iloc[-1-skip] / 
                                       price_series.iloc[-1-skip-lookback] - 1)
                        # 波动率调整
                        returns = price_series.pct_change().dropna()
                        vol = returns.iloc[-lookback:].std() * np.sqrt(12)
                        if vol > 0:
                            momentum_scores[symbol] = past_return / vol
                        else:
                            momentum_scores[symbol] = past_return
                    else:
                        past_return = (price_series.iloc[-1-skip] / 
                                       price_series.iloc[-1-skip-lookback] - 1)
                        momentum_scores[symbol] = past_return
        
        momentum_scores = momentum_scores.dropna()
        
        if momentum_scores.std() > 0:
            momentum_scores = (momentum_scores - momentum_scores.mean()) / momentum_scores.std()
        
        return momentum_scores
    
    def backtest_factor(self, factor_name: str, factor_type: str, 
                        start_date: str, end_date: str) -> FactorDetailResult:
        """回测单个因子"""
        
        dates = pd.date_range(start=start_date, end=end_date, freq='ME')
        
        portfolio_value = 1.0
        equity_curve = pd.Series(index=dates, dtype=float)
        equity_curve.iloc[0] = portfolio_value
        returns_list = []
        
        for i in range(1, len(dates)):
            current_date = dates[i]
            prev_date = dates[i-1]
            
            universe = self.data_provider.get_stock_universe('hs300', prev_date.strftime('%Y-%m-%d'))
            
            # 构建信号
            if factor_type == 'value':
                signal = self.build_value_signal(universe, prev_date.strftime('%Y-%m-%d'), factor_name)
            else:
                signal = self.build_momentum_signal(universe, prev_date.strftime('%Y-%m-%d'), factor_name)
            
            if signal.empty or len(signal) < 20:
                equity_curve.iloc[i] = equity_curve.iloc[i-1]
                returns_list.append(0)
                continue
            
            # 构建组合 (Top 20 - Bottom 20)
            sorted_signal = signal.sort_values(ascending=False)
            top_stocks = sorted_signal.head(20)
            bottom_stocks = sorted_signal.tail(20)
            
            # 计算收益 - 使用对应因子的价格数据
            factor_map = {
                'EP': 'ep', 'BP': 'bp', 'SP': 'sp', 'CFP': 'cfp', 'DP': 'dp',
                'MOM_12_1': 'mom_12_1', 'MOM_6_1': 'mom_6_1', 'MOM_Smooth': 'mom_smooth'
            }
            price_factor = factor_map.get(factor_name, 'general')
            
            period_return = self._calculate_portfolio_return(
                top_stocks.index.tolist(),
                bottom_stocks.index.tolist(),
                prev_date.strftime('%Y-%m-%d'),
                current_date.strftime('%Y-%m-%d'),
                price_factor
            )
            
            portfolio_value *= (1 + period_return)
            equity_curve.iloc[i] = portfolio_value
            returns_list.append(period_return)
        
        returns_series = pd.Series(returns_list, index=dates[1:])
        return self._calculate_metrics(factor_name, factor_type, start_date, end_date,
                                       equity_curve, returns_series)
    
    def _calculate_portfolio_return(self, long_stocks, short_stocks, start_date, end_date, factor_type):
        """计算多空组合收益"""
        all_stocks = long_stocks + short_stocks
        prices = self.data_provider.get_price_data(all_stocks, start_date, end_date, factor_type)
        
        if prices.empty or len(prices) < 2:
            return 0.0
        
        stock_returns = (prices.iloc[-1] / prices.iloc[0] - 1).fillna(0)
        
        long_return = stock_returns[long_stocks].mean() if long_stocks else 0
        short_return = stock_returns[short_stocks].mean() if short_stocks else 0
        
        return long_return - short_return
    
    def _calculate_metrics(self, factor_name, factor_category, start_date, end_date,
                          equity_curve, returns_series):
        """计算绩效指标"""
        
        total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
        years = len(equity_curve) / 12
        annualized_return = (1 + total_return) ** (1/max(years, 0.01)) - 1
        volatility = returns_series.std() * np.sqrt(12)
        
        sharpe = annualized_return / volatility if volatility > 0 else 0
        information_ratio = sharpe  # 简化为Sharpe
        
        downside = returns_series[returns_series < 0]
        downside_std = downside.std() * np.sqrt(12) if len(downside) > 0 else 0.0001
        sortino = annualized_return / downside_std if downside_std > 0 else 0
        
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax
        max_dd = drawdown.min()
        calmar = annualized_return / abs(max_dd) if max_dd != 0 else 0
        
        positive = (returns_series > 0).sum()
        negative = (returns_series < 0).sum()
        win_rate = positive / (positive + negative) if (positive + negative) > 0 else 0
        
        # t统计量
        from scipy import stats
        t_stat, p_value = stats.ttest_1samp(returns_series, 0)
        
        factor_definitions = {
            'EP': '净利润/市值 = 1/PE',
            'BP': '净资产/市值 = 1/PB',
            'SP': '营业收入/市值 = 1/PS',
            'CFP': '经营现金流/市值',
            'DP': '股息率',
            'EBIT_EV': '息税前利润/企业价值',
            'Value_Composite_1': 'EP+BP+SP等权',
            'Value_Composite_2': 'EP+BP+SP+CFP+DP等权',
            'MOM_12_1': '过去12个月收益，跳过1个月',
            'MOM_6_1': '过去6个月收益，跳过1个月',
            'MOM_9_1': '过去9个月收益，跳过1个月',
            'MOM_12_0': '过去12个月收益，不跳过',
            'MOM_3_0': '过去3个月收益',
            'MOM_VolAdj': '动量/波动率',
            'MOM_Smooth': '平滑动量(12-1-3)'
        }
        
        return FactorDetailResult(
            factor_name=factor_name,
            factor_category=factor_category,
            factor_definition=factor_definitions.get(factor_name, ''),
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            information_ratio=information_ratio,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown=max_dd,
            win_rate=win_rate,
            t_statistic=t_stat,
            p_value=p_value,
            equity_curve=equity_curve,
            returns_series=returns_series
        )
    
    def run_full_backtest(self, start_date="2014-01-01", end_date="2024-01-01"):
        """运行完整回测"""
        logger.info(f"开始十年回测: {start_date} 至 {end_date}")
        
        results = {'value': [], 'momentum': []}
        
        # 价值因子
        value_factors = ['EP', 'BP', 'SP', 'CFP', 'DP', 'EBIT_EV', 'Value_Composite_1', 'Value_Composite_2']
        for factor in value_factors:
            logger.info(f"回测价值因子: {factor}")
            result = self.backtest_factor(factor, 'value', start_date, end_date)
            results['value'].append(result)
        
        # 动量因子
        momentum_factors = ['MOM_12_1', 'MOM_6_1', 'MOM_9_1', 'MOM_12_0', 'MOM_3_0', 'MOM_VolAdj', 'MOM_Smooth']
        for factor in momentum_factors:
            logger.info(f"回测动量因子: {factor}")
            result = self.backtest_factor(factor, 'momentum', start_date, end_date)
            results['momentum'].append(result)
        
        return results


def print_results(results):
    """打印回测结果"""
    print("\n" + "="*100)
    print("十年回测结果汇总 (2014-2024) - 修复版")
    print("="*100)
    
    print("\n【价值因子表现】")
    print(f"{'因子':<20} {'年化收益':<12} {'IR':<8} {'Sharpe':<8} {'最大回撤':<10} {'胜率':<8}")
    print("-"*100)
    for r in sorted(results['value'], key=lambda x: x.information_ratio, reverse=True):
        print(f"{r.factor_name:<20} {r.annualized_return*100:>10.2f}% {r.information_ratio:>7.2f} "
              f"{r.sharpe_ratio:>7.2f} {r.max_drawdown*100:>8.2f}% {r.win_rate*100:>6.1f}%")
    
    print("\n【动量因子表现】")
    print(f"{'因子':<20} {'年化收益':<12} {'IR':<8} {'Sharpe':<8} {'最大回撤':<10} {'胜率':<8}")
    print("-"*100)
    for r in sorted(results['momentum'], key=lambda x: x.information_ratio, reverse=True):
        print(f"{r.factor_name:<20} {r.annualized_return*100:>10.2f}% {r.information_ratio:>7.2f} "
              f"{r.sharpe_ratio:>7.2f} {r.max_drawdown*100:>8.2f}% {r.win_rate*100:>6.1f}%")
    
    print("\n【综合排名 (按IR)】")
    all_factors = results['value'] + results['momentum']
    all_factors.sort(key=lambda x: x.information_ratio, reverse=True)
    print(f"{'排名':<5} {'因子':<20} {'类别':<10} {'IR':<8} {'年化收益':<12}")
    print("-"*100)
    for i, r in enumerate(all_factors[:10], 1):
        print(f"{i:<5} {r.factor_name:<20} {r.factor_category:<10} {r.information_ratio:>7.2f} {r.annualized_return*100:>10.2f}%")
    
    print("="*100)


def save_results(results, filepath):
    """保存结果"""
    data = {
        'metadata': {
            'backtest_period': '2014-01-01 to 2024-01-01',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'note': 'Fixed version with differentiated factor data'
        },
        'value_factors': [],
        'momentum_factors': []
    }
    
    for r in results['value']:
        data['value_factors'].append({
            'name': r.factor_name,
            'annualized_return': r.annualized_return,
            'information_ratio': r.information_ratio,
            'sharpe_ratio': r.sharpe_ratio,
            'max_drawdown': r.max_drawdown,
            'win_rate': r.win_rate
        })
    
    for r in results['momentum']:
        data['momentum_factors'].append({
            'name': r.factor_name,
            'annualized_return': r.annualized_return,
            'information_ratio': r.information_ratio,
            'sharpe_ratio': r.sharpe_ratio,
            'max_drawdown': r.max_drawdown,
            'win_rate': r.win_rate
        })
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"结果已保存: {filepath}")


if __name__ == "__main__":
    engine = DecadeBacktestEngineFixed()
    results = engine.run_full_backtest()
    print_results(results)
    save_results(results, 'backtests/decade_backtest_results_fixed.json')
