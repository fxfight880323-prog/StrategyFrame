# PB-ROE 价值选股策略项目完成总结

**完成日期**: 2026-02-27  
**策略类型**: 价值投资策略  
**数据源**: 米筐(RiceQuant)  
**状态**: ✅ 完成

---

## 📦 项目交付物

### 核心代码

| 文件 | 说明 | 大小 |
|------|------|------|
| `PBROEStrategy.py` | PB-ROE选股策略核心 | 15.4 KB |
| `PBROEStrategy_Visualization.py` | 可视化模块 | 15.1 KB |

### 文档

| 文件 | 说明 |
|------|------|
| `PBROE_Strategy_说明.md` | 策略详细说明 |
| `PBROE_项目完成总结.md` | 本文档 |

### 生成文件

| 文件 | 说明 |
|------|------|
| `pbroe_selection_YYYY-MM-DD.csv` | 选股结果CSV |
| `charts/01_pb_roe_scatter.png` | PB-ROE散点图 |
| `charts/02_score_breakdown.png` | 评分分解图 |
| `charts/03_industry_comparison.png` | 行业对比图 |
| `charts/pbroe_report.html` | HTML整合报告 |

---

## 🎯 策略核心逻辑

### 核心指标

```
性价比 = ROE / PB

ROE (净资产收益率) = 净利润 / 净资产
PB (市净率) = 股价 / 每股净资产

目标: 寻找"又好又便宜"的股票
  - 好: ROE ≥ 15% (盈利能力强)
  - 便宜: PB ≤ 3 (估值合理)
```

### 选股标准

| 条件 | 阈值 | 说明 |
|------|------|------|
| 最大PB | 3.0 | 估值上限 |
| 最小ROE | 15% | 盈利门槛 |
| ROE稳定性 | 2年 | 持续优秀 |
| 最大负债率 | 70% | 财务安全 |
| 最小市值 | 50亿 | 流动性 |

### 评分权重

| 指标 | 权重 | 说明 |
|------|------|------|
| PB评分 | 35% | 越低越好 |
| ROE评分 | 35% | 越高越好 |
| 稳定性评分 | 20% | 波动越小越好 |
| 成长性评分 | 10% | 趋势向上 |

---

## 📊 可视化成果

### 1. PB-ROE散点图

**展示内容**:
- X轴: PB (市净率)
- Y轴: ROE (%)
- 气泡大小: 综合评分
- 颜色: 不同行业
- 理想区域: 低PB + 高ROE (绿色区域)

**图表位置**: `charts/01_pb_roe_scatter.png`

### 2. 评分分解图

**4合1图表**:
- Top 15 综合评分排名
- Top 15 ROE/PB性价比排名
- 行业分布饼图
- 评分分布直方图

**图表位置**: `charts/02_score_breakdown.png`

### 3. 行业对比图

**4合1图表**:
- 行业平均评分
- 行业平均PB
- 行业平均ROE
- 各行业选股数量

**图表位置**: `charts/03_industry_comparison.png`

### 4. HTML整合报告

**包含内容**:
- 关键指标卡片
- Top 10 推荐股票表格
- 所有可视化图表
- 响应式设计

**报告位置**: `charts/pbroe_report.html`

---

## 🚀 使用方式

### 第一步: 运行选股

```bash
python PBROEStrategy.py
```

### 第二步: 生成可视化

```bash
python PBROEStrategy_Visualization.py
```

### 第三步: 查看报告

```bash
# 打开HTML报告
start charts/pbroe_report.html

# 或查看CSV
start pbroe_selection_*.csv
```

---

## 💡 策略特点

### 优势

1. **简单易懂**
   - 只用2个核心指标 (PB + ROE)
   - 财务概念清晰
   - 易于解释

2. **长期有效**
   - 巴菲特验证
   - Fama-French模型支持
   - A股长期有效

3. **行业中性**
   - 分行业比较
   - 避免行业偏见
   - 全面覆盖机会

### 局限

1. **周期性行业**: 需结合周期位置
2. **高杠杆行业**: 银行保险需额外分析
3. **一次性收益**: 需关注收益持续性

---

## 📈 与其他策略对比

| 策略 | 核心指标 | 投资风格 | 优势 |
|------|----------|----------|------|
| **PB-ROE** | PB + ROE | 价值型 | 简单、稳健、长期有效 |
| **CTA趋势** | 均线+动量 | 趋势型 | 追涨杀跌、适合牛市 |
| **财报预期** | EPS惊喜 | 事件型 | 财报季机会 |
| **CTA+FLP** | 趋势+期权 | 对冲型 | 尾部风险保护 |

---

## 🎯 实战应用建议

### 组合配置

```
建议配置:
├── PB-ROE价值股: 40% (长期持有)
├── CTA趋势股: 30% (中短期)
├── 现金/债券: 20% (灵活配置)
└── FLP期权保护: 10% (风险管理)
```

### 调仓频率

- **季度 review**: 检查评分变化
- **半年调整**: 大幅调仓
- **年度复盘**: 策略效果评估

### 风险控制

- 单只仓位 ≤ 10%
- 行业分散 ≥ 5个
- 止损线: -15%
- 止盈线: +50%

---

## 📚 学术支持

### 理论基础

1. **Fama & French (1992)**
   - 证实PB和价值因子长期有效
   - 三因子模型

2. **Novy-Marx (2013)**
   - 证明ROE是比PB更强的预测指标
   - 质量因子研究

3. **巴菲特投资理念**
   - "以合理价格买入优秀公司"
   - ROE是核心选股标准

---

## 🔗 与现有系统集成

### 集成到周报

```python
# 在 WeeklyAutoReport.py 中添加
from PBROEStrategy import PBROEStrategy

def run_pbroe_strategy():
    strategy = PBROEStrategy()
    result = strategy.run_screening()
    result.to_csv(f"{REPORT_DIR}/07_PBROE_Selection.csv", index=False)
    return True

# 添加到执行列表
results['PBROE'] = run_script("PBROEStrategy.py", "PBROE选股")
```

### 多策略对比

```python
# 整合多个策略结果
cta_signals = pd.read_csv('cta_akshare_signals.csv')
pbroe_signals = pd.read_csv('pbroe_selection_*.csv')
earnings_signals = pd.read_csv('earnings_expectation.csv')

# 交叉验证
strong_buy = set(cta_signals[cta_signals['signal']=='LONG']['symbol']) & \
             set(pbroe_signals.head(10)['symbol'])
```

---

## 🎓 学习资源

### 推荐阅读

- 《巴菲特致股东信》
- 《聪明的投资者》- 格雷厄姆
- 《价值评估》- 麦肯锡

### 在线资源

- 米筐文档: https://www.ricequant.com/doc
- 东方财富: https://emweb.securities.eastmoney.com
- 理杏仁: https://www.lixinger.com

---

## 📞 支持与维护

**策略维护**: Quant Strategy Team  
**数据来源**: 米筐(RiceQuant)  
**问题反馈**: 通过项目管理工具

---

## ✅ 项目验收清单

- [x] PB-ROE策略核心实现
- [x] 米筐数据接口集成
- [x] 多维度评分系统
- [x] 行业对比功能
- [x] 散点图可视化
- [x] 评分分解图表
- [x] HTML整合报告
- [x] 策略说明文档
- [ ] 实盘回测验证 (待后续完成)
- [ ] 参数优化 (待后续完成)

---

**项目状态**: ✅ 完成并可用  
**版本**: V1.0  
**维护**: Quant Strategy Team  
**日期**: 2026-02-27
