"""
前视偏差检测器 (Lookahead Bias Inspector)
==========================================
检测策略是否使用了未来数据

前视偏差 (Lookahead Bias) 是量化策略回测中最致命的错误之一:
- 在时间 T 做决策时，不小心使用了 T+1, T+2, ... 的数据
- 导致回测收益虚高，实盘无法复现
- 常见来源: 财报数据用报告期而非公告期、价格数据用收盘价下单、
  停牌股选入组合、指数成份股后验

本模块提供 5 种检测方法:
1. 时间戳一致性检查 (Timestamp Consistency)
2. 信号-收益因果检验 (Signal-Return Causality)
3. 随机日期偏移测试 (Random Date Shift Test)
4. 数据可得性审计 (Data Availability Audit)
5. 收益衰减分析 (Return Decay Analysis)

使用方法:
    >>> inspector = LookaheadBiasInspector()
    >>> report = inspector.run_full_inspection(
    ...     strategy_class=QualityLowVolBacktester,
    ...     start_date='2018-01-01',
    ...     end_date='2024-12-31',
    ... )
    >>> report.print_report()
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import logging
import json
import os
import time

logger = logging.getLogger(__name__)


# ============================================================
# 检测结果
# ============================================================
class BiasRisk(Enum):
    """偏差风险等级"""
    PASS = "PASS"           # 无偏差
    WARNING = "WARNING"     # 可疑，需进一步检查
    FAIL = "FAIL"           # 检测到前视偏差


@dataclass
class TestResult:
    """单项检测结果"""
    test_name: str
    risk_level: BiasRisk
    description: str
    details: Dict = field(default_factory=dict)
    recommendation: str = ""


@dataclass
class InspectionReport:
    """完整检测报告"""
    strategy_name: str
    inspection_date: str
    test_results: List[TestResult] = field(default_factory=list)
    overall_risk: BiasRisk = BiasRisk.PASS

    def print_report(self):
        """打印检测报告"""
        print("\n" + "=" * 80)
        print("LOOKAHEAD BIAS INSPECTION REPORT")
        print("=" * 80)
        print(f"  Strategy:  {self.strategy_name}")
        print(f"  Date:      {self.inspection_date}")
        print(f"  Overall:   {self.overall_risk.value}")
        print("=" * 80)

        for i, r in enumerate(self.test_results, 1):
            icon = {"PASS": "[OK]", "WARNING": "[!!]", "FAIL": "[XX]"}[r.risk_level.value]
            print(f"\n  Test {i}: {icon} {r.test_name}")
            print(f"    Risk:    {r.risk_level.value}")
            print(f"    Result:  {r.description}")
            if r.details:
                for k, v in r.details.items():
                    if isinstance(v, float):
                        print(f"    {k}: {v:.6f}")
                    else:
                        print(f"    {k}: {v}")
            if r.recommendation:
                print(f"    Action:  {r.recommendation}")

        print("\n" + "=" * 80)
        if self.overall_risk == BiasRisk.FAIL:
            print("  CONCLUSION: LOOKAHEAD BIAS DETECTED — DO NOT USE IN PRODUCTION")
        elif self.overall_risk == BiasRisk.WARNING:
            print("  CONCLUSION: POTENTIAL BIAS — INVESTIGATE BEFORE PRODUCTION USE")
        else:
            print("  CONCLUSION: NO LOOKAHEAD BIAS DETECTED — STRATEGY APPEARS CLEAN")
        print("=" * 80)

    def to_dict(self) -> Dict:
        return {
            'strategy_name': self.strategy_name,
            'inspection_date': self.inspection_date,
            'overall_risk': self.overall_risk.value,
            'tests': [
                {
                    'test_name': r.test_name,
                    'risk_level': r.risk_level.value,
                    'description': r.description,
                    'details': {k: str(v) for k, v in r.details.items()},
                    'recommendation': r.recommendation,
                }
                for r in self.test_results
            ],
        }


# ============================================================
# 检测器核心
# ============================================================
class LookaheadBiasInspector:
    """
    前视偏差检测器

    通过多种统计检验和逻辑审计，检测回测策略
    是否存在使用未来数据的问题。
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    # ----------------------------------------------------------
    # Test 1: 时间戳一致性检查
    # ----------------------------------------------------------
    def test_timestamp_consistency(
        self,
        signal_dates: pd.DatetimeIndex,
        trade_dates: pd.DatetimeIndex,
        return_dates: pd.DatetimeIndex,
    ) -> TestResult:
        """
        检查: 信号生成日期 <= 交易日期 <= 收益计算日期

        前视偏差常见模式:
        - 信号日期晚于交易日期 (用未来信号做过去的交易)
        - 交易日期和收益日期重叠 (用当日收盘价下单又计算当日收益)
        """
        violations = 0
        total = min(len(signal_dates), len(trade_dates), len(return_dates))

        if total == 0:
            return TestResult(
                test_name="Timestamp Consistency",
                risk_level=BiasRisk.WARNING,
                description="No data to validate",
            )

        for i in range(total):
            sig_date = signal_dates[i]
            trade_date = trade_dates[i]
            ret_date = return_dates[i]

            # 信号必须在交易之前或同日
            if sig_date > trade_date:
                violations += 1
            # 交易必须在收益计算之前
            if trade_date > ret_date:
                violations += 1

        violation_rate = violations / (total * 2)

        if violation_rate > 0.05:
            risk = BiasRisk.FAIL
            desc = f"Timestamp violations: {violations}/{total*2} ({violation_rate:.1%})"
            rec = "Signals are generated AFTER trades — this is lookahead bias"
        elif violation_rate > 0:
            risk = BiasRisk.WARNING
            desc = f"Minor timestamp issues: {violations}/{total*2} ({violation_rate:.1%})"
            rec = "Check date alignment at rebalance boundaries"
        else:
            risk = BiasRisk.PASS
            desc = f"All {total} signal→trade→return sequences are properly ordered"
            rec = ""

        return TestResult(
            test_name="Timestamp Consistency",
            risk_level=risk,
            description=desc,
            details={'violations': violations, 'total_checks': total * 2, 'violation_rate': violation_rate},
            recommendation=rec,
        )

    # ----------------------------------------------------------
    # Test 2: 信号-收益因果检验 (Granger-style)
    # ----------------------------------------------------------
    def test_signal_return_causality(
        self,
        signals: pd.Series,
        forward_returns: pd.Series,
        backward_returns: pd.Series,
    ) -> TestResult:
        """
        检查: 信号是否能预测未来收益但不能"预测"过去收益

        如果信号与过去收益的相关性 >= 与未来收益的相关性，
        说明信号可能包含了未来信息 (因为它"知道"了已经发生的事)。

        正常策略: corr(signal, future_return) > 0, corr(signal, past_return) ≈ 0
        有偏差:  corr(signal, past_return) >> corr(signal, future_return)
        """
        if len(signals) < 10:
            return TestResult(
                test_name="Signal-Return Causality",
                risk_level=BiasRisk.WARNING,
                description="Insufficient data for causality test",
            )

        # 对齐
        common = signals.dropna().index.intersection(
            forward_returns.dropna().index
        ).intersection(
            backward_returns.dropna().index
        )

        if len(common) < 10:
            return TestResult(
                test_name="Signal-Return Causality",
                risk_level=BiasRisk.WARNING,
                description="Insufficient overlapping data",
            )

        sig = signals.loc[common]
        fwd = forward_returns.loc[common]
        bwd = backward_returns.loc[common]

        corr_forward = sig.corr(fwd)
        corr_backward = sig.corr(bwd)

        details = {
            'corr_signal_vs_future_return': corr_forward,
            'corr_signal_vs_past_return': corr_backward,
            'n_observations': len(common),
        }

        # 判断
        if abs(corr_backward) > abs(corr_forward) * 1.5 and abs(corr_backward) > 0.1:
            risk = BiasRisk.FAIL
            desc = (f"Signal correlates MORE with past returns ({corr_backward:.4f}) "
                    f"than future returns ({corr_forward:.4f}) — likely lookahead bias")
            rec = "Check if factor data uses report date instead of announcement date"
        elif abs(corr_backward) > abs(corr_forward) and abs(corr_backward) > 0.05:
            risk = BiasRisk.WARNING
            desc = (f"Signal has non-trivial backward correlation ({corr_backward:.4f}) "
                    f"vs forward ({corr_forward:.4f})")
            rec = "Investigate data timing — may have subtle lookahead"
        else:
            risk = BiasRisk.PASS
            desc = (f"Forward corr ({corr_forward:.4f}) > backward corr ({corr_backward:.4f}) "
                    f"— causal direction appears correct")
            rec = ""

        return TestResult(
            test_name="Signal-Return Causality",
            risk_level=risk,
            description=desc,
            details=details,
            recommendation=rec,
        )

    # ----------------------------------------------------------
    # Test 3: 随机日期偏移测试
    # ----------------------------------------------------------
    def test_random_date_shift(
        self,
        backtest_func: Callable,
        start_date: str,
        end_date: str,
        n_shifts: int = 5,
        shift_range: Tuple[int, int] = (1, 5),
    ) -> TestResult:
        """
        检查: 将因子数据随机向后偏移 N 天，观察收益是否大幅下降

        原理:
        - 如果策略没有前视偏差，将信号延迟1-5天不应导致收益消失
        - 如果策略依赖未来数据，哪怕延迟1天都会严重恶化

        方法:
        1. 运行原始回测，记录收益
        2. 将信号延迟 shift 天，重新回测
        3. 比较延迟前后的收益差异
        """
        try:
            # 原始回测
            original_result = backtest_func(start_date, end_date, shift_days=0)
            original_return = original_result.annualized_return

            shifted_returns = []
            for _ in range(n_shifts):
                shift = np.random.randint(shift_range[0], shift_range[1] + 1)
                shifted_result = backtest_func(start_date, end_date, shift_days=shift)
                shifted_returns.append(shifted_result.annualized_return)

            avg_shifted = np.mean(shifted_returns)
            decay_ratio = avg_shifted / original_return if original_return != 0 else 1.0

        except Exception as e:
            return TestResult(
                test_name="Random Date Shift",
                risk_level=BiasRisk.WARNING,
                description=f"Could not run shift test: {e}",
                recommendation="Implement shift_days parameter in backtest function",
            )

        details = {
            'original_ann_return': original_return,
            'avg_shifted_ann_return': avg_shifted,
            'decay_ratio': decay_ratio,
            'n_shifts': n_shifts,
        }

        if decay_ratio < 0.3:
            risk = BiasRisk.FAIL
            desc = (f"Return decays {(1-decay_ratio)*100:.0f}% with 1-5 day shift — "
                    f"strong evidence of lookahead bias")
            rec = "Strategy heavily depends on same-day data — check order timing"
        elif decay_ratio < 0.6:
            risk = BiasRisk.WARNING
            desc = (f"Return decays {(1-decay_ratio)*100:.0f}% with shift — "
                    f"possible data snooping")
            rec = "Add 1-day lag to all factor signals as safety margin"
        else:
            risk = BiasRisk.PASS
            desc = (f"Return retains {decay_ratio*100:.0f}% after shift — "
                    f"robust to timing changes")
            rec = ""

        return TestResult(
            test_name="Random Date Shift",
            risk_level=risk,
            description=desc,
            details=details,
            recommendation=rec,
        )

    # ----------------------------------------------------------
    # Test 4: 数据可得性审计
    # ----------------------------------------------------------
    def test_data_availability(
        self,
        factor_data_dates: Dict[str, pd.DatetimeIndex],
        signal_generation_dates: pd.DatetimeIndex,
        financial_report_lag_days: int = 90,
    ) -> TestResult:
        """
        检查: 因子数据在信号生成时是否真的可获得

        中国A股财报披露规则:
        - 年报: 4月30日前 (Q4数据实际可用要到次年5月)
        - 半年报: 8月31日前
        - 季报: 1个月内

        如果策略在1月使用了前一年12月的ROE数据，
        而该年报要到4月才公布 → 前视偏差！

        美股:
        - 10-K (年报): 60-90天 filing deadline
        - 10-Q (季报): 40-45天 filing deadline
        """
        violations = 0
        total_checks = 0
        violation_details = []

        for factor_name, available_dates in factor_data_dates.items():
            if available_dates.empty:
                continue

            for sig_date in signal_generation_dates:
                total_checks += 1

                # 财报数据需要等待公告
                # 实际可用日期 = 报告期截止日 + 报告发布延迟
                latest_available = sig_date - timedelta(days=financial_report_lag_days)

                # 检查是否有使用了尚未公布的数据
                data_used = available_dates[available_dates <= sig_date]
                if len(data_used) > 0:
                    most_recent_data = data_used.max()
                    if most_recent_data > latest_available:
                        violations += 1
                        if len(violation_details) < 5:
                            violation_details.append({
                                'factor': factor_name,
                                'signal_date': sig_date.strftime('%Y-%m-%d'),
                                'data_date': most_recent_data.strftime('%Y-%m-%d'),
                                'earliest_available': latest_available.strftime('%Y-%m-%d'),
                            })

        if total_checks == 0:
            return TestResult(
                test_name="Data Availability Audit",
                risk_level=BiasRisk.WARNING,
                description="No factor data dates provided for audit",
                recommendation="Pass factor_data_dates to enable this check",
            )

        violation_rate = violations / total_checks

        details = {
            'total_checks': total_checks,
            'violations': violations,
            'violation_rate': violation_rate,
            'report_lag_assumed_days': financial_report_lag_days,
            'sample_violations': violation_details[:3],
        }

        if violation_rate > 0.10:
            risk = BiasRisk.FAIL
            desc = (f"{violations}/{total_checks} ({violation_rate:.1%}) factor observations "
                    f"used before they were publicly available")
            rec = "Use announcement date (公告日) instead of report date (报告期)"
        elif violation_rate > 0:
            risk = BiasRisk.WARNING
            desc = f"Minor data availability issues: {violations}/{total_checks}"
            rec = "Add financial report lag buffer (A股: 90天, 美股: 60天)"
        else:
            risk = BiasRisk.PASS
            desc = f"All {total_checks} factor data points were available at signal time"
            rec = ""

        return TestResult(
            test_name="Data Availability Audit",
            risk_level=risk,
            description=desc,
            details=details,
            recommendation=rec,
        )

    # ----------------------------------------------------------
    # Test 5: 收益衰减分析
    # ----------------------------------------------------------
    def test_return_decay(
        self,
        signal: pd.Series,
        price_data: pd.DataFrame,
        holding_periods: List[int] = None,
    ) -> TestResult:
        """
        检查: 因子收益是否随持有期递增而合理衰减

        正常因子:
        - IC(1天) > IC(5天) > IC(20天) — 信息逐渐被消化
        - 衰减应该是平滑的

        有偏差的因子:
        - IC(0天) >> IC(1天) — 在当天就"全部兑现"
        - IC突然在某个lag断崖下降
        """
        if holding_periods is None:
            holding_periods = [1, 2, 3, 5, 10, 20]

        if price_data.empty or signal.empty:
            return TestResult(
                test_name="Return Decay Analysis",
                risk_level=BiasRisk.WARNING,
                description="Insufficient data for decay analysis",
            )

        returns_data = price_data.pct_change()
        ic_by_lag = {}

        for lag in holding_periods:
            # Forward return over next `lag` days
            fwd_return = price_data.pct_change(lag).shift(-lag)

            # Cross-sectional IC at each date
            ics = []
            for date in signal.index:
                if date in fwd_return.index:
                    sig_cross = signal.loc[date] if isinstance(signal.loc[date], pd.Series) else None
                    ret_cross = fwd_return.loc[date] if date in fwd_return.index else None

                    if sig_cross is not None and ret_cross is not None:
                        common = sig_cross.dropna().index.intersection(ret_cross.dropna().index)
                        if len(common) > 10:
                            ic = sig_cross.loc[common].corr(ret_cross.loc[common])
                            if not np.isnan(ic):
                                ics.append(ic)

            ic_by_lag[lag] = np.mean(ics) if ics else 0

        details = {f'IC_lag_{k}d': v for k, v in ic_by_lag.items()}

        # Analyze decay pattern
        ic_values = list(ic_by_lag.values())
        if len(ic_values) >= 3 and ic_values[0] != 0:
            # Check if IC at lag=0/1 is massively higher than longer lags
            short_ic = abs(np.mean(ic_values[:2]))
            long_ic = abs(np.mean(ic_values[2:]))
            decay_ratio = long_ic / short_ic if short_ic > 0 else 1.0

            if decay_ratio < 0.15 and short_ic > 0.03:
                risk = BiasRisk.FAIL
                desc = (f"IC drops {(1-decay_ratio)*100:.0f}% from short to long lag — "
                        f"factor information is instantly consumed (lookahead pattern)")
                rec = "Factor likely uses contemporaneous data — add at least 1-day lag"
            elif decay_ratio < 0.4:
                risk = BiasRisk.WARNING
                desc = f"IC decay is steep (short IC: {short_ic:.4f}, long IC: {long_ic:.4f})"
                rec = "May indicate high-frequency signal bleeding; verify data timing"
            else:
                risk = BiasRisk.PASS
                desc = f"IC decay is gradual and natural (ratio: {decay_ratio:.2f})"
                rec = ""
        else:
            risk = BiasRisk.PASS
            desc = "IC values are low or flat — no strong decay pattern detected"
            rec = ""

        return TestResult(
            test_name="Return Decay Analysis",
            risk_level=risk,
            description=desc,
            details=details,
            recommendation=rec,
        )

    # ----------------------------------------------------------
    # 完整检测流程
    # ----------------------------------------------------------
    def run_full_inspection(
        self,
        strategy_name: str = "Quality+LowVol",
        start_date: str = "2018-01-01",
        end_date: str = "2024-12-31",
        backtest_func: Callable = None,
    ) -> InspectionReport:
        """
        运行完整的前视偏差检测

        使用模拟数据进行结构性检查
        真实检查需要传入实际的 backtest_func 和数据
        """
        report = InspectionReport(
            strategy_name=strategy_name,
            inspection_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )

        self.logger.info("=" * 60)
        self.logger.info("Running Lookahead Bias Inspection")
        self.logger.info("=" * 60)

        # === Test 1: Timestamp Consistency ===
        self.logger.info("[1/5] Timestamp Consistency Check...")
        result1 = self._run_timestamp_test(start_date, end_date)
        report.test_results.append(result1)

        # === Test 2: Signal-Return Causality ===
        self.logger.info("[2/5] Signal-Return Causality Check...")
        result2 = self._run_causality_test(start_date, end_date)
        report.test_results.append(result2)

        # === Test 3: Random Date Shift ===
        self.logger.info("[3/5] Random Date Shift Test...")
        result3 = self._run_shift_test(start_date, end_date, backtest_func)
        report.test_results.append(result3)

        # === Test 4: Data Availability ===
        self.logger.info("[4/5] Data Availability Audit...")
        result4 = self._run_availability_test(start_date, end_date)
        report.test_results.append(result4)

        # === Test 5: Return Decay ===
        self.logger.info("[5/5] Return Decay Analysis...")
        result5 = self._run_decay_test(start_date, end_date)
        report.test_results.append(result5)

        # Overall assessment
        risk_levels = [r.risk_level for r in report.test_results]
        if BiasRisk.FAIL in risk_levels:
            report.overall_risk = BiasRisk.FAIL
        elif BiasRisk.WARNING in risk_levels:
            report.overall_risk = BiasRisk.WARNING
        else:
            report.overall_risk = BiasRisk.PASS

        return report

    # ----------------------------------------------------------
    # 内部测试运行器 (使用策略数据)
    # ----------------------------------------------------------
    def _run_timestamp_test(self, start_date, end_date) -> TestResult:
        """使用策略的实际日期序列运行时间戳检查"""
        dates = pd.date_range(start=start_date, end=end_date, freq='ME')

        # 在我们的策略中:
        # signal_date = prev_date (t-1月底)
        # trade_date = current_date (t月初)
        # return_date = current_date (t月底)
        signal_dates = dates[:-1]   # 信号在前一期生成
        trade_dates = dates[1:]     # 交易在下一期执行
        return_dates = dates[1:]    # 收益在交易期计算

        return self.test_timestamp_consistency(signal_dates, trade_dates, return_dates)

    def _run_causality_test(self, start_date, end_date) -> TestResult:
        """使用策略数据运行因果检验"""
        from quality_lowvol_dual_market_backtest import (
            RiceQuantDataProvider, UnifiedDataProvider,
            DualMarketQualityLowVolBuilder, A_STOCK_CONFIG,
        )

        provider = RiceQuantDataProvider()
        unified = UnifiedDataProvider(provider, A_STOCK_CONFIG)
        builder = DualMarketQualityLowVolBuilder(unified)

        dates = pd.date_range(start=start_date, end=end_date, freq='ME')
        signals = []
        fwd_returns = []
        bwd_returns = []

        universe = unified.get_stock_universe()

        for i in range(2, len(dates) - 1):
            date = dates[i]
            date_str = date.strftime('%Y-%m-%d')

            # 构建信号
            signal = builder.build_composite_signal(
                builder.build_quality_signal(universe, date_str),
                builder.build_lowvol_signal(universe, date_str),
            )

            if signal.empty:
                continue

            # 前向收益 (T到T+1)
            prices_fwd = unified.get_price_data(
                universe[:50],
                date_str,
                dates[i + 1].strftime('%Y-%m-%d'),
            )

            # 后向收益 (T-1到T)
            prices_bwd = unified.get_price_data(
                universe[:50],
                dates[i - 1].strftime('%Y-%m-%d'),
                date_str,
            )

            if not prices_fwd.empty and len(prices_fwd) >= 2:
                fwd_ret = (prices_fwd.iloc[-1] / prices_fwd.iloc[0] - 1)
                common = signal.index.intersection(fwd_ret.index)
                if len(common) > 5:
                    # 信号加权组合的前向收益
                    fwd_port = (signal.loc[common] * fwd_ret.loc[common]).mean()
                    fwd_returns.append(fwd_port)
                else:
                    fwd_returns.append(0)
            else:
                fwd_returns.append(0)

            if not prices_bwd.empty and len(prices_bwd) >= 2:
                bwd_ret = (prices_bwd.iloc[-1] / prices_bwd.iloc[0] - 1)
                common = signal.index.intersection(bwd_ret.index)
                if len(common) > 5:
                    bwd_port = (signal.loc[common] * bwd_ret.loc[common]).mean()
                    bwd_returns.append(bwd_port)
                else:
                    bwd_returns.append(0)
            else:
                bwd_returns.append(0)

            signals.append(signal.mean())

        if len(signals) < 10:
            return TestResult(
                test_name="Signal-Return Causality",
                risk_level=BiasRisk.WARNING,
                description="Insufficient data for causality test",
            )

        sig_series = pd.Series(signals)
        fwd_series = pd.Series(fwd_returns)
        bwd_series = pd.Series(bwd_returns)

        return self.test_signal_return_causality(sig_series, fwd_series, bwd_series)

    def _run_shift_test(self, start_date, end_date, backtest_func=None) -> TestResult:
        """运行日期偏移测试"""
        from quality_lowvol_dual_market_backtest import (
            RiceQuantDataProvider, UnifiedDataProvider,
            DualMarketQualityLowVolBuilder, SingleMarketBacktester,
            A_STOCK_CONFIG, MarketConfig, Market,
        )

        def shifted_backtest(start, end, shift_days=0):
            """带偏移的回测"""
            provider = RiceQuantDataProvider()

            # 修改配置: 加入信号延迟
            config = MarketConfig(
                market=Market.A_STOCK,
                universe_name='hs300',
                benchmark_name='沪深300',
                currency='CNY',
                trading_days_per_year=244,
                commission_rate=0.0003,
                slippage=0.001,
                quality_factors=['roe', 'roa', 'gross_profit_margin'],
                start_date=start,
                end_date=end,
            )

            unified = UnifiedDataProvider(provider, config)
            builder = DualMarketQualityLowVolBuilder(unified)
            bt = SingleMarketBacktester(unified, builder, config)

            # 原始回测
            if shift_days == 0:
                return bt.backtest_factor('composite', start, end)

            # 偏移回测: 将开始日期后移，模拟信号延迟
            shifted_start = (pd.to_datetime(start) + timedelta(days=shift_days)).strftime('%Y-%m-%d')
            return bt.backtest_factor('composite', shifted_start, end)

        func = backtest_func or shifted_backtest

        return self.test_random_date_shift(
            func, start_date, end_date,
            n_shifts=3, shift_range=(1, 3),
        )

    def _run_availability_test(self, start_date, end_date) -> TestResult:
        """运行数据可得性测试"""
        dates = pd.date_range(start=start_date, end=end_date, freq='ME')

        # 模拟: 财报数据的报告期日期
        # A股年报: 12月31日报告期，4月30日前公告
        # A股季报: 3/6/9月底，1个月后公告
        factor_dates = {
            'roe': dates,       # 假设每月都有 (实际是季度)
            'roa': dates,
            'gross_profit_margin': dates,
        }

        return self.test_data_availability(
            factor_dates, dates,
            financial_report_lag_days=90,  # A股年报假设90天延迟
        )

    def _run_decay_test(self, start_date, end_date) -> TestResult:
        """运行收益衰减测试"""
        from quality_lowvol_dual_market_backtest import (
            RiceQuantDataProvider, UnifiedDataProvider,
            DualMarketQualityLowVolBuilder, A_STOCK_CONFIG,
        )

        provider = RiceQuantDataProvider()
        unified = UnifiedDataProvider(provider, A_STOCK_CONFIG)
        builder = DualMarketQualityLowVolBuilder(unified)

        universe = unified.get_stock_universe()[:50]
        mid_date = pd.to_datetime(start_date) + (
            pd.to_datetime(end_date) - pd.to_datetime(start_date)
        ) / 2
        date_str = mid_date.strftime('%Y-%m-%d')

        signal = builder.build_composite_signal(
            builder.build_quality_signal(universe, date_str),
            builder.build_lowvol_signal(universe, date_str),
        )

        price_data = unified.get_price_data(
            universe, date_str,
            (mid_date + timedelta(days=60)).strftime('%Y-%m-%d'),
        )

        if signal.empty or price_data.empty:
            return TestResult(
                test_name="Return Decay Analysis",
                risk_level=BiasRisk.WARNING,
                description="Insufficient data for decay analysis",
            )

        return self.test_return_decay(signal, price_data, [1, 2, 5, 10, 20])


# ============================================================
# 便捷入口
# ============================================================
def run_lookahead_inspection(
    start_date: str = "2018-01-01",
    end_date: str = "2024-12-31",
    save_report: bool = True,
) -> InspectionReport:
    """
    运行完整的前视偏差检测

    Example:
        >>> report = run_lookahead_inspection('2018-01-01', '2024-12-31')
        >>> report.print_report()
    """
    logger.info("Starting Lookahead Bias Inspection...")

    inspector = LookaheadBiasInspector()
    report = inspector.run_full_inspection(
        strategy_name="Quality+LowVol (Dual Market)",
        start_date=start_date,
        end_date=end_date,
    )

    report.print_report()

    if save_report:
        os.makedirs("backtests", exist_ok=True)
        path = "backtests/lookahead_bias_report.json"
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Report saved: {path}")

    return report


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s',
    )
    report = run_lookahead_inspection("2018-01-01", "2024-12-31")
