"""
Buy the Dip + 下行风险管理 (Downtrend Risk Management)
======================================================

核心问题: Buy the Dip 在下行趋势中会变成 "接飞刀" (catching falling knives)
本模块增加完整的风险管理体系:

风险管理层级:
  Layer 1: 趋势识别 — 区分回调(pullback) vs 下行趋势(downtrend) vs 熊市(bear)
  Layer 2: 止损系统 — 尾随止损 + 最大亏损限制
  Layer 3: 仓位管理 — 根据regime动态调整
  Layer 4: 波动率过滤 — 高波动环境缩小仓位
  Layer 5: 时间止损 — 买入后N天未恢复则减仓
  Layer 6: 组合级风控 — 最大回撤限制 + 风险预算

Data: Yahoo Finance (yfinance) — REAL DATA
Period: 2014-01-01 to 2024-12-31
"""

import warnings
warnings.filterwarnings('ignore')

import json
import logging
import sys
from datetime import datetime
from typing import Dict, List, Tuple
from enum import Enum

import numpy as np
import pandas as pd
import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


# ============================================================
# Market Regime Detection
# ============================================================
class MarketRegime(Enum):
    BULL_STRONG = "强势上涨"        # Strong uptrend
    BULL_NORMAL = "正常上涨"        # Normal uptrend
    PULLBACK = "回调"              # Pullback in uptrend (BUY THE DIP zone)
    SIDEWAYS = "震荡"              # Range-bound
    CORRECTION = "调整"            # Correction (-5% to -10%)
    DOWNTREND = "下行趋势"         # Downtrend (below 200-MA)
    BEAR = "熊市"                  # Bear market (-20%+)
    CRASH = "恐慌"                 # Crash / Panic (VIX>40, rapid decline)


def detect_regime(close: pd.Series, vix: pd.Series = None) -> pd.DataFrame:
    """
    Multi-factor regime detection.
    Returns DataFrame with regime label and confidence score.
    """
    df = pd.DataFrame(index=close.index)
    df['close'] = close

    # Moving averages
    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()

    # Drawdown from all-time high
    ath = close.expanding().max()
    dd_from_ath = (close - ath) / ath

    # Drawdown from 50-day high (short-term)
    high_50 = close.rolling(50).max()
    dd_50 = (close - high_50) / high_50

    # MA slopes (momentum of trend)
    ma50_slope = ma50.pct_change(10)   # 10-day slope of 50-MA
    ma200_slope = ma200.pct_change(20) # 20-day slope of 200-MA

    # Price vs MAs
    above_ma20 = close > ma20
    above_ma50 = close > ma50
    above_ma200 = close > ma200

    # MA alignment (golden cross / death cross)
    ma_aligned_bull = (ma20 > ma50) & (ma50 > ma200)  # 20>50>200
    ma_aligned_bear = (ma20 < ma50) & (ma50 < ma200)  # 20<50<200

    # Realized volatility
    ret = close.pct_change()
    vol_21 = ret.rolling(21).std() * np.sqrt(252)
    vol_percentile = vol_21.rolling(252).rank(pct=True)

    # VIX
    if vix is not None:
        vix_aligned = vix.reindex(close.index, method='ffill')
    else:
        vix_aligned = pd.Series(20, index=close.index)  # default

    # Regime classification
    regime = pd.Series(MarketRegime.SIDEWAYS.value, index=close.index)
    regime_enum = pd.Series(MarketRegime.SIDEWAYS, index=close.index)

    for i in range(200, len(close)):
        idx = close.index[i]

        # Check conditions (order matters: most extreme first)
        if dd_from_ath.iloc[i] < -0.20 and not above_ma200.iloc[i]:
            r = MarketRegime.BEAR
        elif vix_aligned.iloc[i] > 40 and dd_50.iloc[i] < -0.08:
            r = MarketRegime.CRASH
        elif not above_ma200.iloc[i] and ma200_slope.iloc[i] < -0.005:
            r = MarketRegime.DOWNTREND
        elif dd_50.iloc[i] < -0.10:
            r = MarketRegime.CORRECTION
        elif above_ma200.iloc[i] and dd_50.iloc[i] < -0.03:
            r = MarketRegime.PULLBACK
        elif ma_aligned_bull.iloc[i] and ma50_slope.iloc[i] > 0.005:
            r = MarketRegime.BULL_STRONG
        elif above_ma200.iloc[i] and above_ma50.iloc[i]:
            r = MarketRegime.BULL_NORMAL
        else:
            r = MarketRegime.SIDEWAYS

        regime.iloc[i] = r.value
        regime_enum.iloc[i] = r

    df['regime'] = regime
    df['regime_enum'] = regime_enum
    df['dd_from_ath'] = dd_from_ath
    df['dd_50'] = dd_50
    df['above_ma200'] = above_ma200
    df['ma50_slope'] = ma50_slope
    df['ma200_slope'] = ma200_slope
    df['vol_21'] = vol_21
    df['vol_percentile'] = vol_percentile
    df['vix'] = vix_aligned

    return df


# ============================================================
# Technical Indicators (reuse)
# ============================================================
def compute_indicators(spy_close: pd.Series) -> pd.DataFrame:
    """Compute technical indicators for dip detection."""
    df = pd.DataFrame(index=spy_close.index)
    df['close'] = spy_close
    df['ret'] = spy_close.pct_change()

    # RSI (14)
    delta = spy_close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-8)
    df['rsi'] = 100 - (100 / (1 + rs))

    # Drawdown from 50-day high
    rolling_high = spy_close.rolling(50).max()
    df['drawdown'] = (spy_close - rolling_high) / rolling_high

    # Bollinger Bands
    df['bb_mid'] = spy_close.rolling(20).mean()
    bb_std = spy_close.rolling(20).std()
    df['bb_lower'] = df['bb_mid'] - 2 * bb_std
    df['bb_upper'] = df['bb_mid'] + 2 * bb_std
    df['bb_pct'] = (spy_close - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-8)

    # Consecutive down days
    down_day = (df['ret'] < 0).astype(int)
    streak = pd.Series(0, index=spy_close.index)
    for i in range(1, len(streak)):
        if down_day.iloc[i] == 1:
            streak.iloc[i] = streak.iloc[i - 1] + 1
        else:
            streak.iloc[i] = 0
    df['down_streak'] = streak

    # Moving averages
    df['ma50'] = spy_close.rolling(50).mean()
    df['ma200'] = spy_close.rolling(200).mean()

    # ATR (14)
    tr = pd.DataFrame({
        'hl': spy_close.rolling(1).max() - spy_close.rolling(1).min(),
        'hc': abs(spy_close - spy_close.shift(1)),
        'lc': abs(spy_close.rolling(1).min() - spy_close.shift(1)),
    }).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    df['atr_pct'] = df['atr'] / spy_close * 100

    return df


# ============================================================
# Risk Management Engine
# ============================================================
class RiskManager:
    """
    多层风险管理引擎

    Layer 1: Trailing Stop Loss — 从最高点回撤超过阈值止损
    Layer 2: Max Loss Per Trade — 单次买入最大允许亏损
    Layer 3: Time Stop — 买入后N天未恢复则减仓
    Layer 4: Portfolio DD Limit — 组合最大回撤限制
    Layer 5: Vol Scaling — 高波动缩小仓位
    Layer 6: Regime Filter — 不同regime不同风控参数
    """

    def __init__(self,
                 trailing_stop_pct: float = 0.07,       # 7% trailing stop
                 max_loss_per_trade: float = 0.05,       # 5% max loss per dip trade
                 time_stop_days: int = 15,               # 15天时间止损
                 portfolio_max_dd: float = 0.15,          # 15% portfolio max drawdown
                 vol_target: float = 0.15,                # 15% target vol
                 vol_cap: float = 0.30,                   # 30%+ vol → max reduction
                 cooldown_days: int = 5,                  # 止损后冷却期
                 ):
        self.trailing_stop_pct = trailing_stop_pct
        self.max_loss_per_trade = max_loss_per_trade
        self.time_stop_days = time_stop_days
        self.portfolio_max_dd = portfolio_max_dd
        self.vol_target = vol_target
        self.vol_cap = vol_cap
        self.cooldown_days = cooldown_days


def get_regime_params(regime: MarketRegime) -> Dict:
    """
    不同market regime下的风控参数

    核心理念:
    - 上涨趋势: 积极买dip, 宽松止损
    - 回调(pullback): 正常买dip
    - 下行趋势: 缩小仓位, 收紧止损, 不加仓
    - 熊市/恐慌: 最小仓位, 最紧止损, 等待趋势反转
    """
    params = {
        MarketRegime.BULL_STRONG: {
            'max_position': 1.5,        # 最大仓位倍数
            'dip_aggression': 1.0,      # dip加仓激进度
            'trailing_stop': 0.08,      # 尾随止损 8%
            'allow_dip_buy': True,      # 允许买dip
            'base_position': 1.0,       # 基础仓位
            'hedge_ratio': 0.0,         # 对冲比例
            'description': '强势上涨 — 积极买dip，宽松止损',
        },
        MarketRegime.BULL_NORMAL: {
            'max_position': 1.3,
            'dip_aggression': 0.8,
            'trailing_stop': 0.07,
            'allow_dip_buy': True,
            'base_position': 1.0,
            'hedge_ratio': 0.0,
            'description': '正常上涨 — 正常买dip',
        },
        MarketRegime.PULLBACK: {
            'max_position': 1.5,
            'dip_aggression': 1.0,
            'trailing_stop': 0.06,
            'allow_dip_buy': True,
            'base_position': 1.0,
            'hedge_ratio': 0.0,
            'description': '回调 — 最佳买dip时机！',
        },
        MarketRegime.SIDEWAYS: {
            'max_position': 1.2,
            'dip_aggression': 0.5,
            'trailing_stop': 0.06,
            'allow_dip_buy': True,
            'base_position': 0.9,
            'hedge_ratio': 0.05,
            'description': '震荡 — 小幅买dip，注意方向',
        },
        MarketRegime.CORRECTION: {
            'max_position': 1.0,
            'dip_aggression': 0.3,
            'trailing_stop': 0.05,
            'allow_dip_buy': True,       # 允许但小量
            'base_position': 0.8,
            'hedge_ratio': 0.10,
            'description': '调整 — 谨慎小量买dip，收紧止损',
        },
        MarketRegime.DOWNTREND: {
            'max_position': 0.8,
            'dip_aggression': 0.0,       # 不买dip!
            'trailing_stop': 0.04,       # 紧止损
            'allow_dip_buy': False,      # 禁止买dip
            'base_position': 0.6,        # 减仓到60%
            'hedge_ratio': 0.15,         # 15%对冲
            'description': '下行趋势 — 禁止买dip！减仓+对冲',
        },
        MarketRegime.BEAR: {
            'max_position': 0.5,
            'dip_aggression': 0.0,
            'trailing_stop': 0.03,
            'allow_dip_buy': False,
            'base_position': 0.4,
            'hedge_ratio': 0.25,
            'description': '熊市 — 最小仓位，等待趋势反转',
        },
        MarketRegime.CRASH: {
            'max_position': 0.7,         # 恐慌时可以小量抄底
            'dip_aggression': 0.2,       # 极小量
            'trailing_stop': 0.03,
            'allow_dip_buy': True,       # 恐慌时可以少量买
            'base_position': 0.3,
            'hedge_ratio': 0.20,
            'description': '恐慌 — 极少量抄底，但必须止损',
        },
    }
    return params.get(regime, params[MarketRegime.SIDEWAYS])


# ============================================================
# Strategy: Risk-Managed Buy the Dip
# ============================================================
def strategy_risk_managed_dip(
    indicators: pd.DataFrame,
    regime_df: pd.DataFrame,
    spy_ret: pd.Series,
    vix: pd.Series = None,
    risk_mgr: RiskManager = None,
) -> Tuple[pd.Series, pd.DataFrame]:
    """
    完整风险管理版 Buy the Dip

    流程:
    1. 检测market regime
    2. 根据regime确定base position和是否允许买dip
    3. 检测dip信号 → 确定raw dip position
    4. 应用风控:
       - Vol scaling
       - Trailing stop
       - Max drawdown limit
       - Time stop
       - Cooldown period
    5. 输出最终position和交易日志
    """
    if risk_mgr is None:
        risk_mgr = RiskManager()

    n = len(indicators)

    # --- Dip score (same as before) ---
    dip_score = pd.Series(0.0, index=indicators.index)
    dip_score[indicators['rsi'] < 35] += 1
    dip_score[indicators['rsi'] < 25] += 1
    dip_score[indicators['rsi'] < 20] += 1
    dip_score[indicators['drawdown'] < -0.03] += 1
    dip_score[indicators['drawdown'] < -0.05] += 1
    dip_score[indicators['drawdown'] < -0.10] += 1
    dip_score[indicators['bb_pct'] < 0.15] += 1
    dip_score[indicators['down_streak'] >= 3] += 1
    dip_score[indicators['down_streak'] >= 5] += 1

    if vix is not None:
        vix_a = vix.reindex(indicators.index, method='ffill')
        dip_score[vix_a > 25] += 1
        dip_score[vix_a > 35] += 1
        dip_score[vix_a > 45] += 1

    # --- Build position day by day with risk management ---
    position = pd.Series(1.0, index=indicators.index)
    trade_log = []

    # State variables
    peak_equity = 1.0
    equity = 1.0
    dip_entry_price = None
    dip_entry_day = 0
    in_dip_trade = False
    cooldown_remaining = 0
    stopped_out = False
    trailing_high = indicators['close'].iloc[0] if n > 0 else 0

    for i in range(1, n):
        idx = indicators.index[i]
        close = indicators['close'].iloc[i]
        prev_close = indicators['close'].iloc[i - 1]
        ret_today = spy_ret.iloc[i] if not pd.isna(spy_ret.iloc[i]) else 0

        # Get current regime
        regime = regime_df['regime_enum'].iloc[i]
        params = get_regime_params(regime)

        # Update trailing high
        if close > trailing_high:
            trailing_high = close

        # Update equity
        equity *= (1 + position.iloc[i - 1] * ret_today)
        if equity > peak_equity:
            peak_equity = equity

        # ========== RISK CHECK 1: Portfolio Max Drawdown ==========
        portfolio_dd = (equity - peak_equity) / peak_equity
        if portfolio_dd < -risk_mgr.portfolio_max_dd:
            # Circuit breaker: cut to minimum
            position.iloc[i] = 0.3
            trade_log.append({
                'date': idx.strftime('%Y-%m-%d'),
                'action': 'CIRCUIT_BREAKER',
                'reason': f'组合回撤 {portfolio_dd*100:.1f}% 超过限制 {risk_mgr.portfolio_max_dd*100:.0f}%',
                'position': 0.3,
                'regime': regime.value,
                'close': close,
            })
            cooldown_remaining = risk_mgr.cooldown_days
            in_dip_trade = False
            continue

        # ========== RISK CHECK 2: Cooldown Period ==========
        if cooldown_remaining > 0:
            cooldown_remaining -= 1
            position.iloc[i] = params['base_position'] * 0.7  # reduced during cooldown
            continue

        # ========== RISK CHECK 3: Trailing Stop ==========
        trailing_dd = (close - trailing_high) / trailing_high
        if in_dip_trade and trailing_dd < -params['trailing_stop']:
            position.iloc[i] = params['base_position'] * 0.6
            trade_log.append({
                'date': idx.strftime('%Y-%m-%d'),
                'action': 'TRAILING_STOP',
                'reason': f'尾随止损触发: {trailing_dd*100:.1f}% (阈值: {params["trailing_stop"]*100:.0f}%)',
                'position': position.iloc[i],
                'regime': regime.value,
                'close': close,
            })
            in_dip_trade = False
            cooldown_remaining = risk_mgr.cooldown_days
            stopped_out = True
            continue

        # ========== RISK CHECK 4: Time Stop ==========
        if in_dip_trade and dip_entry_price is not None:
            days_held = i - dip_entry_day
            trade_return = (close - dip_entry_price) / dip_entry_price

            # Time stop: N days without recovery
            if days_held >= risk_mgr.time_stop_days and trade_return < 0:
                position.iloc[i] = params['base_position']
                trade_log.append({
                    'date': idx.strftime('%Y-%m-%d'),
                    'action': 'TIME_STOP',
                    'reason': f'{days_held}天未恢复, P&L={trade_return*100:.1f}%',
                    'position': position.iloc[i],
                    'regime': regime.value,
                    'close': close,
                })
                in_dip_trade = False
                continue

            # Max loss per trade
            if trade_return < -risk_mgr.max_loss_per_trade:
                position.iloc[i] = params['base_position'] * 0.7
                trade_log.append({
                    'date': idx.strftime('%Y-%m-%d'),
                    'action': 'MAX_LOSS_STOP',
                    'reason': f'单次亏损 {trade_return*100:.1f}% 超过限制 {risk_mgr.max_loss_per_trade*100:.0f}%',
                    'position': position.iloc[i],
                    'regime': regime.value,
                    'close': close,
                })
                in_dip_trade = False
                cooldown_remaining = risk_mgr.cooldown_days
                continue

        # ========== RISK CHECK 5: Vol Scaling ==========
        vol = regime_df['vol_21'].iloc[i]
        if not pd.isna(vol) and vol > 0:
            vol_scalar = min(risk_mgr.vol_target / vol, 1.5)
            if vol > risk_mgr.vol_cap:
                vol_scalar = risk_mgr.vol_target / risk_mgr.vol_cap * 0.5  # extra reduction
        else:
            vol_scalar = 1.0

        # ========== POSITION CALCULATION ==========
        base = params['base_position']
        score = dip_score.iloc[i]

        if params['allow_dip_buy'] and score > 0:
            # Buy the dip (scaled by regime aggression + vol)
            dip_addition = score * 0.08 * params['dip_aggression'] * vol_scalar
            raw_position = base + dip_addition
            raw_position = min(raw_position, params['max_position'])

            if raw_position > base + 0.05 and not in_dip_trade:
                # New dip trade entry
                in_dip_trade = True
                dip_entry_price = close
                dip_entry_day = i
                trailing_high = close  # reset trailing high for this trade
                stopped_out = False
                trade_log.append({
                    'date': idx.strftime('%Y-%m-%d'),
                    'action': 'DIP_BUY',
                    'reason': f'Dip Score={score:.0f}, Regime={regime.value}, Pos={raw_position:.2f}x',
                    'position': raw_position,
                    'regime': regime.value,
                    'close': close,
                })
        else:
            # No dip buy allowed in this regime
            raw_position = base * vol_scalar

        # Apply hedge in bearish regimes
        hedge = params['hedge_ratio']
        if hedge > 0:
            raw_position *= (1 - hedge)

        # Regime change log
        if i > 0 and regime_df['regime'].iloc[i] != regime_df['regime'].iloc[i - 1]:
            trade_log.append({
                'date': idx.strftime('%Y-%m-%d'),
                'action': 'REGIME_CHANGE',
                'reason': f'{regime_df["regime"].iloc[i-1]} → {regime.value}',
                'position': raw_position,
                'regime': regime.value,
                'close': close,
            })

        position.iloc[i] = max(raw_position, 0.2)  # minimum 20% exposure

    # Apply positions (shift by 1 day)
    position = position.shift(1)
    managed_ret = position * spy_ret

    # Transaction costs
    turnover = position.diff().abs()
    managed_ret -= turnover * 0.0003

    log_df = pd.DataFrame(trade_log) if trade_log else pd.DataFrame()

    return managed_ret, log_df


# ============================================================
# Original Strategies (for comparison)
# ============================================================
def strategy_naive_dip(indicators: pd.DataFrame, spy_ret: pd.Series,
                        vix: pd.Series = None) -> pd.Series:
    """原始无风控 Buy the Dip (对照组)."""
    score = pd.Series(0.0, index=indicators.index)
    score[indicators['rsi'] < 30] += 1
    score[indicators['rsi'] < 20] += 1
    score[indicators['drawdown'] < -0.05] += 1
    score[indicators['drawdown'] < -0.10] += 1
    score[indicators['bb_pct'] < 0.15] += 1
    score[indicators['down_streak'] >= 3] += 1
    if vix is not None:
        vix_a = vix.reindex(indicators.index, method='ffill')
        score[vix_a > 25] += 1
        score[vix_a > 35] += 1

    position = 1.0 + score * 0.1
    position = position.clip(0.8, 1.8).shift(1)
    managed_ret = position * spy_ret
    turnover = position.diff().abs()
    managed_ret -= turnover * 0.0003
    return managed_ret


def strategy_trend_filtered_only(indicators: pd.DataFrame, spy_ret: pd.Series,
                                   vix: pd.Series = None) -> pd.Series:
    """只有趋势过滤 (无完整风控)."""
    uptrend = indicators['close'] > indicators['ma200']

    score = pd.Series(0.0, index=indicators.index)
    score[indicators['rsi'] < 35] += 1
    score[indicators['rsi'] < 25] += 1
    score[indicators['drawdown'] < -0.03] += 1
    score[indicators['drawdown'] < -0.07] += 1
    score[indicators['bb_pct'] < 0.2] += 1
    if vix is not None:
        vix_a = vix.reindex(indicators.index, method='ffill')
        score[vix_a > 25] += 1

    pos_up = (1.0 + score * 0.15).clip(1.0, 1.8)
    pos_down = (0.7 + score * 0.05).clip(0.5, 1.0)
    position = pd.Series(1.0, index=indicators.index)
    position[uptrend] = pos_up[uptrend]
    position[~uptrend] = pos_down[~uptrend]
    position = position.shift(1)

    managed_ret = position * spy_ret
    turnover = position.diff().abs()
    managed_ret -= turnover * 0.0003
    return managed_ret


# ============================================================
# Performance Metrics
# ============================================================
def calc_metrics(daily_returns: pd.Series, name: str) -> Dict:
    dr = daily_returns.dropna()
    if len(dr) < 60:
        return {'name': name, 'error': 'insufficient data'}

    cum = (1 + dr).cumprod()
    total = cum.iloc[-1] - 1
    n_years = len(dr) / 252
    ann_ret = (1 + total) ** (1 / n_years) - 1
    ann_vol = dr.std() * np.sqrt(252)
    rf = 0.025
    sharpe = (ann_ret - rf) / ann_vol if ann_vol > 0 else 0

    downside = dr[dr < 0]
    ds_vol = downside.std() * np.sqrt(252) if len(downside) > 0 else 1e-8
    sortino = (ann_ret - rf) / ds_vol

    rolling_max = cum.cummax()
    dd = (cum - rolling_max) / rolling_max
    max_dd = dd.min()
    calmar = ann_ret / abs(max_dd) if max_dd != 0 else 0

    # Max drawdown duration
    dd_end_idx = dd.idxmin()
    peak_before = cum[:dd_end_idx].idxmax()
    recovery = cum[dd_end_idx:]
    recovery_dates = recovery[recovery >= cum[peak_before]].index
    if len(recovery_dates) > 0:
        dd_duration = (recovery_dates[0] - peak_before).days
    else:
        dd_duration = (cum.index[-1] - peak_before).days

    monthly = dr.resample('ME').sum()
    monthly_win = (monthly > 0).sum() / len(monthly) if len(monthly) > 0 else 0
    yearly = dr.resample('YE').apply(lambda x: (1 + x).prod() - 1)

    # Worst year
    worst_year = yearly.min()
    best_year = yearly.max()

    return {
        'name': name,
        'total_return': float(total),
        'ann_return': float(ann_ret),
        'ann_vol': float(ann_vol),
        'sharpe': float(sharpe),
        'sortino': float(sortino),
        'max_dd': float(max_dd),
        'calmar': float(calmar),
        'dd_duration_days': int(dd_duration),
        'monthly_win_rate': float(monthly_win),
        'worst_year': float(worst_year),
        'best_year': float(best_year),
        'yearly': {str(d.year): float(r) for d, r in yearly.items()},
    }


# ============================================================
# Display
# ============================================================
def print_table(results: List[Dict]):
    print(f"\n{'=' * 140}")
    print(f"{'Strategy':<35} {'Total':>8} {'Ann.Ret':>8} {'Ann.Vol':>8} {'Sharpe':>7}"
          f" {'Sortino':>8} {'MaxDD':>8} {'Calmar':>7} {'DDDays':>7} {'MoWin%':>7} {'WorstYr':>8}")
    print(f"{'=' * 140}")
    for r in results:
        if 'error' in r:
            print(f"{r['name']:<35} ERROR")
            continue
        print(
            f"{r['name']:<35}"
            f" {r['total_return']*100:>7.1f}%"
            f" {r['ann_return']*100:>7.2f}%"
            f" {r['ann_vol']*100:>7.2f}%"
            f" {r['sharpe']:>7.2f}"
            f" {r['sortino']:>8.2f}"
            f" {r['max_dd']*100:>7.2f}%"
            f" {r['calmar']:>7.2f}"
            f" {r['dd_duration_days']:>6}d"
            f" {r['monthly_win_rate']*100:>6.1f}%"
            f" {r['worst_year']*100:>7.2f}%"
        )
    print(f"{'=' * 140}")


def print_yearly(results: List[Dict]):
    all_years = sorted(set(y for r in results for y in r.get('yearly', {}).keys()))
    width = 22

    header = f"{'Year':<6}"
    for r in results:
        header += f" {r['name'][:width-1]:>{width}}"
    print(f"\n{'=' * (6 + (width + 1) * len(results))}")
    print(header)
    print(f"{'=' * (6 + (width + 1) * len(results))}")

    for year in all_years:
        row = f"{year:<6}"
        for r in results:
            yr = r.get('yearly', {}).get(year, None)
            if yr is not None:
                row += f" {yr*100:>{width-1}.2f}%"
            else:
                row += f" {'N/A':>{width}}"
        print(row)
    print(f"{'=' * (6 + (width + 1) * len(results))}")


def print_regime_stats(regime_df: pd.DataFrame):
    """Print regime distribution."""
    print(f"\n{'=' * 80}")
    print(f"  MARKET REGIME DISTRIBUTION (2014-2024)")
    print(f"{'=' * 80}")

    counts = regime_df['regime'].value_counts()
    total = len(regime_df)

    for regime_name, count in counts.items():
        pct = count / total * 100
        bar = '#' * int(pct)
        print(f"  {regime_name:<12} {count:>5} days ({pct:>5.1f}%) {bar}")


def print_trade_log(log_df: pd.DataFrame, max_rows: int = 50):
    """Print risk management trade log."""
    if log_df.empty:
        print("  No risk events recorded.")
        return

    print(f"\n{'=' * 120}")
    print(f"  RISK MANAGEMENT EVENT LOG (last {max_rows})")
    print(f"{'=' * 120}")
    print(f"  {'Date':<12} {'Action':<18} {'Regime':<10} {'Close':>8} {'Position':>9} {'Reason'}")
    print(f"  {'─' * 114}")

    for _, row in log_df.tail(max_rows).iterrows():
        action = row['action']
        # Color markers
        marker = ""
        if action in ['CIRCUIT_BREAKER', 'MAX_LOSS_STOP']:
            marker = " !!!"
        elif action in ['TRAILING_STOP', 'TIME_STOP']:
            marker = " !!"
        elif action == 'DIP_BUY':
            marker = " +"

        print(
            f"  {row['date']:<12}"
            f" {action:<18}"
            f" {row['regime']:<10}"
            f" ${row['close']:>7.2f}"
            f" {row['position']:>8.2f}x"
            f" {row['reason']}{marker}"
        )
    print(f"  {'─' * 114}")

    # Summary
    action_counts = log_df['action'].value_counts()
    print(f"\n  Event Summary:")
    for action, count in action_counts.items():
        print(f"    {action:<20} {count:>4} times")


def print_downtrend_analysis(indicators: pd.DataFrame, regime_df: pd.DataFrame,
                               spy_ret: pd.Series, vix: pd.Series):
    """Analyze what happens during downtrends specifically."""
    print(f"\n{'=' * 80}")
    print(f"  DOWNTREND PERIOD ANALYSIS — Dip Buying 在下行趋势中的表现")
    print(f"{'=' * 80}")

    bearish_regimes = [MarketRegime.DOWNTREND.value, MarketRegime.BEAR.value,
                       MarketRegime.CORRECTION.value, MarketRegime.CRASH.value]
    bullish_regimes = [MarketRegime.BULL_STRONG.value, MarketRegime.BULL_NORMAL.value,
                       MarketRegime.PULLBACK.value]

    for regime_group, label in [(bullish_regimes, '上涨趋势'), (bearish_regimes, '下行趋势')]:
        mask = regime_df['regime'].isin(regime_group)
        if mask.sum() == 0:
            continue

        ret_in_regime = spy_ret[mask].dropna()
        n_days = len(ret_in_regime)
        ann_ret = (1 + ret_in_regime).prod() ** (252 / max(n_days, 1)) - 1

        # Dip signals in this regime
        dip_mask = mask & ((indicators['rsi'] < 30) | (indicators['drawdown'] < -0.05))
        dip_days = dip_mask.sum()

        # Forward returns after dips in this regime
        fwd_21d = indicators['close'].pct_change(21).shift(-21)
        fwd_ret = fwd_21d[dip_mask].dropna()
        if len(fwd_ret) > 0:
            avg_fwd = fwd_ret.mean() * 100
            win_rate = (fwd_ret > 0).mean() * 100
        else:
            avg_fwd = 0
            win_rate = 0

        print(f"\n  [{label}] ({n_days} trading days)")
        print(f"    SPY年化收益:        {ann_ret*100:>+7.2f}%")
        print(f"    Dip信号出现:        {dip_days} days")
        print(f"    Dip后21天平均收益:  {avg_fwd:>+7.2f}%")
        print(f"    Dip后21天胜率:      {win_rate:>6.1f}%")
        print(f"    结论: {'可以买dip' if win_rate > 55 else '不要买dip！'}")


# ============================================================
# Main
# ============================================================
def run_risk_managed_backtest():
    start = '2014-01-01'
    end = '2024-12-31'

    print("=" * 80)
    print("  BUY THE DIP + 下行风险管理 BACKTEST (REAL DATA)")
    print(f"  Period: {start} to {end}")
    print(f"  Data: Yahoo Finance (yfinance)")
    print("=" * 80)

    # Fetch data
    print("\n[1/6] Fetching real market data...")
    tickers = ['SPY', '^VIX', 'TLT', 'SHY']
    data = {}
    for t in tickers:
        try:
            df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
            if df is not None and len(df) > 100:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                data[t] = df
                logger.info(f"  {t}: {len(df)} days")
        except Exception as e:
            logger.warning(f"  {t}: FAILED - {e}")

    spy_close = data['SPY']['Close']
    spy_ret = spy_close.pct_change()
    vix_close = data['^VIX']['Close'] if '^VIX' in data else None

    # Compute indicators
    print("\n[2/6] Computing indicators...")
    indicators = compute_indicators(spy_close)

    # Detect regimes
    print("\n[3/6] Detecting market regimes...")
    regime_df = detect_regime(spy_close, vix_close)
    print_regime_stats(regime_df)

    # Downtrend analysis
    print_downtrend_analysis(indicators, regime_df, spy_ret, vix_close)

    # Run strategies
    print("\n[4/6] Running strategies...")

    strategies = {}

    # 1. Benchmark
    logger.info("  SPY Buy & Hold")

    # 2. Naive dip (no risk management)
    logger.info("  Naive Dip (无风控)")
    strategies['Naive Dip (无风控)'] = strategy_naive_dip(indicators, spy_ret, vix_close)

    # 3. Trend-filtered only
    logger.info("  Trend-Filtered (仅趋势过滤)")
    strategies['Trend-Filtered (仅趋势)'] = strategy_trend_filtered_only(indicators, spy_ret, vix_close)

    # 4. Full risk-managed (default params)
    logger.info("  Risk-Managed Dip (完整风控)")
    rm_ret, rm_log = strategy_risk_managed_dip(
        indicators, regime_df, spy_ret, vix_close,
        RiskManager()
    )
    strategies['Risk-Managed (完整风控)'] = rm_ret

    # 5. Conservative risk management
    logger.info("  Conservative (保守风控)")
    cons_ret, cons_log = strategy_risk_managed_dip(
        indicators, regime_df, spy_ret, vix_close,
        RiskManager(
            trailing_stop_pct=0.05,
            max_loss_per_trade=0.03,
            time_stop_days=10,
            portfolio_max_dd=0.10,
            vol_target=0.12,
            cooldown_days=10,
        )
    )
    strategies['Conservative (保守风控)'] = cons_ret

    # 6. Aggressive risk management
    logger.info("  Aggressive (激进风控)")
    agg_ret, agg_log = strategy_risk_managed_dip(
        indicators, regime_df, spy_ret, vix_close,
        RiskManager(
            trailing_stop_pct=0.10,
            max_loss_per_trade=0.08,
            time_stop_days=20,
            portfolio_max_dd=0.20,
            vol_target=0.18,
            cooldown_days=3,
        )
    )
    strategies['Aggressive (激进风控)'] = agg_ret

    # Results
    print("\n[5/6] Calculating results...")

    results = [calc_metrics(spy_ret, 'SPY Buy & Hold')]
    for name, rets in strategies.items():
        results.append(calc_metrics(rets, name))

    # Sort by Sharpe
    results_sorted = sorted(results, key=lambda x: x.get('sharpe', -99), reverse=True)

    print_table(results_sorted)
    print_yearly(results)

    # Trade log
    print_trade_log(rm_log, max_rows=50)

    # Risk event stats
    print(f"\n{'=' * 80}")
    print(f"  RISK MANAGEMENT EFFECTIVENESS")
    print(f"{'=' * 80}")

    spy_m = next(r for r in results if r['name'] == 'SPY Buy & Hold')
    naive_m = next(r for r in results if 'Naive' in r['name'])

    for r in results_sorted:
        if r['name'] == 'SPY Buy & Hold':
            continue
        alpha_vs_spy = r.get('ann_return', 0) - spy_m.get('ann_return', 0)
        dd_vs_spy = r.get('max_dd', 0) - spy_m.get('max_dd', 0)
        dd_vs_naive = r.get('max_dd', 0) - naive_m.get('max_dd', 0)
        sharpe_vs_spy = r.get('sharpe', 0) - spy_m.get('sharpe', 0)

        print(
            f"\n  {r['name']}"
            f"\n    vs SPY:   Alpha {alpha_vs_spy*100:>+6.2f}%"
            f" | MaxDD改善 {dd_vs_spy*100:>+7.2f}%"
            f" | Sharpe差 {sharpe_vs_spy:>+5.2f}"
            f"\n    vs Naive: MaxDD改善 {dd_vs_naive*100:>+7.2f}%"
            f" | 最差年份 {r.get('worst_year',0)*100:>+7.2f}%"
            f" | 最长回撤 {r.get('dd_duration_days',0)}天"
        )

    # Save
    print("\n[6/6] Saving results...")

    output = {
        'metadata': {
            'period': f"{start} to {end}",
            'data_source': 'Yahoo Finance (REAL DATA)',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'risk_management': {
                'default': {
                    'trailing_stop': '7%',
                    'max_loss_per_trade': '5%',
                    'time_stop': '15 days',
                    'portfolio_max_dd': '15%',
                    'vol_target': '15%',
                    'cooldown': '5 days',
                },
            },
        },
        'regime_distribution': regime_df['regime'].value_counts().to_dict(),
        'results': {r['name']: r for r in results},
    }

    with open('backtests/risk_managed_dip_results.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)

    if not rm_log.empty:
        rm_log.to_csv('backtests/risk_events_log.csv', index=False)

    eq = pd.DataFrame({name: (1 + ret).cumprod() for name, ret in strategies.items()})
    eq['SPY_BH'] = (1 + spy_ret).cumprod()
    eq.to_csv('backtests/risk_managed_equity_curves.csv')

    logger.info("  All results saved to backtests/")

    # Final summary
    print(f"\n{'=' * 80}")
    print(f"  总结: 下行趋势中的风险管理策略")
    print(f"{'=' * 80}")
    print("""
    下行趋势中 Buy the Dip 的6层风控体系:

    ┌─────────────────────────────────────────────────────────────────┐
    │ Layer 1: REGIME DETECTION (趋势识别)                           │
    │   识别8种市场状态, 下行趋势中禁止买dip, 减仓至60%              │
    │                                                                 │
    │ Layer 2: TRAILING STOP (尾随止损)                               │
    │   上涨趋势: 8%止损 | 下行趋势: 4%止损 | 熊市: 3%止损           │
    │                                                                 │
    │ Layer 3: MAX LOSS PER TRADE (单次最大亏损)                      │
    │   每次dip买入最大允许亏损5%, 超过则止损出场                      │
    │                                                                 │
    │ Layer 4: TIME STOP (时间止损)                                   │
    │   买入后15天仍未恢复 → 减仓回基础仓位                           │
    │                                                                 │
    │ Layer 5: VOL SCALING (波动率调整)                               │
    │   高波动环境自动缩小仓位, 目标波动率15%                         │
    │                                                                 │
    │ Layer 6: CIRCUIT BREAKER (熔断机制)                             │
    │   组合回撤超过15% → 强制减仓至30%, 冷却5天                      │
    └─────────────────────────────────────────────────────────────────┘

    关键规则:
    1. 下行趋势 (SPY < 200-MA且MA下行) → 禁止买dip, 减仓到60%
    2. 熊市 (-20%+) → 减仓到40%, 25%对冲
    3. 恐慌 (VIX>40) → 可以极少量抄底, 但必须严格止损
    4. 止损后强制冷却5天, 避免反复抄底被套
    5. 上涨趋势中的回调 → 最佳买dip时机, 积极加仓
    """)

    return results, eq


if __name__ == '__main__':
    results, equity = run_risk_managed_backtest()
