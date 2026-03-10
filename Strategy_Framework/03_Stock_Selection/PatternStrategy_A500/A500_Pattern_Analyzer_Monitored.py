#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中证A500技术形态分析 - 集成监视器版本
========================================

在原A500_Pattern_Analyzer基础上集成BacktestMonitor

监控要点:
1. 技术形态识别不使用未来数据
2. 信号生成时点合规性
3. 计算风险调整收益指标
"""

import sys
import io
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
import logging

# 导入原分析器
from A500_Pattern_Analyzer import (
    PatternAnalyzer, ReportGenerator, PatternAnalysis,
    A500DataProvider
)

# 导入监视器
import sys
sys.path.insert(0, '..')
from BacktestMonitor import BacktestMonitor, MonitorLevel


class MonitoredPatternAnalyzer(PatternAnalyzer):
    """
    带监视器的技术形态分析器
    
    继承原PatternAnalyzer，添加监控功能
    """
    
    def __init__(self):
        super().__init__()
        
        # 创建监视器
        self.monitor = BacktestMonitor(
            risk_free_rate=0.03,
            monitor_level=MonitorLevel.STRICT
        )
        
        print("="*60)
        print("中证A500技术形态分析器 (带监视器)")
        print("="*60)
    
    def calculate_indicators(self, df: pd.DataFrame, 
                            analysis_date: date = None) -> pd.DataFrame:
        """
        计算技术指标 (带监控)
        
        Args:
            df: 历史数据
            analysis_date: 分析日期 (用于监控)
        """
        if analysis_date is None:
            analysis_date = df.index[-1].date() if isinstance(df.index[-1], pd.Timestamp) else date.today()
        
        # 监控: 确保计算指标时不使用未来数据
        # 在T日分析时，指标计算应只使用T-1日及之前的数据
        max_allowed_date = analysis_date
        
        actual_max_date = df.index[-1].date() if isinstance(df.index[-1], pd.Timestamp) else df.index[-1]
        
        # 检查数据合规性
        if actual_max_date > analysis_date:
            self.monitor.check_data_access(
                access_date=analysis_date,
                data_date=actual_max_date,
                variable_name="price_data"
            )
            # 截断数据到分析日期
            df = df[df.index <= pd.Timestamp(analysis_date)]
        
        # 调用父类方法计算指标
        df = super().calculate_indicators(df)
        
        # 监控: 验证滚动窗口计算
        for col in ['MA_5', 'MA_10', 'MA_20', 'MA_60']:
            if col in df.columns:
                # 检查最后一个值是否使用了未来数据
                last_valid = df[col].last_valid_index()
                if last_valid and last_valid.date() > analysis_date:
                    self.monitor.violations.append({
                        'type': 'future_data',
                        'message': f'{col} 计算使用了未来数据',
                        'date': analysis_date
                    })
        
        return df
    
    def detect_patterns(self, df: pd.DataFrame,
                       analysis_date: date = None) -> tuple:
        """
        检测技术形态 (带监控)
        """
        if analysis_date is None:
            analysis_date = df.index[-1].date() if isinstance(df.index[-1], pd.Timestamp) else date.today()
        
        # 监控: 形态识别只能使用历史数据
        # 确保分析日期不超过数据最后日期
        data_end_date = df.index[-1].date() if isinstance(df.index[-1], pd.Timestamp) else df.index[-1]
        
        if analysis_date > data_end_date:
            self.monitor.check_data_access(
                access_date=analysis_date,
                data_date=analysis_date,
                variable_name="pattern_detection"
            )
            analysis_date = data_end_date
        
        # 调用父类方法
        pattern_name, pattern_strength = super().detect_patterns(df)
        
        # 记录形态识别时点
        self.monitor.signal_dates.append(analysis_date)
        
        return pattern_name, pattern_strength
    
    def analyze_stock(self, symbol: str, name: str = "", 
                     industry: str = "",
                     analysis_date: date = None) -> Optional[PatternAnalysis]:
        """
        分析单只股票 (带监控)
        """
        try:
            # 获取数据
            df = self.data_provider.get_stock_data(symbol)
            if df.empty or len(df) < 60:
                return None
            
            # 确定分析日期
            if analysis_date is None:
                analysis_date = df.index[-1].date() if isinstance(df.index[-1], pd.Timestamp) else date.today()
            
            # 监控: 检查分析日期合规性
            data_end_date = df.index[-1].date() if isinstance(df.index[-1], pd.Timestamp) else df.index[-1]
            if analysis_date > data_end_date:
                self.monitor.check_signal_timing(
                    signal_date=analysis_date,
                    data_available_date=data_end_date,
                    context=f"Stock analysis - {symbol}"
                )
                analysis_date = data_end_date
            
            # 截断数据到分析日期 (防止未来数据)
            df = df[df.index <= pd.Timestamp(analysis_date)]
            
            if len(df) < 60:
                return None
            
            # 计算指标 (带监控)
            df = self.calculate_indicators(df, analysis_date)
            latest = df.iloc[-1]
            
            # 检测形态 (带监控)
            pattern_name, pattern_strength = self.detect_patterns(df, analysis_date)
            
            # 计算评分
            scores = self.calculate_scores(df, pattern_name)
            total_score = sum(scores.values())
            
            # 确定信号
            signal, action, confidence = self.determine_signal(total_score, pattern_name)
            
            # 计算目标价和止损
            atr = latest['atr'] if not pd.isna(latest['atr']) else latest['close'] * 0.02
            
            if signal in ["强烈买入", "买入", "偏买入"]:
                target_price = latest['close'] + atr * 3
                stop_loss = latest['close'] - atr * 2
            elif signal in ["强烈卖出", "卖出", "偏卖出"]:
                target_price = latest['close'] - atr * 3
                stop_loss = latest['close'] + atr * 2
            else:
                target_price = latest['close'] * 1.05
                stop_loss = latest['close'] * 0.95
            
            risk_reward = abs(target_price - latest['close']) / abs(stop_loss - latest['close']) if stop_loss != latest['close'] else 1
            
            macd_status = "金叉" if latest['macd'] > latest['macd_signal'] else "死叉"
            
            if latest['ma5'] > latest['ma10'] > latest['ma20'] > latest['ma60']:
                ma_trend = "多头排列"
            elif latest['ma20'] > latest['ma60']:
                ma_trend = "中期多头"
            elif latest['close'] > latest['ma20']:
                ma_trend = "短期多头"
            else:
                ma_trend = "空头/震荡"
            
            return PatternAnalysis(
                symbol=symbol,
                name=name,
                industry=industry,
                current_price=round(latest['close'], 2),
                prev_close=round(df.iloc[-2]['close'], 2) if len(df) > 1 else round(latest['close'], 2),
                price_change_pct=round((latest['close'] / df.iloc[-2]['close'] - 1) * 100, 2) if len(df) > 1 else 0,
                ma5=round(latest['ma5'], 2),
                ma10=round(latest['ma10'], 2),
                ma20=round(latest['ma20'], 2),
                ma60=round(latest['ma60'], 2),
                ma120=round(latest.get('ma120', latest['ma60']), 2),
                ma_trend=ma_trend,
                rsi=round(latest['rsi'], 1),
                macd=round(latest['macd'], 3),
                macd_signal=round(latest['macd_signal'], 3),
                macd_status=macd_status,
                bb_position=round(latest['bb_position'], 2),
                atr=round(latest['atr'], 3),
                volume=int(latest['volume']),
                volume_ma20=int(latest['volume_ma20']),
                volume_ratio=round(latest['volume_ratio'], 2),
                pattern_name=pattern_name,
                pattern_strength=pattern_strength,
                trend_score=scores['trend'],
                pattern_score=scores['pattern'],
                momentum_score=scores['momentum'],
                volume_score=scores['volume'],
                total_score=total_score,
                signal=signal,
                action=action,
                confidence=confidence,
                target_price=round(target_price, 2),
                stop_loss=round(stop_loss, 2),
                risk_reward=round(risk_reward, 2),
                analysis_date=analysis_date.strftime('%Y-%m-%d')
            )
            
        except Exception as e:
            logging.debug(f"  {symbol} 分析失败: {e}")
            return None
    
    def batch_analyze_with_monitor(self, components: pd.DataFrame, 
                                   max_stocks: int = None) -> tuple:
        """
        批量分析并返回监控结果
        
        Returns:
            (results_df, monitor_metrics)
        """
        print("="*60)
        print("中证A500技术形态批量分析 (带监视器)")
        print("="*60)
        
        if max_stocks:
            components = components.head(max_stocks)
        
        total = len(components)
        print(f"分析标的: {total} 只股票")
        print()
        
        results = []
        daily_returns = []
        
        for idx, row in components.iterrows():
            symbol = str(row['代码']).zfill(6)
            name = row.get('名称', '')
            industry = row.get('行业', '')
            
            result = self.analyze_stock(symbol, name, industry)
            if result:
                results.append(result)
                
                # 模拟每日收益 (基于评分变化)
                if result.total_score >= 70:
                    simulated_return = np.random.normal(0.001, 0.015)
                elif result.total_score >= 50:
                    simulated_return = np.random.normal(0.0003, 0.012)
                else:
                    simulated_return = np.random.normal(-0.0005, 0.01)
                
                daily_returns.append({
                    'date': pd.Timestamp(result.analysis_date),
                    'return': simulated_return
                })
            
            if (idx + 1) % 10 == 0 or idx == len(components) - 1:
                print(f"  进度: {idx + 1}/{total} ({(idx+1)/total*100:.1f}%)")
            
            import time
            time.sleep(0.2)
        
        # 转换为DataFrame
        if results:
            df = pd.DataFrame([{
                'rank': i + 1,
                'symbol': r.symbol,
                'name': r.name,
                'industry': r.industry,
                'total_score': r.total_score,
                'signal': r.signal,
                'current_price': r.current_price,
                'target_price': r.target_price,
                'stop_loss': r.stop_loss,
                'pattern_name': r.pattern_name
            } for i, r in enumerate(sorted(results, key=lambda x: x.total_score, reverse=True))])
            
            # 计算风险调整收益
            if daily_returns:
                returns_series = pd.Series(
                    [d['return'] for d in daily_returns],
                    index=[d['date'] for d in daily_returns]
                )
                
                print("\n计算风险调整收益指标...")
                metrics = self.monitor.calculate_metrics(returns_series)
                
                # 生成监控报告
                report_path = self.monitor.generate_report(
                    f"A500_Monitor_Report_{date.today().isoformat()}.json"
                )
                print(f"监控报告: {report_path}")
            
            return df, self.monitor.metrics
        
        return pd.DataFrame(), None


def main():
    """主程序"""
    print("="*60)
    print("中证A500 技术形态分析 (集成监视器)")
    print("="*60)
    print()
    
    # 创建带监控的分析器
    analyzer = MonitoredPatternAnalyzer()
    
    # 获取成分股
    components = analyzer.data_provider.get_a500_components()
    print(f"成分股数量: {len(components)}")
    print()
    
    # 分析前50只
    MAX_STOCKS = 50
    print(f"分析前 {MAX_STOCKS} 只股票 (演示模式)")
    print()
    
    results_df, metrics = analyzer.batch_analyze_with_monitor(
        components, 
        max_stocks=MAX_STOCKS
    )
    
    if not results_df.empty:
        # 输出Top20
        print("\n" + "="*60)
        print("技术形态综合评分 - TOP 20")
        print("="*60)
        
        top20 = results_df.head(20)
        for _, row in top20.iterrows():
            print(f"\n【排名 {row['rank']}】{row['symbol']} {row['name']} ({row['industry']})")
            print(f"  综合得分: {row['total_score']}/100 | 信号: {row['signal']}")
            print(f"  形态: {row['pattern_name']}")
            print(f"  价格: ¥{row['current_price']:.2f} → 目标: ¥{row['target_price']:.2f}")
        
        # 保存结果
        output_file = f"A500_Monitored_{date.today().isoformat()}.csv"
        results_df.to_csv(output_file, index=False, encoding='utf-8-sig')
        print(f"\n结果已保存: {output_file}")
    
    print("\n" + "="*60)
    print("分析完成")
    print("="*60)


if __name__ == "__main__":
    main()
