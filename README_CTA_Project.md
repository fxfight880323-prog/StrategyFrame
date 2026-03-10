# CTA策略研究与实施项目

## 项目简介

本项目完成了从热门CTA策略论文研究到实际复现、评估、风控的完整流程，专门针对**中国期货市场**进行优化。

## 核心功能

```
┌─────────────────────────────────────────────────────────────────┐
│                      CTA策略研究与实施项目                        │
├─────────────────────────────────────────────────────────────────┤
│  Phase 1: 策略研究                                               │
│  ├── 时间序列动量 (TSMOM) - Moskowitz et al. 2012               │
│  ├── 趋势跟踪 (Trend Following) - Man Group 2025                │
│  ├── Carry策略 - ReSolve 2024                                    │
│  └── 元模型动态分配 - Mandatum 2025                             │
├─────────────────────────────────────────────────────────────────┤
│  Phase 2: 策略复现 (国内期货版本)                                 │
│  ├── CTA_Strategies_CN_Futures.py                               │
│  │   ├── MockFuturesDataProvider (模拟数据)                     │
│  │   ├── TSMOMStrategy (时间序列动量)                           │
│  │   ├── TrendFollowingStrategy (趋势跟踪)                      │
│  │   ├── CarryStrategy (Carry策略)                              │
│  │   └── MetaModelAllocator (元模型分配)                        │
├─────────────────────────────────────────────────────────────────┤
│  Phase 3: 策略评估系统                                           │
│  ├── CTA_Strategy_Evaluator.py                                  │
│  │   ├── PerformanceMetrics (绩效指标数据类)                    │
│  │   ├── CTAEvaluator (评估器)                                  │
│  │   │   ├── Sharpe Ratio (夏普比率)                            │
│  │   │   ├── Sortino Ratio (索提诺比率)                         │
│  │   │   ├── Information Ratio (信息比率) ⭐                     │
│  │   │   ├── Calmar Ratio (卡玛比率)                            │
│  │   │   ├── Serenity Ratio (Serenity比率)                      │
│  │   │   └── Alpha/Beta归因分析                                 │
│  │   └── StressTester (压力测试)                                │
├─────────────────────────────────────────────────────────────────┤
│  Phase 4: 组合风控系统                                           │
│  ├── CTA_Portfolio_Risk_System.py                               │
│  │   ├── PreTradeRiskManager (事前风控)                         │
│  │   │   ├── 单品种仓位限制                                     │
│  │   │   ├── 板块集中度限制                                     │
│  │   │   ├── 总仓位限制                                         │
│  │   │   └── 流动性检查                                         │
│  │   ├── PositionSizer (仓位管理)                               │
│  │   │   ├── 波动率目标法                                       │
│  │   │   ├── 风险平价                                           │
│  │   │   └── 动态仓位调整                                       │
│  │   ├── StopLossManager (止损止盈)                             │
│  │   │   ├── 固定止损                                           │
│  │   │   ├── ATR止损                                            │
│  │   │   ├── 移动止损                                           │
│  │   │   └── 时间止损                                           │
│  │   └── PortfolioRiskMonitor (组合监控)                        │
├─────────────────────────────────────────────────────────────────┤
│  Phase 5: 整合回测                                               │
│  └── CTA_Integrated_Backtest_Demo.py                            │
│      ├── 单一策略回测                                           │
│      ├── 多策略组合回测                                         │
│      ├── 元模型动态分配回测                                     │
│      └── 完整绩效报告                                           │
└─────────────────────────────────────────────────────────────────┘
```

## 文件说明

| 文件 | 说明 | 核心功能 |
|------|------|----------|
| `CTA_Strategies_Research_Summary.md` | 策略论文综述 | 汇总2024-2025年最热门的CTA策略论文 |
| `CTA_Strategies_CN_Futures.py` | 策略复现代码 | 4种核心CTA策略的Python实现 |
| `CTA_Strategy_Evaluator.py` | 策略评估系统 | 完整的绩效评估指标(含Information Ratio) |
| `CTA_Portfolio_Risk_System.py` | 组合风控系统 | 事前/事中/事后三层风控体系 |
| `CTA_Integrated_Backtest_Demo.py` | 整合回测演示 | 完整的回测框架和报告生成 |
| `CTA_Project_Summary.md` | 项目总结 | 详细的使用指南和优化建议 |
| `README_CTA_Project.md` | 本文件 | 项目概览和快速开始 |

## 快速开始

### 环境要求
```bash
Python 3.8+
pandas
numpy
scipy
```

### 安装依赖
```bash
pip install pandas numpy scipy
```

### 运行演示
```bash
# 运行策略评估演示
python CTA_Strategy_Evaluator.py

# 运行风控系统演示
python CTA_Portfolio_Risk_System.py

# 运行完整回测
python CTA_Integrated_Backtest_Demo.py
```

## 策略详解

### 1. 时间序列动量 (TSMOM)

**论文来源**: Moskowitz et al. (2012), Ming et al. (2023)

**核心逻辑**:
```python
# 1个月回看期
past_return = Price[t] / Price[t-20] - 1

# 波动率调整
volatility = returns.rolling(60).std() * sqrt(252)
position = (past_return / volatility) * target_vol

# 信号
if past_return > 0: Long
if past_return < 0: Short
```

**参数**:
- 回看期: 20日
- 持有期: 20日
- 目标波动率: 10%

### 2. 趋势跟踪 (Trend Following)

**论文来源**: Man Group (2025)

**核心逻辑**:
```python
# MA交叉 + 通道突破
Fast MA = MA(Close, 20)
Slow MA = MA(Close, 60)
Upper Channel = Fast MA + 2 * ATR(20)
Lower Channel = Fast MA - 2 * ATR(20)

# 综合信号
Long:  Fast MA > Slow MA AND Close > Upper Channel
Short: Fast MA < Slow MA AND Close < Lower Channel
```

### 3. Carry策略

**论文来源**: ReSolve Asset Management (2024)

**核心逻辑**:
```python
# 基于期货期限结构
Carry = (Near Price - Far Price) / Far Price

# 信号
Backwardation (Carry > 0) → Long
Contango (Carry < 0) → Short
```

### 4. 元模型动态分配

**论文来源**: Mandatum Asset Management (2025)

**核心逻辑**:
```python
# 检测市场环境
regime = detect_regime(market_data)

# 动态调整权重
if regime == HIGH_VOL:
    increase_trend_weight()
    decrease_carry_weight()
elif regime == TRENDING:
    increase_trend_weight()
elif regime == RANGE_BOUND:
    increase_carry_weight()
```

## 评估指标

### 风险调整后收益指标

| 指标 | 优秀标准 | 说明 |
|------|----------|------|
| **Sharpe Ratio** | >1.0 | (收益-无风险利率)/波动率 |
| **Sortino Ratio** | >1.5 | (收益-无风险利率)/下行波动率 |
| **Information Ratio** | >0.5 | Alpha/跟踪误差 |
| **Calmar Ratio** | >1.0 | 年化收益/最大回撤 |
| **Serenity Ratio** | >1.0 | CAGR/√(最大回撤²+Pain指数²) |

### 示例输出

```
======================================================================
CTA策略绩效评估报告 - TSMOM_策略
======================================================================
回测区间: 2020-01-01 ~ 2024-12-31
交易天数: 1305天 (约5.2年)

【收益指标】
  总收益率:         6400.95%
  年化收益率:       123.92%
  CAGR:             123.92%

【风险指标】
  年化波动率:       24.03%
  最大回撤:         -12.76%
  VaR (95%):        -1.83%

【风险调整后收益】
  夏普比率:         5.032
  索提诺比率:       11.148
  信息比率:         2.370  ⭐
  卡玛比率:         9.711
  Serenity比率:     9.528

【基准归因】
  Beta:             0.003
  年化Alpha:        83.60%
  相关性:           0.003
```

## 风控系统

### 事前风控检查

```python
# 创建风控系统
risk_system = CTARiskManagementSystem()

# 检查订单
result = risk_system.check_and_size_order(
    symbol='RB',
    signal_strength=0.8,
    expected_return=0.10,
    volatility=0.20,
    current_portfolio=portfolio,
    total_capital=1_000_000
)

# 输出结果
{
    'can_trade': True,
    'recommended_position': 0.25,  # 25%仓位
    'stop_loss': 3360.0,
    'take_profit': 3720.0,
    'risk_checks': [...]
}
```

### 风险控制限制

| 限制项 | 限制值 | 说明 |
|--------|--------|------|
| 单品种仓位 | ≤10% | 分散风险 |
| 板块集中度 | ≤30% | 避免板块风险 |
| 总杠杆 | ≤2倍 | 控制总体风险 |
| 保证金使用 | ≤70% | 保留安全垫 |
| 组合波动率 | ≤15% | 目标波动率 |

## 国内期货实施

### 支持品种

```python
# 商品期货
商品期货 = {
    '黑色': ['RB', 'HC', 'I', 'J', 'JM'],
    '有色': ['CU', 'AL', 'ZN', 'NI', 'AU', 'AG'],
    '能源': ['SC', 'LU'],
    '化工': ['TA', 'MA', 'PP', 'L'],
    '农产品': ['M', 'RM', 'OI', 'CF', 'SR'],
}

# 金融期货
金融期货 = {
    '股指': ['IF', 'IC', 'IM'],
    '国债': ['T', 'TF', 'TS'],
}
```

### 数据接入

```python
# 模拟数据 (内置)
provider = MockFuturesDataProvider()

# 接入真实数据 (需要自行实现)
class RealDataProvider(FuturesDataProvider):
    def get_futures_data(self, symbol, start_date, end_date):
        # 接入米筐、聚宽、Tushare等
        df = your_api.get_data(symbol, start_date, end_date)
        return df
```

## 自定义策略

```python
from CTA_Strategies_CN_Futures import CTAStrategy, Signal

class MyCustomStrategy(CTAStrategy):
    def __init__(self):
        super().__init__("MyStrategy", {})
    
    def generate_signals(self, data, current_date):
        signals = []
        
        for symbol, df in data.items():
            # 你的策略逻辑
            df = self.calculate_indicators(df)
            latest = df.iloc[-1]
            
            # 生成信号
            if your_condition:
                signal = Signal.LONG
            else:
                signal = Signal.FLAT
            
            signals.append(StrategySignal(
                symbol=symbol,
                date=current_date,
                signal=signal,
                strength=0.8,
                target_position=0.5,
                expected_return=0.1,
                volatility=0.2
            ))
        
        return signals
```

## 参考文献

1. **Moskowitz, T. J., & Grinblatt, M. (2012)**. Time series momentum. *Journal of Financial Economics*.
2. **Hurst, B., Ooi, Y. H., & Pedersen, L. H. (2017)**. A century of evidence on trend-following investing.
3. **Ming, L., et al. (2023)**. Revisiting time series momentum in China's commodity futures market.
4. **Man Group (2025)**. A Trend Following Deep Dive: The Optimal Market Mix.
5. **ReSolve Asset Management (2024)**. Managed Futures Carry: A Practitioner's Guide.
6. **Mandatum Asset Management (2025)**. Meta-Models in Practice.

## 许可证

MIT License

## 联系方式

如有问题或建议，欢迎提出Issue或Pull Request。

---

**项目完成日期**: 2026-02-28  
**版本**: 1.0
