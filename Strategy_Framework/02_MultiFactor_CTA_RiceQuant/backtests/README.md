# ValMomEverywhere 回测结果

本文件夹包含 ValMomEverywhere (价值+动量) 策略的回测结果。

## 论文参考

**Value and Momentum Everywhere**  
Clifford S. Asness, Tobias J. Moskowitz, Lasse Heje Pedersen  
*Journal of Finance*, Vol. 68, No. 3, June 2013, pp. 929-985

### 论文核心发现

1. **普遍存在**: 价值和动量溢价在全球8个市场和资产类别中都显著存在
2. **负相关性**: 价值和动量收益呈负相关 (相关系数约 -0.5)
3. **COMBO优势**: 50/50组合可以平滑收益，提高风险调整后收益

## 回测方法

### 价值因子 (Value)

**定义**: 基于估值指标的综合排名

**计算方法**:
```
Value Score = w1 * EP + w2 * BP + w3 * SP

其中:
- EP = Earnings/Price = 1/PE (盈利收益率)
- BP = Book/Price = 1/PB (账面市值比)
- SP = Sales/Price = 1/PS (市销率倒数)
```

**信号构建**:
- 多头: 信号最高的一组股票
- 空头: 信号最低的一组股票
- 使用信号加权或等权配置

### 动量因子 (Momentum)

**定义**: 基于过去12个月收益的排名 (排除最近1个月)

**计算方法**:
```
Momentum = Return(t-12 to t-1)

即: 过去12个月累计收益，排除最近1个月
```

**为什么要排除最近1个月?**
- 避免短期反转效应 (short-term reversal)
- 减少微观结构噪音
- 这是经典的 "12-1" 动量定义 (Jegadeesh & Titman, 1993)

### 组合因子 (COMBO)

**定义**: 价值因子和动量因子的等权组合

**计算方法**:
```
COMBO = 0.5 * Value + 0.5 * Momentum
```

**优势**:
- 价值与动量负相关，天然对冲
- 组合波动率低于单个因子
- 更稳定的收益特征

## 回测配置

| 参数 | 设置 |
|------|------|
| 股票池 | 沪深300成分股 |
| 再平衡频率 | 月度 |
| 多头持仓 | 信号前20只股票 |
| 空头持仓 | 信号后20只股票 |
| 权重方法 | 信号加权 (Signal-Weighted) |
| 手续费 | 0.03% (股票) |
| 滑点 | 0.1% |

## 回测结果

### 收益指标

| 因子 | 年化收益率 | 年化波动率 | 夏普比率 | Information Ratio |
|------|-----------|-----------|---------|------------------|
| Value | TBD | TBD | TBD | TBD |
| Momentum | TBD | TBD | TBD | TBD |
| COMBO | TBD | TBD | TBD | TBD |

### 风险指标

| 因子 | 最大回撤 | Calmar比率 | Sortino比率 |
|------|---------|-----------|------------|
| Value | TBD | TBD | TBD |
| Momentum | TBD | TBD | TBD |
| COMBO | TBD | TBD | TBD |

### 相关性矩阵

|  | Value | Momentum | COMBO |
|--|-------|----------|-------|
| Value | 1.00 | TBD | TBD |
| Momentum | TBD | 1.00 | TBD |
| COMBO | TBD | TBD | 1.00 |

## 输出文件

### JSON 结果文件

- `valmom_results.json`: 三个因子的完整回测结果
- `valmom_value_results.json`: 价值因子单独结果
- `valmom_momentum_results.json`: 动量因子单独结果
- `valmom_combo_results.json`: 组合因子单独结果

### 图表文件

- `valmom_equity.png`: 三个因子的净值曲线对比
- `valmom_drawdown.png`: 三个因子的回撤曲线对比

## Information Ratio 说明

**定义**: Information Ratio (IR) = 年化超额收益 / 跟踪误差

**计算**:
```
IR = Annualized Return / Annualized Volatility
```

在本回测中，我们使用绝对收益作为基准 (假设无风险利率为0)，因此 IR ≈ Sharpe Ratio。

**解读标准**:
- IR > 1.0: 优秀
- IR 0.5-1.0: 良好
- IR 0.0-0.5: 一般
- IR < 0.0: 负收益

**论文中的IR**:
Asness等人在论文中报告，价值和动量因子的IR通常在0.5-1.0之间，COMBO组合的IR更高。

## 使用方法

### 运行回测

```bash
# 运行完整回测
cd ..
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

### Python API

```python
from valmom_backtest import run_valmom_backtests

# 运行回测
results = run_valmom_backtests(
    start_date="2022-01-01",
    end_date="2024-01-01",
    save_results=True
)

# 查看结果
value_result = results['Value']
print(f"Value IR: {value_result.information_ratio:.2f}")
print(f"Value Sharpe: {value_result.sharpe_ratio:.2f}")
```

## 注意事项

1. **数据质量**: 回测使用模拟数据或米筐数据，实际效果可能不同
2. **过拟合风险**: 因子在样本内表现好不代表样本外也能表现好
3. **交易成本**: 回测中考虑了手续费和滑点，但实际交易可能更复杂
4. **流动性风险**: 小市值股票可能存在流动性问题
5. **市场变化**: 因子有效性可能随时间衰减

## 改进方向

1. **多资产类别**: 扩展到债券、商品、外汇等资产类别
2. **动态权重**: 基于市场状态调整价值和动量的权重
3. **风险控制**: 加入止损、回撤控制等风险管理机制
4. **机器学习**: 使用ML预测因子未来收益
5. **高频数据**: 使用日内数据改进信号质量

## 参考资料

1. **Asness et al. (2013)** - Value and Momentum Everywhere
2. **Fama & French (1993)** - Common risk factors in stock returns
3. **Jegadeesh & Titman (1993)** - Returns to buying winners and selling losers
4. **Carhart (1997)** - On persistence in mutual fund performance

---

*最后更新: 2026-03-06*
