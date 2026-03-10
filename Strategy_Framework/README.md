# 投资策略自上而下的决策框架

## 目录结构

```
Strategy_Framework/
├── 01_Macro_Analysis/                 # 第一层：宏观分析
├── 02_MultiFactor_CTA_RiceQuant/      # 第二层：多因子+CTA策略 (米筐)
├── 02_Sector_Analysis/                # 第二层：板块分析
├── 03_Stock_Selection/                # 第三层：个股选择
├── 04_Strategy_Execution/             # 第四层：策略执行
├── 05_Risk_Management/                # 第五层：风险管理
├── 06_Backtesting/                    # 第六层：回测验证
├── 07_Reporting/                      # 第七层：报告输出
├── Data/                              # 数据文件（ Providers, CSV, Excel）
├── Results/                           # 分析结果输出
└── docs/                              # 文档和说明
```

## 决策金字塔

```
Level 7: 报告输出 (Reporting)
    ↑
Level 6: 回测验证 (Backtesting)
    ↑
Level 5: 风险管理 (Risk Management)
    ↑
Level 4: 策略执行 (Strategy Execution)
    ↑
Level 3: 个股选择 (Stock Selection)
    ↑
Level 2: 板块分析 (Sector Analysis)
    ↑
Level 1: 宏观分析 (Macro Analysis)
```

## 各层级核心文件

### Level 1: 宏观分析
- `FedLiquidityAnalyzer.py` - 美联储流动性分析
- `CTA_FLP_Strategy.py` - CTA+FLP宏观对冲
- `FLP_FMP_Strategy.py` - FLP尾部保护

### Level 2: 多因子+CTA策略 (米筐)
- `02_MultiFactor_CTA_RiceQuant/` - **多因子选股+CTA周度换仓策略** ⭐⭐ (新)
  - `factor_model.py` - 多因子选股模型 (价值/质量/成长/技术)
  - `cta_signals.py` - CTA信号生成 (TSMOM/趋势跟踪)
  - `portfolio_manager.py` - 组合管理器 (资产配置/风险管理)
  - `ricequant_backtest.py` - 米筐回测框架
  - `strategy_main.py` - 策略主程序
  - 股票仓位70% + CTA仓位30%，周度换仓

### Level 2: 板块分析
- `CTA_Earnings_Sector_Analysis.py` - CTA+财报交叉分析 ⭐
- `CSI_A500_PatternAnalyzer.py` - A500板块分析

### Level 3: 个股选择
- `Mag7Tracker.py` - 科技七巨头跟踪 ⭐
- `Mag7CTAAnalyzer.py` - Mag7 CTA分析
- `Mag7Tracker_EarningsExpectation.py` - Mag7 财报预期
- `TechnicalPatternAnalyzer.py` - 技术形态分析
- `PBROEStrategy.py` - PB-ROE价值选股
- `OptionsEarningsAnalyzer.py` - 期权异动分析

### Level 4: 策略执行
- `CTA_Strategies_CN_Futures.py` - CTA趋势策略 ⭐
- `CTA_RiceQuant_Backtest.py` - RiceQuant回测
- `IntegratedStrategyAnalyzer.py` - 整合策略分析

### Level 5: 风险管理
- `CTA_Portfolio_Risk_System.py` - 组合风控系统 ⭐

### Level 6: 回测验证
- `CTA_Strategy_Evaluator.py` - 策略评估系统 ⭐
- `CTA_Integrated_Backtest_Demo.py` - 整合回测演示
- `CTABacktester.py` - CTA回测引擎

### Level 7: 报告输出
- `WeeklyAutoReport.py` - 周报自动生成 ⭐
- `Strategy_Visualization.py` - 策略可视化

## 🚀 快速使用

### 方式一: 自动运行（推荐）

设置每周一自动运行：
```bash
# 右键以管理员身份运行
setup_weekly_job.bat
```

### 方式二: 手动运行

双击运行菜单：
```bash
run_manual.bat
```

### 方式三: 运行并检查（推荐）

一键运行并验证结果：
```bash
run_with_check.bat
```

快速运行（跳过回测）：
```bash
run_quick.bat
```

### 方式三: 命令行运行

```bash
# 完整分析
python run_strategy_pipeline.py

# 指定日期
python run_strategy_pipeline.py 2026-02-28

# 仅运行特定层级
python run_strategy_pipeline.py --macro-only
python run_strategy_pipeline.py --sector-only
python run_strategy_pipeline.py --stock-only

# 跳过某些步骤（快速模式）
python run_strategy_pipeline.py --skip-backtest
```

### 方式四: 检查结果

```bash
# 检查今天的执行结果
python check_results.py

# 检查指定日期的结果
python check_results.py 2026-02-28
```

### 方式五: 单独运行各模块

```bash
# 1. 宏观分析
python 01_Macro_Analysis/FedLiquidityAnalyzer.py

# 2. 多因子+CTA策略 (米筐)
cd 02_MultiFactor_CTA_RiceQuant
python strategy_main.py              # 运行回测
python strategy_main.py --signal     # 生成今日信号
python strategy_main.py --backtest --start 2023-01-01 --end 2024-01-01

# 3. 板块分析
python 02_Sector_Analysis/CTA_Earnings_Sector_Analysis.py

# 4. 个股选择
python 03_Stock_Selection/Mag7Tracker.py

# 5. 策略执行
python 04_Strategy_Execution/CTA_Strategies_CN_Futures.py

# 6. 风险检查
python 05_Risk_Management/CTA_Portfolio_Risk_System.py

# 7. 回测验证
python 06_Backtesting/CTA_Strategy_Evaluator.py

# 8. 生成报告
python 07_Reporting/WeeklyAutoReport.py
```

## 详细文档

详见 `docs/Strategy_Decision_Framework.md`
