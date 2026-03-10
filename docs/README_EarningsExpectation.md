# MAG7 财报预期分析系统

## 概述

这个系统基于**真实的财报披露时间**，分析市场对MAG7个股的预期高低，帮助你判断：
- 市场预期是否已被透支
- 业绩超预期/低于预期后该如何操作
- 市场情绪和定价效率

---

## 核心逻辑：如何判断市场预期

### 四种基本情况

| 业绩 Surprise | 股价反应 (Gap) | 市场预期判断 | 含义 | 操作建议 |
|--------------|---------------|-------------|------|---------|
| **超预期** (>0) | **上涨** (>0) | 预期合理/偏低 | 好消息被认可，市场可能继续乐观 | 持有/追涨 |
| **超预期** (>0) | **下跌** (<0) | ⚠️ **预期过高** | 业绩已被Price In，"买预期卖事实" | 减仓/观望 |
| **低于预期** (<0) | **下跌** (<0) | 预期合理/偏高 | 坏消息被消化，可能过度反应 | 等待企稳 |
| **低于预期** (<0) | **上涨** (>0) | ⚠️ **预期过低** | 利空出尽，市场已充分消化 | 抄底/加仓 |

### 详细判断逻辑

```python
if Surprise% > 0 (业绩超预期):
    if Gap% > 0 (股价上涨):
        if 涨幅 > Surprise% 的一半:
            → "预期偏低" (市场保守，仍有空间)
        else:
            → "预期合理" (市场与业绩匹配)
    else (股价下跌):
        → "预期过高" (已被透支)

elif Surprise% < 0 (低于预期):
    if Gap% < 0 (股价下跌):
        if 跌幅 > |Surprise%| 的一半:
            → "预期偏高" (过度悲观)
        else:
            → "预期合理"
    else (股价上涨):
        → "预期过低" (利空出尽)
```

---

## 使用方法

### 1. 获取 Finnhub API Key

1. 访问 https://finnhub.io/register
2. 注册免费账号（每分钟60次调用，足够使用）
3. 复制你的 API Key

### 2. 运行代码

**方式1：环境变量（推荐）**
```bash
# Windows PowerShell
$env:FINNHUB_API_KEY = "你的API_Key"
python Mag7Tracker_EarningsExpectation.py

# Windows CMD
set FINNHUB_API_KEY=你的API_Key
python Mag7Tracker_EarningsExpectation.py
```

**方式2：修改代码**
```python
# 在 Mag7Tracker_EarningsExpectation.py 中修改：
FINNHUB_API_KEY = "你的实际API_Key"
```

### 3. 查看结果

运行后会生成：
- `mag7_earnings_expectation.xlsx` - 详细分析结果（4个sheet）
- `expectation_analysis.csv` - 预期分析数据
- `summary.csv` - 摘要报告

---

## 输出字段说明

### ExpectationAnalysis Sheet

| 字段 | 说明 |
|------|------|
| Ticker | 股票代码 |
| ReportDate | 财报发布日期 |
| Hour | 发布时间 (bmo=盘前, amc=盘后) |
| EPS_Actual | 实际EPS |
| EPS_Estimate | 预期EPS |
| SurprisePct | 超预期百分比 (实际-预期)/预期 |
| GapPct | 财报后跳空幅度 (Open-PrevClose)/PrevClose |
| IntradayPct | 日内涨跌幅 (Close-Open)/Open |
| DayChange | 全天涨跌幅 (Close-PrevClose)/PrevClose |
| **SurpriseClass** | 业绩分类 (Strong Beat/Beat/Inline/Miss/Strong Miss) |
| **ReactionClass** | 反应分类 (Positive/Neutral/Negative) |
| **ExpectationLevel** | 预期判断 (Expectation High/Low/Reasonable) |
| **ExpectationComment** | 详细解读 |
| **SignalScore** | 综合信号得分 |

### Summary Sheet

每只股票的最新财报摘要，按信号强度排序。

---

## 实战案例分析

### 案例1：NVDA 业绩超预期但股价下跌
```
EPS: 实际 $5.20 vs 预期 $4.50 → Surprise: +15.6%
股价: 跳空 -2.3%

判断: 预期过高 (Expectation High)
解读: 业绩虽好但已被Price In，机构借利好出货
操作: 短期回避，等待回调到位
```

### 案例2：TSLA 业绩低于预期但股价上涨
```
EPS: 实际 $0.60 vs 预期 $0.75 → Surprise: -20%
股价: 跳空 +3.5%

判断: 预期过低 (Expectation Low)
解读: 市场已充分消化利空，甚至过度悲观，利空出尽反弹
操作: 关注买入机会，可能是阶段性底部
```

### 案例3：AAPL 业绩符合预期，股价大涨
```
EPS: 实际 $1.50 vs 预期 $1.48 → Surprise: +1.4%
股价: 跳空 +5.2%

判断: 预期偏低 (Expectation Low)
解读: 市场此前过于保守，对苹果信心不足，实际业绩验证后追赶
操作: 持有，趋势可能延续
```

---

## 信号得分计算

```
SignalScore = Surprise% × 0.5      (业绩权重50%)
            + Gap% × 0.3           (跳空权重30%)
            + Intraday% × 0.2      (日内权重20%)
```

得分越高，信号越强。

---

## 配置参数

在代码中可调整以下参数：

```python
@dataclass(frozen=True)
class EngineConfig:
    # 信号阈值
    bullish_th: float = 0.03      # 看涨阈值 (3%)
    watch_th: float = 0.015       # 关注阈值 (1.5%)
    bearish_th: float = -0.015    # 看跌阈值 (-1.5%)
    
    # 超预期阈值
    strong_beat_th: float = 0.10   # 大幅超预期 (>10%)
    beat_th: float = 0.05          # 超预期 (>5%)
    miss_th: float = -0.05         # 低于预期 (<-5%)
    strong_miss_th: float = -0.10  # 大幅低于预期 (<-10%)
```

---

## 注意事项

1. **数据延迟**：Finnhub免费版数据可能有15分钟延迟
2. **财报时间**：系统会根据 bmo(盘前)/amc(盘后) 正确匹配反应日期
3. **节假日**：使用美国联邦假日历近似处理交易日
4. **API限制**：免费版每分钟60次调用，代码已内置限流和缓存

---

## 后续改进建议

1. 加入期权市场数据（IV Rank）判断预期
2. 加入分析师评级变化作为预期参考
3. 加入同行业对比（Relative Surprise）
4. 加入历史预期准确度回测
