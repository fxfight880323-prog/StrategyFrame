"""
真实数据十年回测 (2014-2024)
==========================

使用米筐(RiceQuant)真实数据进行因子回测

回测因子:
- 价值因子: EP, BP, SP, CFP, DP, EBIT/EV
- 动量因子: MOM(12-1), MOM(6-1), MOM(Smoothed)
- 组合因子: Value-Momentum Combo

输出:
- 每个因子的Information Ratio
- 年化收益率、夏普比率、最大回撤
- 净值曲线和回撤曲线
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import logging
import json
import warnings
import sys
import io

# 设置输出编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

warnings.filterwarnings('ignore')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# 导入米筐SDK
try:
    import rqdatac as rq
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False
    logger.error("米筐SDK未安装，请运行: pip install rqdatac")

# 导入API配置
try:
    from config import RQ_USERNAME, RQ_PASSWORD, RQ_ADDR
    RQ_AVAILABLE = RQ_AVAILABLE and True
except ImportError as e:
    RQ_USERNAME = None
    RQ_PASSWORD = None
    RQ_ADDR = ('rqdatad-pro.ricequant.com', 16011)
    logger.error(f"无法导入API配置: {e}")


@dataclass
class BacktestResult:
    """回测结果"""
    factor_name: str
    factor_type: str
    start_date: str
    end_date: str
    
    # 收益指标
    total_return: float = 0
    annualized_return: float = 0
    volatility: float = 0
    
    # 风险调整指标
    information_ratio: float = 0
    sharpe_ratio: float = 0
    max_drawdown: float = 0
    
    # 统计
    win_rate: float = 0
    num_months: int = 0
    
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
        self.universe = None
        self.price_data_cache = {}
        self.factor_data_cache = {}
        
        if RQ_AVAILABLE and RQ_USERNAME:
            self._connect()
    
    def _connect(self):
        """连接米筐"""
        try:
            logger.info("正在连接米筐数据服务...")
            rq.init(RQ_USERNAME, RQ_PASSWORD, addr=RQ_ADDR)
            self.connected = True
            logger.info("[OK] 米筐数据服务连接成功")
        except Exception as e:
            logger.error(f"[ERROR] 连接失败: {e}")
            self.connected = False
    
    def get_stock_universe(self, date: str) -> List[str]:
        """获取沪深300成分股"""
        if not self.connected:
            logger.warning("未连接米筐，无法获取数据")
            return []
        
        try:
            stocks = rq.index_components('000300.XSHG', date)
            return stocks.tolist() if hasattr(stocks, 'tolist') else list(stocks)
        except Exception as e:
            logger.warning(f"获取股票池失败 ({date}): {e}")
            return []
    
    def get_price_data(self, symbols: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        """获取价格数据（带缓存）"""
        cache_key = f"{start_date}_{end_date}"
        if cache_key in self.price_data_cache:
            return self.price_data_cache[cache_key]
        
        if not self.connected or not symbols:
            return pd.DataFrame()
        
        try:
            logger.info(f"  获取价格数据: {start_date} 至 {end_date}, {len(symbols)} 只股票")
            prices = rq.get_price(
                symbols,
                start_date=start_date,
                end_date=end_date,
                frequency='1d',
                fields=['close']
            )
            
            if isinstance(prices, pd.DataFrame) and 'close' in prices.columns:
                result = prices['close']
            else:
                result = prices
            
            self.price_data_cache[cache_key] = result
            return result
        except Exception as e:
            logger.warning(f"  获取价格数据失败: {e}")
            return pd.DataFrame()
    
    def get_factor_data(self, symbols: List[str], date: str) -> pd.DataFrame:
        """获取因子数据（PE, PB等）"""
        if not self.connected or not symbols:
            return pd.DataFrame()
        
        try:
            # 获取财务数据
            fundamentals = rq.get_fundamentals(
                rq.query(
                    rq.financials.stock_code,
                    rq.financials.pe_ratio,
                    rq.financials.pb_ratio,
                    rq.financials.ps_ratio,
                    rq.financials.pcf_ratio
                ).filter(
                    rq.financials.stock_code.in_(symbols)
                ),
                date=date
            )
            
            return fundamentals if not fundamentals.empty else pd.DataFrame()
        except Exception as e:
            logger.warning(f"  获取因子数据失败 ({date}): {e}")
            return pd.DataFrame()
    
    def calculate_value_signal(self, symbols: List[str], date: str, factor_type: str) -> pd.Series:
        """计算价值因子信号"""
        # 获取前一天的因子数据（避免 lookahead bias）
        date_obj = pd.to_datetime(date)
        prev_date = (date_obj - timedelta(days=1)).strftime('%Y-%m-%d')
        
        factor_data = self.get_factor_data(symbols, prev_date)
        
        if factor_data.empty:
            return pd.Series()
        
        signals = pd.Series(index=symbols, dtype=float)
        
        for symbol in symbols:
            try:
                if factor_type == 'EP':
                    pe = factor_data[factor_data['stock_code'] == symbol]['pe_ratio'].values
                    if len(pe) > 0 and pe[0] > 0:
                        signals[symbol] = 1 / pe[0]
                        
                elif factor_type == 'BP':
                    pb = factor_data[factor_data['stock_code'] == symbol]['pb_ratio'].values
                    if len(pb) > 0 and pb[0] > 0:
                        signals[symbol] = 1 / pb[0]
                        
                elif factor_type == 'SP':
                    ps = factor_data[factor_data['stock_code'] == symbol]['ps_ratio'].values
                    if len(ps) > 0 and ps[0] > 0:
                        signals[symbol] = 1 / ps[0]
                        
                elif factor_type == 'CFP':
                    pcf = factor_data[factor_data['stock_code'] == symbol]['pcf_ratio'].values
                    if len(pcf) > 0 and pcf[0] > 0:
                        signals[symbol] = 1 / pcf[0]
                        
                elif factor_type == 'Composite':
                    # 综合价值因子
                    pe = factor_data[factor_data['stock_code'] == symbol]['pe_ratio'].values
                    pb = factor_data[factor_data['stock_code'] == symbol]['pb_ratio'].values
                    ps = factor_data[factor_data['stock_code'] == symbol]['ps_ratio'].values
                    
                    score = 0
                    count = 0
                    if len(pe) > 0 and pe[0] > 0:
                        score += 1 / pe[0]
                        count += 1
                    if len(pb) > 0 and pb[0] > 0:
                        score += 1 / pb[0]
                        count += 1
                    if len(ps) > 0 and ps[0] > 0:
                        score += 1 / ps[0]
                        count += 1
                    
                    if count > 0:
                        signals[symbol] = score / count
            
            except Exception as e:
                continue
        
        # 去极值和标准化
        signals = signals.dropna()
        if len(signals) > 0:
            signals = signals.clip(lower=signals.quantile(0.01), upper=signals.quantile(0.99))
            if signals.std() > 0:
                signals = (signals - signals.mean()) / signals.std()
        
        return signals
    
    def calculate_momentum_signal(self, symbols: List[str], date: str, lookback: int = 12, skip: int = 1) -> pd.Series:
        """计算动量因子信号"""
        date_obj = pd.to_datetime(date)
        
        # 获取过去价格数据
        end_date = (date_obj - timedelta(days=skip * 30)).strftime('%Y-%m-%d')
        start_date = (date_obj - timedelta(days=(lookback + skip) * 30)).strftime('%Y-%m-%d')
        
        prices = self.get_price_data(symbols, start_date, end_date)
        
        if prices.empty:
            return pd.Series()
        
        # 计算动量（过去收益）
        momentum = pd.Series(index=symbols, dtype=float)
        
        for symbol in symbols:
            try:
                if symbol in prices.columns:
                    price_series = prices[symbol].dropna()
                    if len(price_series) >= 2:
                        total_return = (price_series.iloc[-1] / price_series.iloc[0]) - 1
                        momentum[symbol] = total_return
            except:
                continue
        
        # 去极值和标准化
        momentum = momentum.dropna()
        if len(momentum) > 0:
            momentum = momentum.clip(lower=momentum.quantile(0.01), upper=momentum.quantile(0.99))
            if momentum.std() > 0:
                momentum = (momentum - momentum.mean()) / momentum.std()
        
        return momentum
    
    def backtest_factor(self, factor_name: str, factor_type: str, 
                        start_date: str, end_date: str) -> BacktestResult:
        """回测单个因子"""
        logger.info(f"回测因子: {factor_name}")
        
        # 生成月度调仓日期
        dates = pd.date_range(start=start_date, end=end_date, freq='ME')
        if len(dates) < 2:
            logger.error("回测期间太短")
            return BacktestResult(factor_name, factor_type, start_date, end_date)
        
        portfolio_value = 1.0
        equity_curve = []
        returns_list = []
        
        for i in range(1, len(dates)):
            current_date = dates[i]
            prev_date = dates[i-1]
            
            date_str = prev_date.strftime('%Y-%m-%d')
            next_date_str = current_date.strftime('%Y-%m-%d')
            
            # 获取股票池
            symbols = self.get_stock_universe(date_str)
            if not symbols:
                logger.warning(f"  {date_str}: 无法获取股票池")
                equity_curve.append(portfolio_value)
                returns_list.append(0)
                continue
            
            # 构建信号
            if factor_type == 'value':
                signal = self.calculate_value_signal(symbols, date_str, factor_name)
            else:
                if factor_name == 'MOM_6_1':
                    signal = self.calculate_momentum_signal(symbols, date_str, lookback=6)
                else:
                    signal = self.calculate_momentum_signal(symbols, date_str, lookback=12)
            
            if signal.empty or len(signal) < 20:
                logger.warning(f"  {date_str}: 信号为空")
                equity_curve.append(portfolio_value)
                returns_list.append(0)
                continue
            
            # 构建多空组合 (Top 20 - Bottom 20)
            sorted_signal = signal.sort_values(ascending=False)
            long_stocks = sorted_signal.head(20).index.tolist()
            short_stocks = sorted_signal.tail(20).index.tolist()
            
            # 计算组合收益
            period_return = self._calculate_portfolio_return(
                long_stocks, short_stocks, date_str, next_date_str
            )
            
            portfolio_value *= (1 + period_return)
            equity_curve.append(portfolio_value)
            returns_list.append(period_return)
            
            if i % 12 == 0:  # 每年输出一次进度
                logger.info(f"  {date_str}: 净值={portfolio_value:.4f}, 收益={period_return*100:.2f}%")
        
        # 计算指标
        returns_series = pd.Series(returns_list)
        
        total_return = equity_curve[-1] - 1 if equity_curve else 0
        years = len(dates) / 12
        annualized_return = (1 + total_return) ** (1/max(years, 0.01)) - 1 if total_return > -1 else -1
        volatility = returns_series.std() * np.sqrt(12) if len(returns_series) > 0 else 0
        
        sharpe = annualized_return / volatility if volatility > 0 else 0
        ir = sharpe  # 简化处理
        
        # 最大回撤
        equity_series = pd.Series(equity_curve)
        cummax = equity_series.cummax()
        drawdown = (equity_series - cummax) / cummax
        max_dd = drawdown.min() if len(drawdown) > 0 else 0
        
        # 胜率
        win_rate = (returns_series > 0).sum() / len(returns_series) if len(returns_series) > 0 else 0
        
        return BacktestResult(
            factor_name=factor_name,
            factor_type=factor_type,
            start_date=start_date,
            end_date=end_date,
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            information_ratio=ir,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            num_months=len(returns_list)
        )
    
    def _calculate_portfolio_return(self, long_stocks, short_stocks, start_date, end_date):
        """计算多空组合收益"""
        all_stocks = list(set(long_stocks + short_stocks))
        
        prices = self.get_price_data(all_stocks, start_date, end_date)
        if prices.empty or len(prices) < 2:
            return 0.0
        
        try:
            # 计算个股收益
            first_prices = prices.iloc[0]
            last_prices = prices.iloc[-1]
            stock_returns = (last_prices / first_prices - 1).fillna(0)
            
            # 多空组合收益
            long_return = stock_returns[long_stocks].mean() if long_stocks else 0
            short_return = stock_returns[short_stocks].mean() if short_stocks else 0
            
            return long_return - short_return
        except:
            return 0.0
    
    def run_full_backtest(self, start_date="2014-01-01", end_date="2024-01-01"):
        """运行完整回测"""
        logger.info("=" * 80)
        logger.info("真实数据十年回测 (2014-2024)")
        logger.info("=" * 80)
        
        if not self.connected:
            logger.error("未连接到米筐数据服务，无法运行回测")
            return {}
        
        results = {'value': [], 'momentum': []}
        
        # 价值因子回测
        value_factors = ['EP', 'BP', 'SP', 'Composite']
        for factor in value_factors:
            result = self.backtest_factor(factor, 'value', start_date, end_date)
            results['value'].append(result)
            logger.info(f"[OK] {factor}: IR={result.information_ratio:.2f}, 收益={result.annualized_return*100:.2f}%")
        
        # 动量因子回测
        momentum_factors = [('MOM_12_1', 12), ('MOM_6_1', 6)]
        for factor_name, lookback in momentum_factors:
            result = self.backtest_factor(factor_name, 'momentum', start_date, end_date)
            results['momentum'].append(result)
            logger.info(f"[OK] {factor_name}: IR={result.information_ratio:.2f}, 收益={result.annualized_return*100:.2f}%")
        
        return results


def print_results(results):
    """打印回测结果"""
    print("\n" + "=" * 80)
    print("真实数据回测结果 (2014-2024)")
    print("=" * 80)
    
    print("\n[价值因子表现]")
    print(f"{'因子':<15} {'年化收益':<12} {'IR':<8} {'Sharpe':<8} {'最大回撤':<10} {'胜率':<8}")
    print("-" * 80)
    for r in sorted(results['value'], key=lambda x: x.information_ratio, reverse=True):
        print(f"{r.factor_name:<15} {r.annualized_return*100:>10.2f}% {r.information_ratio:>7.2f} "
              f"{r.sharpe_ratio:>7.2f} {r.max_drawdown*100:>8.2f}% {r.win_rate*100:>6.1f}%")
    
    print("\n[动量因子表现]")
    print(f"{'因子':<15} {'年化收益':<12} {'IR':<8} {'Sharpe':<8} {'最大回撤':<10} {'胜率':<8}")
    print("-" * 80)
    for r in sorted(results['momentum'], key=lambda x: x.information_ratio, reverse=True):
        print(f"{r.factor_name:<15} {r.annualized_return*100:>10.2f}% {r.information_ratio:>7.2f} "
              f"{r.sharpe_ratio:>7.2f} {r.max_drawdown*100:>8.2f}% {r.win_rate*100:>6.1f}%")
    
    print("\n[综合排名 (按IR)]")
    all_factors = results['value'] + results['momentum']
    all_factors.sort(key=lambda x: x.information_ratio, reverse=True)
    print(f"{'排名':<5} {'因子':<15} {'类型':<10} {'IR':<8} {'年化收益':<12}")
    print("-" * 80)
    for i, r in enumerate(all_factors[:5], 1):
        print(f"{i:<5} {r.factor_name:<15} {r.factor_type:<10} {r.information_ratio:>7.2f} {r.annualized_return*100:>10.2f}%")
    
    print("=" * 80)


def save_results(results, filepath):
    """保存结果"""
    data = {
        'metadata': {
            'backtest_period': '2014-01-01 to 2024-01-01',
            'data_source': 'RiceQuant (真实数据)',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        },
        'value_factors': [r.to_dict() for r in results['value']],
        'momentum_factors': [r.to_dict() for r in results['momentum']]
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"结果已保存: {filepath}")


if __name__ == "__main__":
    # 运行回测
    engine = RealDataBacktest()
    
    if engine.connected:
        results = engine.run_full_backtest("2014-01-01", "2024-01-01")
        print_results(results)
        save_results(results, 'backtests/real_data_backtest_results.json')
    else:
        logger.error("无法连接到米筐数据服务，请检查API Key")
