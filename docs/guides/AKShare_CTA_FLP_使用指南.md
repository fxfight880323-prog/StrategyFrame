# CTA + FLP 策略 - AKShare 版本使用指南

## 🎯 概述

使用 **AKShare** 获取美股数据，实现 CTA + FLP 尾部风险对冲策略。

**优势**:
- ✅ 无需 API Key
- ✅ 国内访问稳定
- ✅ 免费且无需注册
- ✅ 支持美股日线数据

---

## 📦 文件清单

| 文件 | 说明 |
|------|------|
| `AKShare_CTA_FLP_Strategy.py` | 完整策略实现 |
| `cta_akshare_signals.csv` | CTA 信号输出 (运行后生成) |

---

## 🚀 快速开始

### 运行策略

```bash
python AKShare_CTA_FLP_Strategy.py
```

**预期输出**:
```
======================================================================
CTA + FLP 整合策略 (AKShare 版本)
======================================================================

【1. CTA 趋势分析】
============================================================
CTA 趋势分析 (AKShare 数据)
============================================================
获取 SPY 数据...
  ✓ 成功: 751 条记录
获取 QQQ 数据...
  ✓ 成功: 751 条记录
...
TLT   : Signal=LONG , Score= 75.3, Vol= 8.89%

Top 10 强势标的:
symbol  price signal  score
   TLT  90.27   LONG   75.3
   SPY 689.30   FLAT   50.0
...

【2. FLP 尾部保护】
SPY 价格: $689.30
估算 VIX: 13.97
保护模式: Long Put
保护预算: $60,000.00
...

【3. 风险预算分配】
CTA 策略:   75.0%  ($750,000)
FLP 保护:    5.0%  ($50,000)
现金:       20.0%  ($200,000)
```

---

## 📊 策略组件

### 1. CTA 趋势引擎

**分析标的** (默认8只):
- `SPY` - S&P 500 ETF
- `QQQ` - Nasdaq 100 ETF
- `AAPL` - Apple
- `MSFT` - Microsoft
- `NVDA` - NVIDIA
- `TSLA` - Tesla
- `GLD` - Gold ETF
- `TLT` - 20+ Year Treasury ETF

**信号生成**:
```
20日MA > 60日MA + 价格上穿通道 → LONG (买入)
20日MA < 60日MA + 价格下穿通道 → SHORT (卖出)
其他情况 → FLAT (观望)
```

**评分系统** (0-100分):
- 50分为基准
- LONG信号 +20分
- 趋势强度额外加分
- 最终分数越高越强势

### 2. FLP 保护引擎

**执行规则**:
- 每周五执行
- 买入 SPY Put (Delta -0.07 ~ -0.10)
- 根据 VIX 水平调整策略

**VIX 估算**:
```python
# 使用 SPY 实现波动率估算 VIX
realized_vol = returns.rolling(20).std() * sqrt(252) * 100
```

**保护模式**:

| VIX水平 | 模式 | 预算调整 |
|---------|------|----------|
| < 15 | Long Put | +20% |
| 15-30 | Long Put | 基准 |
| > 30 | Put Spread | -30% |

### 3. 风险预算分配

**基础配置**:
- CTA 策略: 75%
- FLP 保护: 5%
- 现金: 20%

**盈利回哺**:
- CTA 盈利时提取 15% 增持 FLP
- 趋势末端自动增强保护

---

## ⚙️ 自定义配置

### 修改分析标的

编辑 `AKShare_CTA_FLP_Strategy.py`:

```python
CTA_CONFIG = {
    'fast_ma': 20,
    'slow_ma': 60,
    'channel_period': 20,
    'channel_width': 2.0,
    'symbols': ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 
                'JPM', 'V', 'XOM', 'JNJ', 'WMT', 'GLD', 'TLT']  # 添加更多
}
```

**常用美股代码**:
- 科技: `AAPL`, `MSFT`, `GOOGL`, `AMZN`, `META`, `NVDA`, `TSLA`
- 金融: `JPM`, `BAC`, `GS`, `V`, `MA`
- 医药: `JNJ`, `PFE`, `UNH`, `ABBV`
- 消费: `WMT`, `COST`, `HD`, `NKE`
- 能源: `XOM`, `CVX`
- ETF: `SPY`, `QQQ`, `IWM`, `GLD`, `TLT`, `VIXY`

### 修改策略参数

```python
CTA_CONFIG = {
    'fast_ma': 10,      # 更快的信号
    'slow_ma': 30,
    'channel_width': 1.5,  # 更窄的通道
}

FLP_CONFIG = {
    'vix_low': 12,      # 更早增加保护
    'vix_high': 25,
    'budget_increase': 0.30,  # 增加30%预算
}
```

---

## 📈 输出文件

### cta_akshare_signals.csv

运行后生成的 CSV 文件，包含:

| 列名 | 说明 |
|------|------|
| symbol | 标的代码 |
| date | 信号日期 |
| price | 当前价格 |
| signal | 交易信号 (LONG/SHORT/FLAT) |
| score | 评分 (0-100) |
| fast_ma | 20日均线 |
| slow_ma | 60日均线 |
| volatility | 年化波动率 (%) |
| position_size | 建议仓位 |

**使用示例**:
```python
import pandas as pd
signals = pd.read_csv('cta_akshare_signals.csv')

# 筛选买入信号
buy_signals = signals[signals['signal'] == 'LONG']

# 按评分排序
top_picks = signals.nlargest(5, 'score')
```

---

## 💡 使用场景

### 场景1: 每日监控

```bash
# 添加到定时任务 (crontab)
# 每天收盘后运行
0 16 * * * cd /path/to/strategy && python AKShare_CTA_FLP_Strategy.py

# 查看今日信号
cat cta_akshare_signals.csv | grep LONG
```

### 场景2: 周末复盘

```bash
# 周五运行完整策略 (包含 FLP 对冲)
python AKShare_CTA_FLP_Strategy.py

# 检查下周 CTA 持仓
python -c "
import pandas as pd
df = pd.read_csv('cta_akshare_signals.csv')
print(df[df['signal'] == 'LONG'])
"
```

### 场景3: 集成到周报

```python
# 在 WeeklyAutoReport.py 中添加
from AKShare_CTA_FLP_Strategy import IntegratedAKShareStrategy

strategy = IntegratedAKShareStrategy()
cta_signals = strategy.cta_engine.generate_signals()
cta_signals.to_excel(f"{REPORT_DIR}/06_CTA_FLP_AKShare.xlsx", index=False)
```

---

## 🔧 故障排除

### 问题1: 数据获取失败

**现象**: `✗ 失败: ...`

**解决**:
```python
# 添加重试机制
import time

for attempt in range(3):
    try:
        df = ak.stock_us_daily(symbol='AAPL')
        break
    except:
        time.sleep(2)
```

### 问题2: 网络超时

**现象**: 长时间无响应

**解决**:
```bash
# 检查网络连接
ping financialmodelingprep.com

# 使用代理 (如需要)
export HTTP_PROXY=http://proxy:port
export HTTPS_PROXY=http://proxy:port
```

### 问题3: 数据不完整

**现象**: 返回数据少于预期

**解决**:
```python
# 使用缓存避免重复请求
data_provider = AKShareDataProvider()
# 第二次请求会从缓存读取
df = data_provider.get_us_stock('AAPL')  
```

---

## 📊 与 FMP 版本对比

| 特性 | AKShare 版本 | FMP 版本 |
|------|-------------|----------|
| API Key | ❌ 不需要 | ✅ 需要 |
| 国内访问 | ✅ 稳定 | ⚠️ 可能不稳定 |
| 实时数据 | ✅ 支持 | ✅ 支持 |
| 期权数据 | ⚠️ 模拟估算 | ✅ 真实数据 |
| VIX 数据 | ⚠️ 估算 | ✅ 真实数据 |
| 成本 | ✅ 免费 | ⚠️ 免费版有限制 |

**建议**:
- 日常使用: AKShare 版本 (简单稳定)
- 生产环境: FMP 版本 (数据更精确)

---

## 🔗 相关文件

| 文件 | 说明 |
|------|------|
| `Mag7CTAAnalyzer.py` | 原有 CTA 分析 (AkShare) |
| `IntegratedStrategyAnalyzer.py` | CTA + 财报综合分析 |
| `WeeklyAutoReport.py` | 周报自动生成 |

---

## 📞 支持

**AKShare 文档**: https://www.akshare.xyz  
**GitHub**: https://github.com/akfamily/akshare

---

**版本**: V1.0  
**日期**: 2026-02-27  
**维护**: Quant Strategy Team
