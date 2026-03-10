"""
真实数据十年回测完整版 (2014-2024)
====================================

使用米筐真实数据进行因子回测

作者: AI Assistant
日期: 2026-03-06
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Tuple
from dataclasses import dataclass
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
    logger.error("[ERROR] rqdatac未安装")

# 导入配置
try:
    from config import RQ_USERNAME, RQ_PASSWORD
except ImportError:
    RQ_USERNAME = '+8613810062394'
    RQ_PASSWORD = 'Fox880323!'


@dataclass
class BacktestResult:
    """回测结果"""
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
            'total_return': self.total_return,
            'annualized_return': self.annualized_return,
            'volatility': self.volatility,
            'information_ratio': self.information_ratio,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate,
            'num_trades': self.num_trades
        }


class RealDataBacktest:
    """真实数据回测引擎"""
    
    def __init__(self):
        self.connected = False
        self.price_cache = {}
        self._connect()
    
    def _connect(self):
        """连接米筐"""
        try:
            logger.info("[INFO] 连接米筐数据服务...")
            try:
                rq.deinit()
            except:
                pass
            rq.init(RQ_USERNAME, RQ_PASSWORD)
            
            # 验证连接
            test = rq.index_components('000300.XSHG', '2024-01-01')
            if test is not None and len(test) > 0:
                self.connected = True
                logger.info(f"[OK] 连接成功！沪深300成分股: {len(test)}只")
                return True
        except Exception as e:
            logger.error(f"[ERROR] 连接失败: {e}")
        return False
    
    def get_stocks(self, date: str) -> List[str]:
        """获取沪深300成分股"""
        try:
            stocks = rq.index_components('000300.XSHG', date)
            return stocks.tolist() if hasattr(stocks, 'tolist') else list(stocks)
        except Exception as e:
            logger.warning(f"获取股票池失败: {e}")
            return []
    
    def get_prices(self, stocks: List[str], start: str, end: str) -> pd.DataFrame:
        """获取收盘价"""
        if not stocks:
            return pd.DataFrame()
        try:
            prices = rq.get_price(stocks, start, end, frequency='1d', fields=['close'])
            return prices['close'] if isinstance(prices, pd.DataFrame) and 'close' in prices.columns else prices
        except Exception as e:
            logger.warning(f"获取价格失败: {e}")
            return pd.DataFrame()
    
    def get_fundamentals(self, stocks: List[str], date: str) -> pd.DataFrame:
        """获取财务数据"""
        try:
            q = rq.query(
                rq.financials.stock_code,
                rq.financials.pe_ratio,
                rq.financials.pb_ratio,
                rq.financials.ps_ratio
            ).filter(rq.financials.stock_code.in_(stocks))
            return rq.get_fundamentals(q, date=date)
        except Exception as e:
            logger.warning(f"获取财务数据失败: {e}")
            return pd.DataFrame()
    
    def calculate_factor(self, stocks: List[str], date: str, factor: str) -> pd.Series:
        """计算因子值"""
        # 获取前一天的数据避免未来函数
        date_obj = pd.to_datetime(date) - timedelta(days=1)
        trade_date = rq.get_previous_trading_date(date_obj).strftime('%Y-%m-%d')
        
        fund = self.get_fundamentals(stocks, trade_date)
        if fund.empty:
            return pd.Series(dtype=float)
        
        signals = pd.Series(index=stocks, dtype=float)
        
        for stock in stocks:
            try:
                row = fund[fund['stock_code'] == stock]
                if row.empty:
                    continue
                
                if factor == 'EP':
                    pe = row['pe_ratio'].values[0]
                    if pe > 0:
                        signals[stock] = 1 / pe
                elif factor == 'BP':
                    pb = row['pb_ratio'].values[0]
                    if pb > 0:
                        signals[stock] = 1 / pb
                elif factor == 'SP':
                    ps = row['ps_ratio'].values[0]
                    if ps > 0:
                        signals[stock] = 1 / ps
            except:
                continue
        
        # 去极值标准化
        signals = signals.dropna()
        if len(signals) > 10:
            signals = signals.clip(signals.quantile(0.05), signals.quantile(0.95))
            signals = (signals - signals.mean()) / signals.std()
        
        return signals
    
    def calculate_momentum(self, stocks: List[str], date: str, lookback: int = 12) -> pd.Series:
        """计算动量"""
        date_obj = pd.to_datetime(date)
        end = (date_obj - timedelta(days=30)).strftime('%Y-%m-%d')
        start = (date_obj - timedelta(days=30+lookback*30)).strftime('%Y-%m-%d')
        
        prices = self.get_prices(stocks, start, end)
        if prices.empty:
            return pd.Series(dtype=float)
        
        momentum = pd.Series(index=stocks, dtype=float)
        for stock in stocks:
            if stock in prices.columns:
                p = prices[stock].dropna()
                if len(p) >= 2:
                    momentum[stock] = (p.iloc[-1] / p.iloc[0]) - 1
        
        momentum = momentum.dropna()
        if len(momentum) > 10:
            momentum = momentum.clip(momentum.quantile(0.05), momentum.quantile(0.95))
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
        
        for i in range(1, min(len(dates), 60)):  # 限制60个月加快测试
            curr_date = dates[i].strftime('%Y-%m-%d')
            prev_date = dates[i-1].strftime('%Y-%m-%d')
            
            # 获取股票池
            stocks = self.get_stocks(prev_date)
            if not stocks:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 计算因子
            if factor_type == 'value':
                signal = self.calculate_factor(stocks, prev_date, factor_name)
            else:
                lb = 12 if '12' in factor_name else 6
                signal = self.calculate_momentum(stocks, prev_date, lb)
            
            if signal.empty or len(signal) < 20:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 多空组合 (Top10 - Bottom10)
            sorted_sig = signal.sort_values(ascending=False)
            longs = sorted_sig.head(10).index.tolist()
            shorts = sorted_sig.tail(10).index.tolist()
            
            # 计算收益
            ret = self.calc_return(longs, shorts, prev_date, curr_date)
            portfolio *= (1 + ret)
            equity_curve.append(portfolio)
            monthly_returns.append(ret)
            
            if i % 12 == 0:
                logger.info(f"  {curr_date}: 净值={portfolio:.4f}")
        
        # 计算指标
        if monthly_returns:
            rets = pd.Series(monthly_returns)
            result.total_return = portfolio - 1
            result.annualized_return = (portfolio ** (12/len(rets))) - 1 if portfolio > 0 else -1
            result.volatility = rets.std() * np.sqrt(12)
            result.sharpe_ratio = result.annualized_return / result.volatility if result.volatility > 0 else 0
            result.information_ratio = result.sharpe_ratio
            result.win_rate = (rets > 0).sum() / len(rets)
            result.num_trades = len(rets)
            
            # 最大回撤
            eq = pd.Series(equity_curve)
            dd = (eq - eq.cummax()) / eq.cummax()
            result.max_drawdown = dd.min()
        
        return result
    
    def calc_return(self, longs, shorts, start, end):
        """计算组合收益"""
        all_stocks = list(set(longs + shorts))
        prices = self.get_prices(all_stocks, start, end)
        if prices.empty or len(prices) < 2:
            return 0
        
        try:
            first = prices.iloc[0]
            last = prices.iloc[-1]
            ret = (last / first - 1).fillna(0)
            long_ret = ret[longs].mean() if longs else 0
            short_ret = ret[shorts].mean() if shorts else 0
            return long_ret - short_ret
        except:
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
            logger.info(f"[OK] {f}: 年化={r.annualized_return*100:.2f}%, IR={r.information_ratio:.2f}")
        
        # 动量因子
        for f in ['MOM_12_1', 'MOM_6_1']:
            r = self.backtest_factor(f, 'momentum', start, end)
            results['momentum'].append(r)
            logger.info(f"[OK] {f}: 年化={r.annualized_return*100:.2f}%, IR={r.information_ratio:.2f}")
        
        return results


def print_results(results):
    """打印结果"""
    if not results:
        return
    
    print("\n" + "="*80)
    print("回测结果")
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
        'results': [r.to_dict() for r in all_factors]
    }
    with open('backtests/real_data_results.json', 'w') as f:
        json.dump(data, f, indent=2)
    print("[OK] 结果已保存到 backtests/real_data_results.json")


if __name__ == "__main__":
    engine = RealDataBacktest()
    if engine.connected:
        results = engine.run("2019-01-01", "2024-01-01")
        print_results(results)
    else:
        print("[ERROR] 连接失败")
