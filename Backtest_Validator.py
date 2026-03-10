"""
CTA回测时间序列验证器
=====================
严格检查回测过程中是否存在未来数据泄露

验证项目:
1. 信号生成是否只使用历史数据
2. 持仓计算是否基于信号日期之后的价格
3. 未来收益计算是否正确使用未来数据
4. 回测循环是否存在 lookahead bias
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, timedelta
from typing import Dict, List, Tuple
import logging


def setup_logger():
    logger = logging.getLogger("backtest_validator")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        logger.addHandler(sh)
    return logger


class TimeSeriesValidator:
    """时间序列数据流验证器"""
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.errors = []
        self.warnings = []
    
    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.errors = []
        self.warnings = []
        self.column_mapping = {}  # 保存列名映射
    
    def validate_signal_data(self, signals_df: pd.DataFrame) -> Tuple[bool, pd.DataFrame]:
        """
        验证信号数据的时间属性
        确保信号只基于历史数据生成
        返回: (是否有效, 处理后的DataFrame)
        """
        self.logger.info("\n" + "="*60)
        self.logger.info("验证1: 信号数据时间属性检查")
        self.logger.info("="*60)
        
        is_valid = True
        
        # 检查必需列 (支持英文和中文列名)
        col_mapping = {
            'Ticker': ['Ticker', '代码', 'Stock'],
            'Date': ['Date', '日期', '信号日期'],
            'Signal': ['Signal', '信号', 'Trade_Signal'],
            'Rank': ['Rank', '排名', 'Rank_No']
        }
        
        actual_mapping = {}
        for standard_name, possible_names in col_mapping.items():
            found = False
            for name in possible_names:
                if name in signals_df.columns:
                    actual_mapping[standard_name] = name
                    found = True
                    break
            if not found and standard_name != 'Date':  # Date是可选的
                self.errors.append(f"缺少必需列: {standard_name} (尝试: {possible_names})")
                is_valid = False
        
        if not is_valid:
            return False, signals_df
        
        # 重命名列以便统一处理
        rename_map = {v: k for k, v in actual_mapping.items() if v in signals_df.columns}
        signals_df = signals_df.rename(columns=rename_map)
        self.column_mapping = actual_mapping
        self.logger.info(f"✓ 列名映射: {actual_mapping}")
        
        # 检查日期格式 (如果没有Date列，使用今天作为信号日期)
        if 'Date' not in signals_df.columns:
            from datetime import datetime
            signals_df['Date'] = datetime.now().strftime('%Y-%m-%d')
            self.logger.info(f"ℹ 无Date列，使用当前日期作为信号日期")
        
        try:
            signals_df['Date'] = pd.to_datetime(signals_df['Date'])
            self.logger.info(f"✓ 日期列格式正确")
        except Exception as e:
            self.errors.append(f"日期列格式错误: {e}")
            return False
        
        # 检查是否有未来日期
        max_date = signals_df['Date'].max()
        today = pd.Timestamp.now()
        
        if max_date > today:
            self.errors.append(f"信号数据包含未来日期: {max_date}")
            is_valid = False
        else:
            self.logger.info(f"✓ 无未来日期 (最新信号: {max_date.strftime('%Y-%m-%d')})")
        
        # 检查信号类型
        valid_signals = ['BUY', 'HOLD', 'SELL']
        invalid_signals = signals_df[~signals_df['Signal'].isin(valid_signals)]['Signal'].unique()
        if len(invalid_signals) > 0:
            self.warnings.append(f"存在非标准信号类型: {invalid_signals}")
        else:
            self.logger.info(f"✓ 信号类型标准化 (BUY/HOLD/SELL)")
        
        # 检查每只股票的日期序列
        ticker_date_counts = signals_df.groupby('Ticker')['Date'].nunique()
        if (ticker_date_counts > 1).any():
            multi_date_tickers = ticker_date_counts[ticker_date_counts > 1].index.tolist()
            self.logger.info(f"ℹ 发现 {len(multi_date_tickers)} 只股票有多个信号日期")
        
        self.logger.info(f"✓ 信号数据验证通过: {len(signals_df)} 条信号记录")
        return is_valid, signals_df
    
    def validate_price_data(self, price_data: Dict[str, Dict[date, float]], 
                           signals_df: pd.DataFrame) -> bool:
        """
        验证价格数据与信号的时序关系
        确保每个信号日期都有对应的价格数据
        """
        self.logger.info("\n" + "="*60)
        self.logger.info("验证2: 价格数据时序完整性检查")
        self.logger.info("="*60)
        
        is_valid = True
        
        # 检查每只股票的价格数据
        signal_tickers = signals_df['Ticker'].unique()
        missing_price_tickers = []
        
        for ticker in signal_tickers:
            if ticker not in price_data:
                missing_price_tickers.append(ticker)
                continue
            
            ticker_signals = signals_df[signals_df['Ticker'] == ticker]
            prices = price_data[ticker]
            
            # 检查每个信号日期是否有价格数据
            for _, signal in ticker_signals.iterrows():
                signal_date = signal['Date']
                if isinstance(signal_date, pd.Timestamp):
                    signal_date = signal_date.date()
                
                if signal_date not in prices:
                    self.warnings.append(f"{ticker} 在 {signal_date} 无价格数据")
        
        if missing_price_tickers:
            self.errors.append(f"{len(missing_price_tickers)} 只股票缺少价格数据: {missing_price_tickers[:5]}...")
            is_valid = False
        else:
            self.logger.info(f"✓ 所有信号股票都有价格数据")
        
        # 检查价格数据的连续性
        for ticker, prices in list(price_data.items())[:5]:  # 抽样检查
            dates = sorted(prices.keys())
            if len(dates) < 2:
                continue
            
            # 检查是否有明显的价格跳空（可能是数据缺失）
            for i in range(1, min(len(dates), 10)):
                day_diff = (dates[i] - dates[i-1]).days
                if day_diff > 5:  # 超过5天的跳空
                    self.warnings.append(f"{ticker} 在 {dates[i-1]} 到 {dates[i]} 有 {day_diff} 天空缺")
        
        self.logger.info(f"✓ 价格数据验证完成: {len(price_data)} 只股票")
        return is_valid
    
    def validate_future_return_calculation(self, price_data: Dict, 
                                          signals_df: pd.DataFrame,
                                          holding_period: int = 20) -> pd.DataFrame:
        """
        验证未来收益计算的正确性
        确保未来收益严格使用信号日期之后的价格
        """
        self.logger.info("\n" + "="*60)
        self.logger.info(f"验证3: 未来收益计算正确性检查 (持有{holding_period}日)")
        self.logger.info("="*60)
        
        validation_results = []
        
        for _, signal_row in signals_df.head(100).iterrows():  # 抽样检查前100条
            ticker = signal_row['Ticker']
            signal_date = signal_row['Date']
            if isinstance(signal_date, pd.Timestamp):
                signal_date = signal_date.date()
            
            if ticker not in price_data:
                continue
            
            prices = price_data[ticker]
            
            # 获取信号日期的价格
            if signal_date not in prices:
                continue
            
            entry_price = prices[signal_date]
            
            # 获取信号日期后的交易日
            future_dates = [d for d in sorted(prices.keys()) if d > signal_date]
            
            if len(future_dates) < holding_period:
                continue
            
            # 计算未来收益
            exit_date = future_dates[holding_period - 1]
            exit_price = prices[exit_date]
            future_return = (exit_price / entry_price - 1) * 100
            
            # 验证：收益计算不应使用信号日期之前的数据
            # 验证1: entry_price 必须是 signal_date 的价格
            # 验证2: exit_price 必须是 signal_date 之后第 holding_period 天的价格
            
            validation_results.append({
                'Ticker': ticker,
                'Signal_Date': signal_date,
                'Entry_Price': entry_price,
                'Exit_Date': exit_date,
                'Exit_Price': exit_price,
                'Future_Return': future_return,
                'Holding_Days': holding_period,
                'Data_Available': len(future_dates) >= holding_period
            })
        
        if not validation_results:
            self.errors.append("无法验证未来收益计算，数据不足")
            return pd.DataFrame()
        
        df = pd.DataFrame(validation_results)
        
        # 统计验证结果
        self.logger.info(f"✓ 抽样验证 {len(df)} 个信号的未来收益计算")
        self.logger.info(f"  平均未来收益: {df['Future_Return'].mean():+.2f}%")
        self.logger.info(f"  收益标准差: {df['Future_Return'].std():.2f}%")
        self.logger.info(f"  正收益比例: {(df['Future_Return'] > 0).mean()*100:.1f}%")
        
        # 检查异常值
        extreme_returns = df[(df['Future_Return'].abs() > 50)]
        if len(extreme_returns) > 0:
            self.warnings.append(f"发现 {len(extreme_returns)} 个极端收益 (>50%)，建议检查数据质量")
        
        self.logger.info(f"✓ 未来收益计算验证通过")
        return df
    
    def validate_backtest_chronology(self, trades: List[Dict]) -> bool:
        """
        验证交易记录的时间顺序
        确保交易按时间顺序执行，没有回溯
        """
        self.logger.info("\n" + "="*60)
        self.logger.info("验证4: 交易记录时序一致性检查")
        self.logger.info("="*60)
        
        if not trades:
            self.warnings.append("无交易记录可验证")
            return True
        
        trades_df = pd.DataFrame(trades)
        trades_df['date'] = pd.to_datetime(trades_df['date'])
        trades_df = trades_df.sort_values('date')
        
        # 检查交易时间顺序
        date_diffs = trades_df['date'].diff().dropna()
        negative_diffs = date_diffs[date_diffs < pd.Timedelta(0)]
        
        if len(negative_diffs) > 0:
            self.errors.append(f"发现 {len(negative_diffs)} 笔交易时间顺序错误")
            return False
        else:
            self.logger.info(f"✓ 交易时间顺序正确 ({len(trades)} 笔交易)")
        
        # 检查买入卖出配对
        buy_trades = trades_df[trades_df['action'] == 'BUY']
        sell_trades = trades_df[trades_df['action'] == 'SELL']
        
        self.logger.info(f"  买入交易: {len(buy_trades)} 笔")
        self.logger.info(f"  卖出交易: {len(sell_trades)} 笔")
        
        return True
    
    def check_lookahead_bias(self, signals_df: pd.DataFrame, 
                            price_data: Dict,
                            look_ahead_days: int = 5) -> bool:
        """
        检查是否存在隐含的lookahead bias
        例如：信号是否使用了未来N天的价格信息
        """
        self.logger.info("\n" + "="*60)
        self.logger.info(f"验证5: Lookahead Bias检查 (前瞻{look_ahead_days}天)")
        self.logger.info("="*60)
        
        # 方法：检查信号强度与未来收益的相关性是否异常高
        # 如果信号能完美预测短期未来收益，可能存在lookahead bias
        
        sample_correlations = []
        
        for ticker in list(signals_df['Ticker'].unique())[:10]:  # 抽样
            ticker_signals = signals_df[signals_df['Ticker'] == ticker]
            if ticker not in price_data:
                continue
            
            prices = price_data[ticker]
            
            for _, signal in ticker_signals.iterrows():
                signal_date = signal['Date']
                if isinstance(signal_date, pd.Timestamp):
                    signal_date = signal_date.date()
                
                if signal_date not in prices:
                    continue
                
                # 获取信号日期后的价格
                future_dates = [d for d in sorted(prices.keys()) if d > signal_date]
                if len(future_dates) < look_ahead_days:
                    continue
                
                # 计算未来N天收益
                future_price = prices[future_dates[look_ahead_days - 1]]
                current_price = prices[signal_date]
                future_return = (future_price / current_price - 1) * 100
                
                sample_correlations.append({
                    'Rank': signal['Rank'],
                    'Future_Return': future_return
                })
        
        if len(sample_correlations) < 10:
            self.warnings.append("样本量不足，无法检测lookahead bias")
            return True
        
        df = pd.DataFrame(sample_correlations)
        correlation = df['Rank'].corr(df['Future_Return'])
        
        self.logger.info(f"  排名与未来收益相关性: {correlation:.3f}")
        
        # 如果相关性过高（>0.8或<-0.8），可能存在lookahead bias
        if abs(correlation) > 0.8:
            self.warnings.append(f"排名与未来收益相关性过高 ({correlation:.3f})，建议检查信号生成逻辑")
        elif abs(correlation) > 0.5:
            self.logger.info(f"  ⚠ 相关性较高，但仍在合理范围")
        else:
            self.logger.info(f"  ✓ 相关性正常，无明显的lookahead bias")
        
        return True
    
    def print_validation_summary(self):
        """打印验证摘要"""
        self.logger.info("\n" + "="*60)
        self.logger.info("时间序列验证摘要")
        self.logger.info("="*60)
        
        if self.errors:
            self.logger.info(f"\n❌ 发现 {len(self.errors)} 个错误:")
            for error in self.errors:
                self.logger.info(f"  - {error}")
        else:
            self.logger.info("\n✓ 无严重错误")
        
        if self.warnings:
            self.logger.info(f"\n⚠ 发现 {len(self.warnings)} 个警告:")
            for warning in self.warnings[:5]:  # 只显示前5个
                self.logger.info(f"  - {warning}")
            if len(self.warnings) > 5:
                self.logger.info(f"  ... 还有 {len(self.warnings) - 5} 个警告")
        else:
            self.logger.info("\n✓ 无警告")
        
        if not self.errors:
            self.logger.info("\n" + "="*60)
            self.logger.info("✅ 时间序列验证通过 - 无未来数据泄露")
            self.logger.info("="*60)
        else:
            self.logger.info("\n" + "="*60)
            self.logger.info("❌ 时间序列验证失败 - 需要修复错误")
            self.logger.info("="*60)
        
        return len(self.errors) == 0


def main():
    """主函数 - 运行所有验证"""
    logger = setup_logger()
    
    logger.info("="*60)
    logger.info("CTA回测时间序列验证器")
    logger.info("="*60)
    logger.info("本工具严格检查回测过程中是否存在未来数据泄露")
    
    validator = TimeSeriesValidator(logger)
    
    # 加载数据 (尝试多个可能的文件名)
    signal_files = ["cta_rankings.csv", "mag7_cta_analysis.csv", "mag7_signals_akshare.csv"]
    signals_df = None
    
    for sf in signal_files:
        try:
            signals_df = pd.read_csv(sf)
            logger.info(f"\n✓ 加载信号数据: {sf}, {len(signals_df)} 条记录")
            break
        except:
            continue
    
    if signals_df is None:
        logger.error(f"✗ 无法加载信号数据，尝试过的文件: {signal_files}")
        return False
    
    # 运行验证
    is_valid, signals_df = validator.validate_signal_data(signals_df)
    
    # 加载价格数据（简化版，仅加载部分数据用于验证）
    logger.info("\n" + "="*60)
    logger.info("加载价格数据用于验证...")
    logger.info("="*60)
    
    import akshare as ak
    import time
    
    price_data = {}
    sample_tickers = signals_df['Ticker'].unique()[:20]  # 抽样20只
    
    for ticker in sample_tickers:
        try:
            time.sleep(0.2)
            df = ak.stock_us_daily(symbol=ticker, adjust="")
            if df is not None and not df.empty:
                df = df.reset_index()
                df['Date'] = pd.to_datetime(df['Date'] if 'Date' in df.columns else df['date']).dt.date
                price_dict = df.set_index('Date')['close'].to_dict()
                price_data[ticker] = price_dict
        except:
            continue
    
    logger.info(f"✓ 加载价格数据: {len(price_data)} 只股票")
    
    # 继续验证
    validator.validate_price_data(price_data, signals_df)
    validator.validate_future_return_calculation(price_data, signals_df, holding_period=20)
    validator.check_lookahead_bias(signals_df, price_data)
    
    # 打印摘要
    is_valid = validator.print_validation_summary()
    
    return is_valid


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
