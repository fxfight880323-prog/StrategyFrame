# 策略框架自动化运行指南

## 📋 概述

策略框架提供两种运行方式：
1. **自动运行**: 每周一定时自动执行
2. **手动运行**: 按需手动触发

## 🚀 快速开始

### 1. 设置每周自动任务

1. 右键点击 `setup_weekly_job.bat`，选择"**以管理员身份运行**"
2. 按提示输入执行时间（默认周一 8:00）
3. 任务将添加到Windows计划任务中

```batch
setup_weekly_job.bat
```

**任务详情:**
- 名称: `策略框架_每周分析`
- 时间: 每周一早上（默认 8:00）
- 操作: 自动运行完整7层分析管道

### 2. 手动运行分析

双击 `run_manual.bat`，选择运行模式：

```
[1] 完整分析管道 (全部7层)
[2] 仅宏观分析 (Level 1)
[3] 仅板块分析 (Level 2)
[4] 仅个股选择 (Level 3)
[5] 跳过回测 (快速模式)
[6] 指定日期运行
[7] 查看历史报告
[8] 退出
```

### 3. 快速运行

双击 `run_quick.bat` 直接运行（跳过回测，节省时间）

---

## 📁 文件说明

| 文件 | 用途 |
|------|------|
| `run_strategy_pipeline.py` | Python主运行脚本 |
| `setup_weekly_job.bat` | 设置定时任务（需管理员权限） |
| `run_manual.bat` | 手动运行菜单 |
| `run_quick.bat` | 快速运行（跳过回测） |

---

## ⚙️ 命令行参数

### 基础用法

```bash
# 完整运行
python run_strategy_pipeline.py

# 指定日期
python run_strategy_pipeline.py 2026-02-28

# 仅运行特定层级
python run_strategy_pipeline.py --macro-only
python run_strategy_pipeline.py --sector-only
python run_strategy_pipeline.py --stock-only

# 跳过某些步骤
python run_strategy_pipeline.py --skip-backtest
python run_strategy_pipeline.py --skip-risk
python run_strategy_pipeline.py --skip-report
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `date` | 指定运行日期 (YYYY-MM-DD) |
| `--macro-only` | 仅运行宏观分析 |
| `--sector-only` | 仅运行板块分析 |
| `--stock-only` | 仅运行个股选择 |
| `--skip-macro` | 跳过宏观分析 |
| `--skip-sector` | 跳过板块分析 |
| `--skip-stock` | 跳过个股选择 |
| `--skip-execution` | 跳过策略执行 |
| `--skip-risk` | 跳过风险检查 |
| `--skip-backtest` | 跳过回测验证 |
| `--skip-report` | 跳过报告生成 |

---

## 📊 执行流程

```
运行管道
    │
    ├── Level 1: 宏观分析
    │   └── FedLiquidityAnalyzer.py (2分钟)
    │
    ├── Level 2: 板块分析
    │   └── CTA_Earnings_Sector_Analysis.py (3分钟)
    │
    ├── Level 3: 个股选择
    │   ├── Mag7Tracker.py (3分钟)
    │   ├── Mag7Tracker_EarningsExpectation.py (3分钟)
    │   └── TechnicalPatternAnalyzer.py (3分钟)
    │
    ├── Level 4: 策略执行
    │   └── CTA_Strategies_CN_Futures.py (3分钟)
    │
    ├── Level 5: 风险管理
    │   └── CTA_Portfolio_Risk_System.py (2分钟)
    │
    ├── Level 6: 回测验证
    │   └── CTA_Strategy_Evaluator.py (5分钟)
    │
    └── Level 7: 报告输出
        └── WeeklyAutoReport.py (3分钟)

预计总耗时: 15-25分钟
```

---

## 📂 输出结果

所有结果保存在 `Results/Report_YYYY-MM-DD/` 目录下：

```
Results/
└── Report_2026-02-28/
    ├── execution_log.txt          # 执行日志
    ├── execution_summary.txt      # 执行摘要
    ├── macro_analysis.xlsx        # 宏观分析结果
    ├── sector_ranking.csv         # 板块排名
    ├── mag7_analysis.xlsx         # Mag7分析
    ├── stock_signals.csv          # 个股信号
    ├── risk_report.txt            # 风险报告
    ├── backtest_results.xlsx      # 回测结果
    └── weekly_report.xlsx         # 综合周报
```

---

## 🔧 管理定时任务

### 查看任务
```batch
schtasks /query /tn "策略框架_每周分析"
```

### 删除任务
```batch
schtasks /delete /tn "策略框架_每周分析" /f
```

### 修改时间
1. 打开"任务计划程序"（Task Scheduler）
2. 找到 `策略框架_每周分析`
3. 右键 → 属性 → 触发器 → 编辑

---

## ⚠️ 注意事项

1. **管理员权限**: 设置定时任务需要管理员权限
2. **Python环境**: 确保Python已添加到系统PATH
3. **依赖包**: 运行前确保已安装所需包
   ```bash
   pip install pandas numpy matplotlib akshare yfinance
   ```
4. **网络连接**: 分析需要联网获取数据
5. **执行时间**: 完整分析约需15-25分钟

---

## 🐛 故障排除

### 问题1: "Python未安装"
**解决**: 安装Python并添加到PATH

### 问题2: "创建任务失败"
**解决**: 右键以管理员身份运行 setup_weekly_job.bat

### 问题3: 脚本执行超时
**解决**: 检查网络连接，或增加timeout参数

### 问题4: 中文显示乱码
**解决**: 确保使用chcp 65001 (UTF-8)编码

---

## 📧 联系支持

如有问题，请查看执行日志：`Results/Report_日期/execution_log.txt`
