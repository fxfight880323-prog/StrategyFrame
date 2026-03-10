# 米筐 API Key 配置指南

## 概述

本策略框架使用**米筐(RiceQuant)**的数据服务获取股票、期货等市场数据。

你的API Key已经配置完成，无需额外操作即可使用。

---

## API Key 信息

```
状态: ✓ 已配置
存储位置: config.py
长度: 616 字符
前缀: Mg8lEL3dGgIyxrwc2rNsq...
```

---

## 使用方法

### 方法1: 自动读取（推荐）

数据提供器会自动从 `config.py` 读取API Key：

```python
from factor_model import FactorDataProvider
from cta_signals import FuturesDataProvider

# 自动读取 config.py 中的 API Key
stock_provider = FactorDataProvider()
futures_provider = FuturesDataProvider()
```

### 方法2: 手动传入

如果需要使用其他API Key，可以手动传入：

```python
from factor_model import FactorDataProvider

# 使用自定义API Key
my_api_key = "your-api-key-here"
provider = FactorDataProvider(api_key=my_api_key)
```

### 方法3: 从环境变量读取

```python
import os
from factor_model import FactorDataProvider

# 从环境变量读取
api_key = os.getenv('RQ_API_KEY')
provider = FactorDataProvider(api_key=api_key)
```

---

## 检查API Key状态

运行检查工具：

```bash
python check_api_key.py
```

输出示例：
```
======================================================================
米筐(RiceQuant) API Key 检查
======================================================================

[✓] config.py 中找到 API Key
    长度: 616 字符
    前缀: Mg8lEL3dGgIyxrwc2rNsq...

[检查米筐SDK]
[✓] 米筐SDK已安装 (rqdatac)

[测试连接]
[✓] API Key 有效，连接成功！
[✓] 数据获取测试成功！

======================================================================
总结
======================================================================
✓ API Key 已配置
✓ 可以使用米筐数据服务
======================================================================
```

---

## 安装米筐SDK

如果尚未安装米筐SDK，请运行：

```bash
pip install rqdatac
```

---

## API Key 安全性

⚠️ **安全提示**:

1. **不要提交到Git**: API Key是敏感信息，请勿提交到版本控制系统
2. **保护文件权限**: 确保配置文件只能被当前用户读取
3. **定期更换**: 建议定期更换API Key以提高安全性

### 添加到 .gitignore

```gitignore
# 敏感配置文件
.env
config_local.py
*.key

# Python缓存
__pycache__/
*.pyc
```

---

## 故障排除

### 问题1: "未配置API Key"

**原因**: 配置文件未正确导入

**解决**:
```python
# 检查 config.py 是否存在 RQ_API_KEY 变量
from config import RQ_API_KEY
print(RQ_API_KEY[:50])  # 应该能打印出API Key的前50个字符
```

### 问题2: "连接失败"

**原因**: API Key无效或网络问题

**解决**:
1. 检查网络连接
2. 确认API Key未过期
3. 联系米筐客服确认账户状态

### 问题3: "SDK未安装"

**解决**:
```bash
pip install rqdatac --upgrade
```

---

## 使用示例

### 获取股票数据

```python
from factor_model import FactorDataProvider
from datetime import datetime, timedelta

# 初始化（自动读取API Key）
provider = FactorDataProvider()

# 获取沪深300成分股
symbols = provider.get_stock_universe('hs300')
print(f"获取到 {len(symbols)} 只股票")

# 获取因子数据
end_date = datetime.now().strftime('%Y-%m-%d')
factors = ['pe_ttm', 'pb', 'roe']
data = provider.get_factor_data(symbols[:10], factors, end_date)
print(data.head())
```

### 获取期货数据

```python
from cta_signals import FuturesDataProvider

# 初始化（自动读取API Key）
provider = FuturesDataProvider()

# 获取螺纹钢数据
df = provider.get_futures_data('RB', '2024-01-01', '2024-03-01')
print(df.head())
```

---

## 米筐数据服务文档

- 官方文档: https://www.ricequant.com/doc/rqdata
- API参考: https://www.ricequant.com/doc/api
- 数据字典: https://www.ricequant.com/doc/data

---

## 支持的数据类型

### 股票数据
- A股日线/分钟线
- 港股日线
- 美股日线
- 财务数据
- 因子数据

### 期货数据
- 商品期货
- 股指期货
- 国债期货

### 其他数据
- 期权数据
- 基金数据
- 指数数据
- 宏观经济数据

---

*配置时间: 2026-03-06*  
*最后更新: 2026-03-06*
