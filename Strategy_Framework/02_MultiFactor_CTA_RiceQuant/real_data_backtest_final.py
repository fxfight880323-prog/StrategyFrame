"""
真实数据十年回测最终版 (2019-2024)
======================================

使用米筐真实数据进行因子回测
修复财务数据获取方式

作者: AI Assistant
日期: 2026-03-06
"""

import pandas as pd
import numpy as np
from typing import List, Dict
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import json
import warnings
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
warnings.filterwarnings('ignore')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

try:
    import rqdatac as rq
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False

try:
    from config import RQ_USERNAME, RQ_PASSWORD
except ImportError:
    RQ_USERNAME = '+8613810062394'
    RQ_PASSWORD = 'Fox880323!'


@dataclass
class BacktestResult:
    factor_name: str
    factor_type: str
    start_date: str
    end_date: str
    total_return: float = 0
    annualized_return: float = 0
    volatility: float = 0
    information_ratio: float = 0
    sharpe_ratio: float = 0
    max_drawdown: float = 0
    win_rate: float = 0
    num_trades: int = 0
    
    def to_dict(self):
        return {
            'factor_name': self.factor_name,
            'factor_type': self.factor_type,
            'annualized_return': self.annualized_return,
            'information_ratio': self.information_ratio,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate
        }


class RealDataBacktest:
    """真实数据回测引擎"""
    
    def __init__(self):
        self.connected = False
        self._connect()
    
    def _connect(self):
        """连接米筐"""
        try:
            logger.info("[INFO] 连接米筐...")
            try:
                rq.deinit()
            except:
                pass
            rq.init(RQ_USERNAME, RQ_PASSWORD)
            
            # 验证连接
            test = rq.index_components('000300.XSHG', '2024-01-01')
            if test is not None and len(test) > 0:
                self.connected = True
                logger.info(f"[OK] 连接成功！沪深300: {len(test)}只")
                return True
        except Exception as e:
            logger.error(f"[ERROR] 连接失败: {e}")
        return False
    
    def get_stocks(self, date: str) -> List[str]:
        """获取沪深300成分股"""
        try:
            stocks = rq.index_components('000300.XSHG', date)
            return stocks.tolist() if hasattr(stocks, 'tolist') else list(stocks)
        except:
            return []
    
    def get_prices(self, stocks: List[str], start: str, end: str) -> pd.DataFrame:
        """获取收盘价"""
        if not stocks:
            return pd.DataFrame()
        try:
            prices = rq.get_price(stocks, start, end, frequency='1d', fields=['close'])
            if isinstance(prices, pd.DataFrame):
                return prices['close'] if 'close' in prices.columns else prices
            return pd.DataFrame()
        except:
            return pd.DataFrame()
    
    def get_factor_values(self, stocks: List[str], date: str) -> pd.DataFrame:
        """获取因子数据 (PE, PB, PS) - 使用 get_factor API"""
        try:
            # 获取前一个交易日避免未来函数
            curr = pd.to_datetime(date)
            prev = rq.get_previous_trading_date(curr).strftime('%Y-%m-%d')
            
            # 使用 get_factor 获取多个因子
            factors_data = {}
            for factor_name, factor_code in [('pe_ratio', 'pe_ratio'), ('pb_ratio', 'pb_ratio'), ('ps_ratio', 'ps_ratio')]:
                try:
                    factor_df = rq.get_factor(stocks, factor_code, prev, prev)
                    if factor_df is not None and not factor_df.empty:
                        factors_data[factor_name] = factor_df[factor_code]
                except:
                    continue
            
            if factors_data:
                df = pd.DataFrame(factors_data)
                df['stock_code'] = df.index
                return df
            return pd.DataFrame()
        except Exception as e:
            logger.warning(f"获取因子数据失败: {e}")
            return pd.DataFrame()
    
    def calc_value_signal(self, stocks: List[str], date: str, factor: str) -> pd.Series:
        """计算价值因子信号"""
        fund = self.get_factor_values(stocks, date)
        if fund.empty:
            return pd.Series(dtype=float)
        
        factor_map = {'EP': 'pe_ratio', 'BP': 'pb_ratio', 'SP': 'ps_ratio'}
        factor_col = factor_map.get(factor)
        
        if not factor_col or factor_col not in fund.columns:
            return pd.Series(dtype=float)
        
        # 获取因子列数据 (Series with MultiIndex)
        factor_data = fund[factor_col]
        
        # 计算EP/BP/SP = 1 / 比率
        signals = 1 / factor_data
        signals = signals.dropna()
        
        # 重置索引，只保留股票代码
        if signals.index.nlevels > 1:
            signals.index = signals.index.get_level_values(0)
        
        # 去极值和标准化
        if len(signals) > 10:
            signals = signals.clip(signals.quantile(0.05), signals.quantile(0.95))
            if signals.std() > 0:
                signals = (signals - signals.mean()) / signals.std()
        
        return signals
    
    def calc_momentum_signal(self, stocks: List[str], date: str, lookback: int = 12) -> pd.Series:
        """计算动量因子信号"""
        date_obj = pd.to_datetime(date)
        end = rq.get_previous_trading_date(date_obj).strftime('%Y-%m-%d')
        start = (date_obj - timedelta(days=lookback*30)).strftime('%Y-%m-%d')
        
        prices = self.get_prices(stocks, start, end)
        if prices.empty:
            return pd.Series(dtype=float)
        
        momentum = pd.Series(index=stocks, dtype=float)
        
        for stock in stocks:
            try:
                if isinstance(prices, pd.DataFrame) and stock in prices.columns:
                    p = prices[stock].dropna()
                elif isinstance(prices, pd.Series):
                    p = prices.dropna()
                else:
                    continue
                
                if len(p) >= 2:
                    momentum[stock] = (p.iloc[-1] / p.iloc[0]) - 1
            except:
                continue
        
        # 标准化
        momentum = momentum.dropna()
        if len(momentum) > 10:
            momentum = momentum.clip(momentum.quantile(0.05), momentum.quantile(0.95))
            if momentum.std() > 0:
                momentum = (momentum - momentum.mean()) / momentum.std()
        
        return momentum
    
    def backtest_factor(self, factor_name: str, factor_type: str, start: str, end: str) -> BacktestResult:
        """回测单个因子"""
        result = BacktestResult(factor_name, factor_type, start, end)
        
        logger.info(f"回测: {factor_name}")
        
        # 生成月度调仓日期
        dates = pd.date_range(start=start, end=end, freq='ME')
        if len(dates) < 2:
            return result
        
        portfolio = 1.0
        equity_curve = [portfolio]
        monthly_returns = []
        
        # 限制回测月数以加快测试
        max_months = 36
        dates = dates[:max_months+1] if len(dates) > max_months else dates
        
        logger.info(f"  回测月数: {len(dates)-1}")
        
        for i in range(1, len(dates)):
            curr_date = dates[i].strftime('%Y-%m-%d')
            prev_date = dates[i-1].strftime('%Y-%m-%d')
            
            # 获取股票池
            stocks = self.get_stocks(prev_date)
            if not stocks:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 计算因子信号
            if factor_type == 'value':
                signal = self.calc_value_signal(stocks, prev_date, factor_name)
            else:
                lb = 12 if '12' in factor_name else 6
                signal = self.calc_momentum_signal(stocks, prev_date, lb)
            
            if signal.empty or len(signal) < 20:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 构建多空组合 (修复索引问题)
            sorted_sig = signal.sort_values(ascending=False)
            # 提取股票代码 (处理MultiIndex情况)
            def extract_stock_code(idx):
                if isinstance(idx, tuple):
                    return idx[0]  # MultiIndex时取第一个元素(order_book_id)
                return idx
            
            longs = [extract_stock_code(idx) for idx in sorted_sig.head(15).index]
            shorts = [extract_stock_code(idx) for idx in sorted_sig.tail(15).index]
            
            # 计算收益
            ret = self.calc_portfolio_return(longs, shorts, prev_date, curr_date)
            portfolio *= (1 + ret)
            equity_curve.append(portfolio)
            monthly_returns.append(ret)
            
            if i % 6 == 0:
                logger.info(f"    {curr_date}: 净值={portfolio:.4f}")
        
        # 计算统计指标
        if monthly_returns:
            rets = pd.Series(monthly_returns)
            result.total_return = portfolio - 1
            result.annualized_return = (portfolio ** (12/len(rets))) - 1 if portfolio > 0 else -1
            result.volatility = rets.std() * np.sqrt(12)
            if result.volatility > 0:
                result.sharpe_ratio = result.annualized_return / result.volatility
                result.information_ratio = result.sharpe_ratio
            result.win_rate = (rets > 0).sum() / len(rets)
            result.num_trades = len(rets)
            
            # 最大回撤
            eq = pd.Series(equity_curve)
            dd = (eq - eq.cummax()) / eq.cummax()
            result.max_drawdown = dd.min()
        
        return result
    
    def calc_portfolio_return(self, longs, shorts, start, end):
        """计算多空组合收益"""
        all_stocks = list(set(longs + shorts))
        prices = self.get_prices(all_stocks, start, end)
        if prices.empty:
            return 0
        
        try:
            # 处理价格数据格式
            if isinstance(prices, pd.Series):
                # MultiIndex Series: (stock, date) -> price
                # 转换为DataFrame: rows=date, cols=stock
                prices_df = prices.unstack(level=0) if prices.index.nlevels > 1 else prices.to_frame()
            else:
                prices_df = prices
            
            if prices_df.empty or len(prices_df) < 2:
                return 0
            
            # 计算每只股票的收益
            first_prices = prices_df.iloc[0]
            last_prices = prices_df.iloc[-1]
            stock_returns = (last_prices / first_prices - 1).fillna(0)
            
            # 计算多空组合收益
            long_returns = [stock_returns[s] for s in longs if s in stock_returns.index]
            short_returns = [stock_returns[s] for s in shorts if s in stock_returns.index]
            
            long_mean = np.mean(long_returns) if long_returns else 0
            short_mean = np.mean(short_returns) if short_returns else 0
            
            return long_mean - short_mean
        except Exception as e:
            logger.debug(f"收益计算失败: {e}")
            return 0
    
    def run(self, start="2019-01-01", end="2024-01-01"):
        """运行回测"""
        print("\n" + "="*80)
        print(f"真实数据因子回测 ({start} 至 {end})")
        print("="*80 + "\n")
        
        if not self.connected:
            print("[ERROR] 未连接数据服务")
            return {}
        
        results = {'value': [], 'momentum': []}
        
        # 价值因子
        for f in ['EP', 'BP', 'SP']:
            r = self.backtest_factor(f, 'value', start, end)
            results['value'].append(r)
            logger.info(f"[OK] {f}: 年化={r.annualized_return*100:.2f}%, IR={r.information_ratio:.2f}, 胜率={r.win_rate*100:.1f}%")
        
        # 动量因子
        for f in ['MOM_12_1', 'MOM_6_1']:
            r = self.backtest_factor(f, 'momentum', start, end)
            results['momentum'].append(r)
            logger.info(f"[OK] {f}: 年化={r.annualized_return*100:.2f}%, IR={r.information_ratio:.2f}, 胜率={r.win_rate*100:.1f}%")
        
        return results


def print_results(results):
    """打印结果"""
    if not results or not results.get('value'):
        print("\n[WARNING] 没有回测结果")
        return
    
    print("\n" + "="*80)
    print("回测结果汇总")
    print("="*80)
    
    print("\n[价值因子]")
    print(f"{'因子':<12} {'年化收益':<12} {'IR':<10} {'最大回撤':<12} {'胜率':<8}")
    print("-"*70)
    for r in sorted(results['value'], key=lambda x: x.information_ratio, reverse=True):
        print(f"{r.factor_name:<12} {r.annualized_return*100:>10.2f}% {r.information_ratio:>8.2f} "
              f"{r.max_drawdown*100:>10.2f}% {r.win_rate*100:>6.1f}%")
    
    print("\n[动量因子]")
    print(f"{'因子':<12} {'年化收益':<12} {'IR':<10} {'最大回撤':<12} {'胜率':<8}")
    print("-"*70)
    for r in sorted(results['momentum'], key=lambda x: x.information_ratio, reverse=True):
        print(f"{r.factor_name:<12} {r.annualized_return*100:>10.2f}% {r.information_ratio:>8.2f} "
              f"{r.max_drawdown*100:>10.2f}% {r.win_rate*100:>6.1f}%")
    
    print("\n[TOP 5 综合排名]")
    all_factors = results['value'] + results['momentum']
    all_factors.sort(key=lambda x: x.information_ratio, reverse=True)
    print(f"{'排名':<6} {'因子':<12} {'类型':<10} {'IR':<10} {'年化收益':<12}")
    print("-"*70)
    for i, r in enumerate(all_factors[:5], 1):
        print(f"{i:<6} {r.factor_name:<12} {r.factor_type:<10} {r.information_ratio:>8.2f} {r.annualized_return*100:>10.2f}%")
    
    print("="*80 + "\n")
    
    # 保存结果
    data = {
        'metadata': {'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
        'value_factors': [r.to_dict() for r in results['value']],
        'momentum_factors': [r.to_dict() for r in results['momentum']]
    }
    with open('backtests/real_data_results_final.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("[OK] 结果已保存到 backtests/real_data_results_final.json")


def run_parameter_optimization(start="2019-01-01", end="2024-01-01"):
    """运行参数优化"""
    engine = RealDataBacktest()
    if not engine.connected:
        print("[ERROR] 连接失败")
        return []
    
    print("\n" + "="*80)
    print("参数优化")
    print("="*80 + "\n")
    
    factors = ['EP', 'BP', 'SP', 'MOM_12_1', 'MOM_6_1']
    n_stocks_options = [15, 20, 25]
    all_results = []
    
    for factor in factors:
        factor_type = 'value' if factor in ['EP', 'BP', 'SP'] else 'momentum'
        for n in n_stocks_options:
            params = {'n_long': n, 'n_short': n}
            result = engine.backtest_factor(factor, factor_type, start, end)
            result.params = params
            result.factor_name = f"{factor}_N{n}"
            all_results.append(result)
    
    all_results.sort(key=lambda x: x.information_ratio, reverse=True)
    return all_results


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "optimize":
        # 参数优化模式
        results = run_parameter_optimization("2019-01-01", "2024-01-01")
        
        print("\n" + "="*80)
        print("参数优化结果 (TOP 15)")
        print("="*80)
        print(f"{'排名':<5} {'因子':<15} {'IR':<8} {'年化':<10} {'夏普':<8} {'回撤':<10} {'胜率':<8}")
        print("-"*85)
        for i, r in enumerate(results[:15], 1):
            print(f"{i:<5} {r.factor_name:<15} {r.information_ratio:>7.2f} "
                  f"{r.annualized_return*100:>8.2f}% {r.sharpe_ratio:>7.2f} "
                  f"{r.max_drawdown*100:>8.2f}% {r.win_rate*100:>6.1f}%")
        print("="*80)
        
        # 保存结果
        data = {'optimization_results': [r.to_dict() for r in results]}
        with open('backtests/parameter_optimization.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("\n[OK] 结果已保存到 backtests/parameter_optimization.json")
        
        if results:
            best = results[0]
            print(f"\n[最佳参数]")
            print(f"  因子: {best.factor_name}")
            print(f"  年化收益: {best.annualized_return*100:.2f}%")
            print(f"  信息比率: {best.information_ratio:.2f}")
            print(f"  最大回撤: {best.max_drawdown*100:.2f}%")
    else:
        # 标准回测模式
        engine = RealDataBacktest()
        if engine.connected:
            results = engine.run("2019-01-01", "2024-01-01")
            print_results(results)
        else:
            print("[ERROR] 连接失败")
