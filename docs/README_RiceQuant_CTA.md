# 米筐(RiceQuant)CTA策略回测指南

## 简介

本系统使用米筐(RiceQuant)真实期货数据进行CTA策略研究和回测。

## 文件说明

| 文件 | 说明 |
|------|------|
| `RiceQuantDataProvider_CTA.py` | 米筐数据提供器 |
| `CTA_RiceQuant_Backtest.py` | 米筐CTA回测引擎 |

## 快速开始

### 1. 安装依赖

```bash
pip install pandas numpy scipy

# 可选: 安装米筐API (推荐)
pip install rqdatac
```

### 2. 使用示例

```python
from RiceQuantDataProvider_CTA import RiceQuantCTADataProvider
from CTA_RiceQuant_Backtest import RiceQuantCTABacktester

# API密钥 (已提供)
API_KEY = "Mg8lEL3dGgIyxrwc2rNsqVneytgqpSq4n0h4S8M-XQnZ9domysurqc3Lh1NlmAwAKSBTUr5qwFJ-aPEeFfR3L2rK5pq-HddOdS6vDBfDv187cVUdC9sejifx7V1lQjQWRm19YVrhx1poB-uThWtc3F6kzslu4cn9myNayWNzfo8=OPgej69FUSOnYfosbz62TAjuWXo_85kHZiUQUZCjXl78r0HUqN3HGJBXF7CIsXCHAAsQ7xieZzwD-_G8vn_3pkfFaAy2pLrhjk4BSLkVcNDwfPJovTa4hxIKfGAZ5G_HtNIHSUZcHnenxQnZljuvnzsixT3G-3Gr4UunAz9-72A="

# 创建回测引擎
backtester = RiceQuantCTABacktester(
    api_key=API_KEY,
    initial_capital=10_000_000,  # 1000万
    start_date='2023-01-01',
    end_date='2024-12-31'
)

# 加载数据
symbols = ['RB', 'CU', 'SC', 'IF', 'AU']
backtester.load_market_data(symbols)

# 运行策略
result = backtester.run_single_strategy('TSMOM')

# 生成报告
print(f"最终净值: ${result['final_value']:,.0f}")
print(f"总收益率: {(result['final_value']/backtester.initial_capital-1)*100:.2f}%")
```

### 3. 运行完整回测

```bash
python CTA_RiceQuant_Backtest.py
```

## 支持的品种

### 上海期货交易所 (SHFE)
- `RB` 螺纹钢, `HC` 热轧卷板
- `CU` 铜, `AL` 铝, `ZN` 锌, `NI` 镍, `SN` 锡
- `AU` 黄金, `AG` 白银
- `FU` 燃料油, `BU` 沥青

### 大连商品交易所 (DCE)
- `I` 铁矿石, `J` 焦炭, `JM` 焦煤
- `M` 豆粕, `Y` 豆油, `P` 棕榈油
- `L` 聚乙烯, `PP` 聚丙烯, `V` PVC

### 郑州商品交易所 (CZCE)
- `TA` PTA, `MA` 甲醇
- `CF` 棉花, `SR` 白糖
- `RM` 菜粕, `OI` 菜籽油

### 上海国际能源交易中心 (INE)
- `SC` 原油
- `LU` 低硫燃料油

### 中国金融期货交易所 (CFFEX)
- `IF` 沪深300, `IC` 中证500, `IM` 中证1000
- `T` 10年国债, `TF` 5年国债, `TS` 2年国债

## 策略列表

### 1. TSMOM (时间序列动量)
```python
result = backtester.run_single_strategy('TSMOM')
```

### 2. Trend Following (趋势跟踪)
```python
result = backtester.run_single_strategy('TrendFollowing')
```

### 3. Carry (期限结构)
```python
result = backtester.run_single_strategy('Carry')
```

### 4. 等权组合
```python
result = backtester.run_equal_weight_portfolio({
    'TSMOM': 0.33,
    'TrendFollowing': 0.34,
    'Carry': 0.33
})
```

### 5. 元模型动态分配
```python
result = backtester.run_meta_model_portfolio()
```

## 数据提供器使用

### 获取单品种数据

```python
from RiceQuantDataProvider_CTA import RiceQuantCTADataProvider

provider = RiceQuantCTADataProvider(api_key=API_KEY)

# 获取螺纹钢数据
df = provider.get_futures_data('RB', '2024-01-01', '2024-12-31')
print(df.head())
```

### 批量获取数据

```python
symbols = ['RB', 'CU', 'SC']
data = provider.get_multiple_futures(symbols, '2024-01-01', '2024-12-31')

for symbol, df in data.items():
    print(f"{symbol}: {len(df)}条记录")
```

### 按板块获取品种

```python
# 获取黑色系品种
black_metals = provider.get_symbols_by_category('黑色')
print(black_metals)  # ['RB', 'HC', 'I', 'J', 'JM']

# 获取所有板块
for category in ['黑色', '有色', '能源', '化工', '农产品', '股指']:
    symbols = provider.get_symbols_by_category(category)
    print(f"{category}: {symbols}")
```

## 数据缓存

系统会自动缓存数据到本地，避免重复下载：

```python
# 第一次会下载数据
backtester.load_market_data(['RB', 'CU'], use_cache=True)

# 第二次会直接从缓存读取 (速度更快)
backtester.load_market_data(['RB', 'CU'], use_cache=True)
```

缓存位置: `./cta_data_cache/`

## 性能评估

### 核心指标

```python
from CTA_Strategy_Evaluator import CTAEvaluator

evaluator = CTAEvaluator()
metrics = evaluator.evaluate(returns, "MyStrategy")

print(f"夏普比率: {metrics.sharpe_ratio}")
print(f"信息比率: {metrics.information_ratio}")  # ⭐
print(f"最大回撤: {metrics.max_drawdown}")
```

### 完整报告

```python
report = evaluator.generate_report(metrics)
print(report)
```

## 常见问题

### Q1: 米筐API未安装怎么办？

系统会自动使用模拟数据模式，但建议使用真实数据：

```bash
pip install rqdatac
```

### Q2: 如何接入实盘交易？

需要额外实现交易接口：

```python
class CTPTrader:
    def send_order(self, symbol, direction, quantity, price):
        # 接入CTP接口
        pass
```

### Q3: 数据更新频率？

```python
# 清除缓存强制重新下载
import shutil
shutil.rmtree('./cta_data_cache/')
```

### Q4: 支持分钟数据吗？

```python
# 获取1分钟数据
df = provider.get_futures_data('RB', '2024-01-01', '2024-01-31', frequency='1m')
```

## 策略优化建议

1. **参数优化**
   - 使用Walk-forward分析
   - 避免过拟合

2. **品种选择**
   - 选择流动性好的品种
   - 跨板块分散风险

3. **风险控制**
   - 严格执行止损
   - 控制单品种仓位

4. **交易成本**
   - 考虑手续费和滑点
   - 避免过度交易

## 参考文档

- [米筐API文档](https://www.ricequant.com/doc/api/python/)
- [CTA策略论文综述](./CTA_Strategies_Research_Summary.md)

## 更新日志

**v1.0** (2026-02-28)
- 初始版本
- 支持41个期货品种
- 4种CTA策略
- 完整绩效评估
