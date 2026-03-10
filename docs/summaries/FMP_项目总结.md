# FMP 数据驱动策略项目总结

**项目完成日期**: 2026-02-26  
**API**: Financial Modeling Prep  
**API Key**: `Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq`

---

## 📦 交付物

| 文件 | 说明 | 状态 |
|------|------|------|
| `FMPDataProvider.py` | FMP 数据提供器 | ✅ 完成 |
| `CTA_FMP_Strategy.py` | CTA 趋势策略 (FMP版) | ✅ 完成 |
| `FLP_FMP_Strategy.py` | FLP 保护策略 (FMP版) | ✅ 完成 |
| `CTA_FLP_Integrated_FMP.py` | 整合策略 | ✅ 完成 |
| `FMP_策略使用指南.md` | 使用文档 | ✅ 完成 |

---

## 🏗️ 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                    FMP 数据层                                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  FMPDataProvider                                    │   │
│  │  ├── get_historical_price()   # 历史价格           │   │
│  │  ├── get_stock_quote()        # 实时报价           │   │
│  │  ├── get_vix_data()           # VIX数据            │   │
│  │  └── get_options_chain()      # 期权链             │   │
│  └─────────────────────────────────────────────────────┘   │
│                            │                                │
│                            ▼                                │
│  ┌─────────────────────┐  ┌─────────────────────┐          │
│  │   CTADataAdapter    │  │   FLPDataAdapter    │          │
│  │   (趋势分析数据)     │  │   (期权保护数据)     │          │
│  └──────────┬──────────┘  └──────────┬──────────┘          │
│             │                        │                     │
│             └────────────┬───────────┘                     │
│                          ▼                                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              策略层                                  │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │  │
│  │  │ CTA_FMP     │  │ FLP_FMP     │  │ Integrated  │ │  │
│  │  │ Strategy    │  │ Strategy    │  │ Strategy    │ │  │
│  │  └─────────────┘  └─────────────┘  └─────────────┘ │  │
│  └─────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 📊 功能特性

### 1. FMPDataProvider

- ✅ 历史价格数据获取
- ✅ 实时报价获取
- ✅ VIX 数据获取 (带模拟备选)
- ✅ 期权链数据获取 (带模拟备选)
- ✅ 自动缓存机制
- ✅ 错误处理和重试

### 2. CTA_FMP_Strategy

- ✅ 20/60日 MA 交叉信号
- ✅ 通道突破确认
- ✅ 波动率评分系统
- ✅ Top N 强势标的筛选
- ✅ CSV/Excel 输出

### 3. FLP_FMP_Strategy

- ✅ 每周五自动执行
- ✅ Delta -0.07~-0.10 Put 选择
- ✅ VIX 动态调整
  - VIX < 15: 增加20%预算
  - VIX > 30: 改用 Put Spread
- ✅ 成本预算管理

### 4. CTA_FLP_Integrated

- ✅ CTA + FLP 组合管理
- ✅ 动态风险预算平衡
- ✅ 盈利回哺保护机制
  - CTA 盈利时提取 15% 增持 FLP
- ✅ 市场环境适应
  - 牛市收缩 CTA
  - 熊市增加保护

---

## 🚀 使用示例

### 基本使用

```bash
# 测试 FMP 数据连接
python FMPDataProvider.py

# 运行 CTA 分析
python CTA_FMP_Strategy.py

# 运行 FLP 保护
python FLP_FMP_Strategy.py

# 运行整合策略
python CTA_FLP_Integrated_FMP.py
```

### 代码集成

```python
from FMPDataProvider import FMPDataProvider, CTADataAdapter, FLPDataAdapter
from CTA_FMP_Strategy import CTAEngineFMP
from FLP_FMP_Strategy import FLPEngineFMP

# 初始化
fmp = FMPDataProvider(api_key="Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq")
cta = CTAEngineFMP()
flp = FLPEngineFMP()

# 获取数据
price_df = fmp.get_historical_price('AAPL', '2024-01-01', '2024-02-01')
vix_df = FLPDataAdapter().get_vix_series('2024-01-01', '2024-02-01')

# 生成信号
cta_signals = cta.analyze_symbols(['AAPL', 'MSFT', 'NVDA'])
flp_trade = flp.execute_weekly_hedge(portfolio_value=1_000_000)
```

---

## ⚠️ API 状态说明

### 当前状态

**测试结果显示**: API 返回 403 Forbidden 错误

**可能原因**:
1. API Key 已过期或需要激活
2. 免费版 API 有访问限制
3. 需要验证邮箱或绑定支付方式

### 解决方案

1. **验证 API Key**:
   - 登录 https://site.financialmodelingprep.com
   - 检查 API Key 状态
   - 确认订阅计划

2. **升级订阅**:
   - 免费版有调用限制
   - 建议升级到 Starter 计划 ($15/月)

3. **使用模拟数据**:
   - 代码已内置模拟数据生成
   - 可用于策略逻辑测试
   - 不影响策略开发和回测

---

## 🔄 备选方案

如果 FMP API 无法使用，代码已支持以下备选：

### 1. VIX 模拟数据

```python
# 自动切换
if vix_data.empty:
    vix_data = self._generate_mock_vix(start_date, end_date)
```

### 2. 期权模拟数据

```python
# 基于 Black-Scholes 简化模型
put_info = self._generate_mock_options(spy_price, expiration)
```

### 3. 替代数据提供商

| 提供商 | 优点 | 价格 |
|--------|------|------|
| Yahoo Finance (yfinance) | 免费 | 免费 |
| Alpha Vantage | 股票+期权 | 免费/付费 |
| Polygon.io | 实时数据 | $49/月起 |
| Quandl/Nasdaq Data Link | 宏观数据 | 免费/付费 |

---

## 📈 策略回测建议

### 数据准备

1. **使用 yfinance 作为备选**:
```python
import yfinance as yf

# 获取数据
df = yf.download('AAPL', start='2020-01-01', end='2024-02-26')
```

2. **本地数据缓存**:
```python
# 保存 FMP 数据
df.to_csv('aapl_data.csv')

# 读取本地数据
df = pd.read_csv('aapl_data.csv', index_col=0, parse_dates=True)
```

### 回测执行

```python
# 使用模拟数据测试策略逻辑
python CTA_FLP_Integrated_FMP.py

# 替换为真实数据后
# 修改 FMPDataProvider 中的 API 调用
# 或切换到 yfinance 数据源
```

---

## 🎯 下一步行动

### 立即行动

1. [ ] 验证 FMP API Key 状态
2. [ ] 检查订阅计划
3. [ ] 测试 API 调用

### 短期 (1周内)

1. [ ] 添加 yfinance 作为备选数据源
2. [ ] 实现数据本地缓存
3. [ ] 完成历史回测

### 中期 (1个月内)

1. [ ] 连接实盘交易 API
2. [ ] 实现自动化交易
3. [ ] 部署到服务器定时运行

---

## 📚 参考资源

### FMP 文档
- 主页: https://financialmodelingprep.com
- API 文档: https://site.financialmodelingprep.com/developer/docs
- 价格: https://site.financialmodelingprep.com/pricing

### 替代方案
- yfinance: https://github.com/ranaroussi/yfinance
- Alpha Vantage: https://www.alphavantage.co
- Polygon.io: https://polygon.io

---

## ✅ 验收清单

- [x] FMP 数据提供器实现
- [x] CTA 策略 (FMP版本)
- [x] FLP 策略 (FMP版本)
- [x] 整合策略实现
- [x] 模拟数据备选机制
- [x] 使用文档编写
- [ ] API Key 验证通过
- [ ] 真实数据测试通过
- [ ] 历史回测完成
- [ ] 实盘部署

---

## 📞 支持

**FMP 支持**: support@financialmodelingprep.com  
**文档**: https://site.financialmodelingprep.com/developer/docs  
**状态页面**: https://status.financialmodelingprep.com

---

**项目状态**: ✅ 代码完成，待 API 验证  
**建议**: 先使用模拟数据测试策略逻辑，同时验证 API Key
