"""
测试米筐连接方式
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import rqdatac as rq
from config import RQ_API_KEY

print("="*60)
print("测试米筐连接")
print("="*60)
print(f"API Key长度: {len(RQ_API_KEY)}")
print(f"API Key前50字符: {RQ_API_KEY[:50]}...")

# 方式1: 直接传入API Key
print("\n[方式1] 直接传入API Key...")
try:
    rq.init(RQ_API_KEY)
    print("[OK] 方式1连接成功")
except Exception as e:
    print(f"[ERROR] 方式1失败: {e}")

# 方式2: 使用uri参数
print("\n[方式2] 使用uri参数...")
try:
    rq.init(uri=RQ_API_KEY)
    print("[OK] 方式2连接成功")
except Exception as e:
    print(f"[ERROR] 方式2失败: {e}")

# 方式3: 尝试解析API Key格式 (可能是username:password格式)
print("\n[方式3] 尝试解析为username:password格式...")
try:
    # 有些API Key可能是 base64编码的 username:password
    import base64
    decoded = base64.b64decode(RQ_API_KEY).decode('utf-8')
    print(f"解码后: {decoded[:50]}...")
    if ':' in decoded:
        parts = decoded.split(':')
        rq.init(parts[0], parts[1])
        print("[OK] 方式3连接成功")
except Exception as e:
    print(f"[ERROR] 方式3失败: {e}")

# 方式4: 查看rq.init的文档
print("\n[方式4] 查看rq.init参数...")
import inspect
sig = inspect.signature(rq.init)
print(f"rq.init参数: {sig}")

print("\n" + "="*60)
