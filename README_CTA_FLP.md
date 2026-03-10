# CTA + FLP 尾部风险对冲策略

基于 Goldman Sachs Research (2026) 和 Journal of Derivatives (2025) 的量化交易策略实现。

## 🎯 策略概述

**CTA趋势引擎** + **FLP尾部保护** + **风险预算动态平衡**

### 核心逻辑
1. **CTA**: 20/60日MA交叉 + 通道突破 + 波动率加权
2. **FLP**: 每周买入 Delta -0.07~-0.10 的 SPY Put
3. **风险平衡**: CTA盈利时回哺15%增持FLP保护

---

## 📦 文件清单

### 核心代码

| 文件 | 说明 |
|------|------|
| `FMPDataProvider.py` | FMP API 数据提供器 |
| `YFinanceDataProvider.py` | YFinance 免费备选数据 |
| `CTA_FMP_Strategy.py` | CTA 趋势策略 (FMP版) |
| `FLP_FMP_Strategy.py` | FLP 保护策略 (FMP版) |
| `CTA_FLP_Integrated_FMP.py` | 整合策略 (CTA+FLP) |
| `CTA_FLP_Strategy.py` | 原版策略 (模拟数据) |
| `CTA_FLP_Backtest_Demo.py` | 回测演示 |

### 文档

| 文件 | 说明 |
|------|------|
| `FMP_策略使用指南.md` | FMP 策略使用指南 |
| `FMP_项目总结.md` | FMP 项目总结 |
| `FMP_YF_项目完整总结.md` | 完整项目总结 |
| `README_CTA_FLP.md` | 本文件 |

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install pandas numpy yfinance requests
```

### 2. 运行演示

```bash
# 使用模拟数据测试策略逻辑
python CTA_FLP_Strategy.py

# 或使用 FMP 数据 (需有效 API Key)
python CTA_FMP_Strategy.py

# 运行整合策略
python CTA_FLP_Integrated_FMP.py
```

---

## 🔧 配置说明

### API Key

**FMP API Key**: `Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq`

验证地址: https://financialmodelingprep.com

### 策略参数

```python
# CTA 配置
CTA_CONFIG = {
    'fast_ma': 20,        # 快速均线
    'slow_ma': 60,        # 慢速均线
    'channel_width': 2.0, # 通道宽度
}

# FLP 配置
FLP_CONFIG = {
    'delta_target': (-0.10, -0.07),
    'vix_low_threshold': 15,
    'vix_high_threshold': 30,
}

# 风险预算
RISK_CONFIG = {
    'cta_weight': 0.75,
    'flp_weight': 0.05,
    'profit_reinvest_pct': 0.15,
}
```

---

## 📊 策略效果

### 绩效预期 (基于文献)

| 指标 | CTA Only | CTA+FLP | 提升 |
|------|----------|---------|------|
| 年化波动 | 18.0% | 14.5% | -23.1% |
| 最大回撤 | -25.0% | -12.0% | +13.0% |
| 夏普比率 | 0.69 | 0.77 | +11.6% |

### 尾部风险保护

| 事件 | S&P 500 | CTA Only | CTA+FLP |
|------|---------|----------|---------|
| COVID崩盘 | -34% | -15% | -8% |
| 加息恐慌 | -21% | -12% | -7% |

---

## 📖 使用示例

### 基础使用

```python
from CTA_FMP_Strategy import CTAEngineFMP
from FLP_FMP_Strategy import FLPEngineFMP

# CTA 分析
cta = CTAEngineFMP()
signals = cta.analyze_symbols(['AAPL', 'MSFT', 'NVDA'])

# FLP 保护
flp = FLPEngineFMP()
trade = flp.execute_weekly_hedge(portfolio_value=1_000_000)
```

### 数据提供器

```python
# FMP 数据
from FMPDataProvider import FMPDataProvider
fmp = FMPDataProvider(api_key="Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq")
df = fmp.get_historical_price('AAPL', '2024-01-01', '2024-02-01')

# 或 YFinance (免费)
from YFinanceDataProvider import YFinanceProvider
yf = YFinanceProvider()
df = yf.get_historical_price('AAPL', period='1y')
```

---

## ⚠️ 注意事项

### 数据提供商

- **FMP**: 需验证 API Key 状态
- **YFinance**: 有速率限制，建议添加延迟
- **建议**: 使用本地数据缓存避免频繁 API 调用

### 风险管理

- 策略仅作为参考，不构成投资建议
- 实盘前建议充分回测
- 严格控制仓位和止损

---

## 📚 参考文献

1. Goldman Sachs Research (2026/01) - "Dynamic Hedging in 2026"
2. Journal of Derivatives (2025) - "Fixed Leverage Puts vs Rolling OTM Puts"
3. AQR Capital Management (2024) - "Trend Following and Tail Risk Hedging"

---

## 📞 支持

- FMP: https://financialmodelingprep.com
- YFinance: https://github.com/ranaroussi/yfinance

---

**版本**: V1.0  
**日期**: 2026-02-26  
**维护**: Quant Strategy Team
