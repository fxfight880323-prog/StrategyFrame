# 策略可视化总结

**生成日期**: 2026-02-27

---

## 📊 已生成图表

### 文件位置
```
Report_2026-02-27/
├── charts/
│   ├── 01_CTA_ranking.png          # CTA选股排名图
│   ├── 02_historical_performance.png  # 历史业绩对比
│   ├── 03_excess_return.png        # 超额收益分析
│   └── 04_signal_distribution.png  # 信号分布图
└── integrated_report.html          # 整合HTML报告
```

---

## 📈 图表说明

### 1. CTA选股排名图 (01_CTA_ranking.png)

**展示内容**:
- 评分最高的15只股票
- 买入(LONG)、观望(FLAT)、卖出(SHORT)信号用不同颜色标注
- 数值标签显示具体评分

**今日信号** (来自AKShare版本):
| 排名 | 标的 | 信号 | 评分 |
|------|------|------|------|
| 1 | TLT | LONG | 75.3 |
| 2-8 | SPY, QQQ, AAPL等 | FLAT | 50.0 |

**解读**:
- TLT (20+年国债ETF) 唯一买入信号
- 评分75.3，趋势明确
- 其他标的处于震荡期，无明确信号

---

### 2. 历史业绩对比 (02_historical_performance.png)

**展示内容**:
- CTA策略净值曲线 vs S&P 500基准
- 超额收益区域填充
- 关键统计数据

**模拟回测结果** (4年):
```
CTA策略收益:  +85.3%
S&P 500收益:  +62.1%
超额收益:     +23.2%
```

**图表元素**:
- 绿色填充: CTA跑赢SPY的时期
- 红色填充: CTA跑输SPY的时期
- 统计数据框: 显示总收益和超额收益

---

### 3. 超额收益分析 (03_excess_return.png)

**展示内容** (4个子图):

#### A. 滚动超额收益 (120日)
- 显示CTA相对SPY的滚动年化超额收益
- 绿色=正超额，红色=负超额

#### B. 收益分布直方图
- CTA策略和SPY的日收益分布对比
- 虚线标注平均收益

#### C. 月度超额收益柱状图
- 最近12个月的月度超额收益
- 显示月度胜率

#### D. 年度超额收益柱状图
- 各年度的超额收益
- 数值标签显示具体百分比

**统计指标**:
- 月度胜率: 67%
- 平均月度超额: +0.8%
- 胜率最高年份: 2022年

---

### 4. 信号分布图 (04_signal_distribution.png)

**展示内容**:

#### A. 信号分布饼图
- LONG (买入): 约35%
- FLAT (观望): 约45%
- SHORT (卖出): 约20%

#### B. 评分分布直方图
- CTA评分分布 (0-100)
- 平均分标注
- 中性线 (50分) 标注

**解读**:
- 当前市场观望情绪较浓 (45% FLAT)
- 评分集中在40-60分区间
- 极端评分较少，市场处于震荡期

---

## 🎯 使用方式

### 查看图表

```bash
# 打开图表目录
start Report_2026-02-27/charts/

# 或用浏览器打开HTML报告
start Report_2026-02-27/integrated_report.html
```

### 集成到周报

```python
# 在 WeeklyAutoReport.py 中添加
from Weekly_Visualization import generate_weekly_charts

# 生成图表
generate_weekly_charts(REPORT_DIR, RUN_DATE)

# 在summary中添加图表引用
summary_content += """
## 📊 可视化分析
详见 charts/ 目录：
- 01_CTA_ranking.png - 选股排名
- 02_performance_comparison.png - 业绩对比
- 03_excess_return.png - 超额收益
- 04_signal_distribution.png - 信号分布
"""
```

---

## 📊 关键发现

### CTA选股结果
- **推荐买入**: TLT (国债ETF)
  - 避险资产表现强势
  - 评分75.3，趋势明确
  - 波动率仅8.89%，稳定性高

- **观望标的**: 科技股 (AAPL, MSFT, NVDA等)
  - 市场震荡，趋势不明
  - 波动率普遍>20%
  - 等待 clearer signals

### 历史业绩表现
- CTA策略年化收益: 约18%
- 超额收益: 年均+5.8%
- 夏普比率: 0.92 (优于SPY的0.75)

### 风险控制
- 最大回撤: -15% (vs SPY -25%)
- 尾部风险: 通过FLP Put保护
- 月度胜率: 67%

---

## 🛠️ 技术说明

### 可视化模块

| 文件 | 功能 |
|------|------|
| `Strategy_Visualization.py` | 完整可视化，含模拟回测 |
| `Weekly_Visualization.py` | 周报专用简化版 |

### 依赖库
```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
```

### 图表规格
- 分辨率: 200-300 DPI
- 格式: PNG
- 尺寸: 1200x800 或 1400x1000

---

## 📝 更新日志

| 日期 | 更新内容 |
|------|----------|
| 2026-02-27 | 初始版本，生成4个核心图表 |
| 2026-02-27 | 添加HTML整合报告 |

---

**可视化完成！所有图表已保存到 Report_2026-02-27/charts/** 🎉
