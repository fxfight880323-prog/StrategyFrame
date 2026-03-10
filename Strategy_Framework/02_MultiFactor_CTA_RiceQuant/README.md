# 多因子选股 + CTA 策略 (米筐回测框架)

## 策略概述

本策略整合**多因子选股**和**CTA趋势跟踪**，构建一个多资产、多策略的量化投资组合。

### 核心特点

| 特性 | 说明 |
|------|------|
| **资产配置** | 股票 70% + CTA 30% |
| **换仓频率** | 周度换仓 (每周一) |
| **选股范围** | 沪深300成分股 (可配置) |
| **CTA品种** | 商品期货 + 股指期货 |
| **风险控制** | 个股权重上限 10%，止损 8% |

---

## 策略架构

```
┌─────────────────────────────────────────────────────────────────┐
│                      策略架构图                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────────────┐      ┌──────────────────────┐       │
│   │     多因子选股        │      │      CTA策略          │       │
│   │   (股票 70%)         │      │   (期货 30%)         │       │
│   ├──────────────────────┤      ├──────────────────────┤       │
│   │ • 价值因子: PE, PB   │      │ • 时间序列动量       │       │
│   │ • 质量因子: ROE, ROA │      │ • 趋势跟踪           │       │
│   │ • 成长因子: 营收增长 │      │ • 波动率目标         │       │
│   │ • 技术因子: 动量     │      │ • 跨品种套利         │       │
│   └──────────┬───────────┘      └──────────┬───────────┘       │
│              │                              │                   │
│              └──────────────┬───────────────┘                   │
│                             ▼                                   │
│              ┌──────────────────────────┐                      │
│              │      组合管理器          │                      │
│              │  • 资产配置              │                      │
│              │  • 风险平衡              │                      │
│              │  • 周度再平衡            │                      │
│              └──────────┬───────────────┘                      │
│                         ▼                                      │
│              ┌──────────────────────────┐                      │
│              │    米筐回测框架          │                      │
│              │  • 模拟回测              │                      │
│              │  • 实盘交易 (扩展)       │                      │
│              └──────────────────────────┘                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 文件结构

```
02_MultiFactor_CTA_RiceQuant/
├── config.py                    # 策略配置文件
├── factor_model.py              # 多因子选股模型
├── cta_signals.py               # CTA信号生成
├── portfolio_manager.py         # 组合管理器
├── ricequant_backtest.py        # 米筐回测框架
├── valmom_backtest.py           # ValMomEverywhere 回测
├── run_valmom_backtest.py       # ValMomEverywhere 运行脚本
├── strategy_main.py             # 策略主程序
├── README.md                    # 本文件
├── requirements.txt             # 依赖列表
└── backtests/                   # 回测结果文件夹
    ├── README.md                # 回测结果说明
    ├── valmom_results.json      # 回测结果数据
    ├── valmom_equity.png        # 净值曲线图
    └── valmom_drawdown.png      # 回撤曲线图
```

---

## 安装依赖

```bash
# 安装基础依赖
pip install pandas numpy

# 安装米筐SDK (需要API Key)
pip install rqdatac

# 安装回测框架
pip install rqalpha
```

---

## 配置说明

### API Key 配置

在 `config.py` 中配置米筐API Key:

```python
RQ_API_KEY = "你的米筐API Key"
```

### 策略参数配置

```python
# config.py

StrategyConfig(
    # 基础配置
    INITIAL_CAPITAL = 10_000_000,    # 初始资金 1000万
    
    # 换仓配置
    REBALANCE_FREQUENCY = "weekly",   # 周度换仓
    REBALANCE_DAY = 1,                # 周一换仓
    
    # 股票池配置
    STOCK_UNIVERSE = "hs300",         # 沪深300
    MAX_STOCK_HOLDINGS = 20,          # 最多持仓20只股票
    
    # 资产配置
    STOCK_ALLOCATION = 0.70,          # 股票仓位 70%
    CTA_ALLOCATION = 0.30,            # CTA仓位 30%
    
    # 风控配置
    MAX_SINGLE_STOCK_WEIGHT = 0.10,   # 个股最大权重 10%
    STOP_LOSS_PCT = 0.08,             # 止损线 8%
)
```

---

## 使用方法

### 1. 快速回测

```bash
# 运行默认回测 (2022-01-01 至 2024-12-31)
python strategy_main.py

# 指定回测期间
python strategy_main.py --backtest --start 2023-01-01 --end 2024-01-01
```

### 2. 生成今日信号

```bash
# 获取今日选股和CTA信号
python strategy_main.py --signal
```

### 3. ValMomEverywhere 回测

基于 Asness, Moskowitz & Pedersen (2013) 经典论文：

```bash
# 运行价值和动量因子回测
python run_valmom_backtest.py

# 指定回测期间
python run_valmom_backtest.py --start 2022-01-01 --end 2024-01-01

# 快速测试
python run_valmom_backtest.py --quick

# 只回测单个因子
python run_valmom_backtest.py --factor value
python run_valmom_backtest.py --factor momentum
python run_valmom_backtest.py --factor combo
```

回测结果保存在 `backtests/` 文件夹中：
- `valmom_results.json` - 完整回测数据
- `valmom_equity.png` - 净值曲线图
- `valmom_drawdown.png` - 回撤曲线图

### 4. 单独使用模块

#### 多因子选股

```python
from factor_model import quick_screen

# 快速选股
result = quick_screen(
    universe="hs300",      # 股票池
    date="2024-03-01",     # 选股日期
    top_n=20               # 选择前20只
)

print(result[['symbol', 'total_score', 'rank']])
```

#### CTA信号

```python
from cta_signals import get_cta_signals

# 获取CTA信号
signals = get_cta_signals(
    symbols=['RB', 'CU', 'SC', 'IF']  # 品种代码
)

for sym, sig in signals.items():
    print(f"{sym}: {sig.signal.name}, Position: {sig.target_position:.2f}")
```

#### 组合回测

```python
from ricequant_backtest import quick_backtest

# 运行回测
result = quick_backtest(
    start_date="2023-01-01",
    end_date="2024-01-01"
)

# 查看结果
print(f"总收益率: {result.total_return*100:.2f}%")
print(f"夏普比率: {result.sharpe_ratio:.2f}")
```

---

## 因子配置

### 默认因子权重

```python
FACTOR_WEIGHTS = {
    # 价值因子 (40%)
    'pe_ttm': -0.15,              # 市盈率TTM (负向)
    'pb': -0.15,                  # 市净率 (负向)
    'ps_ttm': -0.10,              # 市销率TTM (负向)
    
    # 质量因子 (45%)
    'roe': 0.20,                  # ROE (正向)
    'roa': 0.15,                  # ROA (正向)
    'gross_profit_margin': 0.10,  # 毛利率 (正向)
    
    # 成长因子 (20%)
    'revenue_growth': 0.10,       # 营收增长 (正向)
    'profit_growth': 0.10,        # 利润增长 (正向)
    
    # 技术因子 (15%)
    'momentum_20': 0.15,          # 20日动量 (正向)
}
```

### 自定义因子

```python
from factor_model import MultiFactorModel

# 自定义因子权重
my_factors = {
    'pe_ttm': -0.25,
    'pb': -0.25,
    'roe': 0.30,
    'momentum_20': 0.20,
}

model = MultiFactorModel(factor_weights=my_factors)
```

---

## CTA策略配置

### 支持的品种

| 类别 | 代码 | 名称 |
|------|------|------|
| 黑色金属 | RB | 螺纹钢 |
| | HC | 热轧卷板 |
| | I | 铁矿石 |
| 有色金属 | CU | 铜 |
| | AL | 铝 |
| | ZN | 锌 |
| 能源化工 | SC | 原油 |
| | TA | PTA |
| | MA | 甲醇 |
| 股指期货 | IF | 沪深300 |
| | IC | 中证500 |

### CTA信号参数

```python
CTA_CONFIG = {
    'time_series_momentum': {
        'enabled': True,
        'lookback_periods': [20, 60, 120],  # 多周期动量
        'weights': [0.5, 0.3, 0.2],
        'volatility_target': 0.10,           # 10%目标波动率
    },
    
    'trend_following': {
        'enabled': True,
        'short_window': 20,
        'medium_window': 60,
        'long_window': 120,
    }
}
```

---

## 回测结果解读

### 示例输出

```
======================================================================
回测报告
======================================================================

回测期间: 2023-01-01 至 2024-01-01
初始资金: 10,000,000
期末价值: 11,500,000

【收益指标】
  总收益率:      15.00%
  年化收益率:    15.00%

【风险指标】
  年化波动率:    12.00%
  最大回撤:      -8.00%

【风险调整收益】
  夏普比率:       1.25
  Sortino比率:    1.80
  Calmar比率:     1.88

【交易统计】
  总交易次数:     120
  胜率:          55.00%
```

### 关键指标说明

| 指标 | 说明 | 优秀标准 |
|------|------|----------|
| 夏普比率 | 风险调整收益 | > 1.0 |
| 最大回撤 | 最大资金回落 | < 15% |
| 胜率 | 盈利交易占比 | > 50% |
| Calmar比率 | 收益/回撤比 | > 1.0 |

---

## 风险管理

### 内置风控机制

1. **仓位限制**
   - 个股最大权重: 10%
   - 单个期货品种最大权重: 5%
   - 总杠杆上限: 1.5x

2. **止损机制**
   - 个股止损线: 8%
   - 组合回撤限制: 15%

3. **风险检查**
   - 换仓前自动检查风险限制
   - 违反限制时发出警告

### 风险预警条件

```python
# 模型失效预警
RED_FLAGS = [
    '通胀反弹超过4%',
    '失业率突破5.5%',
    '债务上限技术性违约',
]
```

---

## 策略优化方向

### 1. 因子优化

```python
# 添加更多因子
FACTOR_WEIGHTS.update({
    'dividend_yield': 0.05,      # 股息率
    'earnings_momentum': 0.10,   # 盈利动量
    'turnover_adjusted_momentum': 0.10,  # 换手率调整动量
})
```

### 2. 动态资产配置

```python
# 基于市场状态的动态调整
def dynamic_allocation(market_state):
    if market_state['volatility'] > 0.25:
        return {'stock': 0.50, 'cta': 0.30, 'cash': 0.20}
    else:
        return {'stock': 0.70, 'cta': 0.30, 'cash': 0.00}
```

### 3. 机器学习增强

```python
# 使用机器学习预测因子收益
from sklearn.ensemble import RandomForestRegressor

model = RandomForestRegressor()
model.fit(X_factors, y_returns)
factor_weights = model.feature_importances_
```

---

## 常见问题

### Q1: 米筐API Key如何获取？

A: 访问 [米筐官网](https://www.ricequant.com) 注册账号并申请数据权限。

### Q2: 没有API Key能否使用？

A: 可以！框架会自动使用模拟数据进行回测，但结果仅供测试参考。

### Q3: 如何扩展更多期货品种？

A: 在 `cta_signals.py` 的 `SYMBOL_MAP` 中添加新品种代码映射。

### Q4: 策略适合实盘吗？

A: 策略提供了完整的回测框架，但实盘前建议：
1. 进行至少2年的滚动回测
2. 验证过拟合风险
3. 小规模试运行
4. 严格风控监控

---

## 更新日志

### v1.0.0 (2026-03-04)
- 初始版本发布
- 多因子选股框架
- CTA信号生成
- 米筐回测集成
- 周度换仓机制

---

## 联系与反馈

如有问题或建议，欢迎反馈！

---

**免责声明**: 本策略仅供研究和学习使用，不构成投资建议。投资有风险，入市需谨慎。
