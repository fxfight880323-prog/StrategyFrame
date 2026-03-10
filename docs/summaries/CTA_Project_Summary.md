# CTA策略研究与实施项目总结

## 项目概述

本项目完成了从热门CTA策略论文研究到实际复现、评估、风控的完整流程。

---

## 一、复现的CTA策略

### 1. 时间序列动量 (TSMOM)
**来源**: Moskowitz et al. (2012), Ming et al. (2023)

**核心逻辑**:
```python
# 1个月回看期收益为正 → 做多
# 1个月回看期收益为负 → 做空
Position Size ∝ (Past Return / Volatility)
```

**参数**:
- 回看期: 20个交易日 (约1个月)
- 持有期: 20个交易日
- 目标波动率: 10%年化
- 波动率调整: 使用指数加权标准差

**特点**:
- 中国市场1个月回看期效果最佳
- 盈利主要来自空头头寸
- 需要波动率调整以控制风险

---

### 2. 趋势跟踪 (Trend Following)
**来源**: Man Group (2025) "A Trend Following Deep Dive"

**核心逻辑**:
```python
# MA交叉 + 通道突破确认
Long:  Fast MA > Slow MA AND Close > Upper Channel
Short: Fast MA < Slow MA AND Close < Lower Channel
```

**参数**:
- 快速MA: 20日
- 慢速MA: 60日
- 通道周期: 20日
- ATR倍数: 2.0

**特点**:
- 多时间框架验证 (短、中、长期)
- 波动率倒数加权仓位
- 适合捕捉中期趋势

---

### 3. Carry策略
**来源**: ReSolve Asset Management (2024)

**核心逻辑**:
```python
# Backwardation (远月<近月) → 做多
# Contango (远月>近月) → 做空
Carry = (Near Price - Far Price) / Far Price
```

**特点**:
- 基于期货期限结构
- 与趋势策略低相关性
- 适合震荡市场

---

### 4. 元模型动态分配
**来源**: Mandatum Asset Management (2025)

**核心逻辑**:
```python
# 根据市场环境动态调整策略权重
if 高波动市场:
    减少Carry权重, 增加趋势权重
elif 强趋势市场:
    增加中期趋势权重
elif 震荡市场:
    增加Carry权重, 减少趋势权重
```

**状态识别**:
- 高波动状态
- 趋势状态
- 震荡状态
- 危机状态

---

## 二、策略评估指标体系

### 收益指标
| 指标 | 说明 | 优秀标准 |
|------|------|----------|
| 总收益率 | 累计收益 | >30% (5年) |
| 年化收益率 | CAGR | >8% |
| 年化波动率 | 风险水平 | <15% |

### 风险调整后收益
| 指标 | 公式 | 优秀标准 |
|------|------|----------|
| **Sharpe Ratio** | (R - Rf) / σ | >1.0 |
| **Sortino Ratio** | (R - Rf) / σ_down | >1.5 |
| **Information Ratio** | α / Tracking Error | >0.5 |
| **Calmar Ratio** | CAGR / Max DD | >1.0 |
| **Serenity Ratio** | CAGR / √(MaxDD² + Pain²) | >1.0 |

### CTA特有指标
| 指标 | 说明 | 优秀标准 |
|------|------|----------|
| 胜率 | 盈利交易比例 | >40% |
| 盈亏比 | 平均盈利/平均亏损 | >2.0 |
| 偏度 | 收益分布 | >0 (正偏) |
| 危机Alpha | 市场下跌时表现 | 正收益 |

---

## 三、风控系统架构

### 1. 事前风控 (Pre-trade)
```python
检查项:
- 单品种仓位 ≤ 10%
- 板块集中度 ≤ 30%
- 总杠杆 ≤ 2倍
- 订单量/成交量 ≤ 5%
- 交易频率控制
```

### 2. 仓位管理
```python
# 波动率目标法
Position Size = Target Vol / (Asset Vol × √Correlation)

# 风险平价
Weight ∝ 1 / Volatility

# 动态调整
Position = Base Position × Vol Adjustment × Regime Adjustment
```

### 3. 止损止盈
```python
# 固定止损
Stop Loss = Entry × (1 - 3%)
Take Profit = Entry × (1 + 6%)  # 1:2 盈亏比

# ATR止损
Stop Loss = Entry - 2 × ATR

# 移动止损
Trailing Stop = Highest Price × (1 - 5%)

# 时间止损
Max Hold Days = 20
```

### 4. 实时监控
```python
风险等级:
- GREEN:  所有指标正常
- YELLOW: 某项指标接近限制
- ORANGE: 某项指标触及限制
- RED:    多项指标超限,需减仓
```

---

## 四、国内期货实施要点

### 数据获取
```python
# 推荐数据源
1. AKShare (免费) - stock_us_daily, futures_zh_daily
2. Tushare Pro - 期货主力合约
3. 米筐(RiceQuant) - 专业级期货数据
4. 聚宽(JoinQuant) - 量化平台
```

### 合约选择
```python
# 主要交易品种
商品期货 = {
    '黑色': ['RB', 'HC', 'I', 'J', 'JM'],
    '有色': ['CU', 'AL', 'ZN', 'NI', 'AU', 'AG'],
    '能源': ['SC', 'LU'],
    '化工': ['TA', 'MA', 'PP', 'L'],
    '农产品': ['M', 'RM', 'OI', 'CF', 'SR'],
}

金融期货 = {
    '股指': ['IF', 'IC', 'IM'],
    '国债': ['T', 'TF', 'TS'],
}
```

### 特殊考虑
1. **夜盘交易**: 信号计算需考虑连续性
2. **涨跌停板**: 处理价格不连续
3. **合约换月**: 主力合约连续化处理
4. **保证金变化**: 节假日调整
5. **交易费用**: 手续费、滑点

---

## 五、回测结果示例

### 单一策略表现
| 策略 | 年化收益 | 波动率 | 夏普 | 最大回撤 | 信息比率 |
|------|----------|--------|------|----------|----------|
| TSMOM | 12% | 12% | 0.75 | -15% | 0.45 |
| Trend | 10% | 10% | 0.70 | -12% | 0.40 |
| Carry | 8% | 8% | 0.63 | -8% | 0.30 |

### 组合策略表现
| 组合 | 年化收益 | 波动率 | 夏普 | 最大回撤 | Serenity |
|------|----------|--------|------|----------|----------|
| 等权组合 | 10% | 8% | 0.88 | -10% | 1.00 |
| 元模型组合 | 11% | 8% | 1.00 | -9% | 1.22 |

---

## 六、使用指南

### 快速开始
```bash
# 1. 安装依赖
pip install pandas numpy scipy

# 2. 运行演示
python CTA_Integrated_Backtest_Demo.py
```

### 自定义策略
```python
from CTA_Strategies_CN_Futures import CTAStrategy, Signal

class MyStrategy(CTAStrategy):
    def generate_signals(self, data, current_date):
        # 实现你的策略逻辑
        signals = []
        # ...
        return signals
```

### 接入真实数据
```python
from CTA_Strategies_CN_Futures import FuturesDataProvider

class RealDataProvider(FuturesDataProvider):
    def get_futures_data(self, symbol, start_date, end_date):
        # 接入你的数据源
        df = your_data_api.get_data(symbol, start_date, end_date)
        return df
```

---

## 七、文件说明

| 文件 | 说明 |
|------|------|
| `CTA_Strategies_Research_Summary.md` | 策略论文综述 |
| `CTA_Strategies_CN_Futures.py` | 策略复现代码 |
| `CTA_Strategy_Evaluator.py` | 策略评估系统 |
| `CTA_Portfolio_Risk_System.py` | 组合风控系统 |
| `CTA_Integrated_Backtest_Demo.py` | 整合回测演示 |
| `CTA_Project_Summary.md` | 项目总结 (本文件) |

---

## 八、参考文献

1. Moskowitz, T. J., & Grinblatt, M. (2012). Time series momentum. *Journal of Financial Economics*.
2. Hurst, B., Ooi, Y. H., & Pedersen, L. H. (2017). A century of evidence on trend-following investing. *The Journal of Portfolio Management*.
3. Ming, L., et al. (2023). Revisiting time series momentum in China's commodity futures market. *Economic Modelling*.
4. Man Group. (2025). A Trend Following Deep Dive: The Optimal Market Mix.
5. ReSolve Asset Management. (2024). Managed Futures Carry: A Practitioner's Guide.
6. Mandatum Asset Management. (2025). Meta-Models in Practice.

---

## 九、后续优化方向

1. **数据层面**
   - 接入更多品种数据
   - 获取tick级别数据用于回测优化
   - 加入基本面数据

2. **策略层面**
   - 加入机器学习信号筛选
   - 优化参数 (Walk-forward优化)
   - 开发更多策略变体

3. **风控层面**
   - 实现更精细的压力测试
   - 加入尾部风险对冲
   - 开发实时监控Dashboard

4. **执行层面**
   - 优化订单执行算法
   - 减少滑点和冲击成本
   - 接入实盘交易接口

---

**项目完成日期**: 2026-02-28  
**版本**: 1.0
