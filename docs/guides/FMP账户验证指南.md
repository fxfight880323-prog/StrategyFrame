# FMP (Financial Modeling Prep) 账户验证完整指南

## 🔑 你的 API Key

```
Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq
```

---

## 📋 验证步骤清单

### 步骤 1: 访问 FMP 网站

1. 打开浏览器，访问: https://site.financialmodelingprep.com
2. 点击右上角的 **"Login"** 或 **"Sign In"
3. 使用注册时的邮箱和密码登录

---

### 步骤 2: 检查 Dashboard

登录后，进入 Dashboard 页面:

```
https://site.financialmodelingprep.com/developer/dashboard
```

**检查项目**:
- [ ] 确认邮箱已验证（如未验证，会显示验证提示）
- [ ] 查看 API Key 状态
- [ ] 检查订阅计划
- [ ] 查看 API 调用限额使用情况

---

### 步骤 3: 验证 API Key 有效性

#### 方法 A: 使用浏览器直接测试

在浏览器地址栏输入:

```
https://financialmodelingprep.com/api/v3/quote/AAPL?apikey=Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq
```

**预期结果**:
- ✅ 有效: 返回 JSON 数据，包含 AAPL 的实时报价
- ❌ 无效: 返回错误信息，如 `"Error": "Invalid API Key"` 或 `"message": "Invalid API key"`

#### 方法 B: 使用 Python 测试

```python
import requests

API_KEY = "Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq"
url = f"https://financialmodelingprep.com/api/v3/quote/AAPL?apikey={API_KEY}"

response = requests.get(url)
print(f"状态码: {response.status_code}")
print(f"响应: {response.text[:200]}")

if response.status_code == 200:
    data = response.json()
    if data and len(data) > 0:
        print(f"✅ API Key 有效")
        print(f"AAPL 价格: ${data[0].get('price', 'N/A')}")
    else:
        print(f"⚠️ 返回数据为空")
elif response.status_code == 403:
    print(f"❌ 403 Forbidden - API Key 无效或需要验证")
    print(f"可能原因:")
    print(f"  1. API Key 错误")
    print(f"  2. 账户未激活")
    print(f"  3. 订阅已过期")
elif response.status_code == 429:
    print(f"⚠️ 429 Too Many Requests - 超出速率限制")
else:
    print(f"❌ 错误: {response.status_code}")
```

---

### 步骤 4: 检查订阅计划

访问价格页面:

```
https://site.financialmodelingprep.com/pricing
```

**常见订阅类型**:

| 计划 | 价格 | 限制 | 适用场景 |
|------|------|------|----------|
| **Free** | $0 | 250 calls/day | 测试/开发 |
| **Starter** | $15/月 | 10,000 calls/day | 个人使用 |
| **Professional** | $49/月 | 100,000 calls/day | 专业交易 |
| **Enterprise** | $199/月 | 无限 | 机构使用 |

**检查你的计划**:
1. 在 Dashboard 查看当前计划
2. 确认是否在免费试用期内
3. 检查是否需要升级

---

### 步骤 5: 邮箱验证

如果账户显示"Email not verified":

1. 检查注册邮箱的收件箱（包括垃圾邮件文件夹）
2. 查找来自 `noreply@financialmodelingprep.com` 的邮件
3. 点击邮件中的验证链接
4. 或者点击 Dashboard 中的 **"Resend Verification Email"**

---

### 步骤 6: 绑定支付方式（如需要）

某些功能需要绑定信用卡/支付方式:

1. 进入 Dashboard → Billing
2. 点击 **"Add Payment Method"**
3. 输入信用卡信息（仅用于验证，免费计划不会扣费）
4. 或者使用 PayPal

---

## 🔍 常见问题排查

### 问题 1: 403 Forbidden 错误

**可能原因**:
- API Key 输入错误
- 账户未激活
- 订阅已过期
- IP 被限制

**解决方案**:
```bash
# 1. 检查 API Key 是否复制完整
# 确保没有多余空格或字符

# 2. 重新生成 API Key
# Dashboard → API Keys → Generate New Key

# 3. 检查账户状态
# Dashboard → Account Status
```

### 问题 2: 429 Too Many Requests

**可能原因**:
- 超出每日调用限额
- 超出每分钟调用限额

**解决方案**:
```python
import time

# 添加请求间隔
def make_request_with_delay(url):
    time.sleep(0.2)  # 200ms 延迟
    return requests.get(url)

# 或使用指数退避
for attempt in range(3):
    response = requests.get(url)
    if response.status_code == 429:
        time.sleep(2 ** attempt)  # 1s, 2s, 4s
    else:
        break
```

### 问题 3: 返回空数据

**可能原因**:
- Symbol 格式错误
- 该标的无数据
- 日期范围无效

**解决方案**:
```python
# 检查 symbol 格式
# 股票: AAPL, MSFT, TSLA
# 指数: ^GSPC (S&P 500), ^DJI (Dow Jones)
# 注意: FMP 可能不支持 ^VIX，使用 VIXY 作为替代

# 测试有效 symbol
test_symbols = ['AAPL', 'MSFT', 'SPY', 'QQQ']
for sym in test_symbols:
    url = f"https://financialmodelingprep.com/api/v3/quote/{sym}?apikey={API_KEY}"
    response = requests.get(url)
    print(f"{sym}: {response.status_code}")
```

### 问题 4: 期权数据为空

**可能原因**:
- 免费版不包含期权数据
- 该到期日无数据

**解决方案**:
```python
# 1. 确认订阅计划支持期权数据
# Starter 及以上计划支持

# 2. 检查到期日格式
# 正确格式: 2024-03-15

# 3. 使用备选数据源
from YFinanceDataProvider import YFinanceProvider
yf = YFinanceProvider()
options = yf.get_options_chain('SPY')
```

---

## 🚀 快速验证脚本

保存以下代码为 `verify_fmp.py` 并运行:

```python
"""
FMP API Key 验证脚本
"""
import requests
import sys

API_KEY = "Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq"
BASE_URL = "https://financialmodelingprep.com/api/v3"

def test_endpoint(name, endpoint, params=None):
    """测试单个 API 端点"""
    if params is None:
        params = {}
    params['apikey'] = API_KEY
    
    url = f"{BASE_URL}/{endpoint}"
    
    try:
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if data:
                print(f"✅ {name}: 成功")
                return True
            else:
                print(f"⚠️  {name}: 返回空数据")
                return False
        elif response.status_code == 403:
            print(f"❌ {name}: 403 Forbidden - API Key 无效")
            return False
        elif response.status_code == 429:
            print(f"⚠️  {name}: 429 速率限制")
            return False
        else:
            print(f"❌ {name}: 错误 {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ {name}: 异常 - {e}")
        return False

def main():
    print("="*60)
    print("FMP API Key 验证")
    print("="*60)
    print(f"API Key: {API_KEY[:10]}...{API_KEY[-4:]}")
    print()
    
    tests = [
        ("实时报价", "quote/AAPL"),
        ("历史价格", "historical-price-full/AAPL", {"from": "2024-01-01", "to": "2024-01-31"}),
        ("股票列表", "stock/list"),
        ("财报日历", "earning_calendar", {"from": "2024-01-01", "to": "2024-01-31"}),
    ]
    
    results = []
    for name, endpoint, *params in tests:
        params = params[0] if params else None
        success = test_endpoint(name, endpoint, params)
        results.append((name, success))
    
    print()
    print("="*60)
    print("验证结果")
    print("="*60)
    
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    print(f"通过: {success_count}/{total_count}")
    print()
    
    if success_count == total_count:
        print("✅ API Key 有效，所有端点正常")
        return 0
    elif success_count > 0:
        print("⚠️  部分端点可用，可能有限制")
        print("建议:")
        print("  1. 检查订阅计划")
        print("  2. 确认邮箱已验证")
        return 1
    else:
        print("❌ API Key 无效或账户未激活")
        print("解决方案:")
        print("  1. 访问 https://financialmodelingprep.com 登录账户")
        print("  2. 验证邮箱")
        print("  3. 检查订阅状态")
        print("  4. 或重新生成 API Key")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

**运行**:
```bash
python verify_fmp.py
```

---

## 📞 联系支持

如果以上步骤无法解决问题:

1. **FMP 支持邮箱**: support@financialmodelingprep.com
2. **在线客服**: Dashboard 右下角的聊天窗口
3. **状态页面**: https://status.financialmodelingprep.com

---

## 🎯 验证流程图

```
开始
  ↓
访问 https://financialmodelingprep.com
  ↓
登录账户
  ↓
检查 Dashboard
  ↓
邮箱已验证? ──否──→ 验证邮箱 ──→ 重新登录
  │是
  ↓
API Key 显示正常? ──否──→ 重新生成 Key
  │是
  ↓
运行验证脚本
  ↓
测试通过? ──否──→ 检查订阅计划/联系支持
  │是
  ↓
✅ 验证完成，可以正常使用
```

---

## ✅ 验证后检查清单

- [ ] 可以成功登录 FMP 网站
- [ ] Dashboard 显示 API Key
- [ ] 邮箱已验证（无警告提示）
- [ ] 浏览器访问测试 URL 返回数据
- [ ] Python 脚本测试返回 200
- [ ] 了解每日 API 调用限额
- [ ] 确认订阅计划满足需求

---

**完成验证后，即可使用 FMP 数据运行 CTA + FLP 策略！**
