"""
FMP API Key 验证脚本
====================
快速验证你的 FMP API Key 是否有效

使用方法:
    python verify_fmp.py

API Key: Cq68ZgXyTUwVHBMgYNMCcCUleyJ4U0Vq
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import json

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
                return True, data
            else:
                return False, "返回空数据"
        elif response.status_code == 403:
            return False, "403 Forbidden - API Key 无效或账户未激活"
        elif response.status_code == 429:
            return False, "429 Too Many Requests - 超出速率限制"
        else:
            return False, f"HTTP {response.status_code}"
            
    except Exception as e:
        return False, f"异常: {e}"


def main():
    print("="*70)
    print("FMP API Key 验证工具")
    print("="*70)
    print(f"API Key: {API_KEY[:15]}...{API_KEY[-4:]}")
    print()
    
    # 测试项目
    tests = [
        ("实时报价 (AAPL)", "quote/AAPL", None),
        ("历史价格 (AAPL)", "historical-price-full/AAPL", {"from": "2024-01-01", "to": "2024-01-31"}),
        ("股票列表", "stock/list", None),
    ]
    
    results = []
    sample_data = None
    
    for name, endpoint, params in tests:
        print(f"测试: {name}...", end=" ")
        success, data = test_endpoint(name, endpoint, params)
        
        if success:
            print("✅ 通过")
            results.append((name, True, None))
            if sample_data is None:
                sample_data = data
        else:
            print(f"❌ 失败 - {data}")
            results.append((name, False, data))
    
    print()
    print("="*70)
    print("验证结果汇总")
    print("="*70)
    
    success_count = sum(1 for _, success, _ in results if success)
    total_count = len(results)
    
    print(f"通过: {success_count}/{total_count}")
    print()
    
    if success_count == total_count:
        print("✅ API Key 有效！")
        print()
        print("样本数据:")
        if isinstance(sample_data, list) and len(sample_data) > 0:
            item = sample_data[0]
            print(f"  Symbol: {item.get('symbol', 'N/A')}")
            print(f"  Price: ${item.get('price', 'N/A')}")
            print(f"  Change: {item.get('changesPercentage', 'N/A')}%")
        print()
        print("你现在可以使用 FMP 数据运行策略了！")
        print("运行: python CTA_FMP_Strategy.py")
        return 0
        
    elif success_count > 0:
        print("⚠️  部分端点可用")
        print()
        print("可能原因:")
        print("  • 免费版 API 有访问限制")
        print("  • 某些数据需要付费订阅")
        print()
        print("建议:")
        print("  1. 访问 https://financialmodelingprep.com/pricing 查看订阅计划")
        print("  2. 考虑升级到 Starter 计划 ($15/月)")
        print("  3. 或使用 YFinance 作为免费备选")
        return 1
        
    else:
        print("❌ API Key 无效或账户未激活")
        print()
        print("解决方案:")
        print("  1. 访问 https://site.financialmodelingprep.com 登录账户")
        print("  2. 检查邮箱是否已验证")
        print("  3. 确认订阅计划状态")
        print("  4. 在 Dashboard 中重新生成 API Key")
        print("  5. 联系支持: support@financialmodelingprep.com")
        print()
        print("或者使用 YFinance 作为免费备选:")
        print("  python YFinanceDataProvider.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())
