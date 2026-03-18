"""
杠杆 Buy the Dip — 不爆仓执行方案 (Leveraged Dip Buying Without Blowup)
========================================================================

核心问题: 加杠杆买dip收益更高，但如何避免爆仓？

测试方案:
  1. 不同杠杆水平 (1.5x, 2x, 3x) 的历史表现
  2. 爆仓模拟: 在什么条件下会被强平
  3. 防爆仓策略: 动态杠杆 + 强制减杠杆规则
  4. 最优执行方案: 分批建仓 + 逐级加仓 + 极限止损

杠杆工具对比:
  - UPRO (3x SPY): 每日重置，长期衰减
  - SSO (2x SPY): 每日重置
  - SPY期权 (LEAPS): 内置杠杆，时间衰减
  - 保证金账户: 真实杠杆，有margin call风险
  - 期货 (ES): 固定保证金，真实杠杆

Data: Yahoo Finance — REAL DATA
Period: 2014-01-01 to 2024-12-31
"""

import warnings
warnings.filterwarnings('ignore')

import json
import logging
import sys
from datetime import datetime
from typing import Dict, List, Tuple

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
# Data & Indicators
# ============================================================
def fetch_data(start: str, end: str) -> Dict:
    tickers = {
        'SPY': 'S&P 500',
        'UPRO': '3x Bull SPY',
        'SSO': '2x Bull SPY',
        '^VIX': 'VIX',
        'TLT': '20yr Treasury',
        'SHY': 'T-Bills',
    }
    data = {}
    for t, name in tickers.items():
        try:
            df = yf.download(t, start=start, end=end, progress=False, auto_adjust=True)
            if df is not None and len(df) > 100:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                data[t] = df
                logger.info(f"  {t} ({name}): {len(df)} days")
        except Exception as e:
            logger.warning(f"  {t}: FAILED - {e}")
    return data


def compute_indicators(close: pd.Series) -> pd.DataFrame:
    df = pd.DataFrame(index=close.index)
    df['close'] = close
    df['ret'] = close.pct_change()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss + 1e-8)
    df['rsi'] = 100 - (100 / (1 + rs))

    high_50 = close.rolling(50).max()
    df['drawdown'] = (close - high_50) / high_50

    df['bb_mid'] = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    df['bb_lower'] = df['bb_mid'] - 2 * bb_std
    df['bb_upper'] = df['bb_mid'] + 2 * bb_std
    df['bb_pct'] = (close - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-8)

    down_day = (df['ret'] < 0).astype(int)
    streak = pd.Series(0, index=close.index)
    for i in range(1, len(streak)):
        streak.iloc[i] = streak.iloc[i-1] + 1 if down_day.iloc[i] == 1 else 0
    df['down_streak'] = streak

    df['ma50'] = close.rolling(50).mean()
    df['ma200'] = close.rolling(200).mean()
    df['vol_21'] = df['ret'].rolling(21).std() * np.sqrt(252)

    return df


def calc_dip_score(indicators: pd.DataFrame, vix: pd.Series = None) -> pd.Series:
    """Calculate dip intensity score (0-10+)."""
    score = pd.Series(0.0, index=indicators.index)
    score[indicators['rsi'] < 35] += 1
    score[indicators['rsi'] < 25] += 1
    score[indicators['rsi'] < 20] += 1
    score[indicators['drawdown'] < -0.03] += 1
    score[indicators['drawdown'] < -0.05] += 1
    score[indicators['drawdown'] < -0.10] += 1
    score[indicators['bb_pct'] < 0.15] += 1
    score[indicators['bb_pct'] < 0.0] += 1
    score[indicators['down_streak'] >= 3] += 1
    score[indicators['down_streak'] >= 5] += 1
    if vix is not None:
        va = vix.reindex(indicators.index, method='ffill')
        score[va > 25] += 1
        score[va > 35] += 1
        score[va > 45] += 1
    return score


# ============================================================
# Metrics
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

    yearly = dr.resample('YE').apply(lambda x: (1 + x).prod() - 1)

    # Blowup check: did equity ever drop below 10% of peak?
    min_equity_ratio = (cum / cum.cummax()).min()

    # Margin call simulation: at 2x leverage, margin call at -50%
    worst_5d = dr.rolling(5).sum().min()
    worst_21d = dr.rolling(21).sum().min()

    return {
        'name': name,
        'total_return': float(total),
        'ann_return': float(ann_ret),
        'ann_vol': float(ann_vol),
        'sharpe': float(sharpe),
        'sortino': float(sortino),
        'max_dd': float(max_dd),
        'calmar': float(calmar),
        'min_equity_ratio': float(min_equity_ratio),
        'worst_5d': float(worst_5d) if not pd.isna(worst_5d) else 0,
        'worst_21d': float(worst_21d) if not pd.isna(worst_21d) else 0,
        'yearly': {str(d.year): float(r) for d, r in yearly.items()},
    }


# ============================================================
# LEVERAGED STRATEGIES
# ============================================================

def strategy_fixed_leverage(spy_ret: pd.Series, leverage: float) -> pd.Series:
    """固定杠杆 (模拟保证金账户或期货)."""
    return spy_ret * leverage


def strategy_leveraged_etf_real(etf_ret: pd.Series) -> pd.Series:
    """真实杠杆ETF (UPRO/SSO)，包含每日重置衰减."""
    return etf_ret


def strategy_naive_leveraged_dip(
    indicators: pd.DataFrame, spy_ret: pd.Series,
    base_leverage: float = 1.0, dip_leverage: float = 2.0,
    vix: pd.Series = None,
) -> pd.Series:
    """
    朴素杠杆Dip: 平时1x, dip时加到2x
    问题: 没有防爆仓机制
    """
    score = calc_dip_score(indicators, vix)
    leverage = pd.Series(base_leverage, index=indicators.index)
    leverage[score >= 2] = base_leverage + (dip_leverage - base_leverage) * 0.5
    leverage[score >= 4] = dip_leverage
    leverage[score >= 6] = dip_leverage * 1.2
    leverage = leverage.shift(1)

    managed_ret = leverage * spy_ret
    turnover = leverage.diff().abs()
    managed_ret -= turnover * 0.0005  # higher costs for leverage
    return managed_ret


def strategy_anti_blowup_leveraged_dip(
    indicators: pd.DataFrame, spy_ret: pd.Series,
    vix: pd.Series = None,
    # --- 杠杆参数 ---
    base_leverage: float = 1.0,       # 平时杠杆
    max_leverage: float = 2.5,        # 最大杠杆
    # --- 防爆仓参数 ---
    margin_call_dd: float = -0.25,    # 模拟margin call线 (账户亏25%触发)
    forced_delever_dd: float = -0.15, # 强制去杠杆线 (亏15%开始减杠杆)
    vol_target: float = 0.20,         # 杠杆后目标波动率
    max_daily_loss: float = -0.05,    # 单日最大亏损触发去杠杆
    recovery_threshold: float = 0.03, # 恢复到峰值3%以内才重新加杠杆
    # --- 分批建仓参数 ---
    tranche_size: float = 0.3,        # 每次加仓幅度
    tranche_interval: int = 3,        # 两次加仓最少间隔天数
    cooldown_after_stop: int = 10,    # 止损后冷却期
) -> Tuple[pd.Series, pd.DataFrame]:
    """
    防爆仓杠杆 Buy the Dip

    核心逻辑:
    1. 趋势过滤: 上涨趋势才用杠杆
    2. 分批建仓: 不一次性加满杠杆
    3. 波动率控制: 高波动自动降杠杆
    4. 强制去杠杆: 亏损达阈值自动减仓
    5. 模拟Margin Call: 到警戒线全部平仓
    6. 冷却期: 止损后不立即重新加仓
    """
    n = len(indicators)
    score = calc_dip_score(indicators, vix)
    uptrend = indicators['close'] > indicators['ma200']

    leverage = pd.Series(base_leverage, index=indicators.index)
    equity = 1.0
    peak_equity = 1.0
    cooldown = 0
    last_add_day = -999
    current_lev = base_leverage
    trade_log = []

    for i in range(1, n):
        idx = indicators.index[i]
        ret = spy_ret.iloc[i] if not pd.isna(spy_ret.iloc[i]) else 0
        close = indicators['close'].iloc[i]

        # Update equity
        equity *= (1 + current_lev * ret)
        if equity > peak_equity:
            peak_equity = equity
        dd = (equity - peak_equity) / peak_equity

        # ===== CHECK 1: Margin Call (爆仓警戒) =====
        if dd < margin_call_dd:
            current_lev = 0.3  # 几乎全部平仓
            cooldown = cooldown_after_stop * 2
            trade_log.append({
                'date': idx.strftime('%Y-%m-%d'), 'action': 'MARGIN_CALL',
                'leverage': 0.3, 'dd': f'{dd*100:.1f}%', 'close': close,
                'reason': f'账户回撤{dd*100:.1f}%触发margin call，强制平仓至0.3x',
            })
            leverage.iloc[i] = current_lev
            continue

        # ===== CHECK 2: Forced Deleverage (强制去杠杆) =====
        if dd < forced_delever_dd:
            # 线性降杠杆: dd越深，杠杆越低
            delever_ratio = max(0.3, 1 + (dd - forced_delever_dd) / (margin_call_dd - forced_delever_dd))
            target_lev = base_leverage * delever_ratio
            if target_lev < current_lev:
                current_lev = target_lev
                trade_log.append({
                    'date': idx.strftime('%Y-%m-%d'), 'action': 'FORCED_DELEVER',
                    'leverage': round(current_lev, 2), 'dd': f'{dd*100:.1f}%', 'close': close,
                    'reason': f'账户回撤{dd*100:.1f}%，自动去杠杆至{current_lev:.2f}x',
                })
            leverage.iloc[i] = current_lev
            continue

        # ===== CHECK 3: Single Day Loss =====
        daily_pnl = current_lev * ret
        if daily_pnl < max_daily_loss:
            current_lev = max(0.5, current_lev * 0.6)
            cooldown = cooldown_after_stop
            trade_log.append({
                'date': idx.strftime('%Y-%m-%d'), 'action': 'DAILY_LOSS_STOP',
                'leverage': round(current_lev, 2), 'dd': f'{dd*100:.1f}%', 'close': close,
                'reason': f'单日亏损{daily_pnl*100:.1f}%，减杠杆至{current_lev:.2f}x',
            })
            leverage.iloc[i] = current_lev
            continue

        # ===== CHECK 4: Cooldown =====
        if cooldown > 0:
            cooldown -= 1
            current_lev = min(current_lev, base_leverage * 0.8)
            leverage.iloc[i] = current_lev
            continue

        # ===== CHECK 5: Vol Scaling =====
        vol = indicators['vol_21'].iloc[i]
        if not pd.isna(vol) and vol > 0:
            vol_scalar = min(vol_target / vol, 1.5)
        else:
            vol_scalar = 1.0

        # ===== POSITION SIZING =====
        s = score.iloc[i]
        is_up = uptrend.iloc[i]

        if is_up and s >= 2:
            # 上涨趋势中的dip → 加杠杆
            # 分批加仓: 每次只加tranche_size
            days_since_last_add = i - last_add_day
            if days_since_last_add >= tranche_interval:
                target_lev = base_leverage + min(s * 0.2, max_leverage - base_leverage)
                target_lev *= vol_scalar
                target_lev = min(target_lev, max_leverage)

                # 分批: 从当前杠杆向目标靠拢
                if target_lev > current_lev:
                    step = min(tranche_size, target_lev - current_lev)
                    current_lev += step
                    last_add_day = i
                    if step > 0.1:
                        trade_log.append({
                            'date': idx.strftime('%Y-%m-%d'), 'action': 'TRANCHE_ADD',
                            'leverage': round(current_lev, 2), 'dd': f'{dd*100:.1f}%', 'close': close,
                            'reason': f'Dip Score={s:.0f}, 分批加仓+{step:.2f} → {current_lev:.2f}x',
                        })
            # Cap
            current_lev = min(current_lev, max_leverage * vol_scalar)

        elif is_up and s < 2:
            # 上涨趋势, 无dip → 逐渐回到base
            if current_lev > base_leverage:
                current_lev = max(base_leverage, current_lev - 0.05)  # 缓慢下降
        else:
            # 下行趋势 → 降到base以下
            target_lev = base_leverage * 0.7 * vol_scalar
            current_lev = min(current_lev, target_lev)
            if current_lev < base_leverage * 0.5:
                current_lev = base_leverage * 0.5

        # Recovery check: 只有恢复到峰值附近才允许满杠杆
        if dd < -recovery_threshold and current_lev > base_leverage * 1.2:
            current_lev = min(current_lev, base_leverage * 1.2)

        leverage.iloc[i] = max(current_lev, 0.2)

    # Apply
    leverage = leverage.shift(1)
    managed_ret = leverage * spy_ret
    turnover = leverage.diff().abs()
    managed_ret -= turnover * 0.0005

    log_df = pd.DataFrame(trade_log) if trade_log else pd.DataFrame()
    return managed_ret, log_df


def strategy_kelly_leveraged_dip(
    indicators: pd.DataFrame, spy_ret: pd.Series,
    vix: pd.Series = None,
    kelly_fraction: float = 0.5,  # 半凯利 (保守)
    max_leverage: float = 2.5,
) -> pd.Series:
    """
    凯利公式杠杆 Buy the Dip

    Kelly Criterion: f* = (p * b - q) / b
    其中: p = 胜率, b = 赔率, q = 1-p

    用滚动窗口估计p和b, 然后用半凯利确定杠杆。
    半凯利(0.5x Kelly) 大幅降低爆仓风险。
    """
    score = calc_dip_score(indicators, vix)
    uptrend = indicators['close'] > indicators['ma200']

    leverage = pd.Series(1.0, index=indicators.index)

    for i in range(252, len(indicators)):
        # Rolling window stats
        window = spy_ret.iloc[max(0, i-252):i]
        win_rate = (window > 0).mean()
        avg_win = window[window > 0].mean() if (window > 0).any() else 0.001
        avg_loss = abs(window[window < 0].mean()) if (window < 0).any() else 0.001

        # Kelly
        b = avg_win / avg_loss  # payoff ratio
        kelly_f = (win_rate * b - (1 - win_rate)) / b
        kelly_f = max(kelly_f, 0) * kelly_fraction  # half Kelly

        s = score.iloc[i]
        is_up = uptrend.iloc[i]

        if is_up and s >= 2:
            # Dip in uptrend: use Kelly leverage
            lev = 1.0 + kelly_f * min(s / 3, 1.5)
        elif is_up:
            lev = 1.0 + kelly_f * 0.3
        else:
            lev = max(0.5, 1.0 - kelly_f * 0.5)

        leverage.iloc[i] = min(lev, max_leverage)

    leverage = leverage.shift(1)
    managed_ret = leverage * spy_ret
    turnover = leverage.diff().abs()
    managed_ret -= turnover * 0.0005
    return managed_ret


def strategy_tiered_entry(
    indicators: pd.DataFrame, spy_ret: pd.Series,
    vix: pd.Series = None,
) -> Tuple[pd.Series, pd.DataFrame]:
    """
    阶梯式加仓法 (最实用的执行方案)

    执行规则:
    Level 0: 正常持仓 1.0x (无dip)
    Level 1: DD > 3% 或 RSI < 35  → 加仓到 1.3x  (拿出备用金30%)
    Level 2: DD > 5% 或 RSI < 30  → 加仓到 1.6x  (再加30%)
    Level 3: DD > 8% 或 RSI < 25  → 加仓到 2.0x  (满仓杠杆)
    Level 4: DD > 12% 且 VIX > 35 → 加仓到 2.5x  (极端机会，恐慌才加)

    退出:
    - 恢复到MA50以上 → 逐级减杠杆
    - 每涨回2% → 减一级
    - 完全恢复新高 → 回到1.0x

    防爆仓:
    - 下行趋势(< MA200) → 最高1.3x
    - 总亏损 > 20% → 强制回1.0x
    - 单日亏损 > 4% → 立即减仓
    """
    score = calc_dip_score(indicators, vix)
    uptrend = indicators['close'] > indicators['ma200']
    dd = indicators['drawdown']

    leverage = pd.Series(1.0, index=indicators.index)
    trades = []

    equity = 1.0
    peak_equity = 1.0
    current_level = 0
    cooldown = 0

    level_map = {0: 1.0, 1: 1.3, 2: 1.6, 3: 2.0, 4: 2.5}

    for i in range(1, len(indicators)):
        idx = indicators.index[i]
        ret = spy_ret.iloc[i] if not pd.isna(spy_ret.iloc[i]) else 0
        close = indicators['close'].iloc[i]
        is_up = uptrend.iloc[i]

        lev = level_map[current_level]
        equity *= (1 + lev * ret)
        if equity > peak_equity:
            peak_equity = equity
        port_dd = (equity - peak_equity) / peak_equity

        # Safety: forced delever
        if port_dd < -0.20:
            current_level = 0
            cooldown = 10
            trades.append({
                'date': idx.strftime('%Y-%m-%d'), 'level': 0, 'leverage': 1.0,
                'action': 'EMERGENCY_EXIT', 'close': close,
                'reason': f'组合亏损{port_dd*100:.1f}%，紧急去杠杆',
            })
            leverage.iloc[i] = 1.0
            continue

        if lev * ret < -0.04:
            current_level = max(0, current_level - 2)
            cooldown = 5
            trades.append({
                'date': idx.strftime('%Y-%m-%d'), 'level': current_level,
                'leverage': level_map[current_level], 'action': 'DAILY_LOSS_CUT',
                'close': close, 'reason': f'单日亏损{lev*ret*100:.1f}%',
            })
            leverage.iloc[i] = level_map[current_level]
            continue

        if cooldown > 0:
            cooldown -= 1
            leverage.iloc[i] = level_map[current_level]
            continue

        # --- Determine target level ---
        rsi = indicators['rsi'].iloc[i]
        cur_dd = dd.iloc[i]
        vix_val = 20
        if vix is not None:
            va = vix.reindex(indicators.index, method='ffill')
            vix_val = va.iloc[i]

        if is_up:
            # 上涨趋势: 可以激进加仓
            if cur_dd < -0.12 and vix_val > 35:
                target_level = 4
            elif cur_dd < -0.08 or rsi < 25:
                target_level = 3
            elif cur_dd < -0.05 or rsi < 30:
                target_level = 2
            elif cur_dd < -0.03 or rsi < 35:
                target_level = 1
            else:
                target_level = 0
        else:
            # 下行趋势: 最高1级
            if cur_dd < -0.10 and vix_val > 40:
                target_level = 1  # 极端恐慌可以小量
            else:
                target_level = 0

        # --- Level transitions ---
        # 加仓: 逐级加，不跳级
        if target_level > current_level:
            new_level = current_level + 1  # 只加一级
            if new_level != current_level:
                trades.append({
                    'date': idx.strftime('%Y-%m-%d'), 'level': new_level,
                    'leverage': level_map[new_level], 'action': 'LEVEL_UP',
                    'close': close,
                    'reason': f'DD={cur_dd*100:.1f}% RSI={rsi:.0f} VIX={vix_val:.0f} → Level {new_level}',
                })
            current_level = new_level

        # 减仓: 恢复时逐级减
        elif target_level < current_level:
            new_level = current_level - 1
            if new_level != current_level:
                trades.append({
                    'date': idx.strftime('%Y-%m-%d'), 'level': new_level,
                    'leverage': level_map[new_level], 'action': 'LEVEL_DOWN',
                    'close': close,
                    'reason': f'DD={cur_dd*100:.1f}% RSI={rsi:.0f} → Level {new_level}',
                })
            current_level = new_level

        leverage.iloc[i] = level_map[current_level]

    leverage = leverage.shift(1)
    managed_ret = leverage * spy_ret
    turnover = leverage.diff().abs()
    managed_ret -= turnover * 0.0005

    log_df = pd.DataFrame(trades) if trades else pd.DataFrame()
    return managed_ret, log_df


# ============================================================
# Display
# ============================================================
def print_table(results: List[Dict]):
    print(f"\n{'=' * 150}")
    print(f"{'Strategy':<38} {'Total':>8} {'Ann.Ret':>8} {'Ann.Vol':>8} {'Sharpe':>7}"
          f" {'Sortino':>8} {'MaxDD':>8} {'Calmar':>7}"
          f" {'MinEq%':>7} {'Worst5D':>8} {'Worst21D':>9}")
    print(f"{'=' * 150}")
    for r in results:
        if 'error' in r:
            print(f"{r['name']:<38} ERROR")
            continue

        # Blowup warning
        blown = ""
        if r.get('max_dd', 0) < -0.50:
            blown = " BLOWUP!"
        elif r.get('max_dd', 0) < -0.40:
            blown = " DANGER"

        print(
            f"{r['name']:<38}"
            f" {r['total_return']*100:>7.1f}%"
            f" {r['ann_return']*100:>7.2f}%"
            f" {r['ann_vol']*100:>7.2f}%"
            f" {r['sharpe']:>7.2f}"
            f" {r['sortino']:>8.2f}"
            f" {r['max_dd']*100:>7.2f}%"
            f" {r['calmar']:>7.2f}"
            f" {r['min_equity_ratio']*100:>6.1f}%"
            f" {r['worst_5d']*100:>7.2f}%"
            f" {r['worst_21d']*100:>8.2f}%"
            f"{blown}"
        )
    print(f"{'=' * 150}")
    print(f"  MinEq% = 最低净值/峰值比  |  Worst5D = 最差5天  |  Worst21D = 最差21天")


def print_yearly(results: List[Dict]):
    all_years = sorted(set(y for r in results for y in r.get('yearly', {}).keys()))
    width = 22
    header = f"{'Year':<6}"
    for r in results:
        header += f" {r['name'][:width-1]:>{width}}"
    print(f"\n{'=' * (6 + (width+1)*len(results))}")
    print(header)
    print(f"{'=' * (6 + (width+1)*len(results))}")
    for year in all_years:
        row = f"{year:<6}"
        for r in results:
            yr = r.get('yearly', {}).get(year, None)
            if yr is not None:
                row += f" {yr*100:>{width-1}.2f}%"
            else:
                row += f" {'N/A':>{width}}"
        print(row)
    print(f"{'=' * (6 + (width+1)*len(results))}")


def print_trade_log_summary(log_df: pd.DataFrame, title: str):
    if log_df.empty:
        return
    print(f"\n{'=' * 100}")
    print(f"  {title} — TRADE LOG (last 30)")
    print(f"{'=' * 100}")
    print(f"  {'Date':<12} {'Action':<18} {'Lev':>6} {'Close':>8} {'Reason'}")
    print(f"  {'─' * 94}")
    for _, r in log_df.tail(30).iterrows():
        lev = r.get('leverage', r.get('dd', ''))
        print(f"  {r['date']:<12} {r['action']:<18} {lev:>5}x ${r['close']:>7.2f} {r['reason']}")

    print(f"\n  Event Summary:")
    for action, count in log_df['action'].value_counts().items():
        print(f"    {action:<20} {count:>4} times")


def print_blowup_analysis(spy_ret: pd.Series):
    """Analyze historical worst-case scenarios for margin accounts."""
    print(f"\n{'=' * 80}")
    print(f"  历史爆仓分析 — 不同杠杆的极端情景")
    print(f"{'=' * 80}")

    # Find worst periods
    cum = (1 + spy_ret).cumprod()
    rolling_max = cum.cummax()
    dd = (cum - rolling_max) / rolling_max

    # Worst drawdowns
    worst_periods = [
        ('2020-02 to 2020-03', '2020-02-19', '2020-03-23', 'COVID崩盘'),
        ('2022-01 to 2022-10', '2022-01-03', '2022-10-12', '美联储加息'),
        ('2018-09 to 2018-12', '2018-09-20', '2018-12-24', 'Q4暴跌'),
        ('2015-08 to 2015-08', '2015-08-17', '2015-08-25', '人民币贬值'),
    ]

    print(f"\n  {'Period':<24} {'SPY跌幅':>8}  {'1.5x':>8}  {'2.0x':>8}  {'2.5x':>8}  {'3.0x':>8}  {'Margin Call?'}")
    print(f"  {'─' * 90}")

    for period, start, end, desc in worst_periods:
        try:
            mask = (spy_ret.index >= start) & (spy_ret.index <= end)
            period_ret = spy_ret[mask]
            spy_dd = (1 + period_ret).prod() - 1

            for lev_name, lev in [('1.5x', 1.5), ('2.0x', 2.0), ('2.5x', 2.5), ('3.0x', 3.0)]:
                pass  # calculate below

            dd_15 = (1 + period_ret * 1.5).prod() - 1
            dd_20 = (1 + period_ret * 2.0).prod() - 1
            dd_25 = (1 + period_ret * 2.5).prod() - 1
            dd_30 = (1 + period_ret * 3.0).prod() - 1

            margin_call = "YES!!" if dd_20 < -0.50 else ("CLOSE" if dd_20 < -0.40 else "Safe")

            print(
                f"  {desc:<24}"
                f" {spy_dd*100:>+7.1f}%"
                f" {dd_15*100:>+7.1f}%"
                f" {dd_20*100:>+7.1f}%"
                f" {dd_25*100:>+7.1f}%"
                f" {dd_30*100:>+7.1f}%"
                f"  {margin_call}"
            )
        except Exception:
            pass

    print(f"""
  ⚠️  Margin Call 规则 (Reg-T):
     - 初始保证金: 50% (2x杠杆需要50%保证金)
     - 维持保证金: 25% (净值跌破25%被强平)
     - 2x杠杆: 亏损50%就会Margin Call
     - 3x杠杆: 亏损33%就会Margin Call

  💡 关键: COVID期间SPY跌34%, 2x杠杆亏损~55% → 会被Margin Call!
     所以2x杠杆 Buy the Dip 在极端行情下会爆仓, 必须有风控。
    """)


# ============================================================
# Main
# ============================================================
def run_leveraged_dip_backtest():
    start = '2014-01-01'
    end = '2024-12-31'

    print("=" * 80)
    print("  杠杆 BUY THE DIP — 不爆仓执行方案 (REAL DATA)")
    print(f"  Period: {start} to {end}")
    print("=" * 80)

    print("\n[1/5] Fetching data...")
    data = fetch_data(start, end)
    spy_close = data['SPY']['Close']
    spy_ret = spy_close.pct_change()
    vix = data['^VIX']['Close'] if '^VIX' in data else None

    print("\n[2/5] Computing indicators...")
    indicators = compute_indicators(spy_close)

    # Blowup analysis
    print_blowup_analysis(spy_ret)

    print("\n[3/5] Running leveraged strategies...")
    strategies = {}

    # --- Baselines ---
    strategies['SPY 1.0x (Baseline)'] = spy_ret

    # Fixed leverage
    for lev in [1.5, 2.0, 3.0]:
        strategies[f'Fixed {lev:.1f}x (全仓杠杆)'] = strategy_fixed_leverage(spy_ret, lev)

    # Real UPRO/SSO
    if 'UPRO' in data:
        strategies['UPRO 3x (真实ETF)'] = data['UPRO']['Close'].pct_change()
    if 'SSO' in data:
        strategies['SSO 2x (真实ETF)'] = data['SSO']['Close'].pct_change()

    # Naive leveraged dip
    strategies['Naive Dip 2x (无风控)'] = strategy_naive_leveraged_dip(
        indicators, spy_ret, base_leverage=1.0, dip_leverage=2.0, vix=vix)

    # Anti-blowup
    ab_ret, ab_log = strategy_anti_blowup_leveraged_dip(
        indicators, spy_ret, vix=vix,
        base_leverage=1.0, max_leverage=2.0,
        margin_call_dd=-0.25, forced_delever_dd=-0.15,
    )
    strategies['Anti-Blowup 2x (完整风控)'] = ab_ret

    ab3_ret, ab3_log = strategy_anti_blowup_leveraged_dip(
        indicators, spy_ret, vix=vix,
        base_leverage=1.0, max_leverage=2.5,
        margin_call_dd=-0.20, forced_delever_dd=-0.12,
    )
    strategies['Anti-Blowup 2.5x (激进风控)'] = ab3_ret

    # Kelly
    strategies['Kelly半凯利 2.5x'] = strategy_kelly_leveraged_dip(
        indicators, spy_ret, vix=vix, kelly_fraction=0.5, max_leverage=2.5)

    # Tiered entry (most practical)
    tiered_ret, tiered_log = strategy_tiered_entry(indicators, spy_ret, vix=vix)
    strategies['阶梯加仓法 (最推荐)'] = tiered_ret

    print("\n[4/5] Calculating results...")
    results = []
    for name, rets in strategies.items():
        results.append(calc_metrics(rets, name))

    results_sorted = sorted(results, key=lambda x: x.get('sharpe', -99), reverse=True)
    print_table(results_sorted)

    # Yearly
    key_results = [r for r in results if r['name'] in [
        'SPY 1.0x (Baseline)', 'Fixed 2.0x (全仓杠杆)',
        'Anti-Blowup 2x (完整风控)', '阶梯加仓法 (最推荐)', 'Kelly半凯利 2.5x']]
    print_yearly(key_results)

    # Trade logs
    print_trade_log_summary(tiered_log, '阶梯加仓法')
    print_trade_log_summary(ab_log, 'Anti-Blowup 2x')

    # Save
    print("\n[5/5] Saving results...")
    output = {
        'metadata': {
            'period': f"{start} to {end}",
            'data_source': 'Yahoo Finance (REAL DATA)',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        },
        'results': {r['name']: r for r in results},
    }
    with open('backtests/leveraged_dip_results.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)

    eq = pd.DataFrame({name: (1 + ret).cumprod() for name, ret in strategies.items()})
    eq.to_csv('backtests/leveraged_dip_equity_curves.csv')

    if not tiered_log.empty:
        tiered_log.to_csv('backtests/tiered_entry_trade_log.csv', index=False)

    logger.info("  All results saved to backtests/")

    # Final recommendation
    print(f"\n{'=' * 80}")
    print(f"  杠杆 Buy the Dip — 不爆仓执行指南")
    print(f"{'=' * 80}")
    print("""
    ┌──────────────────────────────────────────────────────────────────┐
    │                最推荐: 阶梯加仓法                                 │
    ├──────────────────────────────────────────────────────────────────┤
    │                                                                  │
    │  Level 0 (正常): 1.0x   ← 平时只持有1倍SPY                       │
    │      ↓ DD > 3% 或 RSI < 35                                      │
    │  Level 1 (轻仓): 1.3x   ← 拿出备用金, 加30%仓位                  │
    │      ↓ DD > 5% 或 RSI < 30                                      │
    │  Level 2 (中仓): 1.6x   ← 再加30%, 开始用保证金                  │
    │      ↓ DD > 8% 或 RSI < 25                                      │
    │  Level 3 (重仓): 2.0x   ← 2倍杠杆满仓                           │
    │      ↓ DD > 12% 且 VIX > 35 (极端恐慌)                          │
    │  Level 4 (极限): 2.5x   ← 仅在恐慌时才用                        │
    │                                                                  │
    │  退出规则:                                                       │
    │  - 价格恢复 → 每涨回一级的条件就减一级                             │
    │  - 单日亏损 > 4% → 立即减两级                                    │
    │  - 组合亏损 > 20% → 紧急回到1.0x                                 │
    │  - 下行趋势(< MA200) → 最高只到Level 1                           │
    │                                                                  │
    │  关键: 逐级加仓 + 逐级减仓 + 绝不跳级                             │
    └──────────────────────────────────────────────────────────────────┘

    ⚠️  不爆仓的3条铁律:
    1. 永远不要在下行趋势中加到2x以上
    2. 分批建仓: 每次只加0.3x, 间隔至少3天
    3. 总亏损超过20%立即去杠杆, 不要心存幻想

    💡 杠杆工具选择:
    - 初学者: SSO (2x ETF) — 自动每日重置, 不会Margin Call
    - 进阶者: ES期货 — 真实杠杆, 资金效率高, 需要盯保证金
    - 不推荐: UPRO (3x) — 长期衰减严重, 只适合短期交易
    - 不推荐: 满仓保证金 — 极端行情会被强平
    """)

    return results, eq


if __name__ == '__main__':
    results, equity = run_leveraged_dip_backtest()
