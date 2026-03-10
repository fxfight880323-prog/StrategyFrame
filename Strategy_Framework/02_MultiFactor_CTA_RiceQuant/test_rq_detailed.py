"""
详细测试米筐连接方式
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import rqdatac as rq

API_KEY = "Mg8lEL3dGgIyxrwc2rNsqVneytgqpSq4n0h4S8M-XQnZ9domysurqc3Lh1NlmAwAKSBTUr5qwFJ-aPEeFfR3L2rK5pq-HddOdS6vDBfDv187cVUdC9sejifx7V1lQjQWRm19YVrhx1poB-uThWtc3F6kzslu4cn9myNayWNzfo8=OPgej69FUSOnYfosbz62TAjuWXo_85kHZiUQUZCjXl78r0HUqN3HGJBXF7CIsXCHAAsQ7xieZzwD-_G8vn_3pkfFaAy2pLrhjk4BSLkVcNDwfPJovTa4hxIKfGAZ5G_HtNIHSUZcHnenxQnZljuvnzsixT3G-3Gr4UunAz9-72A="

print("="*80)
print("米筐连接详细测试")
print("="*80)
print(f"API Key长度: {len(API_KEY)}")
print(f"包含'=': {'=' in API_KEY}")
print(f"'='的位置: {API_KEY.find('=')}")
print()

# 分割方式1: 第一个=号分割
pos = API_KEY.find('=')
username1 = API_KEY[:pos]
password1 = API_KEY[pos+1:]
print(f"[方式1] 第一个'='分割:")
print(f"  Username长度: {len(username1)}")
print(f"  Password长度: {len(password1)}")

# 分割方式2: 最后一个是=号
if API_KEY.endswith('='):
    print("[方式2] API Key以'='结尾，可能是base64 padding")
else:
    print("[方式2] API Key不以'='结尾")

# 尝试不同的连接方式
test_methods = [
    ("方式1: 第一个'='分割的用户名/密码", lambda: rq.init(username1, password1)),
    ("方式2: 整个字符串作为username，无密码", lambda: rq.init(API_KEY, "")),
    ("方式3: 整个字符串作为password，默认用户名", lambda: rq.init("", API_KEY)),
]

for name, init_func in test_methods:
    print(f"\n{'='*60}")
    print(f"测试: {name}")
    print('='*60)
    
    try:
        # 先断开之前的连接
        try:
            rq.deinit()
        except:
            pass
        
        # 尝试连接
        init_func()
        print("  [OK] init() 成功")
        
        # 测试获取数据
        try:
            result = rq.index_components('000300.XSHG', '2024-01-01')
            if result is not None and len(result) > 0:
                print(f"  [OK] 数据获取成功，返回 {len(result)} 只股票")
                print(f"  [SUCCESS] {name} 完全可用！")
                break
            else:
                print(f"  [ERROR] 数据返回为空")
        except Exception as e:
            print(f"  [ERROR] 数据获取失败: {e}")
            
    except Exception as e:
        print(f"  [ERROR] init() 失败: {e}")

print("\n" + "="*80)
