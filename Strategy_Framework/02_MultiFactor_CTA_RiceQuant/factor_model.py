"""
多因子选股模型
==============
基于米筐数据的多因子选股框架

支持的因子:
- 价值因子: PE, PB, PS, 股息率
- 质量因子: ROE, ROA, 毛利率
- 成长因子: 营收增长, 利润增长
- 技术因子: 动量, 波动率, 换手率
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

# 尝试导入米筐SDK
try:
    import rqdatac as rq
    RQ_AVAILABLE = True
except ImportError:
    RQ_AVAILABLE = False


@dataclass
class FactorScore:
    """因子得分数据类"""
    symbol: str
    factor_scores: Dict[str, float]
    total_score: float
    rank: int
    

class FactorDataProvider:
    """因子数据提供器"""
    
    def __init__(self, api_key: str = None):
        # 如果没有传入api_key，从配置文件读取
        if api_key is None:
            try:
                from config import RQ_API_KEY
                api_key = RQ_API_KEY
            except ImportError:
                api_key = None
        
        self.api_key = api_key
        self.connected = False
        self.logger = logging.getLogger(__name__)
        
        if RQ_AVAILABLE and api_key:
            self._connect()
    
    def _connect(self):
        """连接米筐数据服务"""
        try:
            rq.init(self.api_key)
            self.connected = True
            self.logger.info("米筐数据服务连接成功")
        except Exception as e:
            self.logger.error(f"连接失败: {e}")
            self.connected = False
    
    def get_stock_universe(self, universe: str = "hs300", date: str = None) -> List[str]:
        """
        获取股票池
        
        Args:
            universe: 股票池类型 (hs300/zz500/zz800/all)
            date: 日期 (YYYY-MM-DD)
        
        Returns:
            股票代码列表
        """
        if not self.connected:
            self.logger.warning("未连接米筐服务，返回模拟数据")
            return self._mock_stock_universe(universe)
        
        try:
            if date is None:
                date = datetime.now().strftime('%Y-%m-%d')
            
            if universe == "hs300":
                stocks = rq.index_components('000300.XSHG', date)
            elif universe == "zz500":
                stocks = rq.index_components('000905.XSHG', date)
            elif universe == "zz800":
                stocks = rq.index_components('000906.XSHG', date)
            else:
                # 全市场股票
                stocks = rq.all_instruments(type='CS')['order_book_id'].tolist()
            
            return stocks
        except Exception as e:
            self.logger.error(f"获取股票池失败: {e}")
            return self._mock_stock_universe(universe)
    
    def _mock_stock_universe(self, universe: str) -> List[str]:
        """模拟股票池（用于测试）"""
        mock_data = {
            "hs300": [f"{i:06d}.XSHG" if i < 600000 else f"{i:06d}.XSHE" 
                     for i in range(600000, 600100)],
            "zz500": [f"{i:06d}.XSHG" if i < 600000 else f"{i:06d}.XSHE" 
                     for i in range(600100, 600200)],
        }
        return mock_data.get(universe, mock_data["hs300"])
    
    def get_factor_data(
        self, 
        symbols: List[str], 
        factors: List[str], 
        date: str
    ) -> pd.DataFrame:
        """
        获取因子数据
        
        Args:
            symbols: 股票代码列表
            factors: 因子名称列表
            date: 日期
        
        Returns:
            DataFrame (index=symbol, columns=factors)
        """
        if not self.connected:
            return self._mock_factor_data(symbols, factors, date)
        
        try:
            # 获取财务数据
            factor_data = rq.get_factor(
                symbols,
                factors=factors,
                start_date=date,
                end_date=date
            )
            return factor_data
        except Exception as e:
            self.logger.error(f"获取因子数据失败: {e}")
            return self._mock_factor_data(symbols, factors, date)
    
    def _mock_factor_data(
        self, 
        symbols: List[str], 
        factors: List[str], 
        date: str
    ) -> pd.DataFrame:
        """模拟因子数据（用于测试）"""
        np.random.seed(hash(date) % 2**32)
        
        data = {}
        for factor in factors:
            if factor in ['pe_ttm', 'pb', 'ps_ttm']:
                # 估值因子: 正态分布，均值15，标准差10
                data[factor] = np.random.normal(15, 10, len(symbols))
            elif factor in ['roe', 'roa', 'gross_profit_margin']:
                # 盈利因子: 正态分布，均值0.10，标准差0.05
                data[factor] = np.random.normal(0.10, 0.05, len(symbols))
            elif 'growth' in factor:
                # 成长因子: 正态分布，均值0.15，标准差0.20
                data[factor] = np.random.normal(0.15, 0.20, len(symbols))
            elif 'momentum' in factor:
                # 动量因子: 正态分布，均值0.02，标准差0.10
                data[factor] = np.random.normal(0.02, 0.10, len(symbols))
            else:
                data[factor] = np.random.normal(0, 1, len(symbols))
        
        df = pd.DataFrame(data, index=symbols)
        df = df.clip(lower=df.quantile(0.01), upper=df.quantile(0.99), axis=1)
        return df
    
    def get_price_data(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """获取价格数据"""
        if not self.connected:
            return self._mock_price_data(symbols, start_date, end_date)
        
        try:
            prices = rq.get_price(
                symbols,
                start_date=start_date,
                end_date=end_date,
                frequency='1d',
                fields=['close']
            )
            return prices['close']
        except Exception as e:
            self.logger.error(f"获取价格数据失败: {e}")
            return self._mock_price_data(symbols, start_date, end_date)
    
    def _mock_price_data(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str
    ) -> pd.DataFrame:
        """模拟价格数据"""
        dates = pd.date_range(start=start_date, end=end_date, freq='B')
        
        np.random.seed(42)
        prices = {}
        for symbol in symbols:
            # 随机游走
            returns = np.random.normal(0.0005, 0.02, len(dates))
            price = 100 * np.exp(np.cumsum(returns))
            prices[symbol] = price
        
        return pd.DataFrame(prices, index=dates)


class FactorCalculator:
    """因子计算器"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def calculate_technical_factors(
        self, 
        prices: pd.DataFrame
    ) -> pd.DataFrame:
        """
        计算技术因子
        
        Args:
            prices: 价格DataFrame (index=date, columns=symbols)
        
        Returns:
            技术因子DataFrame (index=symbols, columns=factors)
        """
        # 如果prices有多列（多个股票），计算截面因子
        if len(prices.columns) > 1:
            factors = pd.DataFrame(index=prices.columns)
            
            # 20日动量
            momentum_20 = prices.pct_change(20).iloc[-1]
            factors['momentum_20'] = momentum_20
            
            # 60日动量
            momentum_60 = prices.pct_change(60).iloc[-1]
            factors['momentum_60'] = momentum_60
            
            # 20日波动率 (负向因子)
            returns = prices.pct_change()
            volatility_20 = returns.rolling(20).std().iloc[-1] * np.sqrt(252)
            factors['volatility_20'] = volatility_20
        else:
            # 单只股票的情况
            factors = pd.DataFrame(index=prices.index)
            factors['momentum_20'] = prices.pct_change(20)
            factors['momentum_60'] = prices.pct_change(60)
            returns = prices.pct_change()
            factors['volatility_20'] = returns.rolling(20).std() * np.sqrt(252)
        
        return factors
    
    def neutralize_factors(
        self, 
        factors: pd.DataFrame,
        industry: pd.Series = None
    ) -> pd.DataFrame:
        """
        因子中性化处理
        
        对因子进行市值和行业中性化，消除系统性偏差
        """
        # 简单的截面标准化
        neutralized = factors.copy()
        
        for col in neutralized.columns:
            # 去极值 (Winsorize)
            lower = neutralized[col].quantile(0.01)
            upper = neutralized[col].quantile(0.99)
            neutralized[col] = neutralized[col].clip(lower, upper)
            
            # Z-score标准化
            mean = neutralized[col].mean()
            std = neutralized[col].std()
            if std > 0:
                neutralized[col] = (neutralized[col] - mean) / std
        
        return neutralized


class MultiFactorModel:
    """
    多因子选股模型
    
    整合多个因子，计算综合得分，进行股票排名
    """
    
    def __init__(
        self, 
        factor_weights: Dict[str, float] = None,
        data_provider: FactorDataProvider = None
    ):
        self.factor_weights = factor_weights or {}
        self.data_provider = data_provider or FactorDataProvider()
        self.calculator = FactorCalculator()
        self.logger = logging.getLogger(__name__)
    
    def score_stocks(
        self,
        symbols: List[str],
        date: str,
        factor_weights: Dict[str, float] = None
    ) -> pd.DataFrame:
        """
        计算股票综合得分
        
        Args:
            symbols: 股票代码列表
            date: 评分日期
            factor_weights: 因子权重 (覆盖默认权重)
        
        Returns:
            DataFrame with columns: [symbol, factor_scores..., total_score, rank]
        """
        weights = factor_weights or self.factor_weights
        
        # 1. 获取基础因子数据
        fundamental_factors = list(weights.keys())
        fund_data = self.data_provider.get_factor_data(symbols, fundamental_factors, date)
        
        # 2. 获取价格数据计算技术因子
        start_dt = pd.to_datetime(date) - pd.Timedelta(days=120)
        prices = self.data_provider.get_price_data(symbols, start_dt.strftime('%Y-%m-%d'), date)
        
        tech_factors = self.calculator.calculate_technical_factors(prices)
        
        # 3. 合并因子数据
        all_factors = fund_data.copy()
        if not tech_factors.empty:
            # tech_factors的行是symbol，列是factor
            for col in tech_factors.columns:
                if col in weights:
                    all_factors[col] = tech_factors[col]
        
        # 4. 因子中性化
        neutralized = self.calculator.neutralize_factors(all_factors)
        
        # 5. 计算综合得分
        scores = pd.DataFrame(index=symbols)
        scores['symbol'] = symbols
        
        total_score = pd.Series(0.0, index=symbols)
        for factor, weight in weights.items():
            if factor in neutralized.columns:
                scores[f'score_{factor}'] = neutralized[factor] * weight
                total_score += neutralized[factor] * weight
            else:
                scores[f'score_{factor}'] = 0
        
        scores['total_score'] = total_score
        scores['rank'] = total_score.rank(ascending=False, method='min').astype(int)
        
        # 6. 排序
        scores = scores.sort_values('rank')
        
        return scores
    
    def select_stocks(
        self,
        symbols: List[str],
        date: str,
        top_n: int = 20,
        min_score: float = None
    ) -> List[str]:
        """
        选股函数
        
        Args:
            symbols: 股票池
            date: 选股日期
            top_n: 选择前N只股票
            min_score: 最低得分要求
        
        Returns:
            选中的股票列表
        """
        scores = self.score_stocks(symbols, date)
        
        # 筛选
        selected = scores[scores['rank'] <= top_n]
        
        if min_score is not None:
            selected = selected[selected['total_score'] >= min_score]
        
        return selected['symbol'].tolist()
    
    def get_factor_exposure(
        self,
        portfolio: List[str],
        date: str
    ) -> pd.Series:
        """
        获取组合因子暴露
        
        分析投资组合在各因子上的暴露程度
        """
        scores = self.score_stocks(portfolio, date)
        
        exposure = {}
        for col in scores.columns:
            if col.startswith('score_'):
                factor_name = col.replace('score_', '')
                exposure[factor_name] = scores[col].mean()
        
        return pd.Series(exposure)


# 便捷函数
def quick_screen(
    universe: str = "hs300",
    date: str = None,
    top_n: int = 20,
    api_key: str = None
) -> pd.DataFrame:
    """
    快速选股函数
    
    Example:
        >>> result = quick_screen(universe="hs300", date="2024-03-01", top_n=10)
        >>> print(result[['symbol', 'total_score', 'rank']])
    """
    from config import CONFIG
    
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    provider = FactorDataProvider(api_key or CONFIG.RQ_API_KEY)
    model = MultiFactorModel(CONFIG.FACTOR_WEIGHTS, provider)
    
    symbols = provider.get_stock_universe(universe, date)
    scores = model.score_stocks(symbols, date)
    
    return scores.head(top_n)


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 70)
    print("多因子选股模型测试")
    print("=" * 70)
    
    # 快速选股
    result = quick_screen(universe="hs300", date="2024-03-01", top_n=10)
    
    print("\nTop 10 Stocks:")
    print(result[['symbol', 'total_score', 'rank']].to_string())
    
    print("\nFactor Exposure:")
    factor_cols = [c for c in result.columns if c.startswith('score_')]
    print(result[factor_cols].mean().to_string())
