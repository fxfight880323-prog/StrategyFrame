"""
测试米筐连接方式 - 尝试更多方法
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import rqdatac as rq
from config import RQ_API_KEY
import base64

print("="*60)
print("测试米筐连接 - 进阶")
print("="*60)

# 检查API Key是否包含特定分隔符
print(f"API Key长度: {len(RQ_API_KEY)}")
print(f"是否包含'=': {'=' in RQ_API_KEY}")
print(f"是否包含':': {':' in RQ_API_KEY}")
print(f"是否包含'_': {'_' in RQ_API_KEY}")

# 尝试使用标准base64解码（处理padding）
print("\n[尝试1] 尝试不同padding的base64解码...")
for i in range(4):
    try:
        padded_key = RQ_API_KEY + '=' * i
        decoded = base64.b64decode(padded_key)
        print(f"  padding={i}: 解码成功，长度={len(decoded)}")
        try:
            text = decoded.decode('utf-8')
            print(f"    UTF-8文本: {text[:50]}...")
            if ':' in text:
                parts = text.split(':')
                print(f"    发现冒号，分割为: {parts[0][:20]}... : {parts[1][:20]}...")
        except:
            print(f"    非UTF-8数据")
    except Exception as e:
        print(f"  padding={i}: 解码失败 - {e}")

# 尝试URL-safe base64解码
print("\n[尝试2] URL-safe base64解码...")
try:
    decoded = base64.urlsafe_b64decode(RQ_API_KEY + '=' * (4 - len(RQ_API_KEY) % 4))
    print(f"  解码成功，长度={len(decoded)}")
    try:
        text = decoded.decode('utf-8')
        print(f"  UTF-8文本: {text[:100]}...")
    except:
        print(f"  非UTF-8数据")
except Exception as e:
    print(f"  解码失败: {e}")

# 尝试直接用API Key作为用户名密码组合
print("\n[尝试3] 分割API Key为username/password...")
mid = len(RQ_API_KEY) // 2
username = RQ_API_KEY[:mid]
password = RQ_API_KEY[mid:]
print(f"  Username长度: {len(username)}, Password长度: {len(password)}")

try:
    rq.init(username, password)
    print("  [OK] 连接成功!")
except Exception as e:
    print(f"  [ERROR] 失败: {e}")

# 查找配置中的其他信息
print("\n[尝试4] 检查API Key中是否有隐藏信息...")
# 有些API Key中间可能有=号分隔
equal_pos = RQ_API_KEY.find('=')
if equal_pos > 0:
    print(f"  发现'='在第{equal_pos}位")
    part1 = RQ_API_KEY[:equal_pos]
    part2 = RQ_API_KEY[equal_pos+1:]
    print(f"  Part1: {part1[:50]}...")
    print(f"  Part2: {part2[:50]}...")
    
    # 尝试这两部分作为用户名密码
    try:
        rq.init(part1, part2)
        print("  [OK] 使用=分隔的两部分连接成功!")
    except Exception as e:
        print(f"  [ERROR] 失败: {e}")

# 最后一个字符是=的base64处理
print("\n[尝试5] 完整base64解码...")
try:
    # 确保padding正确
    key = RQ_API_KEY.replace('-', '+').replace('_', '/')
    padding_needed = 4 - len(key) % 4
    if padding_needed != 4:
        key += '=' * padding_needed
    decoded = base64.b64decode(key)
    print(f"  解码成功，长度={len(decoded)}")
    
    # 尝试作为pickle或其他格式
    try:
        import pickle
        obj = pickle.loads(decoded)
        print(f"  Pickle对象: {obj}")
    except:
        pass
    
    # 尝试hex解码
    try:
        hex_str = decoded.hex()
        print(f"  Hex: {hex_str[:100]}...")
    except:
        pass
        
except Exception as e:
    print(f"  解码失败: {e}")

print("\n" + "="*60)
