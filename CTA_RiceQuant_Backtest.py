"""
米筐数据CTA策略回测演示
=======================

使用米筐(RiceQuant)真实期货数据进行CTA策略回测

策略:
1. TSMOM (时间序列动量)
2. Trend Following (趋势跟踪)
3. Carry (期限结构)
4. Meta-Model Portfolio (元模型组�?

数据:
- 米筐期货主力合约数据
- 支持多品种、多板块
- 数据自动缓存
"""

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import logging
import warnings
warnings.filterwarnings('ignore')

# 导入模块
from RiceQuantDataProvider_CTA import RiceQuantCTADataProvider, CTADatamanager, CATEGORY_MAP
from CTA_Strategies_CN_Futures import TSMOMStrategy, TrendFollowingStrategy, CarryStrategy, MetaModelAllocator
from CTA_Strategy_Evaluator import CTAEvaluator


# ============================================================
# 米筐CTA回测引擎
# ============================================================
class RiceQuantCTABacktester:
    """
    米筐数据CTA回测引擎
    
    特点:
    - 使用真实期货数据
    - 支持多策略组�?
    - 完整的绩效评�?
    - 详细的交易记�?
    """
    
    def __init__(self, 
                 api_key: str = None,
                 initial_capital: float = 10_000_000,
                 start_date: str = '2023-01-01',
                 end_date: str = '2024-12-31',
                 logger: logging.Logger = None):
        """
        初始化回测引�?
        
        Args:
            api_key: 米筐API密钥
            initial_capital: 初始资金 (默认1000�?
            start_date: 回测开始日�?
            end_date: 回测结束日期
        """
        self.logger = logger or logging.getLogger(__name__)
        self.initial_capital = initial_capital
        self.start_date = start_date
        self.end_date = end_date
        
        # 初始化数据提供器
        self.logger.info("="*70)
        self.logger.info("初始化米筐CTA回测引擎")
        self.logger.info("="*70)
        
        self.provider = RiceQuantCTADataProvider(api_key=api_key)
        self.data_manager = CTADatamanager(self.provider)
        
        # 初始化策�?
        self.strategies = {
            'TSMOM': TSMOMStrategy(),
            'TrendFollowing': TrendFollowingStrategy(),
            'Carry': CarryStrategy()
        }
        
        # 评估�?
        self.evaluator = CTAEvaluator(risk_free_rate=0.03)
        
        # 回测数据存储
        self.market_data = {}
        self.trading_dates = []
    
    def load_market_data(self, symbols: List[str], use_cache: bool = True):
        """
        加载市场数据
        
        Args:
            symbols: 品种代码列表
            use_cache: 是否使用本地缓存
        """
        self.logger.info(f"\n加载市场数据: {len(symbols)}个品�?)
        self.logger.info(f"时间区间: {self.start_date} ~ {self.end_date}")
        
        self.market_data = self.data_manager.load_data(
            symbols, self.start_date, self.end_date, use_cache
        )
        
        # 获取共同交易�?
        all_dates = set()
        for df in self.market_data.values():
            all_dates.update(df.index)
        
        self.trading_dates = sorted(list(all_dates))
        
        self.logger.info(f"�?数据加载完成: {len(self.market_data)}个品�? {len(self.trading_dates)}个交易日")
    
    def run_single_strategy(self, 
                           strategy_name: str,
                           rebalance_freq: int = 5,
                           position_size: float = 0.1) -> Dict:
        """
        运行单一策略回测
        
        Args:
            strategy_name: 策略名称
            rebalance_freq: 调仓频率 (交易�?
            position_size: 单品种仓位上�?
        """
        strategy = self.strategies.get(strategy_name)
        if not strategy:
            raise ValueError(f"未知策略: {strategy_name}")
        
        self.logger.info(f"\n{'='*70}")
        self.logger.info(f"开始回�? {strategy_name}")
        self.logger.info(f"{'='*70}")
        
        # 回测状�?
        capital = self.initial_capital
        positions = {}  # symbol -> {'quantity': int, 'cost': float}
        portfolio_values = []
        trades = []
        
        # 回测循环
        for i, current_date in enumerate(self.trading_dates):
            # 定期调仓
            if i % rebalance_freq == 0:
                # 生成信号
                signals = strategy.generate_signals(self.market_data, current_date)
                
                # 筛选有效信�?
                valid_signals = [s for s in signals if abs(s.target_position) > 0.1]
                
                if valid_signals:
                    # 计算目标仓位
                    total_target = sum(abs(s.target_position) for s in valid_signals)
                    
                    for signal in valid_signals:
                        symbol = signal.symbol
                        
                        if symbol not in self.market_data:
                            continue
                        
                        # 获取当前价格
                        df = self.market_data[symbol]
                        if current_date not in df.index:
                            continue
                        
                        price = df.loc[current_date, 'close']
                        
                        # 计算目标持仓价�?
                        weight = abs(signal.target_position) / total_target if total_target > 0 else 0
                        target_value = capital * position_size * weight * np.sign(signal.target_position)
                        
                        # 获取合约乘数
                        info = self.provider.get_symbol_info(symbol)
                        multiplier = info.get('multiplier', 10)
                        
                        # 计算手数
                        target_quantity = int(target_value / (price * multiplier))
                        
                        # 记录交易
                        old_quantity = positions.get(symbol, {}).get('quantity', 0)
                        if target_quantity != old_quantity:
                            trades.append({
                                'date': current_date,
                                'symbol': symbol,
                                'old_quantity': old_quantity,
                                'new_quantity': target_quantity,
                                'price': price,
                                'signal_strength': signal.strength,
                                'signal_direction': signal.signal.name
                            })
                            
                            if target_quantity != 0:
                                positions[symbol] = {
                                    'quantity': target_quantity,
                                    'cost': price,
                                    'multiplier': multiplier
                                }
                            elif symbol in positions:
                                del positions[symbol]
            
            # 计算当日组合价�?
            total_value = capital
            for symbol, pos in positions.items():
                if symbol in self.market_data and current_date in self.market_data[symbol].index:
                    price = self.market_data[symbol].loc[current_date, 'close']
                    position_value = pos['quantity'] * price * pos['multiplier']
                    total_value += position_value
            
            portfolio_values.append({
                'date': current_date,
                'total_value': total_value,
                'num_positions': len(positions)
            })
            
            capital = total_value
            
            # 定期输出
            if i % 50 == 0 or i == len(self.trading_dates) - 1:
                self.logger.info(f"  [{current_date}] 净�? ${total_value:,.0f} 持仓: {len(positions)}")
        
        # 生成结果
        df_portfolio = pd.DataFrame(portfolio_values)
        df_portfolio['daily_return'] = df_portfolio['total_value'].pct_change()
        
        return {
            'strategy_name': strategy_name,
            'portfolio_values': df_portfolio,
            'trades': pd.DataFrame(trades),
            'final_value': df_portfolio['total_value'].iloc[-1],
            'returns': df_portfolio['daily_return'].dropna(),
            'positions_history': positions
        }
    
    def run_equal_weight_portfolio(self, 
                                   strategy_weights: Dict[str, float] = None,
                                   rebalance_freq: int = 5) -> Dict:
        """
        运行等权多策略组合回�?
        """
        if strategy_weights is None:
            strategy_weights = {name: 1/len(self.strategies) for name in self.strategies}
        
        self.logger.info(f"\n{'='*70}")
        self.logger.info(f"开始多策略组合回测")
        self.logger.info(f"策略权重: {strategy_weights}")
        self.logger.info(f"{'='*70}")
        
        # 为每个子策略分配资金
        sub_capital = {name: self.initial_capital * weight 
                      for name, weight in strategy_weights.items()}
        
        # 运行各子策略回测
        sub_returns = {}
        
        for name, weight in strategy_weights.items():
            # 临时修改初始资金
            original_capital = self.initial_capital
            self.initial_capital = sub_capital[name]
            
            result = self.run_single_strategy(name, rebalance_freq)
            
            # 获取收益率序�?
            returns = result['portfolio_values'].set_index('date')['daily_return'].fillna(0)
            sub_returns[name] = returns
            
            self.initial_capital = original_capital
        
        # 合并各策略收�?
        combined_returns = pd.Series(0.0, index=self.trading_dates)
        
        for name, returns in sub_returns.items():
            weight = strategy_weights[name]
            combined_returns += returns * weight
        
        # 计算组合净�?
        combined_values = (1 + combined_returns).cumprod() * self.initial_capital
        
        df_portfolio = pd.DataFrame({
            'date': self.trading_dates,
            'total_value': combined_values,
            'daily_return': combined_returns
        })
        
        return {
            'strategy_name': 'Equal_Weight_Portfolio',
            'portfolio_values': df_portfolio,
            'sub_returns': sub_returns,
            'final_value': combined_values.iloc[-1],
            'returns': combined_returns.dropna()
        }
    
    def run_meta_model_portfolio(self, rebalance_freq: int = 5) -> Dict:
        """
        运行元模型动态分配组�?
        
        根据市场环境动态调整策略权�?
        """
        self.logger.info(f"\n{'='*70}")
        self.logger.info(f"开始元模型动态分配回�?)
        self.logger.info(f"{'='*70}")
        
        allocator = MetaModelAllocator(list(self.strategies.values()))
        
        # 预计算各策略每日收益
        self.logger.info("预计算各策略收益...")
        strategy_returns = {}
        
        for name, strategy in self.strategies.items():
            returns = []
            for i, current_date in enumerate(self.trading_dates):
                if i == 0:
                    returns.append(0)
                    continue
                
                signals = strategy.generate_signals(self.market_data, current_date)
                
                # 简�? 用信号计算当日收�?
                daily_ret = 0
                if signals:
                    for s in signals:
                        if abs(s.target_position) > 0.1 and s.symbol in self.market_data:
                            try:
                                df = self.market_data[s.symbol]
                                if current_date in df.index and self.trading_dates[i-1] in df.index:
                                    price_now = df.loc[current_date, 'close']
                                    price_prev = df.loc[self.trading_dates[i-1], 'close']
                                    ret = (price_now / price_prev - 1) * np.sign(s.target_position)
                                    daily_ret += ret / len(signals)
                            except:
                                pass
                
                returns.append(daily_ret)
            
            strategy_returns[name] = pd.Series(returns, index=self.trading_dates)
        
        # 动态组�?
        portfolio_values = []
        current_weights = {name: 1/len(self.strategies) for name in self.strategies}
        
        for i, current_date in enumerate(self.trading_dates):
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
                regime = allocator.detect_regime(self.market_data, current_date)
                
                # 更新权重
                recent_returns = {name: series.iloc[max(0,i-20):i].mean() 
                                for name, series in strategy_returns.items()}
                allocator.update_weights(regime, recent_returns)
                current_weights = allocator.weights.copy()
                
                self.logger.info(f"  [{current_date}] 状�? {regime.value}, "
                               f"权重: TSMOM={current_weights.get('TSMOM',0):.2f}, "
                               f"Trend={current_weights.get('TrendFollowing',0):.2f}, "
                               f"Carry={current_weights.get('Carry',0):.2f}")
            
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
        
        df_portfolio = pd.DataFrame(portfolio_values)
        df_portfolio['daily_return'] = df_portfolio['total_value'].pct_change()
        
        return {
            'strategy_name': 'Meta_Model_Portfolio',
            'portfolio_values': df_portfolio,
            'final_value': df_portfolio['total_value'].iloc[-1],
            'returns': df_portfolio['daily_return'].dropna()
        }
    
    def generate_report(self, results: List[Dict], 
                       benchmark_returns: pd.Series = None):
        """
        生成完整回测报告
        """
        print("\n" + "="*80)
        print("米筐CTA策略回测报告")
        print("="*80)
        print(f"回测区间: {self.start_date} ~ {self.end_date}")
        print(f"初始资金: ${self.initial_capital:,.0f}")
        print(f"交易品种: {list(self.market_data.keys())}")
        print()
        
        metrics_list = []
        
        for result in results:
            if 'returns' not in result or len(result['returns']) < 30:
                continue
            
            # 评估绩效
            metrics = self.evaluator.evaluate(
                result['returns'],
                result['strategy_name'],
                benchmark_returns
            )
            metrics_list.append(metrics)
            
            # 打印报告
            print()
            print(self.evaluator.generate_report(metrics))
        
        # 策略对比
        if len(metrics_list) > 1:
            print()
            print("="*80)
            print("策略对比")
            print("="*80)
            comparison = self.evaluator.compare_strategies(metrics_list)
            print(comparison.to_string())
        
        return metrics_list


# ============================================================
# 主程�?
# ============================================================
def main():
    """
    米筐CTA回测主程�?
    
    演示如何使用米筐数据进行CTA策略回测
    """
    
    # 米筐API密钥 (用户提供�?
    API_KEY = "Mg8lEL3dGgIyxrwc2rNsqVneytgqpSq4n0h4S8M-XQnZ9domysurqc3Lh1NlmAwAKSBTUr5qwFJ-aPEeFfR3L2rK5pq-HddOdS6vDBfDv187cVUdC9sejifx7V1lQjQWRm19YVrhx1poB-uThWtc3F6kzslu4cn9myNayWNzfo8=OPgej69FUSOnYfosbz62TAjuWXo_85kHZiUQUZCjXl78r0HUqN3HGJBXF7CIsXCHAAsQ7xieZzwD-_G8vn_3pkfFaAy2pLrhjk4BSLkVcNDwfPJovTa4hxIKfGAZ5G_HtNIHSUZcHnenxQnZljuvnzsixT3G-3Gr4UunAz9-72A="
    
    print("="*80)
    print("米筐(RiceQuant)CTA策略回测系统")
    print("="*80)
    print()
    print("本演示使用米筐真实期货数据进行CTA策略回测")
    print("支持的策�?")
    print("  1. TSMOM (时间序列动量)")
    print("  2. Trend Following (趋势跟踪)")
    print("  3. Carry (期限结构)")
    print("  4. Meta-Model Portfolio (元模型动态分�?")
    print()
    
    # 初始化回测引�?
    backtester = RiceQuantCTABacktester(
        api_key=API_KEY,
        initial_capital=10_000_000,  # 1000万初始资�?
        start_date='2023-01-01',
        end_date='2024-12-31'
    )
    
    # 选择交易品种 (多板块分�?
    symbols = [
        'RB', 'HC',    # 黑色
        'CU', 'AL',    # 有色
        'SC',          # 能源
        'TA', 'MA',    # 化工
        'M', 'CF',     # 农产�?
        'AU',          # 贵金�?
        'IF',          # 股指
    ]
    
    # 加载数据
    backtester.load_market_data(symbols, use_cache=True)
    
    # 运行回测
    all_results = []
    
    # 1. 单一策略回测
    print("\n" + "="*80)
    print("第一阶段: 单一策略回测")
    print("="*80)
    
    for strategy_name in ['TSMOM', 'TrendFollowing', 'Carry']:
        result = backtester.run_single_strategy(strategy_name, rebalance_freq=5)
        all_results.append(result)
    
    # 2. 等权组合回测
    print("\n" + "="*80)
    print("第二阶段: 多策略组合回�?)
    print("="*80)
    
    equal_weight_result = backtester.run_equal_weight_portfolio(
        strategy_weights={'TSMOM': 0.33, 'TrendFollowing': 0.34, 'Carry': 0.33}
    )
    all_results.append(equal_weight_result)
    
    # 3. 元模型动态分配回�?
    print("\n" + "="*80)
    print("第三阶段: 元模型动态分配回�?)
    print("="*80)
    
    meta_result = backtester.run_meta_model_portfolio(rebalance_freq=5)
    all_results.append(meta_result)
    
    # 生成报告
    # 创建模拟基准
    np.random.seed(42)
    benchmark_returns = pd.Series(
        np.random.normal(0.0002, 0.016, len(backtester.trading_dates)),
        index=backtester.trading_dates
    )
    
    metrics_list = backtester.generate_report(all_results, benchmark_returns)
    
    # 总结
    print()
    print("="*80)
    print("总结与建�?)
    print("="*80)
    print()
    print("【回测结果摘要�?)
    print()
    
    for m in metrics_list:
        print(f"  {m.strategy_name:20s}: "
              f"年化收益={m.annualized_return*100:6.2f}%, "
              f"夏普={m.sharpe_ratio:5.2f}, "
              f"最大回�?{m.max_drawdown*100:6.2f}%, "
              f"信息比率={m.information_ratio:5.2f}")
    
    print()
    print("【关键发现�?)
    print("  1. 单一策略在不同市场环境下表现各异")
    print("  2. 多策略组合可降低回撤，提高风险调整后收益")
    print("  3. 元模型动态分配可根据市场环境优化权重")
    print()
    print("【实盘建议�?)
    print("  1. 使用米筐实时数据进行信号计算")
    print("  2. 严格执行风控系统(单品种≤10%, 板块�?0%)")
    print("  3. 定期(月度)回顾策略表现，调整参�?)
    print("  4. 考虑交易费用和滑点的影响")
    print()
    print("="*80)
    print("回测完成!")
    print("="*80)


if __name__ == "__main__":
    main()
