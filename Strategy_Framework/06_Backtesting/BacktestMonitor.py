#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
回测监视器 - Backtest Monitor
=============================

功能:
1. 检查信号生成是否使用未来数据 (Look-ahead Bias Detection)
2. 计算风险调整收益指标 (Sharpe, Calmar, Information Ratio等)
3. 监控回测过程合规性
4. 生成详细监控报告

适用策略:
- CTA_FLP_Strategy
- PatternStrategy_A500
- CTA策略
- 所有使用历史数据的量化策略

作者: Quant Monitor System
日期: 2026-03-03
"""

import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging
import traceback
import json


# ============================================================
# 配置与常量
# ============================================================
class MonitorLevel(Enum):
    STRICT = "strict"      # 严格模式 - 任何可疑行为都报警
    NORMAL = "normal"      # 正常模式 - 仅检测明显违规
    RELAXED = "relaxed"    # 宽松模式 - 只检测严重违规


class ViolationType(Enum):
    FUTURE_DATA = "future_data"          # 使用未来数据
    SIGNAL_TIMING = "signal_timing"      # 信号时点异常
    RETURN_CALC = "return_calc"          # 收益计算异常
    DATA_LEAK = "data_leak"              # 数据泄露


@dataclass
class Violation:
    """违规记录"""
    type: ViolationType
    message: str
    timestamp: datetime
    details: Dict = field(default_factory=dict)
    severity: str = "WARNING"  # ERROR, WARNING, INFO


@dataclass
class PerformanceMetrics:
    """绩效指标"""
    # 基础指标
    total_return: float = 0.0           # 总收益率
    annual_return: float = 0.0          # 年化收益率
    volatility: float = 0.0             # 年化波动率
    max_drawdown: float = 0.0           # 最大回撤
    
    # 风险调整收益
    sharpe_ratio: float = 0.0           # 夏普比率
    sortino_ratio: float = 0.0          # 索提诺比率
    calmar_ratio: float = 0.0           # 卡玛比率
    information_ratio: float = 0.0      # 信息比率
    treynor_ratio: float = 0.0          # 特雷诺比率
    
    # 其他指标
    win_rate: float = 0.0               # 胜率
    profit_factor: float = 0.0          # 盈亏比
    skewness: float = 0.0               # 偏度
    kurtosis: float = 0.0               # 峰度
    var_95: float = 0.0                 # 95% VaR
    cvar_95: float = 0.0                # 95% CVaR
    
    # 合规指标
    violations: List[Violation] = field(default_factory=list)
    compliance_score: float = 100.0     # 合规分数


# ============================================================
# 日志设置
# ============================================================
def setup_logger(name: str = "backtest_monitor") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    if not logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)s | [Monitor] %(message)s",
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    
    return logger


logger = setup_logger()


# ============================================================
# 核心监视器类
# ============================================================
class BacktestMonitor:
    """
    回测监视器
    
    用于监控回测过程中的:
    1. 数据合规性 (防止未来数据)
    2. 信号生成时点
    3. 绩效指标计算
    """
    
    def __init__(self, 
                 risk_free_rate: float = 0.03,
                 benchmark_returns: Optional[pd.Series] = None,
                 monitor_level: MonitorLevel = MonitorLevel.NORMAL):
        """
        初始化监视器
        
        Args:
            risk_free_rate: 无风险利率 (年化)
            benchmark_returns: 基准收益率序列 (用于计算信息比率)
            monitor_level: 监控严格程度
        """
        self.risk_free_rate = risk_free_rate
        self.benchmark_returns = benchmark_returns
        self.monitor_level = monitor_level
        self.violations: List[Violation] = []
        self.metrics = PerformanceMetrics()
        
        # 跟踪数据使用情况
        self.signal_dates: List[date] = []
        self.data_access_log: List[Dict] = []
        
        logger.info("="*60)
        logger.info("回测监视器初始化")
        logger.info(f"监控级别: {monitor_level.value}")
        logger.info(f"无风险利率: {risk_free_rate*100:.2f}%")
        logger.info("="*60)
    
    # ========================================================
    # 1. 未来数据检测
    # ========================================================
    def check_signal_timing(self, 
                           signal_date: date, 
                           data_available_date: date,
                           context: str = "") -> bool:
        """
        检查信号时点是否合规
        
        Args:
            signal_date: 信号生成日期
            data_available_date: 数据可用日期 (应该是T日收盘后)
            context: 上下文说明
            
        Returns:
            bool: 是否合规
        """
        # 信号应该在数据可用之后生成 (T+1)
        if signal_date < data_available_date:
            violation = Violation(
                type=ViolationType.SIGNAL_TIMING,
                message=f"信号日期 {signal_date} 早于数据可用日期 {data_available_date}",
                timestamp=datetime.now(),
                details={
                    "signal_date": str(signal_date),
                    "data_date": str(data_available_date),
                    "context": context
                },
                severity="ERROR"
            )
            self.violations.append(violation)
            logger.error(f"[违规] {violation.message}")
            return False
        
        # 记录信号日期
        self.signal_dates.append(signal_date)
        return True
    
    def check_data_access(self,
                         access_date: date,
                         data_date: date,
                         variable_name: str = "") -> bool:
        """
        检查数据访问是否合规
        
        检测逻辑:
        - 在T日决策时，只能使用T-1日及之前的数据
        - 不能使用T日或之后的数据
        
        Args:
            access_date: 访问数据的日期 (当前回测日期)
            data_date: 被访问数据的日期
            variable_name: 变量名 (用于调试)
            
        Returns:
            bool: 是否合规
        """
        # 记录访问日志
        self.data_access_log.append({
            "access_date": access_date,
            "data_date": data_date,
            "variable": variable_name,
            "timestamp": datetime.now()
        })
        
        # 检查是否使用了未来数据
        if data_date > access_date:
            violation = Violation(
                type=ViolationType.FUTURE_DATA,
                message=f"使用了未来数据! 在{access_date}访问了{data_date}的数据",
                timestamp=datetime.now(),
                details={
                    "access_date": str(access_date),
                    "future_date": str(data_date),
                    "variable": variable_name
                },
                severity="ERROR"
            )
            self.violations.append(violation)
            logger.error(f"[严重违规] {violation.message}")
            
            if self.monitor_level == MonitorLevel.STRICT:
                raise ValueError(f"检测到未来数据使用: {variable_name}")
            return False
        
        # 宽松模式下的警告
        if data_date == access_date and self.monitor_level == MonitorLevel.STRICT:
            # 严格模式下，T日决策不能使用T日数据 (假设是收盘价)
            logger.warning(f"[警告] 在{access_date}使用了当日数据 {variable_name}，"
                          "请确保这不是收盘价数据")
        
        return True
    
    def validate_rolling_window(self,
                               current_date: date,
                               window_data: pd.DataFrame,
                               expected_max_date: date) -> bool:
        """
        验证滚动窗口数据是否合规
        
        Args:
            current_date: 当前回测日期
            window_data: 滚动窗口数据
            expected_max_date: 期望的最大数据日期 (应该是T-1)
            
        Returns:
            bool: 是否合规
        """
        if window_data.empty:
            return True
        
        actual_max_date = window_data.index.max()
        
        if isinstance(actual_max_date, pd.Timestamp):
            actual_max_date = actual_max_date.date()
        
        if actual_max_date > expected_max_date:
            violation = Violation(
                type=ViolationType.DATA_LEAK,
                message=f"滚动窗口包含未来数据! 当前{current_date}, "
                       f"窗口最大日期{actual_max_date}, 期望最大{expected_max_date}",
                timestamp=datetime.now(),
                details={
                    "current_date": str(current_date),
                    "window_max": str(actual_max_date),
                    "expected_max": str(expected_max_date)
                },
                severity="ERROR"
            )
            self.violations.append(violation)
            logger.error(f"[严重违规] {violation.message}")
            return False
        
        return True
    
    # ========================================================
    # 2. 风险调整收益计算
    # ========================================================
    def calculate_metrics(self,
                         returns: pd.Series,
                         positions: Optional[pd.Series] = None,
                         trades: Optional[pd.DataFrame] = None) -> PerformanceMetrics:
        """
        计算完整的绩效指标
        
        Args:
            returns: 日收益率序列 (index为日期)
            positions: 持仓序列 (可选，用于计算持仓分析)
            trades: 交易记录 (可选)
            
        Returns:
            PerformanceMetrics: 绩效指标对象
        """
        logger.info("="*60)
        logger.info("计算风险调整收益指标")
        logger.info("="*60)
        
        if returns.empty:
            logger.warning("收益率序列为空")
            return self.metrics
        
        # 清理数据
        returns = returns.dropna()
        
        # 基础统计
        self.metrics.total_return = (1 + returns).prod() - 1
        n_days = len(returns)
        n_years = n_days / 252
        self.metrics.annual_return = (1 + self.metrics.total_return) ** (1/n_years) - 1 if n_years > 0 else 0
        
        # 波动率
        self.metrics.volatility = returns.std() * np.sqrt(252)
        
        # 下行波动率 (索提诺比率用)
        downside_returns = returns[returns < 0]
        downside_vol = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
        
        # 最大回撤
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        self.metrics.max_drawdown = drawdown.min()
        
        # 夏普比率
        if self.metrics.volatility > 0:
            self.metrics.sharpe_ratio = (self.metrics.annual_return - self.risk_free_rate) / self.metrics.volatility
        
        # 索提诺比率
        if downside_vol > 0:
            self.metrics.sortino_ratio = (self.metrics.annual_return - self.risk_free_rate) / downside_vol
        
        # 卡玛比率
        if self.metrics.max_drawdown < 0:
            self.metrics.calmar_ratio = self.metrics.annual_return / abs(self.metrics.max_drawdown)
        
        # 信息比率 (需要基准)
        if self.benchmark_returns is not None and not self.benchmark_returns.empty:
            self.metrics.information_ratio = self._calculate_information_ratio(returns, self.benchmark_returns)
        
        # 特雷诺比率 (需要Beta，简化计算)
        if self.benchmark_returns is not None and not self.benchmark_returns.empty:
            beta = self._calculate_beta(returns, self.benchmark_returns)
            if beta > 0:
                self.metrics.treynor_ratio = (self.metrics.annual_return - self.risk_free_rate) / beta
        
        # 胜率
        self.metrics.win_rate = (returns > 0).sum() / len(returns)
        
        # 盈亏比
        avg_gain = returns[returns > 0].mean() if (returns > 0).any() else 0
        avg_loss = abs(returns[returns < 0].mean()) if (returns < 0).any() else 1
        self.metrics.profit_factor = avg_gain / avg_loss if avg_loss != 0 else 0
        
        # 分布特征
        self.metrics.skewness = returns.skew()
        self.metrics.kurtosis = returns.kurtosis()
        
        # VaR and CVaR
        self.metrics.var_95 = np.percentile(returns, 5)
        self.metrics.cvar_95 = returns[returns <= self.metrics.var_95].mean()
        
        # 合规分数
        self.metrics.compliance_score = max(0, 100 - len(self.violations) * 10)
        self.metrics.violations = self.violations.copy()
        
        # 输出结果
        self._print_metrics()
        
        return self.metrics
    
    def _calculate_information_ratio(self,
                                    returns: pd.Series,
                                    benchmark: pd.Series) -> float:
        """计算信息比率"""
        # 对齐日期
        aligned_data = pd.concat([returns, benchmark], axis=1).dropna()
        if len(aligned_data) < 30:
            return 0.0
        
        active_returns = aligned_data.iloc[:, 0] - aligned_data.iloc[:, 1]
        tracking_error = active_returns.std() * np.sqrt(252)
        
        if tracking_error > 0:
            return active_returns.mean() * 252 / tracking_error
        return 0.0
    
    def _calculate_beta(self,
                       returns: pd.Series,
                       benchmark: pd.Series) -> float:
        """计算Beta"""
        aligned_data = pd.concat([returns, benchmark], axis=1).dropna()
        if len(aligned_data) < 30:
            return 1.0
        
        covariance = aligned_data.iloc[:, 0].cov(aligned_data.iloc[:, 1])
        benchmark_variance = aligned_data.iloc[:, 1].var()
        
        if benchmark_variance > 0:
            return covariance / benchmark_variance
        return 1.0
    
    def _print_metrics(self):
        """打印绩效指标"""
        m = self.metrics
        
        print("\n" + "="*60)
        print("风险调整收益指标报告")
        print("="*60)
        
        print("\n【基础指标】")
        print(f"  总收益率:      {m.total_return*100:>10.2f}%")
        print(f"  年化收益率:    {m.annual_return*100:>10.2f}%")
        print(f"  年化波动率:    {m.volatility*100:>10.2f}%")
        print(f"  最大回撤:      {m.max_drawdown*100:>10.2f}%")
        
        print("\n【风险调整收益】")
        print(f"  夏普比率:      {m.sharpe_ratio:>10.2f}  {'优秀' if m.sharpe_ratio > 1 else '良好' if m.sharpe_ratio > 0.5 else '一般'}")
        print(f"  索提诺比率:    {m.sortino_ratio:>10.2f}  {'优秀' if m.sortino_ratio > 2 else '良好' if m.sortino_ratio > 1 else '一般'}")
        print(f"  卡玛比率:      {m.calmar_ratio:>10.2f}  {'优秀' if m.calmar_ratio > 2 else '良好' if m.calmar_ratio > 1 else '一般'}")
        print(f"  信息比率:      {m.information_ratio:>10.2f}  {'优秀' if m.information_ratio > 0.5 else '良好' if m.information_ratio > 0 else '一般'}")
        print(f"  特雷诺比率:    {m.treynor_ratio:>10.2f}")
        
        print("\n【其他指标】")
        print(f"  胜率:          {m.win_rate*100:>10.1f}%")
        print(f"  盈亏比:        {m.profit_factor:>10.2f}")
        print(f"  收益偏度:      {m.skewness:>10.2f}")
        print(f"  收益峰度:      {m.kurtosis:>10.2f}")
        print(f"  VaR (95%):     {m.var_95*100:>10.2f}%")
        print(f"  CVaR (95%):    {m.cvar_95*100:>10.2f}%")
        
        print("\n【合规检查】")
        print(f"  合规分数:      {m.compliance_score:>10.1f}/100")
        print(f"  违规次数:      {len(m.violations):>10} 次")
        
        if m.violations:
            print("\n  违规详情:")
            for i, v in enumerate(m.violations[:5], 1):
                print(f"    {i}. [{v.severity}] {v.type.value}: {v.message}")
        
        print("="*60)
    
    # ========================================================
    # 3. 报告生成
    # ========================================================
    def generate_report(self, output_path: str = None) -> str:
        """生成详细监控报告"""
        output_path = output_path or f"monitor_report_{date.today().isoformat()}.json"
        
        report = {
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "monitor_level": self.monitor_level.value,
                "risk_free_rate": self.risk_free_rate
            },
            "compliance": {
                "score": self.metrics.compliance_score,
                "violations_count": len(self.violations),
                "violations": [
                    {
                        "type": v.type.value,
                        "message": v.message,
                        "severity": v.severity,
                        "timestamp": v.timestamp.isoformat(),
                        "details": v.details
                    }
                    for v in self.violations
                ]
            },
            "metrics": {
                "total_return": self.metrics.total_return,
                "annual_return": self.metrics.annual_return,
                "volatility": self.metrics.volatility,
                "max_drawdown": self.metrics.max_drawdown,
                "sharpe_ratio": self.metrics.sharpe_ratio,
                "sortino_ratio": self.metrics.sortino_ratio,
                "calmar_ratio": self.metrics.calmar_ratio,
                "information_ratio": self.metrics.information_ratio,
                "treynor_ratio": self.metrics.treynor_ratio,
                "win_rate": self.metrics.win_rate,
                "profit_factor": self.metrics.profit_factor,
                "var_95": self.metrics.var_95,
                "cvar_95": self.metrics.cvar_95
            }
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"监控报告已保存: {output_path}")
        return output_path


# ============================================================
# 装饰器 - 便于集成到现有策略
# ============================================================
def monitored_backtest(func: Callable) -> Callable:
    """
    回测监控装饰器
    
    使用方法:
        @monitored_backtest
        def my_backtest():
            # 回测逻辑
            pass
    """
    def wrapper(*args, **kwargs):
        monitor = BacktestMonitor()
        
        try:
            result = func(*args, monitor=monitor, **kwargs)
            return result, monitor
        except Exception as e:
            logger.error(f"回测执行失败: {e}")
            logger.error(traceback.format_exc())
            raise
    
    return wrapper


# ============================================================
# 使用示例与测试
# ============================================================
def demo_usage():
    """演示如何使用监视器"""
    print("="*60)
    print("BacktestMonitor 使用演示")
    print("="*60)
    
    # 创建监视器
    monitor = BacktestMonitor(
        risk_free_rate=0.03,
        monitor_level=MonitorLevel.NORMAL
    )
    
    # 模拟回测数据
    np.random.seed(42)
    dates = pd.date_range('2020-01-01', '2023-12-31', freq='B')
    returns = pd.Series(np.random.normal(0.0005, 0.02, len(dates)), index=dates)
    
    # 模拟未来数据违规检测
    print("\n测试1: 检测未来数据违规")
    today = date(2023, 6, 1)
    future_date = date(2023, 6, 5)  # 未来日期
    monitor.check_data_access(today, future_date, "test_price")
    
    # 正常数据访问
    print("\n测试2: 正常数据访问")
    past_date = date(2023, 5, 30)  # 过去日期
    monitor.check_data_access(today, past_date, "valid_price")
    
    # 计算绩效指标
    print("\n测试3: 计算绩效指标")
    metrics = monitor.calculate_metrics(returns)
    
    # 生成报告
    print("\n测试4: 生成监控报告")
    report_path = monitor.generate_report("demo_monitor_report.json")
    
    print("\n" + "="*60)
    print("演示完成")
    print(f"报告路径: {report_path}")
    print("="*60)


if __name__ == "__main__":
    demo_usage()
