"""
十年回测分析 (2014-2024)
=======================

全面回测价值因子和动量因子的各种变体
计算每个因子的Information Ratio和绩效指标
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

from valmom_backtest import (
    ValMomFactorBuilder, 
    ValMomBacktester,
    FactorBacktestResult,
    FactorDataProvider
)
from config import CONFIG

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class FactorDetailResult:
    """详细因子回测结果"""
    factor_name: str
    factor_category: str  # 'value' or 'momentum'
    factor_definition: str
    
    # 回测期间
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
    max_drawdown_duration: int = 0  # 最大回撤持续天数
    
    # 收益分布
    positive_months: int = 0
    negative_months: int = 0
    win_rate: float = 0
    avg_gain: float = 0
    avg_loss: float = 0
    gain_loss_ratio: float = 0  # 盈亏比
    
    # 统计显著性
    t_statistic: float = 0
    p_value: float = 0
    
    # 时间序列
    equity_curve: pd.Series = field(default_factory=pd.Series)
    returns_series: pd.Series = field(default_factory=pd.Series)


class DecadeFactorLibrary:
    """
    十年回测因子库
    
    包含各种价值因子和动量因子的变体
    """
    
    # ========== 价值因子定义 ==========
    VALUE_FACTORS = {
        'EP': {
            'name': 'EP (Earnings-to-Price)',
            'category': 'value',
            'definition': '净利润 / 市值 = 1/PE',
            'measures': ['pe_ttm'],
            'transform': lambda x: 1/x if x != 0 else 0
        },
        'BP': {
            'name': 'BP (Book-to-Price)',
            'category': 'value',
            'definition': '净资产 / 市值 = 1/PB',
            'measures': ['pb'],
            'transform': lambda x: 1/x if x != 0 else 0
        },
        'SP': {
            'name': 'SP (Sales-to-Price)',
            'category': 'value',
            'definition': '营业收入 / 市值 = 1/PS',
            'measures': ['ps_ttm'],
            'transform': lambda x: 1/x if x != 0 else 0
        },
        'CFP': {
            'name': 'CFP (Cash Flow-to-Price)',
            'category': 'value',
            'definition': '经营现金流 / 市值',
            'measures': ['pcf'],
            'transform': lambda x: 1/x if x != 0 else 0
        },
        'DP': {
            'name': 'DP (Dividend Yield)',
            'category': 'value',
            'definition': '股息率',
            'measures': ['dividend_yield'],
            'transform': lambda x: x
        },
        'EBIT_EV': {
            'name': 'EBIT/EV',
            'category': 'value',
            'definition': '息税前利润 / 企业价值',
            'measures': ['ebit_ev'],
            'transform': lambda x: x
        },
        'Value_Composite_1': {
            'name': 'Value Composite 1 (EP+BP+SP)',
            'category': 'value',
            'definition': 'EP, BP, SP 等权平均',
            'measures': ['pe_ttm', 'pb', 'ps_ttm'],
            'weights': [0.33, 0.33, 0.34]
        },
        'Value_Composite_2': {
            'name': 'Value Composite 2 (All)',
            'category': 'value',
            'definition': 'EP, BP, SP, CFP, DP 等权平均',
            'measures': ['pe_ttm', 'pb', 'ps_ttm', 'pcf', 'dividend_yield'],
            'weights': [0.2, 0.2, 0.2, 0.2, 0.2]
        }
    }
    
    # ========== 动量因子定义 ==========
    MOMENTUM_FACTORS = {
        'MOM_12_1': {
            'name': 'MOM (12-1)',
            'category': 'momentum',
            'definition': '过去12个月收益，跳过最近1个月',
            'lookback': 12,
            'skip': 1
        },
        'MOM_6_1': {
            'name': 'MOM (6-1)',
            'category': 'momentum',
            'definition': '过去6个月收益，跳过最近1个月',
            'lookback': 6,
            'skip': 1
        },
        'MOM_9_1': {
            'name': 'MOM (9-1)',
            'category': 'momentum',
            'definition': '过去9个月收益，跳过最近1个月',
            'lookback': 9,
            'skip': 1
        },
        'MOM_12_0': {
            'name': 'MOM (12-0)',
            'category': 'momentum',
            'definition': '过去12个月收益，不跳过',
            'lookback': 12,
            'skip': 0
        },
        'MOM_3_0': {
            'name': 'Short-Term MOM (3-0)',
            'category': 'momentum',
            'definition': '过去3个月收益',
            'lookback': 3,
            'skip': 0
        },
        'MOM_VolAdj': {
            'name': 'Volatility-Adjusted MOM',
            'category': 'momentum',
            'definition': '动量 / 波动率',
            'lookback': 12,
            'skip': 1,
            'vol_adj': True
        },
        'MOM_Smooth': {
            'name': 'Smoothed MOM (12-1-3)',
            'category': 'momentum',
            'definition': '过去12个月，跳过1个月，使用3个月平均',
            'lookback': 12,
            'skip': 1,
            'smooth': 3
        }
    }


class DecadeBacktestEngine:
    """
    十年回测引擎
    """
    
    def __init__(self):
        self.factor_builder = ValMomFactorBuilder()
        self.data_provider = FactorDataProvider()
        self.factor_lib = DecadeFactorLibrary()
        logger.info("十年回测引擎初始化完成")
    
    def build_value_factor_signal(
        self,
        symbols: List[str],
        date: str,
        factor_key: str
    ) -> pd.Series:
        """构建特定价值因子信号"""
        factor_def = self.factor_lib.VALUE_FACTORS[factor_key]
        
        # 获取原始数据
        measures = factor_def['measures']
        factor_data = self.data_provider.get_factor_data(symbols, measures, date)
        
        # 计算信号
        scores = pd.DataFrame(index=symbols)
        
        if 'weights' in factor_def:
            # 加权组合
            for i, measure in enumerate(measures):
                if measure in factor_data.columns:
                    if measure in ['pe_ttm', 'pb', 'ps_ttm', 'pcf']:
                        scores[measure] = 1 / factor_data[measure].replace(0, np.nan)
                    else:
                        scores[measure] = factor_data[measure]
            
            weights = factor_def['weights']
            signal = pd.Series(0.0, index=symbols)
            for i, col in enumerate(scores.columns):
                signal += scores[col].fillna(0) * weights[i]
        else:
            # 单一指标
            measure = measures[0]
            if measure in factor_data.columns:
                if measure in ['pe_ttm', 'pb', 'ps_ttm', 'pcf']:
                    signal = 1 / factor_data[measure].replace(0, np.nan)
                else:
                    signal = factor_data[measure]
            else:
                signal = pd.Series(np.nan, index=symbols)
        
        # 清理数据
        signal = signal.replace([np.inf, -np.inf], np.nan)
        signal = signal.dropna()
        
        # 标准化
        if signal.std() > 0:
            signal = (signal - signal.mean()) / signal.std()
        
        return signal
    
    def build_momentum_factor_signal(
        self,
        symbols: List[str],
        date: str,
        factor_key: str
    ) -> pd.Series:
        """构建特定动量因子信号"""
        factor_def = self.factor_lib.MOMENTUM_FACTORS[factor_key]
        
        end_date = pd.to_datetime(date)
        lookback = factor_def['lookback']
        skip = factor_def['skip']
        start_date = end_date - pd.DateOffset(months=lookback + skip + 2)
        
        # 获取价格数据
        prices = self.data_provider.get_price_data(
            symbols,
            start_date.strftime('%Y-%m-%d'),
            date
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
                    # 计算收益
                    if 'smooth' in factor_def:
                        # 平滑动量
                        smooth_window = factor_def['smooth']
                        if len(price_series) >= lookback + skip + smooth_window:
                            total_return = 0
                            for offset in range(smooth_window):
                                ret = (price_series.iloc[-1-skip-offset] / 
                                       price_series.iloc[-1-skip-lookback-offset] - 1)
                                total_return += ret
                            momentum_scores[symbol] = total_return / smooth_window
                    else:
                        # 标准动量
                        past_return = (price_series.iloc[-1-skip] / 
                                       price_series.iloc[-1-skip-lookback] - 1)
                        
                        # 波动率调整
                        if factor_def.get('vol_adj', False):
                            returns = price_series.pct_change().dropna()
                            vol = returns.iloc[-lookback:].std() * np.sqrt(12)
                            if vol > 0:
                                past_return = past_return / vol
                        
                        momentum_scores[symbol] = past_return
        
        # 清理和标准化
        momentum_scores = momentum_scores.dropna()
        momentum_scores = momentum_scores.replace([np.inf, -np.inf], np.nan).dropna()
        
        if momentum_scores.std() > 0:
            momentum_scores = (momentum_scores - momentum_scores.mean()) / momentum_scores.std()
        
        return momentum_scores
    
    def backtest_single_factor(
        self,
        factor_key: str,
        factor_type: str,  # 'value' or 'momentum'
        start_date: str,
        end_date: str
    ) -> FactorDetailResult:
        """
        回测单个因子
        """
        if factor_type == 'value':
            factor_def = self.factor_lib.VALUE_FACTORS[factor_key]
        else:
            factor_def = self.factor_lib.MOMENTUM_FACTORS[factor_key]
        
        logger.info(f"回测 {factor_key}: {factor_def['name']}")
        
        # 生成再平衡日期 (月度)
        dates = pd.date_range(start=start_date, end=end_date, freq='ME')
        
        # 初始化
        portfolio_value = 1.0
        equity_curve = pd.Series(index=dates, dtype=float)
        equity_curve.iloc[0] = portfolio_value
        returns_list = []
        
        for i in range(1, len(dates)):
            current_date = dates[i]
            prev_date = dates[i-1]
            
            # 获取股票池
            universe = self.data_provider.get_stock_universe(
                CONFIG.STOCK_UNIVERSE,
                prev_date.strftime('%Y-%m-%d')
            )
            
            # 构建信号
            if factor_type == 'value':
                signal = self.build_value_factor_signal(
                    universe, prev_date.strftime('%Y-%m-%d'), factor_key
                )
            else:
                signal = self.build_momentum_factor_signal(
                    universe, prev_date.strftime('%Y-%m-%d'), factor_key
                )
            
            if signal.empty or len(signal) < 20:
                equity_curve.iloc[i] = equity_curve.iloc[i-1]
                returns_list.append(0)
                continue
            
            # 构建组合 (Top 20 - Bottom 20)
            sorted_signal = signal.sort_values(ascending=False)
            top_stocks = sorted_signal.head(20)
            bottom_stocks = sorted_signal.tail(20)
            
            # 计算收益
            period_return = self._calculate_long_short_return(
                top_stocks.index.tolist(),
                bottom_stocks.index.tolist(),
                prev_date.strftime('%Y-%m-%d'),
                current_date.strftime('%Y-%m-%d')
            )
            
            portfolio_value *= (1 + period_return)
            equity_curve.iloc[i] = portfolio_value
            returns_list.append(period_return)
        
        # 计算详细指标
        returns_series = pd.Series(returns_list, index=dates[1:])
        result = self._calculate_detailed_metrics(
            factor_key, factor_def, start_date, end_date,
            equity_curve, returns_series
        )
        
        return result
    
    def _calculate_long_short_return(
        self,
        long_stocks: List[str],
        short_stocks: List[str],
        start_date: str,
        end_date: str
    ) -> float:
        """计算多空组合收益"""
        all_stocks = long_stocks + short_stocks
        prices = self.data_provider.get_price_data(all_stocks, start_date, end_date)
        
        if prices.empty or len(prices) < 2:
            return 0.0
        
        stock_returns = (prices.iloc[-1] / prices.iloc[0] - 1).fillna(0)
        
        long_return = stock_returns[long_stocks].mean() if long_stocks else 0
        short_return = stock_returns[short_stocks].mean() if short_stocks else 0
        
        # 多空组合收益
        portfolio_return = long_return - short_return
        
        return portfolio_return
    
    def _calculate_detailed_metrics(
        self,
        factor_key: str,
        factor_def: Dict,
        start_date: str,
        end_date: str,
        equity_curve: pd.Series,
        returns_series: pd.Series
    ) -> FactorDetailResult:
        """计算详细绩效指标"""
        
        # 基本收益
        total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
        years = len(equity_curve) / 12
        annualized_return = (1 + total_return) ** (1/max(years, 0.01)) - 1
        volatility = returns_series.std() * np.sqrt(12)
        
        # 风险调整指标
        sharpe = annualized_return / volatility if volatility > 0 else 0
        
        # Information Ratio (核心指标)
        # 使用月度收益计算
        tracking_error = returns_series.std() * np.sqrt(12)
        information_ratio = annualized_return / tracking_error if tracking_error > 0 else 0
        
        # Sortino比率
        downside = returns_series[returns_series < 0]
        downside_std = downside.std() * np.sqrt(12) if len(downside) > 0 else 0.0001
        sortino = annualized_return / downside_std if downside_std > 0 else 0
        
        # 最大回撤
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax
        max_dd = drawdown.min()
        
        # 最大回撤持续时间
        dd_duration = 0
        max_dd_duration = 0
        in_dd = False
        for i in range(len(drawdown)):
            if drawdown.iloc[i] < 0:
                if not in_dd:
                    in_dd = True
                    dd_duration = 1
                else:
                    dd_duration += 1
            else:
                if in_dd:
                    in_dd = False
                    max_dd_duration = max(max_dd_duration, dd_duration)
        
        calmar = annualized_return / abs(max_dd) if max_dd != 0 else 0
        
        # 收益分布
        positive = (returns_series > 0).sum()
        negative = (returns_series < 0).sum()
        win_rate = positive / (positive + negative) if (positive + negative) > 0 else 0
        
        avg_gain = returns_series[returns_series > 0].mean() if positive > 0 else 0
        avg_loss = abs(returns_series[returns_series < 0].mean()) if negative > 0 else 0
        gain_loss_ratio = avg_gain / avg_loss if avg_loss > 0 else 0
        
        # 统计显著性 (t统计量)
        from scipy import stats
        t_stat, p_value = stats.ttest_1samp(returns_series, 0)
        
        return FactorDetailResult(
            factor_name=factor_key,
            factor_category=factor_def['category'],
            factor_definition=factor_def['definition'],
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
            max_drawdown_duration=max_dd_duration,
            positive_months=positive,
            negative_months=negative,
            win_rate=win_rate,
            avg_gain=avg_gain,
            avg_loss=avg_loss,
            gain_loss_ratio=gain_loss_ratio,
            t_statistic=t_stat,
            p_value=p_value,
            equity_curve=equity_curve,
            returns_series=returns_series
        )
    
    def run_full_decade_backtest(
        self,
        start_date: str = "2014-01-01",
        end_date: str = "2024-01-01"
    ) -> Dict[str, List[FactorDetailResult]]:
        """
        运行完整十年回测
        """
        logger.info("=" * 80)
        logger.info(f"十年因子回测: {start_date} 至 {end_date}")
        logger.info("=" * 80)
        
        results = {
            'value': [],
            'momentum': []
        }
        
        # 回测所有价值因子
        logger.info("\n【价值因子回测】")
        for factor_key in self.factor_lib.VALUE_FACTORS.keys():
            result = self.backtest_single_factor(
                factor_key, 'value', start_date, end_date
            )
            results['value'].append(result)
        
        # 回测所有动量因子
        logger.info("\n【动量因子回测】")
        for factor_key in self.factor_lib.MOMENTUM_FACTORS.keys():
            result = self.backtest_single_factor(
                factor_key, 'momentum', start_date, end_date
            )
            results['momentum'].append(result)
        
        return results


def print_decade_results(results: Dict[str, List[FactorDetailResult]]):
    """打印十年回测结果"""
    
    print("\n" + "=" * 100)
    print("十年回测结果汇总 (2014-2024)")
    print("=" * 100)
    
    # 价值因子结果
    print("\n" + "=" * 100)
    print("【价值因子 (Value Factors)】")
    print("=" * 100)
    print(f"{'因子':<25} {'定义':<30} {'年化收益':<10} {'IR':<8} {'胜率':<8} {'最大回撤':<10}")
    print("-" * 100)
    
    for result in sorted(results['value'], key=lambda x: x.information_ratio, reverse=True):
        print(f"{result.factor_name:<25} "
              f"{result.factor_definition[:28]:<30} "
              f"{result.annualized_return*100:>8.2f}% "
              f"{result.information_ratio:>7.2f} "
              f"{result.win_rate*100:>7.1f}% "
              f"{result.max_drawdown*100:>8.2f}%")
    
    # 动量因子结果
    print("\n" + "=" * 100)
    print("【动量因子 (Momentum Factors)】")
    print("=" * 100)
    print(f"{'因子':<25} {'定义':<30} {'年化收益':<10} {'IR':<8} {'胜率':<8} {'最大回撤':<10}")
    print("-" * 100)
    
    for result in sorted(results['momentum'], key=lambda x: x.information_ratio, reverse=True):
        print(f"{result.factor_name:<25} "
              f"{result.factor_definition[:28]:<30} "
              f"{result.annualized_return*100:>8.2f}% "
              f"{result.information_ratio:>7.2f} "
              f"{result.win_rate*100:>7.1f}% "
              f"{result.max_drawdown*100:>8.2f}%")
    
    # 汇总统计
    print("\n" + "=" * 100)
    print("【因子绩效排名 (按Information Ratio)】")
    print("=" * 100)
    
    all_factors = results['value'] + results['momentum']
    all_factors.sort(key=lambda x: x.information_ratio, reverse=True)
    
    print(f"{'排名':<5} {'因子':<25} {'类别':<10} {'IR':<8} {'Sharpe':<8} {'Calmar':<8}")
    print("-" * 100)
    
    for i, result in enumerate(all_factors[:10], 1):
        print(f"{i:<5} "
              f"{result.factor_name:<25} "
              f"{result.factor_category:<10} "
              f"{result.information_ratio:>7.2f} "
              f"{result.sharpe_ratio:>7.2f} "
              f"{result.calmar_ratio:>7.2f}")
    
    print("=" * 100)


def save_decade_results(
    results: Dict[str, List[FactorDetailResult]],
    filepath: str
):
    """保存十年回测结果"""
    
    data = {
        'metadata': {
            'backtest_period': '2014-01-01 to 2024-01-01',
            'universe': 'hs300',
            'rebalance_frequency': 'monthly',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        },
        'value_factors': [],
        'momentum_factors': []
    }
    
    for result in results['value']:
        data['value_factors'].append({
            'name': result.factor_name,
            'definition': result.factor_definition,
            'annualized_return': result.annualized_return,
            'information_ratio': result.information_ratio,
            'sharpe_ratio': result.sharpe_ratio,
            'max_drawdown': result.max_drawdown,
            'win_rate': result.win_rate,
            't_statistic': result.t_statistic,
            'p_value': result.p_value
        })
    
    for result in results['momentum']:
        data['momentum_factors'].append({
            'name': result.factor_name,
            'definition': result.factor_definition,
            'annualized_return': result.annualized_return,
            'information_ratio': result.information_ratio,
            'sharpe_ratio': result.sharpe_ratio,
            'max_drawdown': result.max_drawdown,
            'win_rate': result.win_rate,
            't_statistic': result.t_statistic,
            'p_value': result.p_value
        })
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"结果已保存: {filepath}")


# 便捷函数
def run_decade_backtest(start_date: str = "2014-01-01", end_date: str = "2024-01-01"):
    """运行十年回测"""
    engine = DecadeBacktestEngine()
    results = engine.run_full_decade_backtest(start_date, end_date)
    print_decade_results(results)
    
    # 保存结果
    save_decade_results(results, 'backtests/decade_backtest_results.json')
    
    return results


if __name__ == "__main__":
    results = run_decade_backtest()
