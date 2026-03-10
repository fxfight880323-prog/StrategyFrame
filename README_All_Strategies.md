# 量化策略全家桶 - 完整文档

**最后更新**: 2026-02-27

---

## 📚 策略目录

### 1. PB-ROE 价值选股策略 ⭐ (新增)

**核心**: 低PB + 高ROE = 高性价比

```bash
# 运行
python PBROEStrategy.py
python PBROEStrategy_Visualization.py

# 输出
- pbroe_selection_*.csv
- charts/01_pb_roe_scatter.png
- charts/02_score_breakdown.png
- charts/03_industry_comparison.png
- charts/pbroe_report.html
```

**特点**:
- 价值投资经典策略
- 米筐专业数据支持
- 分行业对比分析
- 多维度评分系统

---

### 2. CTA + FLP 趋势对冲策略

**核心**: 趋势跟踪 + 期权保护

```bash
# AKShare版本 (推荐)
python AKShare_CTA_FLP_Strategy.py

# 米筐版本
python CTA_FLP_RiceQuant.py

# 可视化
python Strategy_Visualization.py
```

**特点**:
- 20/60日MA交叉
- 每周Put保护
- 盈利回哺机制
- 超额收益明显

---

### 3. CTA 技术分析策略

**核心**: 多因子技术评分

```bash
# AKShare版本
python Mag7CTAAnalyzer.py

# 米筐版本
python CTA_FMP_Strategy.py
```

**特点**:
- RSI + MACD + 均线
- 101只核心个股
- 买卖信号明确
- 波动率加权

---

### 4. 财报预期分析策略

**核心**: EPS惊喜 vs 价格反应

```bash
python Mag7Tracker_EarningsExpectation.py
```

**特点**:
- 财报超预期分析
- 市场预期判断
- 与CTA交叉验证

---

### 5. 美联储流动性策略

**核心**: 宏观流动性跟踪

```bash
python FedLiquidityAnalyzer.py
```

**特点**:
- WALCL + TGA + RRP
- 净流动性计算
- 政策环境判断

---

## 🎯 策略选择指南

### 按投资风格

| 风格 | 推荐策略 | 理由 |
|------|----------|------|
| **价值投资** | PB-ROE | 低估值+高盈利 |
| **趋势跟踪** | CTA | 均线突破+动量 |
| **事件驱动** | 财报预期 | 超预期博弈 |
| **宏观对冲** | 流动性+CTA+FLP | 多维度择时 |

### 按市场环境

| 市场 | 推荐策略 | 配置比例 |
|------|----------|----------|
| **牛市** | CTA趋势 | 60% |
| **震荡市** | PB-ROE | 50% |
| **熊市** | FLP保护+现金 | 40% |
| **财报季** | 财报预期+CTA | 各30% |

### 按风险偏好

| 风险偏好 | 策略组合 | 预期收益 | 最大回撤 |
|----------|----------|----------|----------|
| **保守** | PB-ROE + FLP | 10-15% | -10% |
| **平衡** | CTA + PB-ROE + FLP | 15-20% | -15% |
| **积极** | CTA + 财报预期 | 20-30% | -25% |

---

## 🏗️ 数据方案对比

| 方案 | 优点 | 缺点 | 适用策略 |
|------|------|------|----------|
| **AKShare** | 免费、国内稳定 | 延迟1天 | PB-ROE、CTA |
| **米筐** | 专业、实时 | 需付费 | 全策略 |
| **FMP** | 美股数据好 | 国内不稳定 | 美股CTA |

**推荐**: AKShare(日常) + 米筐(实盘)

---

## 🚀 快速开始

### 第一步: 环境准备

```bash
# 安装依赖
pip install pandas numpy matplotlib akshare yfinance

# 安装米筐(可选)
pip install rqdatac
```

### 第二步: 运行策略

```bash
# PB-ROE价值选股 (推荐新手)
python PBROEStrategy.py

# CTA趋势分析
python AKShare_CTA_FLP_Strategy.py

# 查看所有结果
python view_charts.py
```

### 第三步: 查看报告

```bash
# 打开HTML报告
start Report_*/integrated_report.html
start charts/pbroe_report.html
```

---

## 📊 策略组合建议

### 保守型组合 (适合熊市)

```
PB-ROE价值股: 50%
FLP期权保护: 10%
现金/债券: 30%
CTA趋势: 10%
```

**预期**: 年化8-12%，最大回撤-12%

### 平衡型组合 (适合震荡市)

```
PB-ROE价值股: 30%
CTA趋势股: 30%
FLP保护: 10%
现金: 20%
财报预期: 10%
```

**预期**: 年化12-18%，最大回撤-15%

### 积极型组合 (适合牛市)

```
CTA趋势股: 40%
财报预期股: 30%
PB-ROE价值股: 20%
现金: 10%
```

**预期**: 年化18-25%，最大回撤-20%

---

## 📈 绩效对比 (预期)

| 策略 | 年化收益 | 夏普比率 | 最大回撤 |
|------|----------|----------|----------|
| PB-ROE | 12-15% | 0.8 | -15% |
| CTA | 15-20% | 0.9 | -20% |
| CTA+FLP | 12-18% | 1.0 | -12% |
| 财报预期 | 18-25% | 0.7 | -25% |
| 组合策略 | 15-20% | 1.1 | -12% |

---

## 🛠️ 故障排除

### 常见问题

**Q: 数据获取失败?**
```bash
# 检查网络
ping www.ricequant.com

# 切换数据源
# 修改代码中的数据源配置
```

**Q: 中文显示乱码?**
```python
# 添加字体设置
plt.rcParams['font.sans-serif'] = ['SimHei']
```

**Q: 图表不生成?**
```bash
# 检查目录权限
mkdir -p charts
mkdir -p Report_$(date +%Y-%m-%d)
```

---

## 📞 支持

**AKShare**: https://www.akshare.xyz  
**米筐**: https://www.ricequant.com  
**FMP**: https://financialmodelingprep.com

---

## 📋 项目维护

**维护团队**: Quant Strategy Team  
**版本**: V2.0  
**最后更新**: 2026-02-27

---

## 🎉 开始使用

```bash
# 1. 价值选股
python PBROEStrategy.py

# 2. 趋势分析  
python AKShare_CTA_FLP_Strategy.py

# 3. 查看可视化
python view_charts.py
```

**祝投资顺利!** 📈
