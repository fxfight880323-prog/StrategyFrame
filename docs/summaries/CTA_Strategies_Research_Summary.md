# CTA策略前沿研究综述与复现指南

## 一、当前最热门的CTA策略论文 (2024-2025)

### 1. 时间序列动量 (Time Series Momentum / TSMOM) ⭐⭐⭐
**核心论文:**
- **Moskowitz et al. (2012)** - "Time Series Momentum" (Journal of Financial Economics)
- **Ming et al. (2023)** - "Revisiting time series momentum in China's commodity futures market" (Economic Modelling)
- **Huang et al. (2020)** - "Time series momentum: is it there?" (Journal of Financial Economics)

**策略原理:**
```
Signal = sign(Past Return over lookback period) × Volatility Scaling
Position ∝ (Return_t-12m to t-1m) / σ (ex-ante volatility)
```

**关键发现:**
- 1个月回看期在中国期货市场预测性最强
- 盈利主要来自空头头寸 (做空过去下跌的品种)
- 有效的市场择时能力是超额收益来源

**国内期货适用性:** ★★★★★

---

### 2. 趋势跟踪策略 (Trend Following) ⭐⭐⭐⭐
**核心论文/报告:**
- **Man Group (2025)** - "A Trend Following Deep Dive: The Optimal Market Mix"
- **Hurst et al. (2017)** - "A Century of Evidence on Trend-Following Investing"
- **Top Traders Unplugged (2025)** - Trend Following Performance Report

**策略变体:**

#### 2.1 通道突破 (Channel Breakout)
```python
Upper Channel = MA(Price, 20) + 2 × ATR(20)
Lower Channel = MA(Price, 20) - 2 × ATR(20)
Long Signal:  Close > Upper Channel
Short Signal: Close < Lower Channel
```

#### 2.2 移动平均交叉 (MA Crossover)
```python
Fast MA = MA(Close, 20)
Slow MA = MA(Close, 60)
Long Signal:  Fast MA > Slow MA
Short Signal: Fast MA < Slow MA
```

#### 2.3 多时间框架趋势 (Multi-Timeframe)
- 短期趋势 (5-10天): 捕捉快速波动
- 中期趋势 (20-60天): 主要盈利来源
- 长期趋势 (120-250天): 捕捉大行情

**关键发现:**
- 传统市场(股指、债券、外汇)提供"危机Alpha"
- 另类市场(小众商品)提供更高夏普比率
- 最优配置取决于投资者目标 (Max Sharpe vs Max Crisis Sharpe)

**国内期货适用性:** ★★★★★

---

### 3. Carry 策略 ⭐⭐⭐
**核心论文:**
- **ReSolve Asset Management (2024)** - "Managed Futures Carry: A Practitioner's Guide"
- **Koijen et al. (2018)** - Carry相关研究

**策略原理:**
```
Carry = Expected return from holding an investment (assuming no price change)
```

**实现方式:**

#### 3.1 期限结构Carry (Calendar Spread)
- 远月合约价格 > 近月合约: 做空价差 (Contango)
- 远月合约价格 < 近月合约: 做多价差 (Backwardation)

#### 3.2 跨品种Carry (Cross-sectional)
```python
# 在每个板块内
Long:  高Carry品种 (前20%)
Short: 低Carry品种 (后20%)
```

#### 3.3 时间序列Carry (Time-series)
```python
Long:  Carry > 0的品种
Short: Carry < 0的品种
```

**国内期货适用性:** ★★★★☆ (需要多合约数据)

---

### 4. 元模型/状态转换策略 (Meta-Models / Regime Switching) ⭐⭐⭐⭐
**核心论文/报告:**
- **Mandatum Asset Management (2025)** - "Meta-Models in Practice"
- **Baltas (2019)** - Crowding研究
- **Bollen et al. (2021)** - CTA相似性研究

**策略原理:**
```
动态调整权重 = f(市场环境, 策略近期表现, 波动率状态)
```

**关键组件:**

#### 4.1 状态识别模型 (Regime Detection)
- 高波动状态 vs 低波动状态
- 趋势状态 vs 震荡状态
- 危机状态识别

#### 4.2 动态权重分配
```python
if 高波动市场:
    降低整体仓位
    增加短期趋势权重
    增加保护性策略权重
elif 强趋势市场:
    增加中期趋势权重
    降低反转策略权重
```

**国内期货适用性:** ★★★★★

---

### 5. 机器学习增强CTA ⭐⭐⭐⭐
**核心论文:**
- **Gresham LLC (2025)** - "Systematic Strategies & Quant Trading"
- **各量化私募内部研究** (2024-2025)

**策略类型:**

#### 5.1 信号增强
- 使用ML筛选/组合多个技术信号
- 随机森林/GBDT预测趋势强度

#### 5.2 仓位优化
- 强化学习动态调整仓位
- 多目标优化 (收益 + 风险控制)

#### 5.3 执行优化
- 订单流预测
- 最优执行时间选择

**国内期货适用性:** ★★★★☆ (需要大量数据)

---

## 二、国内期货市场CTA策略特殊考虑

### 1. 市场特征
| 特征 | 说明 | 策略影响 |
|------|------|----------|
| 夜盘交易 | 多数商品有夜盘 | 信号计算需考虑连续性 |
| 涨跌停板 | 10%左右限制 | 需处理价格不连续 |
| 高散户比例 | 约70-80% | 行为金融学因子有效 |
| 强政策影响 | 保供稳价政策 | 需事件风险管理 |
| 合约不连续 | 每月换月 | 主力合约连续化处理 |

### 2. 数据获取方案
```python
# 推荐数据源
1. AKShare (免费) - 适合入门
2. Tushare Pro - 数据质量较好
3. 米筐(RiceQuant) - 专业级
4. 聚宽(JoinQuant) - 专业级
5. 通联数据 - 机构级
```

### 3. 合约选择
```python
# 主要板块
商品期货 = {
    '黑色': ['RB', 'HC', 'I', 'J', 'JM'],  # 螺纹钢、热卷、铁矿、焦炭、焦煤
    '有色': ['CU', 'AL', 'ZN', 'NI', 'SN'], # 铜、铝、锌、镍、锡
    '能源': ['SC', 'LU', 'FU'],              # 原油、低硫燃料油、燃料油
    '化工': ['TA', 'MA', 'PP', 'L', 'EG'],   # PTA、甲醇、聚丙烯、塑料、乙二醇
    '农产品': ['M', 'RM', 'OI', 'CF', 'SR'], # 豆粕、菜粕、菜油、棉花、白糖
    '贵金属': ['AU', 'AG']                   # 黄金、白银
}

金融期货 = {
    '股指': ['IF', 'IC', 'IM'],  # 沪深300、中证500、中证1000
    '国债': ['T', 'TF', 'TS']    # 10年、5年、2年国债
}
```

---

## 三、策略评估指标体系

### 1. 收益指标
```python
def calculate_return_metrics(returns):
    return {
        'Total_Return': '总收益率',
        'Annualized_Return': '年化收益率',
        'CAGR': '复合年增长率',
    }
```

### 2. 风险指标
```python
def calculate_risk_metrics(returns):
    return {
        'Volatility': '年化波动率',
        'Max_Drawdown': '最大回撤',
        'VaR_95': '95%风险价值',
        'CVaR_95': '95%条件风险价值',
    }
```

### 3. 风险调整后收益 ⭐
```python
def calculate_risk_adjusted_metrics(returns, risk_free_rate=0.03):
    return {
        'Sharpe_Ratio': '夏普比率',
        'Sortino_Ratio': '索提诺比率',
        'Information_Ratio': '信息比率',  # 相对基准
        'Calmar_Ratio': '卡玛比率',
        'Omega_Ratio': 'Omega比率',
        'Serenity_Ratio': 'Serenity比率',
    }
```

### 4. CTA特有指标
```python
def calculate_cta_metrics(returns, positions):
    return {
        'Win_Rate': '胜率',
        'Profit_Loss_Ratio': '盈亏比',
        'Avg_Win': '平均盈利',
        'Avg_Loss': '平均亏损',
        'Long_Short_Ratio': '多空时间比',
        'Correlation_to_Equity': '与股市相关性',
        'Crisis_Alpha': '危机Alpha',
    }
```

---

## 四、组合风控框架

### 1. 事前风控 (Pre-trade)
```python
- 单品种仓位限制: ≤ 10%
- 板块集中度限制: ≤ 30%
- 总仓位限制: ≤ 80%
- 波动率目标: 10-15% 年化
```

### 2. 事中风控 (In-trade)
```python
- 止损: 2-5% 价格止损
- 时间止损: 持仓不超过N天
- 波动率止损: 波动率突增时减仓
```

### 3. 事后风控 (Post-trade)
```python
- 每日风险归因
- 压力测试
- 情景分析
```

---

## 五、参考文献

1. Moskowitz, T. J., Grinblatt, M., & Moskowitz, T. J. (2012). Time series momentum. Journal of Financial Economics.
2. Hurst, B., Ooi, Y. H., & Pedersen, L. H. (2017). A century of evidence on trend-following investing. The Journal of Portfolio Management.
3. Ming, L., et al. (2023). Revisiting time series momentum in China's commodity futures market. Economic Modelling.
4. Man Group. (2025). A Trend Following Deep Dive: The Optimal Market Mix.
5. Baltas, A. O. (2019). The impact of crowding on risk premia strategies.
6. ReSolve Asset Management. (2024). Managed Futures Carry: A Practitioner's Guide.
7. Mandatum Asset Management. (2025). Meta-Models in Practice.
