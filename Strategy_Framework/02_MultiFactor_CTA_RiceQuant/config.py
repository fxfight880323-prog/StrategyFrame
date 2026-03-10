"""
多因子+CTA策略配置文件
========================

集中管理策略参数和API配置
"""

# ============================================================
# RiceQuant API 配置
# ============================================================
# 方式1: 使用 API Key (如已过期请使用方式2)
RQ_API_KEY = "Mg8lEL3dGgIyxrwc2rNsqVneytgqpSq4n0h4S8M-XQnZ9domysurqc3Lh1NlmAwAKSBTUr5qwFJ-aPEeFfR3L2rK5pq-HddOdS6vDBfDv187cVUdC9sejifx7V1lQjQWRm19YVrhx1poB-uThWtc3F6kzslu4cn9myNayWNzfo8=OPgej69FUSOnYfosbz62TAjuWXo_85kHZiUQUZCjXl78r0HUqN3HGJBXF7CIsXCHAAsQ7xieZzwD-_G8vn_3pkfFaAy2pLrhjk4BSLkVcNDwfPJovTa4hxIKfGAZ5G_HtNIHSUZcHnenxQnZljuvnzsixT3G-3Gr4UunAz9-72A="

# 方式2: 使用账号密码登录 (推荐)
RQ_USERNAME = '+8613810062394'
RQ_PASSWORD = 'Fox880323!'

# 服务器配置
RQ_ADDR = ('rqdatad-pro.ricequant.com', 16011)


# ============================================================
# 策略参数配置
# ============================================================

from dataclasses import dataclass, field
from typing import List, Dict, Tuple


@dataclass
class StrategyConfig:
    """策略配置类"""
    
    # === 因子配置 ===
    factor_universe: str = '000300.XSHG'  # 沪深300
    value_factor_weights: Dict[str, float] = field(default_factory=lambda: {
        'EP': 0.25,
        'BP': 0.25,
        'SP': 0.25,
        'CFP': 0.25
    })
    momentum_lookback: int = 12  # 动量回看月数
    momentum_skip: int = 1  # 动量跳过月数
    
    # === CTA配置 ===
    cta_symbols: List[str] = field(default_factory=lambda: [
        'IF8888.CCFX',  # 沪深300期货
        'IC8888.CCFX',  # 中证500期货
        'IH8888.CCFX',  # 上证50期货
    ])
    cta_lookback: int = 20
    
    # === 组合配置 ===
    factor_weight: float = 0.5
    cta_weight: float = 0.5
    rebalance_freq: str = 'ME'  # 月调仓
    
    # === 风控配置 ===
    max_position_pct: float = 0.95
    max_drawdown_limit: float = 0.15
    stop_loss_pct: float = 0.08


# ============================================================
# 因子策略配置
# ============================================================
FACTOR_CONFIG = {
    'universe': '000300.XSHG',
    'neutralize': True,  # 是否行业中性和市值中性
    'outlier_method': 'mad',  # 异常值处理方法
    
    # 价值因子
    'value_factors': {
        'EP': {'weight': 0.20, 'direction': 1},  # 市盈率倒数
        'BP': {'weight': 0.20, 'direction': 1},  # 市净率倒数
        'SP': {'weight': 0.20, 'direction': 1},  # 市销率倒数
        'CFP': {'weight': 0.20, 'direction': 1},  # 市现率倒数
        'DP': {'weight': 0.20, 'direction': 1},  # 股息率
    },
    
    # 动量因子
    'momentum_factors': {
        'MOM_12_1': {'lookback': 12, 'skip': 1, 'weight': 0.5},
        'MOM_6_1': {'lookback': 6, 'skip': 1, 'weight': 0.3},
        'MOM_3_1': {'lookback': 3, 'skip': 1, 'weight': 0.2},
    },
    
    # 回测参数
    'backtest': {
        'start_date': '2014-01-01',
        'end_date': '2024-01-01',
        'benchmark': '000300.XSHG',
        'commission': 0.0003,
        'slippage': 0.001,
    }
}


# ============================================================
# CTA策略配置
# ============================================================
CTA_CONFIG = {
    'symbols': {
        'IF8888.CCFX': {'name': '沪深300期货', 'multiplier': 300},
        'IC8888.CCFX': {'name': '中证500期货', 'multiplier': 200},
        'IH8888.CCFX': {'name': '上证50期货', 'multiplier': 300},
    },
    
    # 策略参数
    'strategy': {
        'trend_lookback': 60,
        'momentum_lookback': 20,
        'volatility_lookback': 20,
        'position_sizing': 'volatility_target',
        'target_volatility': 0.15,
    },
    
    # 信号参数
    'signals': {
        'trend_threshold': 0.05,
        'momentum_threshold': 0.02,
    },
    
    # 风控参数
    'risk': {
        'max_position': 0.3,
        'stop_loss': 0.05,
        'take_profit': 0.10,
    }
}


# ============================================================
# 回测配置
# ============================================================
BACKTEST_CONFIG = {
    'start_date': '2014-01-01',
    'end_date': '2024-01-01',
    'initial_capital': 10000000,  # 初始资金1000万
    'commission_rate': 0.0003,
    'slippage': 0.001,
    'benchmark': '000300.XSHG',
    
    # 月度调仓
    'rebalance_freq': 'ME',
    
    # 多空组合
    'long_pct': 0.3,  # 多头前30%
    'short_pct': 0.3,  # 空头后30%
}


# ============================================================
# 数据缓存配置
# ============================================================
CACHE_CONFIG = {
    'enabled': True,
    'cache_dir': './data_cache',
    'expire_days': 7,
}
