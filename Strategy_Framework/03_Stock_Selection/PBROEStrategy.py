"""
PB-ROE 价值选股策略
===================
基于市净率(PB)和净资产收益率(ROE)的A股选股策略

核心逻辑:
1. 低PB + 高ROE = 高性价比
2. 行业内对比，选择被低估的优质企业
3. ROE稳定性要求，避免一次性收益

数据: 米筐(RiceQuant)
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

# 导入米筐数据提供器
try:
    from RiceQuantDataProvider import RiceQuantDataProvider
    RQ_AVAILABLE = True
except:
    RQ_AVAILABLE = False
    print("⚠️ 请先运行: python install_rqdatac.py")


# ============================================================
# 配置参数
# ============================================================
PBROE_CONFIG = {
    # 筛选条件
    'max_pb': 3.0,              # 最大市净率
    'min_roe': 15.0,            # 最低ROE (%)
    'min_roe_stability': 2,     # ROE连续稳定年数
    'max_debt_ratio': 70.0,     # 最大资产负债率 (%)
    'min_market_cap': 50,       # 最小市值 (亿元)
    
    # 评分权重
    'pb_weight': 0.35,          # PB评分权重
    'roe_weight': 0.35,         # ROE评分权重
    'stability_weight': 0.20,   # ROE稳定性权重
    'growth_weight': 0.10,      # 成长性权重
    
    # 行业对比
    'industry_comparison': True,  # 是否进行行业对比
    'industry_discount': 0.8,     # 行业折价率阈值
    
    # 输出
    'top_n': 30,                # 输出前N只
}


# ============================================================
# 日志设置
# ============================================================
def setup_logger(name: str = "pbroe_strategy") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


# ============================================================
# PB-ROE 策略引擎
# ============================================================
class PBROEStrategy:
    """
    PB-ROE 价值选股策略引擎
    
    核心指标:
    - PB (市净率): 估值水平，越低越好
    - ROE (净资产收益率): 盈利能力，越高越好
    - ROE/PB: 性价比指标
    """
    
    def __init__(self, config: Dict = PBROE_CONFIG):
        self.config = config
        self.logger = setup_logger()
        
        # 初始化米筐数据提供器
        if RQ_AVAILABLE:
            self.provider = RiceQuantDataProvider()
            self.connected = self.provider.connected
        else:
            self.connected = False
            self.logger.error("❌ 米筐SDK未安装")
        
        # 数据缓存
        self.stock_data: Dict[str, pd.DataFrame] = {}
        self.industry_data: Dict[str, pd.DataFrame] = {}
    
    def get_stock_list(self) -> List[str]:
        """
        获取A股股票列表
        
        沪深300 + 中证500 成分股
        """
        if not self.connected:
            return []
        
        self.logger.info("获取A股股票列表...")
        
        # 获取沪深300成分股
        hs300 = self.provider.get_index_components('000300.XSHG')
        # 获取中证500成分股
        zz500 = self.provider.get_index_components('000905.XSHG')
        
        # 合并去重
        all_stocks = list(set(hs300 + zz500))
        
        self.logger.info(f"✓ 共 {len(all_stocks)} 只备选股票")
        return all_stocks
    
    def get_stock_fundamentals(self, symbol: str) -> Optional[Dict]:
        """
        获取股票基本面数据
        
        Returns:
            Dict with pb, roe, debt_ratio, market_cap, etc.
        """
        if not self.connected:
            return None
        
        try:
            # 获取最新交易日
            latest_date = date.today() - timedelta(days=30)
            
            # 获取财务报表数据
            # 注意: 米筐的财务数据接口需要根据实际SDK调整
            # 这里使用模拟逻辑，实际需要调用 rq.get_fundamentals 等接口
            
            # 简化处理: 使用模拟数据演示逻辑
            # 实际使用时需要调用米筐的财务数据接口
            
            # 获取股票当前价格
            price_df = self.provider.get_stock_price(
                symbol,
                (date.today() - timedelta(days=5)).isoformat(),
                date.today().isoformat()
            )
            
            if price_df is None or price_df.empty:
                return None
            
            current_price = price_df['close'].iloc[-1]
            
            # 模拟获取财务数据
            # 实际使用时应调用: rq.get_fundamentals() 或类似接口
            fundamentals = self._simulate_fundamentals(symbol, current_price)
            
            return fundamentals
            
        except Exception as e:
            self.logger.debug(f"{symbol}: 获取数据失败 - {e}")
            return None
    
    def _simulate_fundamentals(self, symbol: str, price: float) -> Dict:
        """
        模拟财务数据
        
        实际使用时应替换为真实的米筐财务数据接口
        """
        np.random.seed(hash(symbol) % 10000)
        
        # 基于股票代码生成相对稳定的模拟数据
        base_pb = np.random.uniform(0.8, 4.0)
        base_roe = np.random.uniform(5, 25)
        
        # 调整使其符合策略要求
        if np.random.random() > 0.7:  # 30%的股票符合要求
            base_pb = np.random.uniform(0.8, 2.5)
            base_roe = np.random.uniform(15, 30)
        
        # 生成多年ROE数据
        roe_history = [base_roe + np.random.normal(0, 2) for _ in range(5)]
        roe_history = [max(5, min(40, r)) for r in roe_history]
        
        return {
            'symbol': symbol,
            'price': price,
            'pb': round(base_pb, 2),
            'roe_ttm': round(base_roe, 2),
            'roe_history': [round(r, 2) for r in roe_history],
            'debt_ratio': round(np.random.uniform(30, 70), 2),
            'market_cap': round(np.random.uniform(50, 5000), 2),
            'industry': self._get_industry(symbol),
        }
    
    def _get_industry(self, symbol: str) -> str:
        """获取行业分类"""
        industry_map = {
            '600519': '食品饮料',
            '000858': '食品饮料',
            '000333': '家用电器',
            '000651': '家用电器',
            '601318': '非银金融',
            '600036': '银行',
            '000001': '银行',
            '600276': '医药生物',
            '000538': '医药生物',
            '600900': '公用事业',
            '601888': '休闲服务',
            '002415': '电子',
            '000725': '电子',
            '601012': '电气设备',
            '300750': '电气设备',
            '600309': '化工',
            '002594': '汽车',
            '601633': '汽车',
        }
        
        code = symbol.split('.')[0]
        return industry_map.get(code, '其他')
    
    def calculate_roe_stability(self, roe_history: List[float]) -> float:
        """
        计算ROE稳定性得分
        
        标准差越小，稳定性越高
        """
        if len(roe_history) < 3:
            return 0
        
        # 计算变异系数 (标准差/均值)
        mean_roe = np.mean(roe_history)
        std_roe = np.std(roe_history)
        
        if mean_roe <= 0:
            return 0
        
        cv = std_roe / mean_roe
        
        # CV越小越好，转换为得分 (0-100)
        stability_score = max(0, 100 - cv * 200)
        
        return round(stability_score, 2)
    
    def calculate_pb_score(self, pb: float, industry_avg_pb: float = None) -> float:
        """
        计算PB评分
        
        PB越低越好，同时考虑行业平均水平
        """
        max_pb = self.config['max_pb']
        
        # 基础评分
        if pb <= 1:
            base_score = 100
        elif pb <= max_pb:
            base_score = 100 - (pb - 1) / (max_pb - 1) * 50
        else:
            base_score = max(0, 50 - (pb - max_pb) / max_pb * 50)
        
        # 行业对比加分
        if industry_avg_pb and pb < industry_avg_pb * self.config['industry_discount']:
            base_score += 10
        
        return round(base_score, 2)
    
    def calculate_roe_score(self, roe: float) -> float:
        """
        计算ROE评分
        
        ROE越高越好
        """
        min_roe = self.config['min_roe']
        
        if roe >= 30:
            score = 100
        elif roe >= min_roe:
            score = 60 + (roe - min_roe) / (30 - min_roe) * 40
        else:
            score = max(0, (roe / min_roe) * 60)
        
        return round(score, 2)
    
    def calculate_comprehensive_score(self, data: Dict) -> Dict:
        """
        计算综合评分
        """
        # 各项子评分
        pb_score = self.calculate_pb_score(data['pb'])
        roe_score = self.calculate_roe_score(data['roe_ttm'])
        stability_score = self.calculate_roe_stability(data['roe_history'])
        
        # 成长性评分 (基于ROE趋势)
        roe_trend = data['roe_history'][-1] - data['roe_history'][0]
        growth_score = min(100, max(0, 50 + roe_trend * 5))
        
        # 性价比指标 ROE/PB
        roe_pb_ratio = data['roe_ttm'] / data['pb'] if data['pb'] > 0 else 0
        
        # 综合评分 (加权)
        weights = {
            'pb': self.config['pb_weight'],
            'roe': self.config['roe_weight'],
            'stability': self.config['stability_weight'],
            'growth': self.config['growth_weight'],
        }
        
        total_score = (
            pb_score * weights['pb'] +
            roe_score * weights['roe'] +
            stability_score * weights['stability'] +
            growth_score * weights['growth']
        )
        
        return {
            **data,
            'pb_score': pb_score,
            'roe_score': roe_score,
            'stability_score': stability_score,
            'growth_score': growth_score,
            'roe_pb_ratio': round(roe_pb_ratio, 2),
            'total_score': round(total_score, 2),
        }
    
    def filter_stocks(self, stocks_data: List[Dict]) -> List[Dict]:
        """
        筛选符合条件的股票
        """
        filtered = []
        
        for data in stocks_data:
            # 基本条件筛选
            if data['pb'] > self.config['max_pb']:
                continue
            if data['roe_ttm'] < self.config['min_roe']:
                continue
            if data['debt_ratio'] > self.config['max_debt_ratio']:
                continue
            if data['market_cap'] < self.config['min_market_cap']:
                continue
            
            # ROE稳定性检查
            positive_roe_years = sum(1 for r in data['roe_history'] if r >= self.config['min_roe'])
            if positive_roe_years < self.config['min_roe_stability']:
                continue
            
            filtered.append(data)
        
        return filtered
    
    def run_screening(self) -> pd.DataFrame:
        """
        运行选股筛选
        
        Returns:
            DataFrame with selected stocks and scores
        """
        self.logger.info("="*60)
        self.logger.info("PB-ROE 价值选股策略")
        self.logger.info("="*60)
        
        if not self.connected:
            self.logger.error("❌ 未连接到米筐服务")
            return pd.DataFrame()
        
        # 1. 获取股票列表
        stock_list = self.get_stock_list()
        if not stock_list:
            return pd.DataFrame()
        
        # 2. 获取基本面数据
        self.logger.info("\n获取股票基本面数据...")
        fundamentals_list = []
        
        for i, symbol in enumerate(stock_list[:100]):  # 先测试前100只
            if i % 20 == 0:
                self.logger.info(f"  进度: {i}/{min(100, len(stock_list))}")
            
            data = self.get_stock_fundamentals(symbol)
            if data:
                fundamentals_list.append(data)
        
        self.logger.info(f"✓ 获取成功: {len(fundamentals_list)} 只股票")
        
        # 3. 初步筛选
        self.logger.info("\n筛选符合条件的股票...")
        filtered = self.filter_stocks(fundamentals_list)
        self.logger.info(f"✓ 通过筛选: {len(filtered)} 只股票")
        
        # 4. 计算综合评分
        self.logger.info("\n计算综合评分...")
        scored_stocks = [self.calculate_comprehensive_score(d) for d in filtered]
        
        # 5. 排序并选择Top N
        df = pd.DataFrame(scored_stocks)
        if not df.empty:
            df = df.sort_values('total_score', ascending=False)
            df = df.head(self.config['top_n'])
        
        return df
    
    def generate_report(self, df: pd.DataFrame):
        """生成选股报告"""
        if df.empty:
            self.logger.warning("无选股结果")
            return
        
        print("\n" + "="*60)
        print("PB-ROE 选股结果")
        print("="*60)
        
        # 显示Top 15
        display_cols = ['symbol', 'industry', 'pb', 'roe_ttm', 'roe_pb_ratio', 'total_score']
        print("\nTop 15 推荐标的:")
        print(df[display_cols].head(15).to_string(index=False))
        
        # 统计
        print("\n" + "="*60)
        print("统计摘要")
        print("="*60)
        print(f"总评分均值: {df['total_score'].mean():.1f}")
        print(f"平均PB: {df['pb'].mean():.2f}")
        print(f"平均ROE: {df['roe_ttm'].mean():.2f}%")
        print(f"平均ROE/PB: {df['roe_pb_ratio'].mean():.2f}")
        
        # 行业分布
        print("\n行业分布:")
        industry_counts = df['industry'].value_counts().head(5)
        for ind, count in industry_counts.items():
            print(f"  {ind}: {count}只")
        
        # 保存结果
        output_file = f"pbroe_selection_{date.today().isoformat()}.csv"
        df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n✓ 结果已保存: {output_file}")


# ============================================================
# 主函数
# ============================================================
def main():
    """主程序"""
    strategy = PBROEStrategy()
    
    # 运行选股
    result_df = strategy.run_screening()
    
    # 生成报告
    strategy.generate_report(result_df)


if __name__ == "__main__":
    main()
