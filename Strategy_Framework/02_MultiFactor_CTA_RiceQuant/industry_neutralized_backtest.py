"""
申万行业中性化多因子回测 (2019-2024)
======================================

使用米筐真实的申万行业分类数据进行行业中性化
同时支持市值中性化

修复内容:
1. 使用 rq.get_industry() 获取申万一级行业分类
2. 使用多元回归一次性控制行业和市值暴露
3. 正确的残差计算和标准化流程

作者: AI Assistant
日期: 2026-03-09
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional
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
    neutralized: bool
    start_date: str
    end_date: str
    annualized_return: float = 0
    volatility: float = 0
    information_ratio: float = 0
    sharpe_ratio: float = 0
    max_drawdown: float = 0
    win_rate: float = 0
    num_months: int = 0
    
    def to_dict(self):
        return {
            'factor_name': self.factor_name,
            'factor_type': self.factor_type,
            'neutralized': self.neutralized,
            'annualized_return': self.annualized_return,
            'information_ratio': self.information_ratio,
            'sharpe_ratio': self.sharpe_ratio,
            'max_drawdown': self.max_drawdown,
            'win_rate': self.win_rate
        }


class IndustryNeutralizedBacktest:
    """申万行业中性化回测引擎"""
    
    def __init__(self):
        self.connected = False
        self._connect()
        self.industry_cache = {}  # 缓存行业数据
    
    def _connect(self):
        """连接米筐"""
        try:
            logger.info("[INFO] 连接米筐...")
            try:
                rq.deinit()
            except:
                pass
            rq.init(RQ_USERNAME, RQ_PASSWORD)
            
            test = rq.index_components('000300.XSHG', '2024-01-01')
            if test is not None and len(test) > 0:
                self.connected = True
                logger.info(f"[OK] 连接成功！沪深300: {len(test)}只")
                
                # 测试申万行业数据获取
                try:
                    sample_stocks = test[:5]
                    industry_test = rq.get_industry(sample_stocks, date='2024-01-01', classification='sws')
                    logger.info(f"[OK] 申万行业数据测试成功: {len(industry_test)}条")
                except Exception as e:
                    logger.warning(f"[WARNING] 申万行业数据测试失败: {e}")
                
                return True
        except Exception as e:
            logger.error(f"[ERROR] 连接失败: {e}")
        return False
    
    def get_stocks(self, date: str) -> List[str]:
        """获取沪深300成分股"""
        try:
            result = rq.index_components('000300.XSHG', date)
            # 兼容不同返回类型
            if isinstance(result, list):
                return result
            elif hasattr(result, 'tolist'):
                return result.tolist()
            else:
                return list(result)
        except Exception as e:
            logger.debug(f"获取股票池失败: {e}")
            return []
    
    def get_prices(self, stocks: List[str], start: str, end: str) -> pd.DataFrame:
        """
        获取收盘价
        
        返回格式: DataFrame，index=date, columns=stock_code
        """
        if not stocks:
            return pd.DataFrame()
        try:
            prices = rq.get_price(stocks, start, end, frequency='1d', fields=['close'])
            if isinstance(prices, pd.DataFrame) and 'close' in prices.columns:
                prices = prices['close']
                # 处理多级索引: unstack将order_book_id转为列
                if prices.index.nlevels > 1:
                    prices = prices.unstack(level=0)
                return prices
            return prices
        except Exception as e:
            logger.debug(f"获取价格失败: {e}")
            return pd.DataFrame()
    
    def get_shenwan_industry(self, stocks: List[str], date: str) -> pd.Series:
        """
        获取申万一级行业分类
        
        使用米筐API: rq.get_instrument_industry() 或 rq.shenwan_instrument_industry()
        
        参数:
            stocks: 股票代码列表
            date: 日期字符串
            
        返回:
            pd.Series: index=stock_code, value=industry_name
        """
        if not stocks:
            return pd.Series(dtype=str)
        
        # 检查缓存
        cache_key = f"{date}_{len(stocks)}"
        if cache_key in self.industry_cache:
            cached = self.industry_cache[cache_key]
            return cached[cached.index.isin(stocks)]
        
        try:
            # 获取前一个交易日（避免未来函数）
            date_obj = pd.to_datetime(date)
            trade_date = rq.get_previous_trading_date(date_obj).strftime('%Y-%m-%d')
            
            # 使用米筐API获取申万行业分类
            # 方法1: get_instrument_industry (推荐，返回一级行业名称)
            try:
                industry_data = rq.get_instrument_industry(stocks, source='sws', date=trade_date)
                if industry_data is not None and not industry_data.empty:
                    if 'first_industry_name' in industry_data.columns:
                        industries = industry_data['first_industry_name']
                    elif 'first_industry_code' in industry_data.columns:
                        # 使用行业代码如果名称不可用
                        industries = industry_data['first_industry_code'].astype(str)
                    else:
                        industries = industry_data.iloc[:, 0]
                else:
                    industries = pd.Series(dtype=str)
            except Exception as e1:
                logger.debug(f"get_instrument_industry失败，尝试shenwan_instrument_industry: {e1}")
                # 方法2: shenwan_instrument_industry (备选)
                industry_data = rq.shenwan_instrument_industry(stocks, date=trade_date)
                if industry_data is not None and not industry_data.empty:
                    if 'index_name' in industry_data.columns:
                        industries = industry_data['index_name']
                    else:
                        industries = industry_data.iloc[:, 0]
                else:
                    industries = pd.Series(dtype=str)
            
            if industries.empty:
                logger.warning(f"[WARNING] {date} 申万行业数据为空")
                return pd.Series(dtype=str)
            
            # 确保索引是股票代码
            if industries.index.nlevels > 1:
                industries.index = industries.index.get_level_values(0)
            
            # 清理数据
            industries = industries.dropna()
            industries = industries[industries != '']
            
            logger.debug(f"[DEBUG] 获取到{len(industries)}只股票的行业数据，共{industries.nunique()}个行业")
            
            # 缓存结果
            self.industry_cache[cache_key] = industries
            
            return industries
            
        except Exception as e:
            logger.error(f"[ERROR] 获取申万行业数据失败: {e}")
            return pd.Series(dtype=str)
    
    def get_market_cap(self, stocks: List[str], date: str) -> pd.Series:
        """获取流通市值数据"""
        try:
            date_obj = pd.to_datetime(date)
            prev = rq.get_previous_trading_date(date_obj).strftime('%Y-%m-%d')
            
            # 获取市值数据
            cap = rq.get_factor(stocks, 'market_cap', prev, prev)
            if cap is not None and not cap.empty:
                series = cap['market_cap']
                if series.index.nlevels > 1:
                    series.index = series.index.get_level_values(0)
                return series
        except Exception as e:
            logger.debug(f"获取市值失败: {e}")
        return pd.Series(dtype=float)
    
    def neutralize_factors(self, signals: pd.Series, date: str,
                          industry_neutral: bool = True,
                          size_neutral: bool = True) -> pd.Series:
        """
        因子中性化处理（修复版）
        
        使用多元回归同时控制行业和市值暴露
        
        参数:
            signals: 原始因子信号
            date: 日期
            industry_neutral: 是否行业中性化
            size_neutral: 是否市值中性化
        """
        if signals.empty:
            return signals
        
        stocks = list(signals.index)
        
        # 准备回归数据
        data = pd.DataFrame({'signal': signals})
        
        # 获取行业数据
        industry_dummies = None
        if industry_neutral:
            industries = self.get_shenwan_industry(stocks, date)
            if not industries.empty:
                # 创建行业哑变量（剔除一个避免完全多重共线性）
                industry_dummies = pd.get_dummies(industries, prefix='ind')
                # 剔除样本量最少的行业（避免奇异矩阵）
                if industry_dummies.shape[1] > 1:
                    min_ind = industry_dummies.sum().idxmin()
                    industry_dummies = industry_dummies.drop(columns=[min_ind])
                # 确保数据类型为float
                industry_dummies = industry_dummies.astype(float)
                data = pd.concat([data, industry_dummies], axis=1)
                logger.debug(f"[DEBUG] 行业数量: {industry_dummies.shape[1]}")
        
        # 获取市值数据
        if size_neutral:
            market_caps = self.get_market_cap(stocks, date)
            if not market_caps.empty:
                data['log_cap'] = np.log(market_caps.replace(0, np.nan))
        
        # 清理数据
        data = data.dropna()
        if len(data) < 30:
            logger.warning(f"[WARNING] 数据不足({len(data)})，跳过中性化")
            return signals
        
        # 准备回归
        y = data['signal']
        X_cols = [c for c in data.columns if c != 'signal']
        
        if len(X_cols) == 0:
            return signals
        
        X = data[X_cols]
        
        # 添加常数项
        X = pd.concat([pd.Series(1, index=X.index, name='const'), X], axis=1)
        
        # 执行回归取残差
        try:
            # 使用numpy进行OLS回归（更快）
            X_np = X.values.astype(float)
            y_np = y.values.astype(float)
            
            # 检查矩阵条件数
            if np.linalg.cond(X_np) > 1e10:
                logger.warning("[WARNING] 设计矩阵条件数过大，使用伪逆")
                beta = np.linalg.pinv(X_np) @ y_np
            else:
                beta = np.linalg.lstsq(X_np, y_np, rcond=None)[0]
            
            # 计算残差
            y_pred = X_np @ beta
            residual = y - pd.Series(y_pred, index=y.index)
            
            # 标准化（仅一次）
            if residual.std() > 0:
                residual = (residual - residual.mean()) / residual.std()
            
            # 对齐到原始信号的所有股票（中性化后的信号）
            result = pd.Series(index=signals.index, dtype=float)
            result[residual.index] = residual
            
            return result
            
        except Exception as e:
            logger.error(f"[ERROR] 中性化回归失败: {e}")
            return signals
    
    def calc_factor_signal(self, stocks: List[str], date: str, factor: str) -> pd.Series:
        """计算因子信号"""
        date_obj = pd.to_datetime(date) - timedelta(days=1)
        trade_date = rq.get_previous_trading_date(date_obj).strftime('%Y-%m-%d')
        
        if factor in ['EP', 'BP', 'SP']:
            factor_map = {'EP': 'pe_ratio', 'BP': 'pb_ratio', 'SP': 'ps_ratio'}
            factor_code = factor_map[factor]
            
            try:
                df = rq.get_factor(stocks, factor_code, trade_date, trade_date)
                if df is None or df.empty:
                    return pd.Series(dtype=float)
                
                values = 1 / df[factor_code].replace([np.inf, -np.inf], np.nan)
                values = values.dropna()
                
                if values.index.nlevels > 1:
                    values.index = values.index.get_level_values(0)
                
                # 去极值和标准化
                if len(values) > 10:
                    values = values.clip(values.quantile(0.05), values.quantile(0.95))
                    if values.std() > 0:
                        values = (values - values.mean()) / values.std()
                
                return values
            except:
                return pd.Series(dtype=float)
        
        else:  # 动量因子
            lookback = 12 if '12' in factor else 6
            end = (date_obj - timedelta(days=30)).strftime('%Y-%m-%d')
            start = (date_obj - timedelta(days=(lookback + 1) * 30)).strftime('%Y-%m-%d')
            
            prices = self.get_prices(stocks, start, end)
            if prices is None or prices.empty:
                return pd.Series(dtype=float)
            
            momentum = pd.Series(index=stocks, dtype=float)
            for stock in stocks:
                try:
                    if isinstance(prices, pd.DataFrame) and stock in prices.columns:
                        p = prices[stock].dropna()
                    elif isinstance(prices, pd.Series) and prices.index.nlevels > 1:
                        try:
                            p = prices.xs(stock, level=0).dropna()
                        except:
                            continue
                    else:
                        continue
                    
                    if len(p) >= 2:
                        momentum[stock] = (p.iloc[-1] / p.iloc[0]) - 1
                except:
                    continue
            
            momentum = momentum.dropna()
            if len(momentum) > 10:
                momentum = momentum.clip(momentum.quantile(0.05), momentum.quantile(0.95))
                if momentum.std() > 0:
                    momentum = (momentum - momentum.mean()) / momentum.std()
            
            return momentum
    
    def backtest_factor(self, factor_name: str, factor_type: str,
                       start: str, end: str, 
                       industry_neutral: bool = False,
                       size_neutral: bool = False) -> BacktestResult:
        """
        回测单个因子
        
        参数:
            industry_neutral: 是否行业中性化
            size_neutral: 是否市值中性化
        """
        result = BacktestResult(
            factor_name=factor_name,
            factor_type=factor_type,
            neutralized=(industry_neutral or size_neutral),
            start_date=start,
            end_date=end
        )
        
        dates = pd.date_range(start=start, end=end, freq='ME')
        if len(dates) < 2:
            return result
        
        portfolio = 1.0
        equity_curve = [portfolio]
        monthly_returns = []
        
        # 中性化模式标签
        mode_parts = []
        if industry_neutral:
            mode_parts.append("行业中性")
        if size_neutral:
            mode_parts.append("市值中性")
        mode = "+".join(mode_parts) if mode_parts else "原始"
        
        logger.info(f"回测: {factor_name} ({mode})")
        
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
            signal = self.calc_factor_signal(stocks, prev_date, factor_name)
            if signal.empty or len(signal) < 20:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 应用中性化
            if industry_neutral or size_neutral:
                signal = self.neutralize_factors(
                    signal, prev_date,
                    industry_neutral=industry_neutral,
                    size_neutral=size_neutral
                )
            
            if signal.empty or len(signal) < 20:
                equity_curve.append(portfolio)
                monthly_returns.append(0)
                continue
            
            # 构建多空组合
            sorted_sig = signal.sort_values(ascending=False)
            longs = list(sorted_sig.head(20).index)
            shorts = list(sorted_sig.tail(20).index)
            
            # 计算收益
            ret = self.calc_portfolio_return(longs, shorts, prev_date, curr_date)
            portfolio *= (1 + ret)
            equity_curve.append(portfolio)
            monthly_returns.append(ret)
            
            if i % 12 == 0:
                logger.info(f"    {curr_date}: 净值={portfolio:.4f}")
        
        # 计算统计指标
        if monthly_returns:
            rets = pd.Series(monthly_returns)
            result.annualized_return = (portfolio ** (12/len(rets))) - 1 if portfolio > 0 else -1
            result.volatility = rets.std() * np.sqrt(12)
            if result.volatility > 0:
                result.sharpe_ratio = result.annualized_return / result.volatility
                result.information_ratio = result.sharpe_ratio
            result.win_rate = (rets > 0).sum() / len(rets)
            result.num_months = len(rets)
            
            eq = pd.Series(equity_curve)
            dd = (eq - eq.cummax()) / eq.cummax()
            result.max_drawdown = dd.min()
        
        return result
    
    def calc_portfolio_return(self, longs, shorts, start, end):
        """计算多空组合收益"""
        all_stocks = list(set(longs + shorts))
        if not all_stocks:
            return 0
        
        try:
            prices = self.get_prices(all_stocks, start, end)
            if prices is None or prices.empty:
                return 0
            
            # prices现在应该是DataFrame，index=date, columns=stock_code
            if isinstance(prices, pd.Series):
                # 如果仍然是Series（单只股票），转换为DataFrame
                prices_df = prices.to_frame()
                prices_df.columns = [all_stocks[0]]
            else:
                prices_df = prices
            
            if prices_df.empty or len(prices_df) < 2:
                return 0
            
            # 计算每只股票在期间的收益率
            first_prices = prices_df.iloc[0]
            last_prices = prices_df.iloc[-1]
            
            # 确保是Series类型
            if isinstance(first_prices, (int, float, np.number)):
                return 0
            
            stock_returns = (last_prices / first_prices - 1)
            stock_returns = stock_returns.fillna(0)
            
            # 计算多空组合收益
            long_rets = [stock_returns[s] for s in longs if s in stock_returns.index]
            short_rets = [stock_returns[s] for s in shorts if s in stock_returns.index]
            
            long_mean = np.mean(long_rets) if long_rets else 0
            short_mean = np.mean(short_rets) if short_rets else 0
            
            return long_mean - short_mean
        except Exception as e:
            logger.debug(f"计算收益失败: {e}")
            return 0
    
    def run_comparison(self, start="2019-01-01", end="2024-01-01"):
        """运行对比测试：原始 vs 行业中性 vs 市值中性 vs 双中性"""
        print("\n" + "="*100)
        print("申万行业中性化效果对比")
        print("="*100 + "\n")
        
        factors = ['EP', 'BP', 'SP', 'MOM_12_1', 'MOM_6_1']
        results = []
        
        for factor in factors:
            factor_type = 'value' if factor in ['EP', 'BP', 'SP'] else 'momentum'
            
            # 1. 原始因子
            r1 = self.backtest_factor(factor, factor_type, start, end, 
                                     industry_neutral=False, size_neutral=False)
            results.append(r1)
            logger.info(f"[原始] {factor}: 年化={r1.annualized_return*100:.2f}%, IR={r1.information_ratio:.2f}")
            
            # 2. 仅行业中性
            r2 = self.backtest_factor(factor, factor_type, start, end,
                                     industry_neutral=True, size_neutral=False)
            results.append(r2)
            logger.info(f"[行业中性] {factor}: 年化={r2.annualized_return*100:.2f}%, IR={r2.information_ratio:.2f}")
            
            # 3. 仅市值中性
            r3 = self.backtest_factor(factor, factor_type, start, end,
                                     industry_neutral=False, size_neutral=True)
            results.append(r3)
            logger.info(f"[市值中性] {factor}: 年化={r3.annualized_return*100:.2f}%, IR={r3.information_ratio:.2f}")
            
            # 4. 行业+市值双中性
            r4 = self.backtest_factor(factor, factor_type, start, end,
                                     industry_neutral=True, size_neutral=True)
            results.append(r4)
            logger.info(f"[双中性] {factor}: 年化={r4.annualized_return*100:.2f}%, IR={r4.information_ratio:.2f}")
            
            logger.info("")
        
        return results
    
    def run(self, start="2019-01-01", end="2024-01-01"):
        """运行回测"""
        print("\n" + "="*100)
        print(f"申万行业中性化多因子回测 ({start} 至 {end})")
        print("="*100 + "\n")
        
        if not self.connected:
            print("[ERROR] 未连接数据服务")
            return []
        
        return self.run_comparison(start, end)


def print_comparison_results(results):
    """打印对比结果"""
    if not results:
        return
    
    print("\n" + "="*120)
    print("申万行业中性化效果对比汇总")
    print("="*120)
    
    print(f"\n{'因子':<12} {'处理方式':<12} {'IR':<8} {'年化收益':<12} {'夏普':<8} {'最大回撤':<12} {'胜率':<10} {'IR改善':<10}")
    print("-"*120)
    
    factor_names = sorted(set(r.factor_name for r in results))
    
    for factor in factor_names:
        factor_results = [r for r in results if r.factor_name == factor]
        
        # 找到原始结果作为基准
        raw = next((r for r in factor_results if not r.neutralized), None)
        raw_ir = raw.information_ratio if raw else 0
        
        for r in factor_results:
            if not r.neutralized:
                mode = "原始"
                improve = "-"
            else:
                # 判断中性化类型
                mode = "中性化"
                improve_val = r.information_ratio - raw_ir
                improve = f"+{improve_val:.2f}" if improve_val >= 0 else f"{improve_val:.2f}"
            
            print(f"{r.factor_name:<12} {mode:<12} {r.information_ratio:>7.2f} "
                  f"{r.annualized_return*100:>10.2f}% {r.sharpe_ratio:>7.2f} "
                  f"{r.max_drawdown*100:>10.2f}% {r.win_rate*100:>8.1f}% {improve:>10}")
        
        print("-"*120)
    
    print("="*120)
    
    # 保存结果
    data = {'comparison': [r.to_dict() for r in results]}
    with open('backtests/shenwan_industry_neutralized.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print("\n[OK] 结果已保存到 backtests/shenwan_industry_neutralized.json")
    
    # 统计改善情况
    print("\n[中性化效果统计]")
    for factor in factor_names:
        factor_results = [r for r in results if r.factor_name == factor]
        raw = next((r for r in factor_results if not r.neutralized), None)
        neutralized = [r for r in factor_results if r.neutralized]
        
        if raw and neutralized:
            print(f"\n  {factor}:")
            for r in neutralized:
                improve = r.information_ratio - raw.information_ratio
                status = "✓ 改善" if improve > 0 else "✗ 下降"
                print(f"    → IR: {raw.information_ratio:.2f} → {r.information_ratio:.2f} "
                      f"({improve:+.2f}) {status}")


if __name__ == "__main__":
    engine = IndustryNeutralizedBacktest()
    if engine.connected:
        results = engine.run("2019-01-01", "2024-01-01")
        print_comparison_results(results)
    else:
        print("[ERROR] 连接失败，请检查米筐账号")
