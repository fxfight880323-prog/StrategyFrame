# 回测监视器使用指南

## 概述

`BacktestMonitor` 是一个通用的回测监控工具，用于：

1. **检测未来数据泄露** (Look-ahead Bias Detection)
2. **计算风险调整收益指标** (Sharpe, Calmar, Information Ratio等)
3. **生成合规报告**
4. **监控回测过程合规性**

## 核心功能

### 1. 未来数据检测

```python
# 检查数据访问是否合规
monitor.check_data_access(
    access_date=current_date,      # 当前回测日期
    data_date=price_date,          # 被访问数据的日期
    variable_name="close_price"    # 变量名
)

# 检查信号时点
monitor.check_signal_timing(
    signal_date=signal_date,
    data_available_date=data_end_date,
    context="CTA信号生成"
)

# 验证滚动窗口
monitor.validate_rolling_window(
    current_date=current_date,
    window_data=rolling_data,
    expected_max_date=current_date - timedelta(days=1)
)
```

### 2. 风险调整收益计算

```python
# 计算完整绩效指标
metrics = monitor.calculate_metrics(
    returns=daily_returns_series,    # 日收益率序列
    positions=positions_series,      # 持仓序列（可选）
    trades=trades_df                 # 交易记录（可选）
)

# 输出指标
print(f"夏普比率: {metrics.sharpe_ratio:.2f}")
print(f"卡玛比率: {metrics.calmar_ratio:.2f}")
print(f"信息比率: {metrics.information_ratio:.2f}")
```

### 3. 生成监控报告

```python
report_path = monitor.generate_report("monitor_report.json")
```

## 监控指标说明

### 基础指标

| 指标 | 说明 | 计算公式 |
|------|------|----------|
| 总收益率 | 回测期总收益 | (期末价值/期初价值) - 1 |
| 年化收益率 | 复合年化收益 | (1+总收益率)^(252/天数) - 1 |
| 年化波动率 | 收益波动程度 | std(日收益) × √252 |
| 最大回撤 | 峰值到谷底最大亏损 | max((峰值-当前)/峰值) |

### 风险调整收益指标

| 指标 | 说明 | 优秀标准 | 计算公式 |
|------|------|----------|----------|
| **夏普比率** | 单位总风险超额收益 | >1.0 | (年化收益-无风险利率)/年化波动率 |
| **索提诺比率** | 单位下行风险超额收益 | >2.0 | (年化收益-无风险利率)/下行波动率 |
| **卡玛比率** | 单位最大回撤超额收益 | >2.0 | 年化收益/|最大回撤| |
| **信息比率** | 相对基准的超额收益 | >0.5 | 年化超额收益/跟踪误差 |
| **特雷诺比率** | 单位系统风险超额收益 | >0.1 | (年化收益-无风险利率)/Beta |

### 其他指标

| 指标 | 说明 |
|------|------|
| 胜率 | 盈利交易次数/总交易次数 |
| 盈亏比 | 平均盈利/平均亏损 |
| 偏度 | 收益分布不对称性 |
| 峰度 | 收益分布尾部厚度 |
| VaR (95%) | 95%置信度下的最大损失 |
| CVaR (95%) | 超过VaR的平均损失 |

## 在各策略中的集成

### 1. CTA_FLP_Strategy

```python
# 使用集成版本
from CTA_FLP_Strategy_Monitored import MonitoredCTAFLPBacktester

backtester = MonitoredCTAFLPBacktester(
    initial_capital=1_000_000,
    risk_free_rate=0.03
)

results = backtester.run_backtest(
    price_data=price_data,
    vix_data=vix_data,
    start_date=start_date,
    end_date=end_date
)

# 自动输出监控报告
```

### 2. PatternStrategy_A500

```python
# 使用集成版本
from A500_Pattern_Analyzer_Monitored import MonitoredPatternAnalyzer

analyzer = MonitoredPatternAnalyzer()
results_df, metrics = analyzer.batch_analyze_with_monitor(
    components,
    max_stocks=100
)

# 输出监控报告和绩效指标
```

### 3. CTA纯策略

```python
# 使用集成版本
from run_backtest_cta_only_monitored import run_cta_backtest_monitored
from BacktestMonitor import BacktestMonitor

monitor = BacktestMonitor(risk_free_rate=0.05)

results_df, trades_df = run_cta_backtest_monitored(
    price_data, start_date, end_date, monitor
)
```

## 监控级别设置

```python
from BacktestMonitor import BacktestMonitor, MonitorLevel

# 严格模式 - 任何可疑行为都报警
monitor = BacktestMonitor(monitor_level=MonitorLevel.STRICT)

# 正常模式 - 仅检测明显违规 (默认)
monitor = BacktestMonitor(monitor_level=MonitorLevel.NORMAL)

# 宽松模式 - 只检测严重违规
monitor = BacktestMonitor(monitor_level=MonitorLevel.RELAXED)
```

## 输出报告格式

### JSON报告示例

```json
{
  "metadata": {
    "generated_at": "2026-03-03T14:30:00",
    "monitor_level": "strict",
    "risk_free_rate": 0.03
  },
  "compliance": {
    "score": 95.0,
    "violations_count": 0,
    "violations": []
  },
  "metrics": {
    "total_return": 0.158,
    "annual_return": 0.052,
    "volatility": 0.12,
    "max_drawdown": -0.08,
    "sharpe_ratio": 0.43,
    "sortino_ratio": 0.65,
    "calmar_ratio": 0.65,
    "information_ratio": 0.32,
    "treynor_ratio": 0.08,
    "win_rate": 0.52,
    "profit_factor": 1.25,
    "var_95": -0.015,
    "cvar_95": -0.022
  }
}
```

## 常见违规类型

### 1. 未来数据使用 (FUTURE_DATA)

**描述**: 在T日决策时使用了T+1或之后的数据

**示例**:
```python
# 违规 - 使用当日收盘价生成信号
today = date(2024, 1, 10)
signal = df.loc[today, 'close'] > df.loc[today, 'ma20']  # 使用收盘价

# 合规 - 使用昨日收盘价
today = date(2024, 1, 10)
yesterday = date(2024, 1, 9)
signal = df.loc[yesterday, 'close'] > df.loc[yesterday, 'ma20']
```

### 2. 信号时点异常 (SIGNAL_TIMING)

**描述**: 信号生成日期早于数据可用日期

### 3. 收益计算异常 (RETURN_CALC)

**描述**: 收益计算使用了未来价格

### 4. 数据泄露 (DATA_LEAK)

**描述**: 滚动窗口包含未来数据

## 最佳实践

### 1. 在策略初始化时创建监视器

```python
def __init__(self):
    self.monitor = BacktestMonitor(
        risk_free_rate=0.03,
        benchmark_returns=spy_returns,  # 可选，用于计算信息比率
        monitor_level=MonitorLevel.NORMAL
    )
```

### 2. 在关键节点添加检查

```python
# 数据获取时
monitor.check_data_access(current_date, data_date, "price")

# 信号生成时
monitor.check_signal_timing(signal_date, data_end_date, "signal")

# 滚动窗口计算时
monitor.validate_rolling_window(current_date, window_data, max_allowed_date)
```

### 3. 回测结束后生成报告

```python
# 计算绩效指标
metrics = monitor.calculate_metrics(returns_series)

# 生成报告
report_path = monitor.generate_report()

# 检查合规分数
if metrics.compliance_score < 80:
    print("警告: 合规分数低于80，请检查策略逻辑")
```

## 故障排查

### 问题1: 频繁的未来数据警告

**原因**: 可能是在循环中错误地使用了当前日期数据

**解决**: 
```python
# 错误
for date in dates:
    signal = df.loc[date, 'close']  # 使用当日数据

# 正确
for i, date in enumerate(dates):
    if i == 0:
        continue
    prev_date = dates[i-1]
    signal = df.loc[prev_date, 'close']  # 使用前一日数据
```

### 问题2: 夏普比率为无穷大

**原因**: 波动率为0（所有日收益相同）

**解决**: 检查数据是否有足够的变化

### 问题3: 信息比率为0

**原因**: 未提供基准收益率

**解决**:
```python
monitor = BacktestMonitor(
    benchmark_returns=spy_daily_returns  # 提供基准
)
```

## 依赖安装

```bash
pip install pandas numpy
```

## 更新日志

- **2026-03-03**: 初始版本发布
  - 未来数据检测功能
  - 风险调整收益计算
  - 多策略集成支持
