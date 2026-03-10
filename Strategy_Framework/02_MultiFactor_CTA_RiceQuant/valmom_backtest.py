"""
ValMomEverywhere 回测实现
==========================

基于 Asness, Moskowitz & Pedersen (2013) 的经典论文:
"Value and Momentum Everywhere"

回测内容:
1. 价值因子 (Value) 回测 - 基于估值指标排序
2. 动量因子 (Momentum) 回测 - 基于过去收益排序
3. 价值+动量组合 (COMBO) 回测
4. Information Ratio 计算

信号构建:
- Value: 基于 PE/PB/PS 等估值指标的倒数排序
- Momentum: 基于过去 12个月收益 (排除最近1个月)
- COMBO: 50% Value + 50% Momentum (等权组合)

参考:
- Asness, C.S., Moskowitz, T.J., & Pedersen, L.H. (2013). 
  Value and Momentum Everywhere. Journal of Finance, 68(3), 929-985.
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import json
import matplotlib.pyplot as plt

from config import StrategyConfig, CONFIG
from factor_model import FactorDataProvider


# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class FactorBacktestResult:
    """因子回测结果"""
    factor_name: str
    start_date: str
    end_date: str
    
    # 收益指标
    total_return: float = 0
    annualized_return: float = 0
    volatility: float = 0
    
    # 风险调整指标
    sharpe_ratio: float = 0
    information_ratio: float = 0  # 核心指标
    sortino_ratio: float = 0
    
    # 风险指标
    max_drawdown: float = 0
    calmar_ratio: float = 0
    
    # 组合统计
    num_stocks_held: int = 0
    turnover: float = 0
    
    # 时间序列
    equity_curve: pd.Series = field(default_factory=pd.Series)
    returns_series: pd.Series = field(default_factory=pd.Series)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'factor_name': self.factor_name,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'total_return': self.total_return,
            'annualized_return': self.annualized_return,
            'volatility': self.volatility,
            'sharpe_ratio': self.sharpe_ratio,
            'information_ratio': self.information_ratio,
            'sortino_ratio': self.sortino_ratio,
            'max_drawdown': self.max_drawdown,
            'calmar_ratio': self.calmar_ratio,
            'num_stocks_held': self.num_stocks_held,
            'turnover': self.turnover,
        }


class ValMomFactorBuilder:
    """
    价值动量因子构建器
    
    按照论文方法构建信号加权组合
    """
    
    def __init__(self, data_provider: FactorDataProvider = None):
        self.data_provider = data_provider or FactorDataProvider()
        self.logger = logging.getLogger(__name__)
    
    def build_value_signal(
        self,
        symbols: List[str],
        date: str,
        value_measures: List[str] = None
    ) -> pd.Series:
        """
        构建价值信号
        
        使用多个估值指标的综合排名:
        - EP (Earnings/Price) = 1/PE
        - BP (Book/Price) = 1/PB
        - SP (Sales/Price) = 1/PS
        
        论文方法: 使用估值指标的倒数，排名越高越"价值"
        """
        if value_measures is None:
            value_measures = ['pe_ttm', 'pb', 'ps_ttm']
        
        # 获取因子数据
        factor_data = self.data_provider.get_factor_data(symbols, value_measures, date)
        
        # 计算估值倒数 (越便宜数值越高)
        value_scores = pd.DataFrame(index=symbols)
        
        if 'pe_ttm' in factor_data.columns:
            value_scores['ep'] = 1 / factor_data['pe_ttm'].replace(0, np.nan)
        if 'pb' in factor_data.columns:
            value_scores['bp'] = 1 / factor_data['pb'].replace(0, np.nan)
        if 'ps_ttm' in factor_data.columns:
            value_scores['sp'] = 1 / factor_data['ps_ttm'].replace(0, np.nan)
        
        # 去极值
        value_scores = value_scores.apply(lambda x: self._winsorize(x), axis=0)
        
        # 标准化
        value_scores = value_scores.apply(lambda x: (x - x.mean()) / x.std() if x.std() > 0 else 0, axis=0)
        
        # 综合价值信号 (等权平均)
        value_signal = value_scores.mean(axis=1).dropna()
        
        return value_signal
    
    def build_momentum_signal(
        self,
        symbols: List[str],
        date: str,
        lookback_months: int = 12,
        skip_months: int = 1
    ) -> pd.Series:
        """
        构建动量信号
        
        论文方法:
        - 使用过去 12个月收益 (排除最近1个月)
        - 即 t-12 到 t-1 月的累计收益
        - 这是经典的 "12-1" 动量
        
        为什么要跳过最近1个月?
        - 短期反转效应 (short-term reversal)
        - 避免微观结构噪音
        """
        end_date = pd.to_datetime(date)
        start_date = end_date - pd.DateOffset(months=lookback_months + skip_months + 1)
        
        # 获取价格数据
        prices = self.data_provider.get_price_data(
            symbols,
            start_date.strftime('%Y-%m-%d'),
            date
        )
        
        if prices.empty:
            return pd.Series()
        
        # 计算过去收益 (排除最近1个月)
        # 使用月度数据近似
        monthly_prices = prices.resample('ME').last()
        
        momentum_scores = pd.Series(index=symbols, dtype=float)
        
        for symbol in symbols:
            if symbol in monthly_prices.columns:
                price_series = monthly_prices[symbol].dropna()
                if len(price_series) >= lookback_months + skip_months + 1:
                    # t-12 到 t-1 的收益
                    past_return = (price_series.iloc[-1-skip_months] / 
                                   price_series.iloc[-1-skip_months-lookback_months] - 1)
                    momentum_scores[symbol] = past_return
        
        # 去极值和标准化
        momentum_scores = self._winsorize(momentum_scores)
        momentum_scores = (momentum_scores - momentum_scores.mean()) / momentum_scores.std() if momentum_scores.std() > 0 else momentum_scores
        
        return momentum_scores.dropna()
    
    def build_combo_signal(
        self,
        value_signal: pd.Series,
        momentum_signal: pd.Series
    ) -> pd.Series:
        """
        构建价值+动量组合信号
        
        论文方法: 50% Value + 50% Momentum (等权)
        
        注意: Value 和 Momentum 是负相关的，组合可以平滑收益
        """
        # 对齐索引
        common_index = value_signal.index.intersection(momentum_signal.index)
        
        value_aligned = value_signal.loc[common_index]
        momentum_aligned = momentum_signal.loc[common_index]
        
        # 再次标准化 (确保两者可比)
        value_aligned = (value_aligned - value_aligned.mean()) / value_aligned.std() if value_aligned.std() > 0 else value_aligned
        momentum_aligned = (momentum_aligned - momentum_aligned.mean()) / momentum_aligned.std() if momentum_aligned.std() > 0 else momentum_aligned
        
        # 50/50 组合
        combo_signal = 0.5 * value_aligned + 0.5 * momentum_aligned
        
        return combo_signal
    
    def _winsorize(self, series: pd.Series, limits: Tuple[float, float] = (0.01, 0.01)) -> pd.Series:
        """去极值 (Winsorize)"""
        lower = series.quantile(limits[0])
        upper = series.quantile(1 - limits[1])
        return series.clip(lower, upper)


class ValMomBacktester:
    """
    ValMomEverywhere 回测引擎
    """
    
    def __init__(
        self,
        config: StrategyConfig = None,
        factor_builder: ValMomFactorBuilder = None
    ):
        self.config = config or CONFIG
        self.factor_builder = factor_builder or ValMomFactorBuilder()
        self.logger = logging.getLogger(__name__)
    
    def backtest_factor(
        self,
        factor_name: str,  # 'value', 'momentum', 'combo'
        start_date: str,
        end_date: str,
        rebalance_freq: str = 'ME',  # 月末再平衡
        top_n: int = 20,  # 做多前N只
        bottom_n: int = 20,  # 做空后N只
        signal_weighted: bool = True  # 使用信号加权
    ) -> FactorBacktestResult:
        """
        单因子回测
        
        Args:
            factor_name: 'value', 'momentum', or 'combo'
            start_date: 回测开始日期
            end_date: 回测结束日期
            rebalance_freq: 再平衡频率 ('ME'=月末, 'W-MON'=周一)
            top_n: 多头组合股票数
            bottom_n: 空头组合股票数
            signal_weighted: 是否使用信号加权 (论文方法)
        """
        self.logger.info(f"开始回测 {factor_name} 因子: {start_date} 至 {end_date}")
        
        # 生成再平衡日期
        dates = pd.date_range(start=start_date, end=end_date, freq=rebalance_freq)
        
        # 初始化
        portfolio_value = 1.0
        equity_curve = pd.Series(index=dates, dtype=float)
        equity_curve.iloc[0] = portfolio_value
        returns_list = []
        
        prev_weights = None
        turnover_list = []
        
        for i in range(1, len(dates)):
            current_date = dates[i]
            prev_date = dates[i-1]
            
            # 获取股票池
            universe = self.factor_builder.data_provider.get_stock_universe(
                self.config.STOCK_UNIVERSE,
                prev_date.strftime('%Y-%m-%d')
            )
            
            # 构建信号
            if factor_name == 'value':
                signal = self.factor_builder.build_value_signal(
                    universe, prev_date.strftime('%Y-%m-%d')
                )
            elif factor_name == 'momentum':
                signal = self.factor_builder.build_momentum_signal(
                    universe, prev_date.strftime('%Y-%m-%d')
                )
            elif factor_name == 'combo':
                value_sig = self.factor_builder.build_value_signal(
                    universe, prev_date.strftime('%Y-%m-%d')
                )
                mom_sig = self.factor_builder.build_momentum_signal(
                    universe, prev_date.strftime('%Y-%m-%d')
                )
                signal = self.factor_builder.build_combo_signal(value_sig, mom_sig)
            else:
                raise ValueError(f"Unknown factor: {factor_name}")
            
            if signal.empty:
                self.logger.warning(f"{prev_date}: 信号为空，跳过")
                equity_curve.iloc[i] = equity_curve.iloc[i-1]
                continue
            
            # 构建组合权重
            weights = self._construct_portfolio_weights(
                signal, top_n, bottom_n, signal_weighted
            )
            
            # 计算换手率
            if prev_weights is not None:
                turnover = self._calculate_turnover(prev_weights, weights)
                turnover_list.append(turnover)
            prev_weights = weights.copy()
            
            # 计算组合收益
            period_return = self._calculate_portfolio_return(
                weights, prev_date.strftime('%Y-%m-%d'), current_date.strftime('%Y-%m-%d')
            )
            
            portfolio_value *= (1 + period_return)
            equity_curve.iloc[i] = portfolio_value
            returns_list.append(period_return)
        
        # 计算指标
        returns_series = pd.Series(returns_list, index=dates[1:])
        result = self._calculate_metrics(
            factor_name, start_date, end_date, equity_curve, returns_series, turnover_list
        )
        
        self.logger.info(f"{factor_name} 回测完成: 年化收益 {result.annualized_return*100:.2f}%, IR {result.information_ratio:.2f}")
        
        return result
    
    def _construct_portfolio_weights(
        self,
        signal: pd.Series,
        top_n: int,
        bottom_n: int,
        signal_weighted: bool
    ) -> pd.Series:
        """构建组合权重"""
        weights = pd.Series(0.0, index=signal.index)
        
        if signal_weighted:
            # 信号加权 (论文方法)
            # 多头: 信号为正的股票，权重与信号成正比
            # 空头: 信号为负的股票，权重与信号绝对值成正比
            positive_signals = signal[signal > 0]
            negative_signals = signal[signal < 0]
            
            if len(positive_signals) > 0:
                weights.loc[positive_signals.index] = positive_signals / positive_signals.sum() * 0.5
            if len(negative_signals) > 0:
                weights.loc[negative_signals.index] = negative_signals / negative_signals.abs().sum() * (-0.5)
        else:
            # 三分位组合 (Top - Bottom)
            sorted_signal = signal.sort_values(ascending=False)
            
            top_stocks = sorted_signal.head(top_n)
            bottom_stocks = sorted_signal.tail(bottom_n)
            
            weights.loc[top_stocks.index] = 0.5 / len(top_stocks)
            weights.loc[bottom_stocks.index] = -0.5 / len(bottom_stocks)
        
        return weights
    
    def _calculate_portfolio_return(
        self,
        weights: pd.Series,
        start_date: str,
        end_date: str
    ) -> float:
        """计算组合收益"""
        symbols = weights.index.tolist()
        
        # 获取价格数据
        prices = self.factor_builder.data_provider.get_price_data(symbols, start_date, end_date)
        
        if prices.empty or len(prices) < 2:
            return 0.0
        
        # 计算个股收益
        stock_returns = (prices.iloc[-1] / prices.iloc[0] - 1).fillna(0)
        
        # 加权组合收益
        portfolio_return = (weights * stock_returns).sum()
        
        return portfolio_return
    
    def _calculate_turnover(
        self,
        prev_weights: pd.Series,
        current_weights: pd.Series
    ) -> float:
        """计算换手率"""
        all_stocks = prev_weights.index.union(current_weights.index)
        prev_aligned = prev_weights.reindex(all_stocks, fill_value=0)
        curr_aligned = current_weights.reindex(all_stocks, fill_value=0)
        
        turnover = np.abs(curr_aligned - prev_aligned).sum() / 2
        return turnover
    
    def _calculate_metrics(
        self,
        factor_name: str,
        start_date: str,
        end_date: str,
        equity_curve: pd.Series,
        returns_series: pd.Series,
        turnover_list: List[float]
    ) -> FactorBacktestResult:
        """计算回测指标"""
        
        # 基本收益指标
        total_return = equity_curve.iloc[-1] / equity_curve.iloc[0] - 1
        years = len(equity_curve) / 12  # 假设月度数据
        annualized_return = (1 + total_return) ** (1 / max(years, 0.01)) - 1
        
        # 波动率 (年化)
        volatility = returns_series.std() * np.sqrt(12)
        
        # 夏普比率 (假设无风险利率为0)
        sharpe = annualized_return / volatility if volatility > 0 else 0
        
        # Information Ratio (核心指标)
        # IR = 超额收益 / 跟踪误差
        # 这里简化为: 年化收益 / 年化波动率 (相对于0基准)
        information_ratio = sharpe
        
        # Sortino比率 (只考虑下行波动)
        downside_returns = returns_series[returns_series < 0]
        downside_std = downside_returns.std() * np.sqrt(12) if len(downside_returns) > 0 else 0.0001
        sortino = annualized_return / downside_std if downside_std > 0 else 0
        
        # 最大回撤
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax
        max_drawdown = drawdown.min()
        
        # Calmar比率
        calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0
        
        # 换手率
        avg_turnover = np.mean(turnover_list) if turnover_list else 0
        
        return FactorBacktestResult(
            factor_name=factor_name,
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe,
            information_ratio=information_ratio,
            sortino_ratio=sortino,
            max_drawdown=max_drawdown,
            calmar_ratio=calmar,
            turnover=avg_turnover,
            equity_curve=equity_curve,
            returns_series=returns_series
        )


class ValMomVisualizer:
    """ValMom 回测可视化"""
    
    @staticmethod
    def plot_equity_curves(
        results: Dict[str, FactorBacktestResult],
        save_path: str = None
    ):
        """绘制净值曲线"""
        plt.figure(figsize=(12, 6))
        
        for name, result in results.items():
            plt.plot(result.equity_curve.index, result.equity_curve.values, label=name)
        
        plt.title('ValMomEverywhere Factor Performance')
        plt.xlabel('Date')
        plt.ylabel('Cumulative Return')
        plt.legend()
        plt.grid(True)
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"图表已保存: {save_path}")
        
        plt.close()
    
    @staticmethod
    def plot_drawdown(
        results: Dict[str, FactorBacktestResult],
        save_path: str = None
    ):
        """绘制回撤曲线"""
        plt.figure(figsize=(12, 6))
        
        for name, result in results.items():
            cummax = result.equity_curve.cummax()
            drawdown = (result.equity_curve - cummax) / cummax
            plt.plot(drawdown.index, drawdown.values * 100, label=name)
        
        plt.title('Drawdown')
        plt.xlabel('Date')
        plt.ylabel('Drawdown (%)')
        plt.legend()
        plt.grid(True)
        
        if save_path:
            plt.savefig(save_path, dpi=150, bbox_inches='tight')
            print(f"图表已保存: {save_path}")
        
        plt.close()


def run_valmom_backtests(
    start_date: str = "2022-01-01",
    end_date: str = "2024-12-31",
    save_results: bool = True
) -> Dict[str, FactorBacktestResult]:
    """
    运行 ValMomEverywhere 回测
    
    回测三个因子:
    1. Value (价值因子)
    2. Momentum (动量因子)
    3. COMBO (价值+动量组合)
    """
    logger.info("=" * 70)
    logger.info("ValMomEverywhere Backtest")
    logger.info("=" * 70)
    
    backtester = ValMomBacktester()
    
    results = {}
    
    # 1. 价值因子回测
    logger.info("\n[1/3] Running VALUE factor backtest...")
    results['Value'] = backtester.backtest_factor(
        factor_name='value',
        start_date=start_date,
        end_date=end_date,
        rebalance_freq='ME'
    )
    
    # 2. 动量因子回测
    logger.info("\n[2/3] Running MOMENTUM factor backtest...")
    results['Momentum'] = backtester.backtest_factor(
        factor_name='momentum',
        start_date=start_date,
        end_date=end_date,
        rebalance_freq='ME'
    )
    
    # 3. 组合因子回测
    logger.info("\n[3/3] Running COMBO (Value + Momentum) backtest...")
    results['COMBO'] = backtester.backtest_factor(
        factor_name='combo',
        start_date=start_date,
        end_date=end_date,
        rebalance_freq='ME'
    )
    
    # 打印结果汇总
    print_backtest_summary(results)
    
    # 保存结果
    if save_results:
        save_path = "backtests/valmom_results.json"
        save_backtest_results(results, save_path)
        
        # 绘制图表
        visualizer = ValMomVisualizer()
        visualizer.plot_equity_curves(results, "backtests/valmom_equity.png")
        visualizer.plot_drawdown(results, "backtests/valmom_drawdown.png")
    
    return results


def print_backtest_summary(results: Dict[str, FactorBacktestResult]):
    """打印回测汇总"""
    print("\n" + "=" * 90)
    print("ValMomEverywhere Backtest Results Summary")
    print("=" * 90)
    print(f"{'Factor':<12} {'Ann Return':<12} {'Volatility':<12} {'Sharpe':<10} {'IR':<10} {'Max DD':<10}")
    print("-" * 90)
    
    for name, result in results.items():
        print(f"{name:<12} "
              f"{result.annualized_return*100:>10.2f}% "
              f"{result.volatility*100:>10.2f}% "
              f"{result.sharpe_ratio:>9.2f} "
              f"{result.information_ratio:>9.2f} "
              f"{result.max_drawdown*100:>9.2f}%")
    
    print("=" * 90)
    
    # 相关性分析
    if len(results) >= 2:
        print("\nFactor Return Correlations:")
        returns_df = pd.DataFrame({
            name: result.returns_series for name, result in results.items()
        })
        corr = returns_df.corr()
        print(corr.to_string())


def save_backtest_results(results: Dict[str, FactorBacktestResult], filepath: str):
    """保存回测结果"""
    data = {
        name: result.to_dict() for name, result in results.items()
    }
    
    # 保存JSON
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"回测结果已保存: {filepath}")


# 便捷函数
def quick_valmom_backtest(start_date: str = None, end_date: str = None):
    """快速运行 ValMom 回测"""
    config = CONFIG
    start = start_date or config.START_DATE
    end = end_date or config.END_DATE
    
    return run_valmom_backtests(start, end, save_results=True)


if __name__ == "__main__":
    # 运行回测
    results = quick_valmom_backtest("2022-01-01", "2024-03-01")
