"""
CTA + FLP 策略回测执行脚本
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

# 导入策略模块
from CTA_FLP_Strategy import (
    CTATrendEngine, FLPEngine, RiskBudgetBalancer, 
    CTAFLPBacktester, PortfolioState, Signal, FLPMode,
    CTA_CONFIG, FLP_CONFIG, RISK_CONFIG, UNIVERSE
)

# 设置随机种子确保可重复性
np.random.seed(42)
random.seed(42)


def generate_mock_data(start_date: date, end_date: date, symbols: list) -> dict:
    """生成模拟价格数据用于回测演示"""
    data = {}
    
    for symbol in symbols:
        # 生成交易日历（排除周末）
        dates = []
        current = start_date
        while current <= end_date:
            if current.weekday() < 5:  # 周一到周五
                dates.append(current)
            current += timedelta(days=1)
        
        n_days = len(dates)
        
        # 为不同标的设置不同的波动特性
        if symbol == 'ES':  # 标普500
            base_price = 4200
            drift = 0.0002
            vol = 0.012
        elif symbol == 'GC':  # 黄金
            base_price = 1950
            drift = 0.0001
            vol = 0.008
        else:  # ZN - 国债
            base_price = 110
            drift = 0.00005
            vol = 0.004
        
        # 生成价格路径（几何布朗运动）
        returns = np.random.normal(drift, vol, n_days)
        prices = base_price * np.exp(np.cumsum(returns))
        
        # 生成OHLC数据
        df = pd.DataFrame({
            'open': prices * (1 + np.random.normal(0, 0.001, n_days)),
            'high': prices * (1 + np.abs(np.random.normal(0, 0.005, n_days))),
            'low': prices * (1 - np.abs(np.random.normal(0, 0.005, n_days))),
            'close': prices,
            'volume': np.random.randint(10000, 100000, n_days)
        }, index=pd.to_datetime(dates))
        
        # 确保 high >= close >= low
        df['high'] = np.maximum(df['high'], df[['open', 'close']].max(axis=1) * 1.001)
        df['low'] = np.minimum(df['low'], df[['open', 'close']].min(axis=1) * 0.999)
        
        data[symbol] = df
    
    return data


def generate_vix_data(start_date: date, end_date: date) -> pd.DataFrame:
    """生成模拟VIX数据"""
    dates = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    
    n_days = len(dates)
    
    # VIX均值回归过程
    vix_base = 20
    vix_values = []
    current_vix = vix_base
    
    for i in range(n_days):
        # 均值回归
        mean_reversion = (vix_base - current_vix) * 0.05
        # 随机冲击
        shock = np.random.normal(0, 1.5)
        current_vix = max(10, min(60, current_vix + mean_reversion + shock))
        vix_values.append(current_vix)
    
    df = pd.DataFrame({
        'open': np.array(vix_values) + np.random.normal(0, 0.5, n_days),
        'high': np.array(vix_values) + np.abs(np.random.normal(0, 1, n_days)),
        'low': np.array(vix_values) - np.abs(np.random.normal(0, 1, n_days)),
        'close': vix_values
    }, index=pd.to_datetime(dates))
    
    return df


def run_detailed_backtest(price_data: dict, vix_data: pd.DataFrame, 
                         start_date: date, end_date: date) -> tuple:
    """
    运行详细回测，生成交易记录
    
    Returns:
        (results_df, trade_records, daily_pnl)
    """
    initial_capital = 1_000_000
    
    # 初始化引擎
    cta_engine = CTATrendEngine()
    flp_engine = FLPEngine()
    risk_balancer = RiskBudgetBalancer()
    
    # 生成CTA信号
    all_cta_signals = {}
    for symbol, df in price_data.items():
        signals = cta_engine.generate_signal(df, symbol)
        signals = cta_engine.calculate_position_sizes(signals)
        all_cta_signals[symbol] = {s.date: s for s in signals}
    
    # 回测循环
    results = []
    trade_records = []
    daily_pnl_records = []
    
    current_date = start_date
    portfolio = PortfolioState(date=current_date, total_value=initial_capital)
    portfolio.cta_positions = {s: 0 for s in price_data.keys()}
    
    prev_value = initial_capital
    trade_id = 0
    
    # 记录持仓成本
    position_costs = {s: 0 for s in price_data.keys()}
    position_sizes = {s: 0 for s in price_data.keys()}
    
    while current_date <= end_date:
        # 获取当日数据
        day_pnl = 0
        
        # 1. CTA交易处理
        for symbol, df in price_data.items():
            if current_date not in all_cta_signals[symbol]:
                continue
                
            signal = all_cta_signals[symbol][current_date]
            current_price = signal.price
            
            # 获取权重
            weights = risk_balancer.calculate_weights(portfolio, "normal")
            cta_allocation = portfolio.total_value * weights['cta']
            
            # 计算目标仓位
            symbol_allocation = cta_allocation / len(price_data)
            target_position = symbol_allocation * signal.position_size / current_price
            
            current_pos = position_sizes[symbol]
            
            # 判断交易信号变化
            if signal.signal == Signal.LONG and current_pos <= 0:
                # 开多仓/平空仓
                if current_pos < 0:
                    # 平空仓
                    pnl = (position_costs[symbol] - current_price) * abs(current_pos) * UNIVERSE[symbol]['multiplier']
                    day_pnl += pnl
                    trade_id += 1
                    trade_records.append({
                        'trade_id': trade_id,
                        'date': current_date,
                        'symbol': symbol,
                        'action': 'COVER_SHORT',
                        'price': current_price,
                        'size': abs(current_pos),
                        'pnl': pnl,
                        'signal': 'LONG'
                    })
                
                # 开多仓
                position_sizes[symbol] = target_position
                position_costs[symbol] = current_price
                trade_id += 1
                trade_records.append({
                    'trade_id': trade_id,
                    'date': current_date,
                    'symbol': symbol,
                    'action': 'BUY_LONG',
                    'price': current_price,
                    'size': target_position,
                    'pnl': 0,
                    'signal': 'LONG'
                })
                
            elif signal.signal == Signal.SHORT and current_pos >= 0:
                # 开空仓/平多仓
                if current_pos > 0:
                    # 平多仓
                    pnl = (current_price - position_costs[symbol]) * current_pos * UNIVERSE[symbol]['multiplier']
                    day_pnl += pnl
                    trade_id += 1
                    trade_records.append({
                        'trade_id': trade_id,
                        'date': current_date,
                        'symbol': symbol,
                        'action': 'SELL_LONG',
                        'price': current_price,
                        'size': current_pos,
                        'pnl': pnl,
                        'signal': 'SHORT'
                    })
                
                # 开空仓
                position_sizes[symbol] = -target_position
                position_costs[symbol] = current_price
                trade_id += 1
                trade_records.append({
                    'trade_id': trade_id,
                    'date': current_date,
                    'symbol': symbol,
                    'action': 'SELL_SHORT',
                    'price': current_price,
                    'size': target_position,
                    'pnl': 0,
                    'signal': 'SHORT'
                })
                
            elif signal.signal == Signal.FLAT and current_pos != 0:
                # 平仓
                if current_pos > 0:
                    pnl = (current_price - position_costs[symbol]) * current_pos * UNIVERSE[symbol]['multiplier']
                    trade_id += 1
                    trade_records.append({
                        'trade_id': trade_id,
                        'date': current_date,
                        'symbol': symbol,
                        'action': 'SELL_LONG',
                        'price': current_price,
                        'size': current_pos,
                        'pnl': pnl,
                        'signal': 'FLAT'
                    })
                else:
                    pnl = (position_costs[symbol] - current_price) * abs(current_pos) * UNIVERSE[symbol]['multiplier']
                    trade_id += 1
                    trade_records.append({
                        'trade_id': trade_id,
                        'date': current_date,
                        'symbol': symbol,
                        'action': 'COVER_SHORT',
                        'price': current_price,
                        'size': abs(current_pos),
                        'pnl': pnl,
                        'signal': 'FLAT'
                    })
                
                day_pnl += pnl
                position_sizes[symbol] = 0
                position_costs[symbol] = 0
        
        # 2. FLP保护处理（每周五）
        flp_signal = None
        if current_date.weekday() == 4:  # Friday
            vix_row = vix_data[vix_data.index.date == current_date]
            vix = vix_row['close'].iloc[0] if not vix_row.empty else 20.0
            spy_price = price_data['ES']['close'].loc[price_data['ES'].index.date == current_date].iloc[0] if len(price_data['ES']) > 0 else 4200
            
            flp_signal = flp_engine.generate_signal(
                current_date, spy_price, vix,
                base_budget=portfolio.total_value * weights['flp']
            )
            
            if flp_signal and flp_signal.mode != FLPMode.NO_HEDGE:
                trade_id += 1
                trade_records.append({
                    'trade_id': trade_id,
                    'date': current_date,
                    'symbol': 'SPY_PUT',
                    'action': f'BUY_{flp_signal.mode.value.upper()}',
                    'price': flp_signal.put_premium,
                    'size': flp_signal.budget / flp_signal.put_premium if flp_signal.put_premium else 0,
                    'pnl': -flp_signal.budget,  # 成本
                    'signal': f"Delta:{flp_signal.put_delta:.2f}",
                    'strike': flp_signal.put_strike,
                    'vix': vix
                })
                day_pnl -= flp_signal.budget * 0.01  # 模拟期权每日损耗
        
        # 3. 计算持仓市值变化（简化）
        for symbol in price_data.keys():
            if position_sizes[symbol] != 0:
                try:
                    current_price = price_data[symbol]['close'].loc[price_data[symbol].index.date == current_date].iloc[0]
                    prev_day = current_date - timedelta(days=1)
                    while prev_day.weekday() >= 5:
                        prev_day -= timedelta(days=1)
                    prev_price_series = price_data[symbol]['close'].loc[price_data[symbol].index.date == prev_day]
                    if len(prev_price_series) > 0:
                        prev_price = prev_price_series.iloc[0]
                        price_change = (current_price - prev_price) * position_sizes[symbol] * UNIVERSE[symbol]['multiplier']
                        day_pnl += price_change * 0.1  # 按10%反映在日内
                except:
                    pass
        
        # 更新组合价值
        portfolio.total_value += day_pnl
        portfolio.date = current_date
        portfolio.cta_pnl += day_pnl if day_pnl > 0 else 0
        
        # 记录结果
        weights = risk_balancer.calculate_weights(portfolio, "normal")
        
        results.append({
            'date': current_date,
            'total_value': portfolio.total_value,
            'daily_pnl': day_pnl,
            'cta_weight': weights['cta'],
            'flp_weight': weights['flp'],
            'cash_weight': weights['cash'],
            'vix': vix if 'vix' in locals() else 20,
            'flp_mode': flp_signal.mode.value if flp_signal else "None",
            'ES_position': position_sizes.get('ES', 0),
            'GC_position': position_sizes.get('GC', 0),
            'ZN_position': position_sizes.get('ZN', 0),
        })
        
        daily_pnl_records.append({
            'date': current_date,
            'daily_pnl': day_pnl,
            'cumulative_pnl': portfolio.total_value - initial_capital
        })
        
        current_date += timedelta(days=1)
    
    results_df = pd.DataFrame(results)
    trades_df = pd.DataFrame(trade_records)
    daily_pnl_df = pd.DataFrame(daily_pnl_records)
    
    return results_df, trades_df, daily_pnl_df


def calculate_performance_metrics(results_df: pd.DataFrame, initial_capital: float = 1_000_000) -> dict:
    """计算绩效指标"""
    if results_df.empty:
        return {}
    
    df = results_df.copy()
    
    # 基础指标
    final_value = df['total_value'].iloc[-1]
    total_return = (final_value / initial_capital - 1) * 100
    
    # 日收益率
    df['daily_return'] = df['total_value'].pct_change()
    
    # 年化波动率
    volatility = df['daily_return'].std() * np.sqrt(252) * 100
    
    # 最大回撤
    df['cummax'] = df['total_value'].cummax()
    df['drawdown'] = (df['total_value'] - df['cummax']) / df['cummax']
    max_drawdown = df['drawdown'].min() * 100
    
    # 夏普比率
    risk_free = 0.05  # 5%无风险利率
    excess_return = total_return / 100 - risk_free
    sharpe = excess_return / (volatility / 100) if volatility > 0 else 0
    
    # 索提诺比率（仅考虑下行波动）
    downside_returns = df['daily_return'][df['daily_return'] < 0]
    downside_vol = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
    sortino = excess_return / downside_vol if downside_vol > 0 else 0
    
    # 卡玛比率
    calmar = total_return / abs(max_drawdown) if max_drawdown != 0 else 0
    
    # 胜率（基于日收益）
    win_rate = (df['daily_return'] > 0).sum() / len(df['daily_return'].dropna()) * 100
    
    # 盈亏比
    avg_gain = df['daily_return'][df['daily_return'] > 0].mean()
    avg_loss = abs(df['daily_return'][df['daily_return'] < 0].mean())
    profit_factor = avg_gain / avg_loss if avg_loss > 0 else 0
    
    # 年化收益率
    n_days = len(df)
    annual_return = ((final_value / initial_capital) ** (252 / n_days) - 1) * 100
    
    return {
        'initial_capital': initial_capital,
        'final_value': final_value,
        'total_return_pct': total_return,
        'annual_return_pct': annual_return,
        'annual_volatility_pct': volatility,
        'max_drawdown_pct': max_drawdown,
        'sharpe_ratio': sharpe,
        'sortino_ratio': sortino,
        'calmar_ratio': calmar,
        'win_rate_pct': win_rate,
        'profit_factor': profit_factor,
        'total_days': n_days,
    }


def generate_analysis_report(metrics: dict, results_df: pd.DataFrame, trades_df: pd.DataFrame) -> str:
    """生成收益分析报告"""
    
    report = f"""# CTA + FLP 策略收益分析报告

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

| 指标 | 数值 | 说明 |
|------|------|------|
| 年化收益率 | {metrics['annual_return_pct']:+.2f}% | 复合年化收益 |
| 总收益率 | {metrics['total_return_pct']:+.2f}% | 回测期总收益 |
| 资金增长 | ${metrics['final_value'] - metrics['initial_capital']:,.2f} | 绝对收益金额 |

### 风险指标

| 指标 | 数值 | 说明 |
|------|------|------|
| 年化波动率 | {metrics['annual_volatility_pct']:.2f}% | 收益波动程度 |
| 最大回撤 | {metrics['max_drawdown_pct']:.2f}% | 峰值到谷值最大亏损 |
| 胜率 | {metrics['win_rate_pct']:.1f}% | 盈利天数占比 |

### 风险调整收益

| 指标 | 数值 | 评价 |
|------|------|------|
| 夏普比率 | {metrics['sharpe_ratio']:.2f} | {'优秀' if metrics['sharpe_ratio'] > 1 else '良好' if metrics['sharpe_ratio'] > 0.5 else '一般'} |
| 索提诺比率 | {metrics['sortino_ratio']:.2f} | {'优秀' if metrics['sortino_ratio'] > 2 else '良好' if metrics['sortino_ratio'] > 1 else '一般'} |
| 卡玛比率 | {metrics['calmar_ratio']:.2f} | {'优秀' if metrics['calmar_ratio'] > 2 else '良好' if metrics['calmar_ratio'] > 1 else '一般'} |
| 盈亏比 | {metrics['profit_factor']:.2f} | {'优秀' if metrics['profit_factor'] > 2 else '良好' if metrics['profit_factor'] > 1.5 else '一般'} |

## 策略权重变化分析

"""
    
    # 权重统计
    weights_stats = results_df[['cta_weight', 'flp_weight', 'cash_weight']].agg(['mean', 'min', 'max'])
    
    report += f"""### 平均持仓权重

| 资产类型 | 平均权重 | 最小权重 | 最大权重 |
|----------|----------|----------|----------|
| CTA趋势 | {weights_stats.loc['mean', 'cta_weight']*100:.1f}% | {weights_stats.loc['min', 'cta_weight']*100:.1f}% | {weights_stats.loc['max', 'cta_weight']*100:.1f}% |
| FLP保护 | {weights_stats.loc['mean', 'flp_weight']*100:.1f}% | {weights_stats.loc['min', 'flp_weight']*100:.1f}% | {weights_stats.loc['max', 'flp_weight']*100:.1f}% |
| 现金 | {weights_stats.loc['mean', 'cash_weight']*100:.1f}% | {weights_stats.loc['min', 'cash_weight']*100:.1f}% | {weights_stats.loc['max', 'cash_weight']*100:.1f}% |

## 交易统计

"""
    
    if not trades_df.empty:
        # 交易类型统计
        action_counts = trades_df['action'].value_counts()
        report += "### 交易类型分布\n\n"
        report += "| 交易类型 | 次数 |\n"
        report += "|----------|------|\n"
        for action, count in action_counts.items():
            report += f"| {action} | {count} |\n"
        
        report += f"\n**总交易次数**: {len(trades_df)}\n\n"
        
        # 各品种交易统计
        symbol_trades = trades_df[trades_df['symbol'] != 'SPY_PUT'].groupby('symbol').size()
        if not symbol_trades.empty:
            report += "### 各品种交易次数\n\n"
            report += "| 品种 | 交易次数 |\n"
            report += "|------|----------|\n"
            for symbol, count in symbol_trades.items():
                report += f"| {symbol} ({UNIVERSE.get(symbol, {}).get('name', '')}) | {count} |\n"
        
        # FLP保护统计
        flp_trades = trades_df[trades_df['symbol'] == 'SPY_PUT']
        if not flp_trades.empty:
            report += f"\n### FLP保护统计\n\n"
            report += f"- **保护交易次数**: {len(flp_trades)} 次\n"
            report += f"- **总保护成本**: ${flp_trades['pnl'].sum():,.2f}\n"
    
    report += f"""
## 市场环境适应性

### VIX分布统计

| VIX区间 | 天数 | 占比 |
|---------|------|------|
| < 15 (低波动) | {len(results_df[results_df['vix'] < 15])} | {len(results_df[results_df['vix'] < 15])/len(results_df)*100:.1f}% |
| 15-30 (正常) | {len(results_df[(results_df['vix'] >= 15) & (results_df['vix'] <= 30)])} | {len(results_df[(results_df['vix'] >= 15) & (results_df['vix'] <= 30)])/len(results_df)*100:.1f}% |
| > 30 (高波动) | {len(results_df[results_df['vix'] > 30])} | {len(results_df[results_df['vix'] > 30])/len(results_df)*100:.1f}% |

### FLP保护模式分布

"""
    
    mode_counts = results_df[results_df['flp_mode'] != 'None']['flp_mode'].value_counts()
    for mode, count in mode_counts.items():
        report += f"- **{mode}**: {count} 次\n"
    
    report += f"""
## 策略评价与建议

### 优势

1. **非对称收益结构**: CTA捕捉趋势 + FLP对冲尾部风险
2. **波动率适应**: 根据VIX动态调整保护成本和CTA仓位
3. **系统化执行**: 机械执行减少情绪干扰

### 风险点

1. **CTA回撤期**: 震荡市可能连续亏损
2. **保护成本**: 长期牛市中FLP持续消耗资金
3. **执行复杂度**: 需要期权交易权限

### 优化建议

1. 考虑加入商品期货趋势，分散单一市场风险
2. 探索动态Delta调整（根据VIX变化调整Put的Delta）
3. 增加宏观因子过滤（如美联储政策周期）

---

*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*
*数据说明: 本报告基于模拟数据生成，仅供参考*
"""
    
    return report


def main():
    """主函数"""
    print("=" * 60)
    print("CTA + FLP 策略回测系统")
    print("=" * 60)
    print()
    
    # 设置回测参数
    start_date = date(2000, 1, 1)
    end_date = date(2026, 3, 1)
    symbols = ['ES', 'GC', 'ZN']
    
    print(f"回测期间: {start_date} 至 {end_date}")
    print(f"交易标的: {', '.join(symbols)}")
    print()
    
    # 生成模拟数据
    print("正在生成模拟市场数据...")
    price_data = generate_mock_data(start_date, end_date, symbols)
    vix_data = generate_vix_data(start_date, end_date)
    print(f"✓ 生成 {len(price_data[symbols[0]])} 个交易日数据")
    print()
    
    # 运行回测
    print("正在执行回测...")
    results_df, trades_df, daily_pnl_df = run_detailed_backtest(
        price_data, vix_data, start_date, end_date
    )
    print(f"✓ 回测完成，生成 {len(results_df)} 条记录")
    print(f"✓ 执行 {len(trades_df)} 笔交易")
    print()
    
    # 计算绩效指标
    print("正在计算绩效指标...")
    metrics = calculate_performance_metrics(results_df)
    print()
    
    # 保存结果
    print("正在保存结果文件...")
    
    # 保存回测结果
    results_df.to_csv('backtest_results.csv', index=False, encoding='utf-8-sig')
    print("✓ 已保存: backtest_results.csv")
    
    # 保存交易记录
    trades_df.to_csv('trade_records.csv', index=False, encoding='utf-8-sig')
    print("✓ 已保存: trade_records.csv")
    
    # 保存每日盈亏
    daily_pnl_df.to_csv('daily_pnl.csv', index=False, encoding='utf-8-sig')
    print("✓ 已保存: daily_pnl.csv")
    
    # 保存绩效指标
    with open('performance_metrics.json', 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)
    print("✓ 已保存: performance_metrics.json")
    
    # 生成并保存分析报告
    report = generate_analysis_report(metrics, results_df, trades_df)
    with open('收益分析报告.md', 'w', encoding='utf-8') as f:
        f.write(report)
    print("✓ 已保存: 收益分析报告.md")
    print()
    
    # 打印摘要
    print("=" * 60)
    print("回测结果摘要")
    print("=" * 60)
    print(f"初始资金: ${metrics['initial_capital']:,.2f}")
    print(f"期末资金: ${metrics['final_value']:,.2f}")
    print(f"总收益率: {metrics['total_return_pct']:+.2f}%")
    print(f"年化收益率: {metrics['annual_return_pct']:+.2f}%")
    print(f"最大回撤: {metrics['max_drawdown_pct']:.2f}%")
    print(f"夏普比率: {metrics['sharpe_ratio']:.2f}")
    print()
    print("所有文件已保存至当前目录")
    print("=" * 60)


if __name__ == "__main__":
    main()
