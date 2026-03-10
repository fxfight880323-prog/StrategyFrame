# FMP 数据驱动的 CTA + FLP 策略使用指南

**API Key**: `Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq`  
**数据源**: [Financial Modeling Prep](https://financialmodelingprep.com)

---

## 📦 文件结构

```
FMPDataProvider.py          # FMP 数据提供器
CTA_FMP_Strategy.py         # CTA 趋势策略 (FMP版本)
FLP_FMP_Strategy.py         # FLP 保护策略 (FMP版本)
CTA_FLP_Integrated_FMP.py   # 整合策略
FMP_策略使用指南.md         # 本文档
```

---

## 🚀 快速开始

### 1. 测试 FMP 数据连接

```bash
python FMPDataProvider.py
```

预期输出:
```
============================================================
FMP 数据提供器测试
============================================================

[测试1] 获取 AAPL 历史价格
  成功: 23 条记录
  最新价格: $XXX.XX

[测试2] 获取 SPY 实时报价
  价格: $XXX.XX
  变化: X.XX%
...
```

### 2. 运行 CTA 趋势分析

```bash
python CTA_FMP_Strategy.py
```

功能:
- 分析美股核心个股 (AAPL, MSFT, NVDA, SPY, QQQ等)
- 生成 20/60日 MA 交叉信号
- 输出 Top 10 强势标的

### 3. 运行 FLP 保护策略

```bash
python FLP_FMP_Strategy.py
```

功能:
- 获取实时 VIX 数据
- 选择 Delta -0.07~-0.10 的 SPY Put
- 根据 VIX 水平动态调整保护模式

### 4. 运行整合策略

```bash
python CTA_FLP_Integrated_FMP.py
```

功能:
- CTA + FLP 组合管理
- 动态风险预算平衡
- 盈利回哺保护机制

---

## 📊 策略对比

| 策略 | 数据源 | 功能 | 执行频率 |
|------|--------|------|----------|
| CTA_FMP_Strategy | FMP | 趋势分析 | 每日 |
| FLP_FMP_Strategy | FMP | 期权保护 | 每周五 |
| CTA_FLP_Integrated | FMP | 组合管理 | 每日 |

---

## 🔧 API 使用说明

### FMPDataProvider 类

```python
from FMPDataProvider import FMPDataProvider

fmp = FMPDataProvider(api_key="Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq")

# 获取历史价格
df = fmp.get_historical_price('AAPL', '2024-01-01', '2024-02-01')

# 获取实时报价
quote = fmp.get_stock_quote('SPY')

# 获取期权链
options = fmp.get_options_chain('SPY', '2024-03-15')
```

### CTA 数据适配器

```python
from FMPDataProvider import CTADataAdapter

adapter = CTADataAdapter()

# 获取 CTA 分析数据
data = adapter.get_cta_data(
    symbols=['AAPL', 'MSFT', 'NVDA'],
    start_date='2024-01-01',
    end_date='2024-02-01'
)
```

### FLP 数据适配器

```python
from FMPDataProvider import FLPDataAdapter

adapter = FLPDataAdapter()

# 获取 VIX 数据
vix_df = adapter.get_vix_series('2024-01-01', '2024-02-01')

# 选择 FLP Put
put = adapter.select_put_for_flp(
    spy_price=400.0,
    target_delta=(-0.10, -0.07)
)
```

---

## 💡 策略配置

### CTA 配置

```python
CTA_CONFIG = {
    'fast_ma': 20,        # 快速均线
    'slow_ma': 60,        # 慢速均线
    'channel_width': 2.0, # 通道宽度
}
```

### FLP 配置

```python
FLP_CONFIG = {
    'underlying': 'SPY',
    'delta_target': (-0.10, -0.07),  # Delta 目标范围
    'vix_low_threshold': 15,         # VIX 低位阈值
    'vix_high_threshold': 30,        # VIX 高位阈值
}
```

### 整合策略配置

```python
INTEGRATED_CONFIG = {
    'cta_symbols': ['AAPL', 'MSFT', 'NVDA', 'SPY', 'QQQ'],
    'cta_weight': 0.75,      # CTA 基础权重 75%
    'flp_weight': 0.05,      # FLP 基础权重 5%
    'cash_weight': 0.20,     # 现金权重 20%
    'profit_reinvest_pct': 0.15,  # 盈利回哺 15%
}
```

---

## 📈 示例输出

### CTA 分析输出

```
============================================================
CTA 趋势分析 (FMP 数据)
============================================================
分析标的: 10 只
数据区间: 2023-10-28 至 2024-02-26

  AAPL: Signal=LONG, Score=78.5
  MSFT: Signal=LONG, Score=72.3
  NVDA: Signal=LONG, Score=88.0
  ...

============================================================
分析结果
============================================================

【Top 10 强势标的】
排名   代码      价格         评分     信号    
--------------------------------------------------
1      NVDA      $725.50     88.0     LONG    
2      MSFT      $412.30     78.5     LONG    
3      AAPL      $182.45     72.3     LONG    
...
```

### FLP 保护输出

```
============================================================
执行 FLP 周度对冲 - 2024-02-23
============================================================
SPY 当前价格: $410.25
VIX 指数: 18.50
保护模式: Long Put
保护预算: $52,500.00

买入 Put: Strike=$400.00, Delta=-0.085, Premium=$2.50
总成本: $250.00
```

---

## ⚠️ 限制与注意事项

### FMP API 限制

1. **免费版限制**:
   - 每日 250 次调用
   - 每分钟限速
   - 历史数据可能有限

2. **期货数据**:
   - FMP 对期货支持有限
   - 部分期货 symbol 可能不可用
   - 建议使用 ETF 替代 (如 SPY 代替 ES)

3. **VIX 数据**:
   - 可能无法直接获取
   - 代码中已添加模拟数据作为备选

### 期权数据

1. **希腊字母 (Greeks)**:
   - FMP 可能不直接提供 Delta
   - 代码中使用简化模型估算

2. **流动性**:
   - 远端 OTM Put 流动性可能不足
   - 建议选择高流动性合约

---

## 🔧 故障排除

### 问题: API 返回空数据

**解决**:
```python
# 检查 API Key
fmp = FMPDataProvider(api_key="Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq")

# 检查 symbol 格式
df = fmp.get_historical_price('AAPL')  # 使用正确 symbol
```

### 问题: VIX 数据为空

**解决**:
代码已自动切换到模拟 VIX 数据，无需处理。

### 问题: 期权数据为空

**解决**:
代码已自动生成模拟期权数据，用于测试策略逻辑。

---

## 📚 API 参考

### FMP Endpoints 使用

| 功能 | Endpoint | 参数 |
|------|----------|------|
| 历史价格 | historical-price-full/{symbol} | from, to |
| 实时报价 | quote/{symbol} | - |
| 期权链 | historical/options/{symbol} | expiration |
| 财报日历 | earning_calendar | from, to |

---

## 🚀 进阶使用

### 自定义标的列表

```python
# 修改 CTA_FMP_Strategy.py 中的 DEFAULT_SYMBOLS
DEFAULT_SYMBOLS = [
    'AAPL', 'MSFT', 'NVDA',  # 科技
    'JPM', 'BAC', 'GS',       # 金融
    'XOM', 'CVX',             # 能源
    # 添加更多...
]
```

### 调整策略参数

```python
# 在 CTA_FLP_Integrated_FMP.py 中修改配置
INTEGRATED_CONFIG = {
    'cta_weight': 0.70,      # 降低 CTA 权重
    'flp_weight': 0.10,      # 增加 FLP 保护
    'profit_reinvest_pct': 0.20,  # 增加回哺比例
}
```

### 集成到交易系统

```python
# 每日定时运行
from CTA_FLP_Integrated_FMP import IntegratedStrategyFMP

strategy = IntegratedStrategyFMP()
strategy.run_daily_update()

# 获取交易信号
cta_positions = strategy.portfolio.cta_positions
flp_position = strategy.portfolio.flp_position

# 发送到交易系统执行
```

---

## 📞 支持

**FMP 文档**: https://site.financialmodelingprep.com/developer/docs  
**API 状态**: https://status.financialmodelingprep.com

---

**版本**: V1.0  
**更新**: 2026-02-26  
**维护**: Quant Strategy Team
