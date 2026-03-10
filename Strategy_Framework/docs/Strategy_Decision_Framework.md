# 投资策略自上而下决策框架

## 框架概览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        投资决策金字塔 (Investment Pyramid)                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Level 1: 宏观分析 (Macro Analysis)                                          │
│  ├── 美联储流动性分析 (Fed Liquidity)                                         │
│  ├── 经济周期定位 (Economic Cycle)                                            │
│  └── 市场情绪指标 (Market Sentiment)                                          │
│                                                                             │
│  Level 2: 板块分析 (Sector Analysis)                                         │
│  ├── CTA + 财报交叉分析 (CTA × Earnings)                                      │
│  ├── 板块轮动策略 (Sector Rotation)                                           │
│  └── 风格因子分析 (Style Factor)                                              │
│                                                                             │
│  Level 3: 个股选择 (Stock Selection)                                         │
│  ├── Mag7 科技巨头跟踪                                                        │
│  ├── 技术形态分析 (Pattern Analysis)                                          │
│  ├── PB-ROE 价值选股                                                         │
│  └── 期权异动分析 (Options Flow)                                              │
│                                                                             │
│  Level 4: 策略执行 (Strategy Execution)                                      │
│  ├── CTA趋势策略 (CTA Trend Following)                                        │
│  ├── FLP尾部保护 (Fixed Leverage Puts)                                        │
│  └── 组合动态平衡 (Dynamic Rebalancing)                                       │
│                                                                             │
│  Level 5: 风险管理 (Risk Management)                                         │
│  ├── 事前风控 (Pre-trade Risk)                                                │
│  ├── 仓位管理 (Position Sizing)                                               │
│  ├── 止损止盈 (Stop Loss/Take Profit)                                         │
│  └── 压力测试 (Stress Testing)                                                │
│                                                                             │
│  Level 6: 回测验证 (Backtesting)                                             │
│  ├── 策略回测 (Strategy Backtest)                                             │
│  ├── 绩效评估 (Performance Evaluation)                                        │
│  └── 参数优化 (Parameter Optimization)                                        │
│                                                                             │
│  Level 7: 报告输出 (Reporting)                                               │
│  ├── 周报自动生成 (Weekly Report)                                             │
│  ├── 可视化图表 (Visualization)                                               │
│  └── 策略归因 (Attribution Analysis)                                          │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 第一层：宏观分析 (Macro Analysis)

### 1.1 美联储流动性分析
**文件**: `FedLiquidityAnalyzer.py`

**核心指标**:
- 净流动性 (Net Liquidity) = 美联储资产负债表 - TGA - RRP
- FRED数据监控
- 流动性周期判断

**决策逻辑**:
```
流动性扩张 → 增加风险资产仓位
流动性收缩 → 减少风险资产，增加防御
```

### 1.2 CTA + FLP 宏观对冲
**文件**: `CTA_FLP_Strategy.py`, `CTA_FLP_Integrated_FMP.py`

**策略组合**:
- CTA趋势跟踪 (60%权重)
- FLP尾部保护 (20%权重)  
- 现金 (20%权重)

---

## 第二层：板块分析 (Sector Analysis)

### 2.1 CTA + 财报交叉分析 ⭐
**文件**: `CTA_Earnings_Sector_Analysis.py`, `CTA_Earnings_Detailed_Analysis.py`

**分析框架**:
```python
板块得分 = CTA趋势信号 × 60% + 财报超预期 × 40%
```

**输出结果**:
| 板块 | 评分 | 推荐 |
|------|------|------|
| Financials | 10.5 | 超配 |
| Technology | 9.5 | 标配 |
| Materials | -3.9 | 低配 |

### 2.2 A500 板块分析
**文件**: `CSI_A500_PatternAnalyzer.py`

**适用市场**: A股中证500

---

## 第三层：个股选择 (Stock Selection)

### 3.1 Mag7 科技巨头跟踪 ⭐
**文件**: `Mag7Tracker.py`, `Mag7CTAAnalyzer.py`, `Mag7Tracker_EarningsExpectation.py`

**覆盖标的**: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA

**分析维度**:
- CTA趋势信号
- 财报预期差
- 估值水平
- 技术形态

**最新推荐**:
- **买入**: ADBE, ORCL, ACN (趋势+财报双强)
- **回避**: 部分估值过高巨头

### 3.2 技术形态分析
**文件**: `TechnicalPatternAnalyzer.py`, `PatternStrategy_Main.py`

**识别形态**:
- 头肩顶/底
- 双顶/双底
- 三角形整理
- 通道突破

### 3.3 PB-ROE 价值选股
**文件**: `PBROEStrategy.py`

**选股逻辑**:
```
高ROE + 低PB = 买入
低ROE + 高PB = 回避
```

### 3.4 期权异动分析
**文件**: `OptionsEarningsAnalyzer.py`, `OptionsBacktest_Tradier.py`

**监控指标**:
- 异常成交量
- Put/Call Ratio
- 隐含波动率变化

---

## 第四层：策略执行 (Strategy Execution)

### 4.1 CTA趋势策略
**文件**: `CTA_Strategies_CN_Futures.py`, `CTA_RiceQuant_Backtest.py`

**策略类型**:
1. **TSMOM** (时间序列动量)
   - 回看期: 20日
   - 波动率调整仓位

2. **Trend Following** (趋势跟踪)
   - MA20/MA60交叉
   - 通道突破确认

3. **Carry** (期限结构)
   - Contango做空
   - Backwardation做多

### 4.2 FLP尾部保护
**文件**: `FLP_FMP_Strategy.py`

**操作规则**:
- 每周五买入7天到期的SPY Put
- Delta目标: -0.07 ~ -0.10
- VIX<15时增加预算

### 4.3 整合策略执行
**文件**: `IntegratedStrategyAnalyzer.py`

---

## 第五层：风险管理 (Risk Management)

### 5.1 组合风控系统 ⭐
**文件**: `CTA_Portfolio_Risk_System.py`

**风控层级**:
```
事前风控:
  - 单品种 ≤ 10%
  - 板块 ≤ 30%
  - 总杠杆 ≤ 2倍

事中风控:
  - 止损: 3%
  - 移动止损: 5%
  - 时间止损: 20天

事后风控:
  - VaR监控
  - 压力测试
  - 归因分析
```

---

## 第六层：回测验证 (Backtesting)

### 6.1 策略评估系统 ⭐
**文件**: `CTA_Strategy_Evaluator.py`

**核心指标**:
- Sharpe Ratio (夏普比率)
- Information Ratio (信息比率)
- Sortino Ratio (索提诺比率)
- Calmar Ratio (卡玛比率)
- Max Drawdown (最大回撤)

### 6.2 回测引擎
**文件**: `CTA_Integrated_Backtest_Demo.py`, `CTABacktester.py`

---

## 第七层：报告输出 (Reporting)

### 7.1 周报自动生成
**文件**: `WeeklyAutoReport.py`, `Weekly_Visualization.py`

### 7.2 可视化图表
**文件**: `Strategy_Visualization.py`, `PatternStrategy_Visualizer.py`

---

## 完整决策流程示例

```
Step 1: 宏观判断
  └─ FedLiquidityAnalyzer → 流动性扩张信号 ✓
  
Step 2: 板块选择
  └─ CTA_Earnings_Sector_Analysis → Financials 最佳 ✓
  
Step 3: 个股选择
  └─ Mag7Tracker → BAC, GS, MS 买入信号 ✓
  
Step 4: 策略执行
  └─ CTA趋势策略 → 建立多头仓位
  └─ FLP保护 → 买入SPY Put对冲
  
Step 5: 风险管理
  └─ CTA_Portfolio_Risk_System → 仓位检查通过 ✓
  
Step 6: 回测验证
  └─ CTA_Strategy_Evaluator → 历史表现良好 ✓
  
Step 7: 报告输出
  └─ WeeklyAutoReport → 生成周报
```

---

## 文件映射关系

| 决策层级 | 核心文件 | 辅助文件 |
|----------|----------|----------|
| 宏观分析 | FedLiquidityAnalyzer.py | CTA_FLP_Strategy.py |
| 板块分析 | CTA_Earnings_Sector_Analysis.py | CSI_A500_PatternAnalyzer.py |
| 个股选择 | Mag7Tracker.py, Mag7CTAAnalyzer.py | TechnicalPatternAnalyzer.py, PBROEStrategy.py |
| 策略执行 | CTA_Strategies_CN_Futures.py | CTA_FLP_RiceQuant.py |
| 风险管理 | CTA_Portfolio_Risk_System.py | - |
| 回测验证 | CTA_Strategy_Evaluator.py | CTA_Integrated_Backtest_Demo.py |
| 报告输出 | WeeklyAutoReport.py | Strategy_Visualization.py |

---

## 数据提供商

| 提供商 | 用途 | 文件 |
|--------|------|------|
| RiceQuant (米筐) | 国内期货 | RiceQuantDataProvider_CTA.py |
| YFinance | 美股数据 | YFinanceDataProvider.py |
| FMP | 财报数据 | FMPDataProvider.py |
| Tradier | 期权数据 | TradierDataProvider.py |
| AKShare | 免费美股 | AKShare_CTA_FLP_Strategy.py |

---

## 快速开始指南

```bash
# 1. 宏观分析
python Strategy_Framework/01_Macro_Analysis/FedLiquidityAnalyzer.py

# 2. 板块分析
python Strategy_Framework/02_Sector_Analysis/CTA_Earnings_Sector_Analysis.py

# 3. 个股选择
python Strategy_Framework/03_Stock_Selection/Mag7Tracker.py

# 4. 策略执行
python Strategy_Framework/04_Strategy_Execution/CTA_Strategies_CN_Futures.py

# 5. 风险管理检查
python Strategy_Framework/05_Risk_Management/CTA_Portfolio_Risk_System.py

# 6. 回测验证
python Strategy_Framework/06_Backtesting/CTA_Strategy_Evaluator.py

# 7. 生成报告
python Strategy_Framework/07_Reporting/WeeklyAutoReport.py
```
