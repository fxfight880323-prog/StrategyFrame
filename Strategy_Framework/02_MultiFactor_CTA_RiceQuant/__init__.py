"""
多因子选股 + CTA策略包
=====================

基于米筐(RiceQuant)数据的多因子选股和CTA策略框架

主要模块:
    - config: 策略配置
    - factor_model: 多因子选股模型
    - cta_signals: CTA信号生成
    - portfolio_manager: 组合管理
    - ricequant_backtest: 回测框架
    - strategy_main: 策略主程序

使用示例:
    >>> from strategy_main import run_backtest_mode
    >>> result = run_backtest_mode("2023-01-01", "2024-01-01")
    >>> print(f"收益率: {result.total_return*100:.2f}%")
"""

__version__ = "1.0.0"
__author__ = "Quant Strategy Team"

# 导出主要类和函数
from config import StrategyConfig, CONFIG
from factor_model import MultiFactorModel, quick_screen
from cta_signals import CTASignalAggregator, get_cta_signals
from portfolio_manager import PortfolioManager, quick_rebalance
from ricequant_backtest import BacktestEngine, quick_backtest

__all__ = [
    'StrategyConfig',
    'CONFIG',
    'MultiFactorModel',
    'CTASignalAggregator',
    'PortfolioManager',
    'BacktestEngine',
    'quick_screen',
    'get_cta_signals',
    'quick_rebalance',
    'quick_backtest',
]
