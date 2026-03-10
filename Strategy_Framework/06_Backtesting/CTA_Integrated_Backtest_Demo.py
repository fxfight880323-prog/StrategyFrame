"""
CTA策略整合回测演示
===================

整合模块:
1. CTA策略复现 (TSMOM, Trend Following, Carry)
2. 策略评估系统 (Sharpe, Information Ratio�?
3. 组合风控系统
4. 多策略组合优�?

输出:
- 各策略独立回测结�?
- 多策略组合回测结�?
- 完整绩效报告
"""

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import logging

# 路径设置
import sys
import os
_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_DIR, '..', '04_Strategy_Execution'))
sys.path.insert(0, os.path.join(_DIR, '..', '05_Risk_Management'))

# 导入自定义模块
from CTA_Strategies_CN_Futures import (
    MockFuturesDataProvider, TSMOMStrategy, TrendFollowingStrategy,
    CarryStrategy, MetaModelAllocator, Signal
)
from CTA_Strategy_Evaluator import CTAEvaluator, PerformanceMetrics
from CTA_Portfolio_Risk_System import CTARiskManagementSystem, Position


# ============================================================
# 回测引擎
# ============================================================
class IntegratedBacktestEngine:
    """整合回测引擎"""
    
    def __init__(self, 
                 initial_capital: float = 10_000_000,
                 start_date: str = '2020-01-01',
                 end_date: str = '2024-12-31'):
        
        self.initial_capital = initial_capital
        self.start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        self.end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        # 数据提供�?
        self.data_provider = MockFuturesDataProvider()
        
        # 策略
        self.strategies = {
            'TSMOM': TSMOMStrategy(),
            'TrendFollowing': TrendFollowingStrategy(),
            'Carry': CarryStrategy()
        }
        
        # 元模型分配器
        self.meta_allocator = MetaModelAllocator(list(self.strategies.values()))
        
        # 风控系统
        self.risk_system = CTARiskManagementSystem()
        
        # 评估�?
        self.evaluator = CTAEvaluator(risk_free_rate=0.03)
        
        # 日志
        self.logger = logging.getLogger(__name__)
        
        # 加载数据
        self._load_data()
    
    def _load_data(self):
        """加载所有品种数�?""
        self.logger.info("加载市场数据...")
        
        self.market_data = {}
        symbols = ['RB', 'CU', 'SC', 'TA', 'M', 'AU', 'IF', 'T']  # 主要品种
        
        for symbol in symbols:
            df = self.data_provider.get_futures_data(
                symbol, 
                self.start_date.isoformat(),
                self.end_date.isoformat()
            )
            if not df.empty:
                self.market_data[symbol] = df
        
        self.logger.info(f"加载完成: {len(self.market_data)}个品�?)
    
    def run_strategy_backtest(self, 
                             strategy_name: str,
                             rebalance_freq: int = 5) -> Dict:
        """
        运行单一策略回测
        
        Args:
            strategy_name: 策略名称
            rebalance_freq: 调仓频率 (交易�?
        
        Returns:
            回测结果字典
        """
        strategy = self.strategies.get(strategy_name)
        if not strategy:
            raise ValueError(f"未知策略: {strategy_name}")
        
        self.logger.info(f"\n开始回�? {strategy_name}")
        
        # 生成交易日历
        all_dates = sorted(list(list(self.market_data.values())[0].index))
        
        # 回测状�?
        capital = self.initial_capital
        positions = {}  # symbol -> quantity
        portfolio_values = []
        trades = []
        
        for i, current_date in enumerate(all_dates):
            # 定期调仓
            if i % rebalance_freq == 0:
                # 生成信号
                signals = strategy.generate_signals(self.market_data, current_date)
                
                # 执行调仓
                for signal in signals:
                    if abs(signal.target_position) > 0.1:
                        # 目标仓位价�?
                        target_value = signal.target_position * capital
                        
                        # 获取当前价格
                        price = self.market_data[signal.symbol].loc[current_date, 'close']
                        
                        # 计算手数 (简化假设每手价�?
                        contract_value = price * 10  # 假设每手10单位
                        quantity = int(target_value / contract_value)
                        
                        # 记录
                        old_qty = positions.get(signal.symbol, 0)
                        if quantity != old_qty:
                            trades.append({
                                'date': current_date,
                                'symbol': signal.symbol,
                                'old_qty': old_qty,
                                'new_qty': quantity,
                                'price': price,
                                'signal': signal.signal.value
                            })
                            positions[signal.symbol] = quantity
            
            # 计算当日市�?
            total_value = capital
            daily_pnl = 0
            
            for symbol, qty in positions.items():
                if symbol in self.market_data and current_date in self.market_data[symbol].index:
                    price = self.market_data[symbol].loc[current_date, 'close']
                    position_value = qty * price * 10
                    total_value += position_value
                    
                    # 简化PnL计算
                    if i > 0:
                        prev_price = self.market_data[symbol].iloc[i-1]['close']
                        daily_pnl += qty * (price - prev_price) * 10
            
            portfolio_values.append({
                'date': current_date,
                'total_value': total_value,
                'daily_pnl': daily_pnl
            })
            
            capital = total_value
        
        # 生成收益率序�?
        df = pd.DataFrame(portfolio_values)
        df['daily_return'] = df['total_value'].pct_change()
        
        return {
            'strategy_name': strategy_name,
            'portfolio_values': df,
            'trades': pd.DataFrame(trades),
            'final_value': df['total_value'].iloc[-1],
            'returns': df['daily_return'].dropna()
        }
    
    def run_multi_strategy_portfolio(self, 
                                    strategy_weights: Dict[str, float] = None,
                                    rebalance_freq: int = 5) -> Dict:
        """
        运行多策略组合回�?
        """
        if strategy_weights is None:
            strategy_weights = {name: 1/len(self.strategies) for name in self.strategies}
        
        self.logger.info("\n开始多策略组合回测")
        self.logger.info(f"策略权重: {strategy_weights}")
        
        # 为每个子策略分配资金
        sub_capital = {name: self.initial_capital * weight 
                      for name, weight in strategy_weights.items()}
        
        # 运行各子策略回测
        sub_results = {}
        for name in self.strategies:
            # 临时修改初始资金
            original_capital = self.initial_capital
            self.initial_capital = sub_capital[name]
            
            result = self.run_strategy_backtest(name, rebalance_freq)
            sub_results[name] = result
            
            self.initial_capital = original_capital
        
        # 合并各策略收�?(按权重加�?
        all_dates = sub_results['TSMOM']['portfolio_values']['date']
        combined_returns = pd.Series(0.0, index=all_dates)
        
        for name, result in sub_results.items():
            weight = strategy_weights[name]
            returns = result['portfolio_values']['daily_return'].fillna(0)
            # 对齐日期
            for i, date in enumerate(all_dates):
                if i < len(returns):
                    combined_returns.loc[date] += returns.iloc[i] * weight
        
        # 计算组合净�?
        combined_values = (1 + combined_returns).cumprod() * self.initial_capital
        
        return {
            'strategy_name': 'Multi_Strategy_Portfolio',
            'portfolio_values': pd.DataFrame({
                'date': all_dates,
                'total_value': combined_values,
                'daily_return': combined_returns
            }),
            'sub_results': sub_results,
            'returns': combined_returns.dropna()
        }
    
    def run_meta_model_portfolio(self, rebalance_freq: int = 5) -> Dict:
        """
        运行元模型动态分配组�?
        """
        self.logger.info("\n开始元模型动态分配组合回�?)
        
        # 生成交易日历
        all_dates = sorted(list(list(self.market_data.values())[0].index))
        
        portfolio_values = []
        current_weights = {name: 1/len(self.strategies) for name in self.strategies}
        
        # 预计算各策略每日收益
        strategy_returns = {}
        for name, strategy in self.strategies.items():
            returns = []
            for i in range(1, len(all_dates)):
                signals = strategy.generate_signals(self.market_data, all_dates[i])
                # 简�? 用信号强度作为当日收益代�?
                avg_signal = np.mean([s.target_position for s in signals]) if signals else 0
                
                # 根据信号和次日价格变动估算收�?
                daily_ret = 0
                for s in signals:
                    if abs(s.target_position) > 0.1 and s.symbol in self.market_data:
                        try:
                            price_now = self.market_data[s.symbol].loc[all_dates[i], 'close']
                            price_prev = self.market_data[s.symbol].loc[all_dates[i-1], 'close']
                            ret = (price_now / price_prev - 1) * np.sign(s.target_position)
                            daily_ret += ret / len(signals)
                        except:
                            pass
                
                returns.append(daily_ret)
            
            strategy_returns[name] = pd.Series([0] + returns, index=all_dates)
        
        # 动态组�?
        for i, current_date in enumerate(all_dates):
            if i == 0:
                portfolio_values.append({
                    'date': current_date,
                    'total_value': self.initial_capital,
                    'weights': current_weights.copy()
                })
                continue
            
            # 每月更新权重
            if i % 20 == 0 and i > 20:
                # 检测市场环�?
                regime = self.meta_allocator.detect_regime(self.market_data, current_date)
                
                # 更新权重
                recent_returns = {name: series.iloc[max(0,i-20):i].mean() 
                                for name, series in strategy_returns.items()}
                self.meta_allocator.update_weights(regime, recent_returns)
                current_weights = self.meta_allocator.weights.copy()
            
            # 计算当日组合收益
            daily_return = sum(
                strategy_returns[name].iloc[i] * weight
                for name, weight in current_weights.items()
            )
            
            prev_value = portfolio_values[-1]['total_value']
            current_value = prev_value * (1 + daily_return)
            
            portfolio_values.append({
                'date': current_date,
                'total_value': current_value,
                'daily_return': daily_return,
                'weights': current_weights.copy()
            })
        
        df = pd.DataFrame(portfolio_values)
        df['daily_return'] = df['total_value'].pct_change()
        
        return {
            'strategy_name': 'Meta_Model_Portfolio',
            'portfolio_values': df,
            'returns': df['daily_return'].dropna()
        }
    
    def evaluate_and_report(self, results: List[Dict], 
                           benchmark_returns: pd.Series = None):
        """
        评估并生成报�?
        """
        print("\n" + "=" * 80)
        print("CTA策略绩效评估报告")
        print("=" * 80)
        
        metrics_list = []
        
        for result in results:
            if 'returns' not in result or len(result['returns']) < 30:
                continue
            
            metrics = self.evaluator.evaluate(
                result['returns'],
                result['strategy_name'],
                benchmark_returns
            )
            metrics_list.append(metrics)
            
            # 打印单个报告
            print()
            print(self.evaluator.generate_report(metrics))
        
        # 策略对比
        if len(metrics_list) > 1:
            print()
            print("=" * 80)
            print("策略对比�?)
            print("=" * 80)
            comparison = self.evaluator.compare_strategies(metrics_list)
            print(comparison.to_string())
        
        return metrics_list


# ============================================================
# 主程�?
# ============================================================
def main():
    """主程�?- 完整演示"""
    
    print("=" * 80)
    print("CTA策略研究与实�?- 完整回测演示")
    print("=" * 80)
    print()
    print("复现策略:")
    print("  1. TSMOM (时间序列动量) - Moskowitz et al. 2012")
    print("  2. Trend Following (趋势跟踪) - Man Group 2025")
    print("  3. Carry (期限结构) - ReSolve 2024")
    print("  4. Meta-Model Portfolio (元模型动态分�?")
    print()
    print("=" * 80)
    
    # 初始化回测引�?
    engine = IntegratedBacktestEngine(
        initial_capital=10_000_000,
        start_date='2020-01-01',
        end_date='2024-12-31'
    )
    
    # 生成基准收益 (模拟股票市场)
    np.random.seed(42)
    benchmark_dates = pd.date_range('2020-01-01', '2024-12-31', freq='B')
    benchmark_returns = pd.Series(
        np.random.normal(0.0002, 0.016, len(benchmark_dates)),
        index=benchmark_dates
    )
    
    # 运行各策略回�?
    all_results = []
    
    # 1. 单一策略回测
    for strategy_name in ['TSMOM', 'TrendFollowing', 'Carry']:
        result = engine.run_strategy_backtest(strategy_name, rebalance_freq=5)
        all_results.append(result)
    
    # 2. 等权组合回测
    equal_weight_result = engine.run_multi_strategy_portfolio(
        strategy_weights={'TSMOM': 0.33, 'TrendFollowing': 0.34, 'Carry': 0.33}
    )
    all_results.append(equal_weight_result)
    
    # 3. 元模型动态分配回�?
    meta_result = engine.run_meta_model_portfolio()
    all_results.append(meta_result)
    
    # 评估与报�?
    metrics_list = engine.evaluate_and_report(all_results, benchmark_returns)
    
    # 总结
    print()
    print("=" * 80)
    print("总结与建�?)
    print("=" * 80)
    print()
    print("【核心发现�?)
    print()
    print("1. 单一策略表现:")
    for m in metrics_list[:3]:
        print(f"   - {m.strategy_name}: 夏普={m.sharpe_ratio:.2f}, "
              f"最大回�?{m.max_drawdown*100:.1f}%, "
              f"信息比率={m.information_ratio:.2f}")
    print()
    
    print("2. 组合策略优势:")
    for m in metrics_list[3:]:
        print(f"   - {m.strategy_name}: 夏普={m.sharpe_ratio:.2f}, "
              f"最大回�?{m.max_drawdown*100:.1f}%, "
              f"Serenity={m.serenity_ratio:.2f}")
    print()
    
    print("【实施建议�?)
    print("  1. 建议采用多策略组�?降低单一策略失效风险")
    print("  2. 元模型动态分配可进一步提升风险调整后收益")
    print("  3. 严格风控: 单品种≤10%, 板块�?0%, 总杠杆≤2�?)
    print("  4. 定期(月度)回顾策略表现,调整权重")
    print()
    
    print("【风险控制�?)
    print("  - 事前风控: 订单检查、流动性评�?)
    print("  - 事中风控: 止损止盈、波动率监控")
    print("  - 事后风控: 压力测试、归因分�?)
    print()
    
    print("=" * 80)
    print("回测完成!")
    print("=" * 80)


if __name__ == "__main__":
    main()
