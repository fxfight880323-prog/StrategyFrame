"""
米筐SDK安装脚本
===============
"""

import subprocess
import sys

def install():
    print("="*60)
    print("安装米筐(RiceQuant) SDK")
    print("="*60)
    print()
    
    packages = [
        "rqdatac>=2.0",
    ]
    
    for package in packages:
        print(f"安装 {package}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"✓ {package} 安装成功")
        except Exception as e:
            print(f"✗ 安装失败: {e}")
    
    print()
    print("="*60)
    print("安装完成")
    print("="*60)
    print("\n现在可以运行: python CTA_FLP_RiceQuant.py")

if __name__ == "__main__":
    install()
