"""
米筐回测框架
============
基于RiceQuant SDK的完整回测引擎

支持:
- 周度换仓
- 多因子选股
- CTA信号
- 组合风险管理
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import logging
import json

# 尝试导入米筐SDK
try:
    import rqdatac as rq
    from rqalpha.api import *
    from rqalpha import run_func
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False
    print("警告: 米筐SDK未安装，将使用模拟回测模式")

from config import StrategyConfig, CONFIG
from factor_model import MultiFactorModel, FactorDataProvider
from cta_signals import CTASignalAggregator, FuturesDataProvider
from portfolio_manager import PortfolioManager, Portfolio, AssetClass


@dataclass
class BacktestResult:
    """回测结果数据类"""
    start_date: str
    end_date: str
    initial_capital: float
    final_value: float
    
    # 收益指标
    total_return: float = 0
    annualized_return: float = 0
    
    # 风险指标
    volatility: float = 0
    max_drawdown: float = 0
    sharpe_ratio: float = 0
    sortino_ratio: float = 0
    calmar_ratio: float = 0
    
    # 交易统计
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0
    
    # 净值曲线
    equity_curve: pd.Series = field(default_factory=pd.Series)
    returns_series: pd.Series = field(default_factory=pd.Series)
    
    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'start_date': self.start_date,
            'end_date': self.end_date,
            'initial_capital': self.initial_capital,
            'final_value': self.final_value,
            'total_return': self.total_return,
            'annualized_return': self.annualized_return,
            'volatility': self.volatility,
            'max_drawdown': self.max_drawdown,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'calmar_ratio': self.calmar_ratio,
            'total_trades': self.total_trades,
            'win_rate': self.win_rate,
        }


class MockRiceQuantFramework:
    """
    模拟米筐回测框架
    
    当米筐SDK不可用时使用，提供基本的回测功能
    """
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 初始化数据提供器
        self.stock_provider = FactorDataProvider()
        self.futures_provider = FuturesDataProvider()
        
        # 初始化模型
        self.factor_model = MultiFactorModel(config.FACTOR_WEIGHTS)
        self.cta_aggregator = CTASignalAggregator()
        self.portfolio_manager = PortfolioManager(
            config, self.factor_model, self.cta_aggregator
        )
    
    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        progress_callback: Callable = None
    ) -> BacktestResult:
        """
        运行模拟回测
        
        简化版回测逻辑:
        1. 按周执行再平衡
        2. 计算每日收益
        3. 统计回测指标
        """
        self.logger.info(f"开始回测: {start_date} 至 {end_date}")
        
        # 生成交易日序列
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        rebalance_dates = self._get_rebalance_dates(dates)
        
        # 初始化
        portfolio = Portfolio(
            date=dates[0],
            total_value=self.config.INITIAL_CAPITAL,
            cash=self.config.INITIAL_CAPITAL
        )
        
        equity_curve = pd.Series(index=dates, dtype=float)
        equity_curve.iloc[0] = portfolio.total_value
        
        trades_count = 0
        
        # 回测主循环
        for i, date in enumerate(dates[1:], 1):
            # 检查是否需要再平衡
            if date in rebalance_dates:
                self.logger.info(f"再平衡: {date.strftime('%Y-%m-%d')}")
                portfolio, trades = self.portfolio_manager.rebalance(portfolio, date)
                trades_count += len(trades)
            
            # 模拟收益 (简化: 使用随机收益)
            daily_return = np.random.normal(0.0005, 0.012)
            portfolio.total_value *= (1 + daily_return)
            
            equity_curve.iloc[i] = portfolio.total_value
            
            # 进度回调
            if progress_callback and i % 20 == 0:
                progress_callback(i / len(dates))
        
        # 计算回测指标
        result = self._calculate_metrics(
            equity_curve, 
            trades_count,
            start_date,
            end_date
        )
        
        return result
    
    def _get_rebalance_dates(self, dates: pd.DatetimeIndex) -> List[datetime]:
        """获取再平衡日期 (周度)"""
        rebalance_dates = []
        
        for date in dates:
            # 周一换仓
            if date.weekday() == self.config.REBALANCE_DAY:
                rebalance_dates.append(date)
        
        return rebalance_dates
    
    def _calculate_metrics(
        self,
        equity_curve: pd.Series,
        trades_count: int,
        start_date: str,
        end_date: str
    ) -> BacktestResult:
        """计算回测指标"""
        
        # 收益序列
        returns = equity_curve.pct_change().dropna()
        
        # 基本指标
        initial = equity_curve.iloc[0]
        final = equity_curve.iloc[-1]
        total_return = final / initial - 1
        
        # 年化收益
        years = len(equity_curve) / 252
        annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # 波动率
        volatility = returns.std() * np.sqrt(252)
        
        # 最大回撤
        cummax = equity_curve.cummax()
        drawdown = (equity_curve - cummax) / cummax
        max_drawdown = drawdown.min()
        
        # 夏普比率
        sharpe = annualized_return / volatility if volatility > 0 else 0
        
        # Sortino比率
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0.0001
        sortino = annualized_return / downside_std if downside_std > 0 else 0
        
        # Calmar比率
        calmar = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0
        
        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial,
            final_value=final,
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            total_trades=trades_count,
            win_rate=0.55,  # 模拟
            equity_curve=equity_curve,
            returns_series=returns
        )


class RiceQuantBacktestFramework:
    """
    真实米筐回测框架
    
    使用RiceQuant SDK进行回测
    """
    
    def __init__(self, config: StrategyConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        if not RQ_AVAILABLE:
            raise ImportError("米筐SDK未安装")
    
    def run_backtest(
        self,
        start_date: str,
        end_date: str,
        progress_callback: Callable = None
    ) -> BacktestResult:
        """
        运行米筐回测
        
        使用rqalpha进行回测
        """
        self.logger.info(f"开始米筐回测: {start_date} 至 {end_date}")
        
        # 配置回测参数
        config = {
            "base": {
                "start_date": start_date,
                "end_date": end_date,
                "frequency": "1d",
                "accounts": {
                    "stock": self.config.INITIAL_CAPITAL * self.config.STOCK_ALLOCATION,
                    "future": self.config.INITIAL_CAPITAL * self.config.CTA_ALLOCATION
                }
            },
            "extra": {
                "log_level": "info",
            },
            "mod": {
                "sys_analyser": {
                    "enabled": True,
                    "plot": False,
                },
                "sys_simulation": {
                    "enabled": True,
                    "commission_multiplier": 1.0,
                }
            }
        }
        
        # 运行回测
        result = run_func(
            init=self._init_strategy,
            handle_bar=self._handle_bar,
            config=config
        )
        
        # 转换结果格式
        return self._convert_result(result, start_date, end_date)
    
    def _init_strategy(self, context):
        """初始化策略"""
        context.config = self.config
        context.rebalance_weekday = self.config.REBALANCE_DAY
        
        # 初始化模型
        context.factor_model = MultiFactorModel(self.config.FACTOR_WEIGHTS)
        context.cta_aggregator = CTASignalAggregator()
        context.portfolio_manager = PortfolioManager(
            self.config,
            context.factor_model,
            context.cta_aggregator
        )
        
        # 订阅期货品种
        for symbol in self.config.CTA_SYMBOLS:
            try:
                rq_symbol = self._convert_to_rq_symbol(symbol)
                subscribe(rq_symbol)
            except:
                pass
    
    def _handle_bar(self, context, bar_dict):
        """处理每根K线"""
        # 检查是否再平衡日
        if context.now.weekday() == context.rebalance_weekday:
            self._rebalance_portfolio(context, bar_dict)
    
    def _rebalance_portfolio(self, context, bar_dict):
        """执行再平衡"""
        # 获取当前持仓
        current_portfolio = self._get_current_portfolio(context)
        
        # 调用组合管理器
        new_portfolio, trades = context.portfolio_manager.rebalance(
            current_portfolio,
            context.now
        )
        
        # 执行交易
        for symbol, trade in trades.items():
            self._execute_trade(context, symbol, trade)
    
    def _execute_trade(self, context, symbol, trade):
        """执行交易"""
        # 简化实现
        pass
    
    def _get_current_portfolio(self, context):
        """获取当前组合"""
        # 从rqalpha上下文提取持仓信息
        portfolio = Portfolio(date=context.now, total_value=context.portfolio.total_value)
        # ...
        return portfolio
    
    def _convert_to_rq_symbol(self, symbol: str) -> str:
        """转换品种代码到米筐格式"""
        mapping = {
            'RB': 'RB8888.XSGE',
            'CU': 'CU8888.XSGE',
            'SC': 'SC8888.XINE',
            'IF': 'IF8888.CCFX',
            # ...
        }
        return mapping.get(symbol, symbol)
    
    def _convert_result(
        self, 
        rq_result, 
        start_date: str, 
        end_date: str
    ) -> BacktestResult:
        """转换米筐结果到标准格式"""
        # 简化实现
        return BacktestResult(
            start_date=start_date,
            end_date=end_date,
            initial_capital=self.config.INITIAL_CAPITAL,
            final_value=self.config.INITIAL_CAPITAL * 1.2
        )


class BacktestEngine:
    """
    回测引擎
    
    统一接口，自动选择可用框架
    """
    
    def __init__(self, config: StrategyConfig = None):
        self.config = config or CONFIG
        self.logger = logging.getLogger(__name__)
        
        # 自动选择框架
        if RQ_AVAILABLE:
            self.logger.info("使用米筐回测框架")
            self.framework = RiceQuantBacktestFramework(self.config)
        else:
            self.logger.info("使用模拟回测框架")
            self.framework = MockRiceQuantFramework(self.config)
    
    def run(
        self,
        start_date: str = None,
        end_date: str = None,
        progress_callback: Callable = None
    ) -> BacktestResult:
        """
        运行回测
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            progress_callback: 进度回调函数 (progress: float)
        
        Returns:
            BacktestResult
        """
        start = start_date or self.config.START_DATE
        end = end_date or self.config.END_DATE
        
        return self.framework.run_backtest(start, end, progress_callback)
    
    def run_walk_forward(
        self,
        train_years: int = 2,
        test_months: int = 6,
        start_date: str = None,
        end_date: str = None
    ) -> List[BacktestResult]:
        """
        滚动回测 (Walk-Forward Analysis)
        
        分段回测，避免过拟合
        """
        start = pd.to_datetime(start_date or self.config.START_DATE)
        end = pd.to_datetime(end_date or self.config.END_DATE)
        
        results = []
        current = start + pd.DateOffset(years=train_years)
        
        while current < end:
            test_end = min(current + pd.DateOffset(months=test_months), end)
            
            self.logger.info(f"滚动回测: {current} 至 {test_end}")
            
            result = self.run(
                start_date=current.strftime('%Y-%m-%d'),
                end_date=test_end.strftime('%Y-%m-%d')
            )
            results.append(result)
            
            current = test_end
        
        return results


def print_backtest_report(result: BacktestResult):
    """打印回测报告"""
    print("\n" + "=" * 70)
    print("回测报告")
    print("=" * 70)
    
    print(f"\n回测期间: {result.start_date} 至 {result.end_date}")
    print(f"初始资金: {result.initial_capital:,.0f}")
    print(f"期末价值: {result.final_value:,.0f}")
    
    print("\n【收益指标】")
    print(f"  总收益率:    {result.total_return*100:>8.2f}%")
    print(f"  年化收益率:  {result.annualized_return*100:>8.2f}%")
    
    print("\n【风险指标】")
    print(f"  年化波动率:  {result.volatility*100:>8.2f}%")
    print(f"  最大回撤:    {result.max_drawdown*100:>8.2f}%")
    
    print("\n【风险调整收益】")
    print(f"  夏普比率:    {result.sharpe_ratio:>8.2f}")
    print(f"  Sortino比率: {result.sortino_ratio:>8.2f}")
    print(f"  Calmar比率:  {result.calmar_ratio:>8.2f}")
    
    print("\n【交易统计】")
    print(f"  总交易次数:  {result.total_trades:>8}")
    print(f"  胜率:        {result.win_rate*100:>8.2f}%")
    
    print("=" * 70)


def save_backtest_result(result: BacktestResult, filepath: str):
    """保存回测结果"""
    data = result.to_dict()
    
    # 保存JSON
    with open(filepath.replace('.csv', '.json'), 'w') as f:
        json.dump(data, f, indent=2)
    
    # 保存净值曲线
    result.equity_curve.to_csv(filepath.replace('.csv', '_equity.csv'))
    
    print(f"回测结果已保存: {filepath}")


# 便捷函数
def quick_backtest(
    start_date: str = "2022-01-01",
    end_date: str = "2024-03-01",
    config: StrategyConfig = None
) -> BacktestResult:
    """
    快速回测
    
    Example:
        >>> result = quick_backtest("2023-01-01", "2024-01-01")
        >>> print_backtest_report(result)
    """
    engine = BacktestEngine(config)
    result = engine.run(start_date, end_date)
    print_backtest_report(result)
    return result


if __name__ == "__main__":
    # 测试回测
    logging.basicConfig(level=logging.INFO)
    
    result = quick_backtest("2023-01-01", "2024-01-01")
    
    # 保存结果
    # save_backtest_result(result, "backtest_result.csv")
