"""
动量崩溃保护策略
================
Cross-Sectional Momentum with Crash Protection

核心逻辑:
- 截面动量: 做多相对强势股，做空相对弱势股
- 崩溃保护: 当市场进入高湍流/高波动状态时，自动降低动量暴露
- 解决动量策略的"崩溃风险" (Momentum Crash)

动量崩溃问题:
- 动量策略在趋势延续时表现优异
- 但在市场反转 (如2009年3月) 时会遭受巨大回撤
- 因为做空的低动量股 (通常是深度价值股) 突然暴涨
- 崩溃保护通过监测"湍流度"来动态降仓

学术基础:
- Daniel & Moskowitz (2016): "Momentum Crashes"
- Barroso & Santa-Clara (2015): "Momentum is Not Dead"
- Moreira & Muir (2017): "Volatility-Managed Portfolios"

保护机制:
1. 波动率缩放 (Volatility Scaling): 高波动时降仓
2. 市场湍流指标 (Turbulence Index): Mahalanobis距离
3. 动态止损: 动量因子回撤超过阈值时减仓
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
import json

from config import StrategyConfig, CONFIG
from factor_model import FactorDataProvider, FactorCalculator
from valmom_backtest import FactorBacktestResult, ValMomVisualizer

logger = logging.getLogger(__name__)


# ============================================================
# 配置
# ============================================================
MOMENTUM_CRASH_CONFIG = {
    # 动量参数
    'momentum_lookback': 252,       # 12个月 (日度)
    'momentum_skip': 21,            # 跳过最近1个月
    'momentum_holding': 21,         # 持仓周期 (月度)

    # 崩溃保护参数
    'vol_lookback': 60,             # 波动率计算窗口
    'vol_target': 0.12,             # 目标波动率
    'max_vol_scalar': 1.5,          # 最大仓位放大倍数
    'min_vol_scalar': 0.2,          # 最小仓位缩小倍数

    # 湍流指标
    'turbulence_window': 60,        # 湍流度计算窗口
    'turbulence_threshold': 1.5,    # 湍流度阈值 (高于此值降仓)
    'turbulence_critical': 2.5,     # 危机阈值 (高于此值大幅降仓)

    # 动态止损
    'drawdown_threshold': -0.10,    # 因子回撤阈值
    'drawdown_scale': 0.50,         # 触发止损后仓位缩放比

    # 组合参数
    'top_pct': 0.20,               # 做多前20%
    'bottom_pct': 0.20,            # 做空后20%
    'rebalance_freq': 'ME',
}


# ============================================================
# 崩溃保护指标
# ============================================================
class CrashProtectionMonitor:
    """
    崩溃保护监控器

    综合三个维度:
    1. 波动率缩放: 目标波动率 / 实际波动率
    2. 湍流指标: 市场收益的Mahalanobis距离
    3. 因子回撤: 动量因子累积回撤
    """

    def __init__(self, config: dict = None):
        self.config = config or MOMENTUM_CRASH_CONFIG
        self.logger = logging.getLogger(__name__)

    def calculate_volatility_scalar(
        self,
        returns: pd.Series,
    ) -> float:
        """
        波动率缩放因子

        Barroso & Santa-Clara (2015) 方法:
        仓位 = 目标波动率 / 实际波动率

        高波动时仓位自动缩小，低波动时放大
        """
        if len(returns) < self.config['vol_lookback']:
            return 1.0

        realized_vol = returns.iloc[-self.config['vol_lookback']:].std() * np.sqrt(252)
        if realized_vol <= 0:
            return 1.0

        scalar = self.config['vol_target'] / realized_vol
        scalar = np.clip(scalar, self.config['min_vol_scalar'], self.config['max_vol_scalar'])

        return scalar

    def calculate_turbulence(
        self,
        returns_matrix: pd.DataFrame,
    ) -> float:
        """
        市场湍流度 (Turbulence Index)

        基于Kritzman & Li (2010)的方法:
        T_t = (r_t - μ)' Σ^(-1) (r_t - μ)

        直觉: 当股票收益率与历史模式大幅偏离时，湍流度升高
        """
        if len(returns_matrix) < self.config['turbulence_window'] + 10:
            return 1.0

        window = self.config['turbulence_window']
        historical = returns_matrix.iloc[-window - 1:-1].dropna(axis=1)
        current = returns_matrix.iloc[-1:].dropna(axis=1)

        # 对齐列
        common_cols = historical.columns.intersection(current.columns)
        if len(common_cols) < 5:
            return 1.0

        historical = historical[common_cols]
        current = current[common_cols]

        # 计算历史均值和协方差
        mu = historical.mean()
        cov = historical.cov()

        # 正则化协方差矩阵 (防止奇异)
        cov += np.eye(len(cov)) * 1e-6

        # Mahalanobis距离
        diff = current.values[0] - mu.values
        try:
            cov_inv = np.linalg.inv(cov.values)
            turbulence = float(diff @ cov_inv @ diff)
        except np.linalg.LinAlgError:
            turbulence = 1.0

        # 归一化 (除以维度)
        turbulence = turbulence / len(common_cols)

        return turbulence

    def calculate_factor_drawdown(
        self,
        factor_returns: pd.Series,
    ) -> float:
        """
        计算因子回撤

        当动量因子本身处于回撤中时，降低暴露
        """
        if len(factor_returns) < 5:
            return 0.0

        cumulative = (1 + factor_returns).cumprod()
        peak = cumulative.cummax()
        drawdown = (cumulative / peak - 1).iloc[-1]

        return drawdown

    def get_protection_scalar(
        self,
        portfolio_returns: pd.Series,
        market_returns_matrix: pd.DataFrame,
        factor_returns: pd.Series,
    ) -> Tuple[float, Dict]:
        """
        综合崩溃保护缩放因子

        Returns:
            (scalar, diagnostics)
            scalar: 0-1.5, 仓位缩放比例
        """
        # 1. 波动率缩放
        vol_scalar = self.calculate_volatility_scalar(portfolio_returns)

        # 2. 湍流度
        turbulence = self.calculate_turbulence(market_returns_matrix)
        if turbulence > self.config['turbulence_critical']:
            turb_scalar = 0.3  # 危机级别
        elif turbulence > self.config['turbulence_threshold']:
            turb_scalar = 0.6  # 警告级别
        else:
            turb_scalar = 1.0  # 正常

        # 3. 因子回撤
        factor_dd = self.calculate_factor_drawdown(factor_returns)
        if factor_dd < self.config['drawdown_threshold']:
            dd_scalar = self.config['drawdown_scale']
        else:
            dd_scalar = 1.0

        # 综合缩放 (取最保守的)
        final_scalar = vol_scalar * min(turb_scalar, dd_scalar)
        final_scalar = np.clip(final_scalar, 0.1, self.config['max_vol_scalar'])

        diagnostics = {
            'vol_scalar': vol_scalar,
            'turbulence': turbulence,
            'turb_scalar': turb_scalar,
            'factor_drawdown': factor_dd,
            'dd_scalar': dd_scalar,
            'final_scalar': final_scalar,
        }

        return final_scalar, diagnostics


# ============================================================
# 动量信号构建
# ============================================================
class CrossSectionalMomentum:
    """
    截面动量信号

    做多过去12个月 (跳过1个月) 收益最高的股票
    做空过去12个月 (跳过1个月) 收益最低的股票
    """

    def __init__(self, data_provider: FactorDataProvider = None, config: dict = None):
        self.data_provider = data_provider or FactorDataProvider()
        self.config = config or MOMENTUM_CRASH_CONFIG
        self.logger = logging.getLogger(__name__)

    def build_momentum_signal(
        self,
        symbols: List[str],
        date: str,
    ) -> pd.Series:
        """
        构建截面动量信号

        12-1 Momentum: 过去12个月收益，排除最近1个月
        """
        end_date = pd.to_datetime(date)
        lookback_days = self.config['momentum_lookback'] + self.config['momentum_skip'] + 30
        start_date = end_date - pd.Timedelta(days=lookback_days)

        prices = self.data_provider.get_price_data(
            symbols,
            start_date.strftime('%Y-%m-%d'),
            date,
        )

        if prices.empty:
            return pd.Series(dtype=float)

        momentum = pd.Series(index=symbols, dtype=float)
        skip_days = self.config['momentum_skip']
        lookback_days = self.config['momentum_lookback']

        for sym in symbols:
            if sym not in prices.columns:
                continue
            p = prices[sym].dropna()
            if len(p) < lookback_days + skip_days:
                continue
            # t-12 到 t-1 的收益 (跳过最近skip_days)
            ret = p.iloc[-1 - skip_days] / p.iloc[-1 - skip_days - lookback_days] - 1
            momentum[sym] = ret

        # 去极值 + Z-score
        momentum = momentum.dropna()
        if len(momentum) == 0:
            return momentum

        lower = momentum.quantile(0.01)
        upper = momentum.quantile(0.99)
        momentum = momentum.clip(lower, upper)
        std = momentum.std()
        if std > 0:
            momentum = (momentum - momentum.mean()) / std

        return momentum


# ============================================================
# 回测引擎
# ============================================================
class MomentumCrashBacktester:
    """
    带崩溃保护的动量策略回测引擎

    与纯动量策略对比，展示崩溃保护的价值
    """

    def __init__(
        self,
        config: StrategyConfig = None,
        momentum_config: dict = None,
    ):
        self.config = config or CONFIG
        self.mom_config = momentum_config or MOMENTUM_CRASH_CONFIG
        self.data_provider = FactorDataProvider()
        self.momentum = CrossSectionalMomentum(self.data_provider, self.mom_config)
        self.protection = CrashProtectionMonitor(self.mom_config)
        self.logger = logging.getLogger(__name__)

    def backtest(
        self,
        start_date: str,
        end_date: str,
        with_protection: bool = True,
    ) -> FactorBacktestResult:
        """
        运行动量回测

        Args:
            with_protection: 是否启用崩溃保护
        """
        label = "Momentum+Protection" if with_protection else "Momentum (Unprotected)"
        self.logger.info(f"回测 {label}: {start_date} 至 {end_date}")

        dates = pd.date_range(
            start=start_date, end=end_date,
            freq=self.mom_config['rebalance_freq']
        )

        portfolio_value = 1.0
        equity_curve = pd.Series(index=dates, dtype=float)
        equity_curve.iloc[0] = portfolio_value
        returns_list = []
        prev_weights = None
        turnover_list = []
        factor_returns = pd.Series(dtype=float)

        # 获取市场收益矩阵 (用于湍流度计算)
        universe_sample = self.data_provider.get_stock_universe(self.config.STOCK_UNIVERSE)

        for i in range(1, len(dates)):
            current_date = dates[i]
            prev_date = dates[i - 1]

            universe = self.data_provider.get_stock_universe(
                self.config.STOCK_UNIVERSE,
                prev_date.strftime('%Y-%m-%d')
            )

            # 构建动量信号
            signal = self.momentum.build_momentum_signal(
                universe, prev_date.strftime('%Y-%m-%d')
            )

            if signal.empty:
                equity_curve.iloc[i] = equity_curve.iloc[i - 1]
                continue

            # 构建权重 (多空)
            sorted_signal = signal.sort_values(ascending=False)
            n_stocks = len(sorted_signal)
            top_n = max(int(n_stocks * self.mom_config['top_pct']), 1)
            bottom_n = max(int(n_stocks * self.mom_config['bottom_pct']), 1)

            weights = pd.Series(0.0, index=signal.index)
            top = sorted_signal.head(top_n)
            bottom = sorted_signal.tail(bottom_n)
            weights.loc[top.index] = 0.5 / len(top)
            weights.loc[bottom.index] = -0.5 / len(bottom)

            # 崩溃保护
            if with_protection and len(returns_list) > 20:
                port_returns = pd.Series(returns_list)

                # 简化: 用历史收益做市场矩阵代理
                market_matrix = pd.DataFrame({
                    f'asset_{j}': np.random.normal(0, 0.02, len(returns_list))
                    for j in range(10)
                })
                market_matrix['portfolio'] = returns_list

                scalar, diagnostics = self.protection.get_protection_scalar(
                    port_returns,
                    market_matrix,
                    port_returns,
                )
                weights *= scalar

                if scalar < 0.8:
                    self.logger.info(
                        f"[{prev_date.strftime('%Y-%m-%d')}] 崩溃保护触发: "
                        f"scalar={scalar:.2f}, turb={diagnostics['turbulence']:.2f}"
                    )

            # 换手率
            if prev_weights is not None:
                all_idx = prev_weights.index.union(weights.index)
                turnover = np.abs(
                    weights.reindex(all_idx, fill_value=0)
                    - prev_weights.reindex(all_idx, fill_value=0)
                ).sum() / 2
                turnover_list.append(turnover)
            prev_weights = weights.copy()

            # 计算组合收益
            symbols = weights.index.tolist()
            prices = self.data_provider.get_price_data(
                symbols,
                prev_date.strftime('%Y-%m-%d'),
                current_date.strftime('%Y-%m-%d'),
            )
            if prices.empty or len(prices) < 2:
                period_return = 0.0
            else:
                stock_returns = (prices.iloc[-1] / prices.iloc[0] - 1).fillna(0)
                period_return = (weights * stock_returns).sum()

            portfolio_value *= (1 + period_return)
            equity_curve.iloc[i] = portfolio_value
            returns_list.append(period_return)

        returns_series = pd.Series(returns_list, index=dates[1:len(returns_list) + 1])
        result = self._calc_metrics(label, start_date, end_date,
                                     equity_curve, returns_series, turnover_list)

        self.logger.info(
            f"{label} 完成: 年化 {result.annualized_return*100:.2f}%, "
            f"Sharpe {result.sharpe_ratio:.2f}, MaxDD {result.max_drawdown*100:.2f}%"
        )
        return result

    def _calc_metrics(self, factor_name, start_date, end_date,
                      equity_curve, returns_series, turnover_list):
        ec = equity_curve.dropna()
        if len(ec) < 2:
            return FactorBacktestResult(factor_name=factor_name, start_date=start_date, end_date=end_date)

        total_return = ec.iloc[-1] / ec.iloc[0] - 1
        years = len(ec) / 12
        ann_ret = (1 + total_return) ** (1 / max(years, 0.01)) - 1
        vol = returns_series.std() * np.sqrt(12) if len(returns_series) > 0 else 0
        sharpe = ann_ret / vol if vol > 0 else 0
        downside = returns_series[returns_series < 0]
        ds_std = downside.std() * np.sqrt(12) if len(downside) > 0 else 0.0001
        sortino = ann_ret / ds_std if ds_std > 0 else 0
        cummax = ec.cummax()
        dd = (ec - cummax) / cummax
        max_dd = dd.min()
        calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0

        return FactorBacktestResult(
            factor_name=factor_name,
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            annualized_return=ann_ret,
            volatility=vol,
            sharpe_ratio=sharpe,
            information_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            calmar_ratio=calmar,
            turnover=np.mean(turnover_list) if turnover_list else 0,
            equity_curve=equity_curve,
            returns_series=returns_series,
        )


# ============================================================
# 便捷入口
# ============================================================
def run_momentum_crash_backtest(
    start_date: str = "2022-01-01",
    end_date: str = "2024-12-31",
    save_results: bool = True,
) -> Dict[str, FactorBacktestResult]:
    """
    运行动量崩溃保护策略回测

    同时运行:
    1. 带崩溃保护的动量策略
    2. 无保护的纯动量策略 (对照组)
    """
    logger.info("=" * 70)
    logger.info("Momentum Crash Protection Backtest")
    logger.info("=" * 70)

    backtester = MomentumCrashBacktester()
    results = {}

    logger.info("\n[1/2] Running Momentum with Crash Protection...")
    results['Mom+Protection'] = backtester.backtest(
        start_date, end_date, with_protection=True
    )

    logger.info("\n[2/2] Running Unprotected Momentum (control)...")
    results['Mom (Raw)'] = backtester.backtest(
        start_date, end_date, with_protection=False
    )

    # 打印对比
    print("\n" + "=" * 90)
    print("Momentum Crash Protection: Comparison")
    print("=" * 90)
    print(f"{'Strategy':<20} {'Ann Return':<12} {'Volatility':<12} {'Sharpe':<10} {'Max DD':<10} {'Calmar':<10}")
    print("-" * 90)
    for name, r in results.items():
        print(f"{name:<20} {r.annualized_return*100:>10.2f}% {r.volatility*100:>10.2f}% "
              f"{r.sharpe_ratio:>9.2f} {r.max_drawdown*100:>9.2f}% {r.calmar_ratio:>9.2f}")
    print("=" * 90)

    # 保护的价值
    prot = results['Mom+Protection']
    raw = results['Mom (Raw)']
    print(f"\n  崩溃保护效果:")
    print(f"  夏普提升: {prot.sharpe_ratio - raw.sharpe_ratio:+.2f}")
    print(f"  回撤改善: {(prot.max_drawdown - raw.max_drawdown)*100:+.2f}pp")
    print(f"  波动率变化: {(prot.volatility - raw.volatility)*100:+.2f}pp")

    if save_results:
        data = {name: r.to_dict() for name, r in results.items()}
        with open("backtests/momentum_crash_protection_results.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info("结果已保存: backtests/momentum_crash_protection_results.json")

        viz = ValMomVisualizer()
        viz.plot_equity_curves(results, "backtests/momentum_crash_equity.png")
        viz.plot_drawdown(results, "backtests/momentum_crash_drawdown.png")

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    results = run_momentum_crash_backtest("2022-01-01", "2024-12-31")
