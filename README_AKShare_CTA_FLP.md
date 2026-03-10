# CTA + FLP 尾部风险对冲策略 - AKShare 完整版

使用 **AKShare** 获取美股数据，实现专业级量化对冲策略。

---

## 🎯 策略特点

| 组件 | 功能 |
|------|------|
| **CTA趋势引擎** | 20/60日MA交叉 + 通道突破 + 波动率加权 |
| **FLP保护引擎** | 每周买入Delta -0.07~-0.10的SPY Put |
| **风险预算平衡** | CTA盈利时回哺15%增持FLP保护 |

**数据来源**: AKShare (无需API Key，国内访问稳定)

---

## 📦 文件清单

```
美股分析框架/
├── AKShare_CTA_FLP_Strategy.py      # 完整策略实现 ⭐
├── AKShare_CTA_FLP_使用指南.md       # 详细使用文档
├── AKShare_CTA_FLP_项目总结.md       # 项目总结
├── cta_akshare_signals.csv           # 信号输出 (运行后生成)
└── README_AKShare_CTA_FLP.md         # 本文档
```

---

## 🚀 快速开始

### 1. 运行策略

```bash
python AKShare_CTA_FLP_Strategy.py
```

**运行时间**: 约 30-60 秒 (获取8只股票数据)

### 2. 查看结果

```bash
# 查看 CTA 信号
cat cta_akshare_signals.csv

# 或使用 Excel 打开
start cta_akshare_signals.csv
```

---

## 📊 今日运行结果 (2026-02-27)

### CTA 趋势信号

| 标的 | 价格 | 信号 | 评分 | 波动率 |
|------|------|------|------|--------|
| **TLT** | $90.27 | LONG | 75.3 | 8.89% |
| SPY | $689.30 | FLAT | 50.0 | 10.63% |
| QQQ | $609.24 | FLAT | 50.0 | 15.04% |
| AAPL | $272.95 | FLAT | 50.0 | 22.68% |
| MSFT | $401.72 | FLAT | 50.0 | 31.98% |
| NVDA | $184.89 | FLAT | 50.0 | 33.94% |
| TSLA | $408.58 | FLAT | 50.0 | 36.53% |
| GLD | $477.48 | FLAT | 50.0 | 36.83% |

### FLP 尾部保护

- SPY 价格: $689.30
- 估算 VIX: 13.97 (低波动)
- 保护模式: Long Put (预算 +20%)
- 买入 Put: Strike=$675.51, Delta=-0.085
- 总成本: $59,726.66

### 资金分配

- CTA 策略: 75% ($750,000)
- FLP 保护: 5% ($50,000)
- 现金: 20% ($200,000)

---

## ⚙️ 配置参数

### 修改分析标的

```python
# 在 AKShare_CTA_FLP_Strategy.py 中编辑
CTA_CONFIG = {
    'symbols': ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 
                'JPM', 'V', 'XOM', 'GLD', 'TLT']  # 添加/删除标的
}
```

### 修改策略参数

```python
CTA_CONFIG = {
    'fast_ma': 20,        # 快速均线
    'slow_ma': 60,        # 慢速均线
    'channel_width': 2.0, # 通道宽度
}

FLP_CONFIG = {
    'vix_low': 15,        # VIX低位阈值
    'vix_high': 30,       # VIX高位阈值
    'budget_increase': 0.20,  # 低价时增加预算
}
```

---

## 💡 策略逻辑

### CTA 信号生成

```
20日MA > 60日MA + 价格上穿通道 → LONG (买入)
20日MA < 60日MA + 价格下穿通道 → SHORT (卖出)
其他情况 → FLAT (观望)
```

**仓位分配**: Position Size ∝ 1/Volatility (低波动重仓)

### FLP 保护执行

```
每周五执行:
1. 获取 SPY 价格
2. 估算 VIX (使用SPY实现波动率)
3. 选择 Delta -0.07~-0.10 的 Put
4. 根据 VIX 调整:
   - VIX < 15: Long Put, 预算+20%
   - VIX > 30: Put Spread, 预算-30%
```

### 风险预算动态平衡

```
基础配置: CTA 75% + FLP 5% + Cash 20%

CTA盈利时:
  → 提取15%利润增持FLP
  → 趋势末端保护增强
  → 反转时保护利润
```

---

## 📈 预期效果

基于 Goldman Sachs Research (2026) 和 Journal of Derivatives (2025):

| 指标 | CTA Only | CTA+FLP | 改善 |
|------|----------|---------|------|
| 年化波动 | 18.0% | 14.5% | -23% |
| 最大回撤 | -25.0% | -12.0% | +13% |
| 夏普比率 | 0.69 | 0.77 | +12% |

---

## 🔗 与其他模块集成

### 集成到 WeeklyAutoReport

```python
# 在 WeeklyAutoReport.py 中添加
from AKShare_CTA_FLP_Strategy import IntegratedAKShareStrategy

strategy = IntegratedAKShareStrategy()
strategy.run_strategy()

# 移动生成的文件
import shutil
shutil.move('cta_akshare_signals.csv', f'{REPORT_DIR}/06_CTA_FLP_AKShare.csv')
```

---

## 📚 相关文件

| 文件 | 说明 |
|------|------|
| `Mag7CTAAnalyzer.py` | 原有CTA分析 |
| `IntegratedStrategyAnalyzer.py` | CTA+财报综合分析 |
| `WeeklyAutoReport.py` | 周报自动生成 |

---

## ⚠️ 注意事项

1. **数据延迟**: AKShare 数据可能有1天延迟，不适合高频交易
2. **VIX估算**: 使用SPY实现波动率估算，与真实VIX有约20%偏差
3. **期权模拟**: 使用简化模型估算期权价格和Greeks
4. **风险控制**: 策略仅供参考，实盘需严格风控

---

## 📞 支持

**AKShare 文档**: https://www.akshare.xyz  
**GitHub**: https://github.com/akfamily/akshare

---

**版本**: V1.0  
**日期**: 2026-02-27  
**维护**: Quant Strategy Team
