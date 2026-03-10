# 美股量化分析框架 V1.0

一个完整的美股量化分析系统，整合**技术分析**、**基本面分析**、**宏观分析**和**策略回测**，实现每周自动化报告生成。

## 项目结构

```
StrategyFrame/
│
├── Strategy_Framework/          # 核心策略框架
│   ├── 01_Macro_Analysis/       # 宏观分析 (美联储流动性, CTA+FLP策略)
│   ├── 02_MultiFactor_CTA_RiceQuant/  # 多因子CTA (米筐平台)
│   ├── 02_Sector_Analysis/      # 行业分析 (CSI A500, 财报交叉分析)
│   ├── 03_Stock_Selection/      # 选股模块 (Mag7追踪, PB-ROE, 技术形态)
│   │   └── PatternStrategy_A500/    # A500形态策略子项目
│   ├── 04_Strategy_Execution/   # 策略执行 (CTA回测, 期货策略)
│   │   └── CTA_FLP_Strategy/        # CTA+FLP策略子项目
│   ├── 05_Risk_Management/      # 风控模块
│   ├── 06_Backtesting/          # 回测引擎
│   ├── 07_Reporting/            # 报告生成 & 可视化
│   ├── data_providers/          # 数据源适配器 (FMP, 米筐, Tradier, YFinance)
│   ├── Results/                 # 框架生成的结果
│   ├── docs/                    # 框架内部文档
│   └── papers/                  # 参考论文
│
├── docs/                        # 项目文档
│   ├── guides/                  # 使用指南
│   ├── summaries/               # 项目总结
│   └── project_notes/           # 技术笔记 & 修复记录
│
├── data/                        # 数据文件
│   ├── csv/                     # CSV原始数据
│   ├── excel/                   # Excel模板 & 分析表
│   ├── cache/                   # API缓存 (Finnhub等)
│   └── charts/                  # 图表输出
│
├── presentations/               # 演示文件 (PPT, PDF)
├── reports/                     # 生成的分析报告 (按日期)
└── scripts/                     # 工具脚本
    ├── tools/                   # 实用工具 (安装, 验证, 图表生成)
    └── demo/                    # 演示/测试脚本
```

## 核心能力

- **智能选股** - CTA技术指标排名，识别强势个股
- **预期分析** - 财报后市场反应，识别预期差
- **宏观判断** - 美联储流动性，判断市场环境
- **策略验证** - 回测系统，验证信号有效性
- **自动周报** - 每周自动生成报告

## 快速开始

```bash
# 1. 查看框架详解
cat docs/美股量化分析框架V1.0.md

# 2. 运行策略管线
python Strategy_Framework/run_strategy_pipeline.py

# 3. 查看报告
ls reports/
```

## 技术栈

- **Python 3.11+**
- **数据源**: AkShare, Finnhub API, FRED API, FMP, 米筐(RiceQuant)
- **核心库**: pandas, numpy, akshare, openpyxl

## 信号表现

| 信号类型 | 20日平均收益 | 准确度 |
|----------|-------------|--------|
| BUY      | +11.82%     | 高     |
| HOLD     | -3.61%      | 中性   |
| SELL     | -16.94%     | 高     |

## 文档导航

- **初学者**: [框架详解](docs/美股量化分析框架V1.0.md) -> [快速参考卡](docs/guides/框架快速参考卡.md) -> [文档导航图](docs/guides/文档导航图.md)
- **策略使用**: [CTA_FLP指南](docs/guides/CTA_FLP_策略使用指南.md) | [FMP指南](docs/guides/FMP_策略使用指南.md) | [期权决策](docs/guides/期权策略决策流程.md)
- **开发者**: [Strategy Framework README](Strategy_Framework/README.md) | [所有策略概览](docs/README_All_Strategies.md)

## 免责声明

本框架仅供学习和研究使用，不构成投资建议。历史回测结果不代表未来收益。
