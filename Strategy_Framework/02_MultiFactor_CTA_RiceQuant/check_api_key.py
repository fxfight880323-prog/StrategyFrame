"""
API Key 检查工具
===============

检查米筐API Key的配置状态

使用方法:
    python check_api_key.py
"""

import sys

def check_api_key():
    """检查API Key配置"""
    
    print("=" * 70)
    print("米筐(RiceQuant) API Key 检查")
    print("=" * 70)
    
    # 从配置文件读取
    try:
        from config import RQ_API_KEY
        config_key = RQ_API_KEY
        print("\n[OK] config.py 中找到 API Key")
        print(f"    长度: {len(config_key)} 字符")
        print(f"    前缀: {config_key[:20]}...")
    except ImportError:
        print("\n[ERROR] 无法导入 config 模块")
        config_key = None
    except AttributeError:
        print("\n[ERROR] config.py 中未找到 RQ_API_KEY")
        config_key = None
    
    # 检查米筐SDK
    print("\n[检查米筐SDK]")
    try:
        import rqdatac as rq
        print("[OK] 米筐SDK已安装 (rqdatac)")
        
        # 尝试连接
        if config_key:
            print("\n[测试连接]")
            try:
                rq.init(config_key)
                print("[OK] API Key 有效，连接成功！")
                
                # 尝试获取数据
                try:
                    # 获取当前日期
                    from datetime import datetime, timedelta
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=5)
                    
                    # 尝试获取一只股票的日线数据
                    df = rq.get_price('000001.XSHE', 
                                     start_date=start_date.strftime('%Y-%m-%d'),
                                     end_date=end_date.strftime('%Y-%m-%d'),
                                     frequency='1d')
                    if not df.empty:
                        print(f"[OK] 数据获取测试成功！")
                        print(f"    获取到 {len(df)} 条数据")
                    else:
                        print("[WARN] 数据获取测试返回空数据")
                except Exception as e:
                    print(f"[WARN] 数据获取测试失败: {e}")
                    
            except Exception as e:
                print(f"[ERROR] 连接失败: {e}")
        else:
            print("[WARN] 未配置API Key，跳过连接测试")
            
    except ImportError:
        print("[ERROR] 米筐SDK未安装")
        print("    请运行: pip install rqdatac")
    
    # 总结
    print("\n" + "=" * 70)
    print("总结")
    print("=" * 70)
    
    if config_key:
        print("[OK] API Key 已配置")
        print("[OK] 可以使用米筐数据服务")
        print("\n使用方法:")
        print("    from factor_model import FactorDataProvider")
        print("    provider = FactorDataProvider()  # 自动读取API Key")
    else:
        print("[ERROR] API Key 未配置")
        print("\n配置方法:")
        print("    1. 编辑 config.py 文件")
        print("    2. 修改 RQ_API_KEY 变量")
    
    print("=" * 70)

if __name__ == "__main__":
    check_api_key()
