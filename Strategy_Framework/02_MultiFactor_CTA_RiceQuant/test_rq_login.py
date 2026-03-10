"""
使用账号密码测试米筐连接
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import rqdatac as rq

print("="*80)
print("米筐账号密码登录测试")
print("="*80)

# 使用账号密码登录
username = '+8613810062394'
password = 'Fox880323!'

print(f"用户名: {username}")
print(f"密码: {'*' * len(password)}")
print()

try:
    # 先断开之前的连接
    try:
        rq.deinit()
    except:
        pass
    
    print("[INFO] 正在登录...")
    rq.init(username, password)
    print("[OK] 登录成功!")
    
    # 测试获取数据
    print("[INFO] 测试获取沪深300成分股...")
    result = rq.index_components('000300.XSHG', '2024-01-01')
    
    if result is not None and len(result) > 0:
        print(f"[OK] 数据获取成功!")
        print(f"[INFO] 沪深300成分股数量: {len(result)}")
        print(f"[INFO] 前5只股票: {list(result)[:5]}")
        
        # 测试获取价格数据
        print("\n[INFO] 测试获取价格数据...")
        test_stock = list(result)[0]
        prices = rq.get_price(test_stock, '2024-01-01', '2024-01-10', frequency='1d')
        if prices is not None and len(prices) > 0:
            print(f"[OK] 价格数据获取成功!")
            print(f"[INFO] {test_stock} 价格数据:\n{prices.head()}")
            
            print("\n" + "="*80)
            print("[SUCCESS] 账号密码登录完全可用！")
            print("="*80)
        else:
            print("[WARNING] 价格数据为空")
    else:
        print(f"[ERROR] 数据返回为空")
        
except Exception as e:
    print(f"[ERROR] 登录或数据获取失败: {e}")
    print("\n可能原因:")
    print("  1. 账号或密码错误")
    print("  2. 账号未开通API权限")
    print("  3. 网络连接问题")
