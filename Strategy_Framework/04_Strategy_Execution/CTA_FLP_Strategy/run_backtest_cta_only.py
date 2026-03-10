"""
CTA 趋势策略回测执行脚本（纯CTA，无FLP保护）
生成回测结果、交易记录和收益分析
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import random
import json

# 导入策略模块（只导入CTA部分）
from CTA_FLP_Strategy import (
    CTATrendEngine, Signal, CTA_CONFIG, UNIVERSE
)

# 设置随机种子
np.random.seed(42)
random.seed(42)


def generate_mock_data(start_date: date, end_date: date, symbols: list) -> dict:
    """生成模拟价格数据用于回测演示（具有趋势特性）"""
    data = {}
    
    for symbol in symbols:
        # 生成交易日历
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        n_days = len(dates)
        
        # 为不同标的设置不同的特性
        if symbol == 'ES':
            base_price = 1500
            returns = np.random.normal(0.0002, 0.012, n_days)
            # 添加趋势周期
            returns[0:500] += 0.0003      # 上涨
            returns[1500:1700] -= 0.001   # 下跌
            returns[2500:4000] += 0.0004  # 上涨
        elif symbol == 'GC':
            base_price = 300
            returns = np.random.normal(0.00015, 0.008, n_days)
        else:  # ZN
            base_price = 100
            returns = np.random.normal(0.00005, 0.004, n_days)
        
        prices = base_price * np.exp(np.cumsum(returns))
        
        # 生成OHLC数据
        df = pd.DataFrame({
            'open': prices * (1 + np.random.normal(0, 0.001, n_days)),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.008, n_days))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.008, n_days))),
            'close': prices,
            'volume': np.random.randint(10000, 100000, n_days)
        }, index=dates)
        
        # 确保 high >= close >= low
        df['high'] = np.maximum(df['high'], df[['open', 'close']].max(axis=1) * 1.001)
        df['low'] = np.minimum(df['low'], df[['open', 'close']].min(axis=1) * 0.999)
        
        data[symbol] = df
    
    return data


def run_cta_backtest(price_data: dict, start_date: date, end_date: date) -> tuple:
    """
    运行纯CTA回测（无FLP保护）
    简化版本：使用日收益率直接计算盈亏
    """
    initial_capital = 1_000_000
    
    # 初始化CTA引擎
    cta_engine = CTATrendEngine()
    
    # 生成CTA信号
    all_signals = {}
    for symbol, df in price_data.items():
        sigs = cta_engine.generate_signal(df, symbol)
        sigs = cta_engine.calculate_position_sizes(sigs)
        # 转换为DataFrame便于处理
        sig_df = pd.DataFrame([
            {
                'date': s.date.date() if hasattr(s.date, 'date') else s.date,
                'signal': s.signal.name,
                'price': s.price,
                'position_size': s.position_size
            }
            for s in sigs
        ])
        if not sig_df.empty:
            sig_df.set_index('date', inplace=True)
        all_signals[symbol] = sig_df
    
    # 统一日期索引
    all_dates = price_data['ES'].index.date
    
    results = []
    trade_records = []
    
    capital = initial_capital
    positions = {s: 0 for s in price_data.keys()}  # 当前持仓方向: 1=多, -1=空, 0=空
    entry_prices = {s: 0 for s in price_data.keys()}
    trade_id = 0
    
    for i, current_date in enumerate(all_dates):
        if current_date < start_date or current_date > end_date:
            continue
        
        daily_pnl = 0
        
        # 获取当日信号
        for symbol in price_data.keys():
            sig_df = all_signals[symbol]
            if current_date not in sig_df.index:
                continue
            
            signal = sig_df.loc[current_date]
            current_price = signal['price']
            sig_type = signal['signal']
            pos_size = signal['position_size']
            
            # 计算目标仓位（简化：按信号强度分配名义价值）
            target_exposure = capital * 0.3 * pos_size  # 单品种最多30%
            
            current_pos = positions[symbol]
            
            # 交易逻辑
            if sig_type == 'LONG' and current_pos <= 0:
                # 平空仓/开多仓
                if current_pos < 0:
                    pnl = (entry_prices[symbol] - current_price) * abs(current_pos) * 0.01  # 简化计算
                    daily_pnl += pnl
                    trade_id += 1
                    trade_records.append({
                        'trade_id': trade_id, 'date': current_date, 'symbol': symbol,
                        'action': 'COVER_SHORT', 'price': current_price, 'pnl': pnl
                    })
                
                positions[symbol] = 1
                entry_prices[symbol] = current_price
                trade_id += 1
                trade_records.append({
                    'trade_id': trade_id, 'date': current_date, 'symbol': symbol,
                    'action': 'BUY_LONG', 'price': current_price, 'pnl': 0
                })
                
            elif sig_type == 'SHORT' and current_pos >= 0:
                # 平多仓/开空仓
                if current_pos > 0:
                    pnl = (current_price - entry_prices[symbol]) * current_pos * 0.01
                    daily_pnl += pnl
                    trade_id += 1
                    trade_records.append({
                        'trade_id': trade_id, 'date': current_date, 'symbol': symbol,
                        'action': 'SELL_LONG', 'price': current_price, 'pnl': pnl
                    })
                
                positions[symbol] = -1
                entry_prices[symbol] = current_price
                trade_id += 1
                trade_records.append({
                    'trade_id': trade_id, 'date': current_date, 'symbol': symbol,
                    'action': 'SELL_SHORT', 'price': current_price, 'pnl': 0
                })
                
            elif sig_type == 'FLAT' and current_pos != 0:
                # 平仓
                if current_pos > 0:
                    pnl = (current_price - entry_prices[symbol]) * current_pos * 0.01
                else:
                    pnl = (entry_prices[symbol] - current_price) * abs(current_pos) * 0.01
                
                daily_pnl += pnl
                trade_id += 1
                action = 'SELL_LONG' if current_pos > 0 else 'COVER_SHORT'
                trade_records.append({
                    'trade_id': trade_id, 'date': current_date, 'symbol': symbol,
                    'action': action, 'price': current_price, 'pnl': pnl
                })
                positions[symbol] = 0
                entry_prices[symbol] = 0
        
        # 持仓盈亏（简化：按当日价格变动计算）
        if i > 0:
            for symbol in price_data.keys():
                if positions[symbol] != 0:
                    today_price = price_data[symbol]['close'].iloc[i]
                    yest_price = price_data[symbol]['close'].iloc[i-1]
                    ret = (today_price - yest_price) / yest_price
                    # 限制单日盈亏
                    position_pnl = positions[symbol] * ret * capital * 0.25  # 单品种名义25%
                    daily_pnl += position_pnl
        
        capital += daily_pnl
        capital = max(capital, 0)  # 防止负值
        
        results.append({
            'date': current_date,
            'total_value': capital,
            'daily_pnl': daily_pnl,
            'ES_position': positions['ES'],
            'GC_position': positions['GC'],
            'ZN_position': positions['ZN'],
        })
    
    results_df = pd.DataFrame(results)
    trades_df = pd.DataFrame(trade_records)
    
    return results_df, trades_df


def calculate_metrics(results_df: pd.DataFrame, initial_capital: float = 1_000_000) -> dict:
    """计算绩效指标"""
    if results_df.empty:
        return {}
    
    df = results_df.copy()
    final_value = df['total_value'].iloc[-1]
    total_return = (final_value / initial_capital - 1) * 100
    
    df['daily_return'] = df['total_value'].pct_change()
    volatility = df['daily_return'].std() * np.sqrt(252) * 100
    
    df['cummax'] = df['total_value'].cummax()
    df['drawdown'] = (df['total_value'] - df['cummax']) / df['cummax']
    max_drawdown = df['drawdown'].min() * 100
    
    risk_free = 0.05
    excess_return = total_return / 100 - risk_free
    sharpe = excess_return / (volatility / 100) if volatility > 0 else 0
    
    downside_returns = df['daily_return'][df['daily_return'] < 0]
    downside_vol = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
    sortino = excess_return / downside_vol if downside_vol > 0 else 0
    
    calmar = total_return / abs(max_drawdown) if max_drawdown != 0 else 0
    win_rate = (df['daily_return'] > 0).sum() / len(df['daily_return'].dropna()) * 100
    
    avg_gain = df['daily_return'][df['daily_return'] > 0].mean()
    avg_loss = abs(df['daily_return'][df['daily_return'] < 0].mean())
    profit_factor = avg_gain / avg_loss if avg_loss > 0 else 0
    
    n_days = len(df)
    annual_return = ((final_value / initial_capital) ** (252 / n_days) - 1) * 100 if n_days > 0 else 0
    
    return {
        'initial_capital': float(initial_capital),
        'final_value': float(final_value),
        'total_return_pct': float(total_return),
        'annual_return_pct': float(annual_return),
        'annual_volatility_pct': float(volatility),
        'max_drawdown_pct': float(max_drawdown),
        'sharpe_ratio': float(sharpe),
        'sortino_ratio': float(sortino),
        'calmar_ratio': float(calmar),
        'win_rate_pct': float(win_rate),
        'profit_factor': float(profit_factor),
        'total_days': int(n_days),
    }


def generate_report(metrics: dict, results_df: pd.DataFrame, trades_df: pd.DataFrame) -> str:
    """生成收益分析报告"""
    
    report = f"""# CTA 纯趋势策略收益分析报告

> **策略类型**: 纯CTA趋势跟踪（无FLP保护）
> **仓位配置**: CTA 95% + 现金 5%

## 回测概况

| 指标 | 数值 |
|------|------|
| 回测期间 | {results_df['date'].min()} 至 {results_df['date'].max()} |
| 初始资金 | ${metrics['initial_capital']:,.2f} |
| 期末资金 | ${metrics['final_value']:,.2f} |
| 总收益率 | {metrics['total_return_pct']:+.2f}% |
| 交易天数 | {metrics['total_days']} 天 |

## 核心绩效指标

### 收益指标

| 指标 | 数值 |
|------|------|
| 年化收益率 | {metrics['annual_return_pct']:+.2f}% |
| 总收益率 | {metrics['total_return_pct']:+.2f}% |
| 资金增长 | ${metrics['final_value'] - metrics['initial_capital']:,.2f} |

### 风险指标

| 指标 | 数值 |
|------|------|
| 年化波动率 | {metrics['annual_volatility_pct']:.2f}% |
| 最大回撤 | {metrics['max_drawdown_pct']:.2f}% |
| 胜率 | {metrics['win_rate_pct']:.1f}% |

### 风险调整收益

| 指标 | 数值 |
|------|------|
| 夏普比率 | {metrics['sharpe_ratio']:.2f} |
| 索提诺比率 | {metrics['sortino_ratio']:.2f} |
| 卡玛比率 | {metrics['calmar_ratio']:.2f} |

## 与CTA+FLP策略对比

| 指标 | CTA纯策略 | CTA+FLP策略 | 差异 |
|------|-----------|-------------|------|
| 年化收益率 | {metrics['annual_return_pct']:+.2f}% | -1.84% | {metrics['annual_return_pct'] - (-1.84):+.2f}% |
| 最大回撤 | {metrics['max_drawdown_pct']:.2f}% | -50.63% | {metrics['max_drawdown_pct'] - (-50.63):+.2f}% |

## 交易统计

总交易次数: {len(trades_df)} 笔

### 交易类型分布

"""
    
    if not trades_df.empty:
        action_counts = trades_df['action'].value_counts()
        for action, count in action_counts.items():
            report += f"- {action}: {count} 笔\n"
        
        win_trades = trades_df[trades_df['pnl'] > 0]
        loss_trades = trades_df[trades_df['pnl'] < 0]
        total_pnl = trades_df['pnl'].sum()
        
        report += f"""
### 盈亏统计

| 指标 | 数值 |
|------|------|
| 总盈亏 | ${total_pnl:,.2f} |
| 盈利交易 | {len(win_trades)} 笔 |
| 亏损交易 | {len(loss_trades)} 笔 |

"""
    
    report += f"""
## 策略评价

### ✅ 优势
1. 无保护成本，资金利用率高
2. 简单执行，无需期权权限
3. 全额趋势敞口

### ⚠️ 风险
1. 无尾部保护，黑天鹅回撤大
2. 震荡市连续亏损
3. 波动率较高

---

*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
"""
    
    return report


def main():
    print("=" * 60)
    print("CTA 纯趋势策略回测（无FLP保护）")
    print("=" * 60)
    print()
    
    start_date = date(2000, 1, 1)
    end_date = date(2026, 3, 1)
    symbols = ['ES', 'GC', 'ZN']
    
    print(f"回测期间: {start_date} 至 {end_date}")
    print(f"交易标的: {', '.join(symbols)}")
    print()
    
    print("生成模拟数据...")
    price_data = generate_mock_data(start_date, end_date, symbols)
    print(f"✓ 生成 {len(price_data[symbols[0]])} 个交易日数据")
    print()
    
    print("执行回测...")
    results_df, trades_df = run_cta_backtest(price_data, start_date, end_date)
    print(f"✓ 回测完成: {len(results_df)} 条记录, {len(trades_df)} 笔交易")
    print()
    
    print("计算绩效指标...")
    metrics = calculate_metrics(results_df)
    print()
    
    print("保存结果...")
    results_df.to_csv('backtest_results_cta_only.csv', index=False, encoding='utf-8-sig')
    trades_df.to_csv('trade_records_cta_only.csv', index=False, encoding='utf-8-sig')
    
    metrics_serializable = {k: float(v) if isinstance(v, (np.integer, np.floating)) else v 
                           for k, v in metrics.items()}
    with open('performance_metrics_cta_only.json', 'w', encoding='utf-8') as f:
        json.dump(metrics_serializable, f, indent=2, ensure_ascii=False)
    
    report = generate_report(metrics, results_df, trades_df)
    with open('收益分析报告_CTA纯策略.md', 'w', encoding='utf-8') as f:
        f.write(report)
    print("✓ 文件保存完成")
    print()
    
    print("=" * 60)
    print("回测结果摘要")
    print("=" * 60)
    print(f"初始资金: ${metrics['initial_capital']:,.2f}")
    print(f"期末资金: ${metrics['final_value']:,.2f}")
    print(f"总收益率: {metrics['total_return_pct']:+.2f}%")
    print(f"年化收益率: {metrics['annual_return_pct']:+.2f}%")
    print(f"最大回撤: {metrics['max_drawdown_pct']:.2f}%")
    print(f"夏普比率: {metrics['sharpe_ratio']:.2f}")
    print(f"交易次数: {len(trades_df)} 笔")
    print("=" * 60)


if __name__ == "__main__":
    main()
