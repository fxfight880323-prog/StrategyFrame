# CTA回测未来数据问题检查报告

## 🔍 问题发现

### 问题1: 历史收益 vs 未来收益命名混淆

**在 `Mag7CTAAnalyzer.py` 中:**
```python
# 这些是历史收益（过去N天的收益）
df['Momentum_5'] = df['Close'].pct_change(periods=5) * 100   # 过去5天收益
df['Momentum_20'] = df['Close'].pct_change(periods=20) * 100 # 过去20天收益

# 被重命名为 Return_XD
result['Return_5D'] = latest['Momentum_5']    # 实际: 过去5天收益
result['Return_20D'] = latest['Momentum_20']  # 实际: 过去20天收益
```

**在 `CTABacktester.py` 中:**
```python
# 错误地解读为未来收益
logger.info(f"{signal} 信号股票未来收益:")
avg_5d_return = signal_stocks['Return_5D'].mean()   # 实际使用的是过去5天收益!
avg_20d_return = signal_stocks['Return_20D'].mean() # 实际使用的是过去20天收益!
```

### 结论
- **CTA信号本身没有使用未来数据** ✅
- `Momentum_5/20` 是合理的技术指标输入
- 但验证部分的命名和理解有误，容易误导

---

## ✅ 需要修复的问题

### 修复1: 命名澄清
将 `Return_5D` / `Return_20D` 重命名为 `Past_Return_5D` / `Past_Return_20D`，避免混淆

### 修复2: 添加真正的未来收益计算
在回测中计算**买入后**的未来持有收益：
```python
# 对于每个信号日期，计算未来N天的收益
future_return = (price_future - price_signal) / price_signal
```

### 修复3: 时间序列验证
确保回测严格按时间顺序执行，没有 lookahead bias

---

## 🔧 修复方案
