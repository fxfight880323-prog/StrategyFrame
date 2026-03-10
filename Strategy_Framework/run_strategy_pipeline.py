#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略框架自上而下运行管道
按照7层决策框架顺序执行分析

使用方法:
    python run_strategy_pipeline.py [日期] [选项]
    
参数:
    日期: YYYY-MM-DD 格式，默认为今天
    选项: --macro-only 仅运行宏观分析
          --sector-only 仅运行板块分析  
          --stock-only 仅运行个股选择
          --skip-backtest 跳过回测
          --skip-risk 跳过风险检查
"""

import os
import sys
import argparse
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

# 设置编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

class StrategyPipeline:
    """策略运行管道"""
    
    def __init__(self, run_date=None):
        self.run_date = run_date or datetime.now().strftime('%Y-%m-%d')
        self.base_dir = Path(__file__).parent
        self.results_dir = self.base_dir / "Results" / f"Report_{self.run_date}"
        self.log_file = self.results_dir / "execution_log.txt"
        
        # 创建结果目录
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        # 执行统计
        self.stats = {
            'start_time': datetime.now(),
            'steps': [],
            'errors': []
        }
    
    def log(self, message, level="INFO"):
        """记录日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        log_line = f"[{timestamp}] [{level}] {message}"
        print(log_line)
        
        # 写入日志文件
        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_line + '\n')
    
    def run_step(self, name, script_path, args=None, timeout=300):
        """运行单个步骤"""
        self.log(f"\n{'='*60}")
        self.log(f"开始执行: {name}")
        self.log(f"{'='*60}")
        
        start = time.time()
        step_info = {'name': name, 'start': datetime.now()}
        
        try:
            # 构建命令
            cmd = ['python', str(script_path)]
            if args:
                cmd.extend(args)
            
            # 运行脚本
            result = subprocess.run(
                cmd,
                cwd=str(self.base_dir),
                capture_output=True,
                timeout=timeout
            )
            
            # 处理输出编码
            try:
                stdout = result.stdout.decode('utf-8', errors='replace')
                stderr = result.stderr.decode('utf-8', errors='replace')
            except:
                stdout = str(result.stdout)
                stderr = str(result.stderr)
            
            elapsed = time.time() - start
            step_info['elapsed'] = elapsed
            
            if result.returncode == 0:
                self.log(f"✅ {name} 完成 (耗时: {elapsed:.1f}秒)")
                if stdout:
                    # 输出最后500字符
                    output = stdout[-500:] if len(stdout) > 500 else stdout
                    self.log(f"输出:\n{output}")
                step_info['status'] = 'SUCCESS'
            else:
                self.log(f"❌ {name} 失败 (耗时: {elapsed:.1f}秒)", "ERROR")
                self.log(f"错误: {stderr}", "ERROR")
                step_info['status'] = 'FAILED'
                step_info['error'] = stderr
                self.stats['errors'].append({'step': name, 'error': stderr})
            
            self.stats['steps'].append(step_info)
            return result.returncode == 0
            
        except subprocess.TimeoutExpired:
            self.log(f"⏱️ {name} 超时 ({timeout}秒)", "ERROR")
            step_info['status'] = 'TIMEOUT'
            self.stats['errors'].append({'step': name, 'error': 'Timeout'})
            self.stats['steps'].append(step_info)
            return False
        except Exception as e:
            self.log(f"💥 {name} 异常: {str(e)}", "ERROR")
            step_info['status'] = 'EXCEPTION'
            step_info['error'] = str(e)
            self.stats['errors'].append({'step': name, 'error': str(e)})
            self.stats['steps'].append(step_info)
            return False
    
    def run_macro_analysis(self):
        """Level 1: 宏观分析"""
        scripts = [
            ("美联储流动性分析", "01_Macro_Analysis/FedLiquidityAnalyzer.py"),
        ]
        
        for name, script in scripts:
            script_path = self.base_dir / script
            if script_path.exists():
                self.run_step(name, script_path, timeout=120)
            else:
                self.log(f"⚠️ 脚本不存在: {script}", "WARN")
    
    def run_sector_analysis(self):
        """Level 2: 板块分析"""
        scripts = [
            ("CTA+财报板块分析", "02_Sector_Analysis/CTA_Earnings_Sector_Analysis.py"),
        ]
        
        for name, script in scripts:
            script_path = self.base_dir / script
            if script_path.exists():
                self.run_step(name, script_path, args=[self.run_date], timeout=180)
            else:
                self.log(f"⚠️ 脚本不存在: {script}", "WARN")
    
    def run_stock_selection(self):
        """Level 3: 个股选择"""
        scripts = [
            ("Mag7科技巨头分析", "03_Stock_Selection/Mag7Tracker_Safe.py"),  # 使用安全版
            ("技术形态扫描", "03_Stock_Selection/TechnicalPatternAnalyzer.py"),
        ]
        
        for name, script in scripts:
            script_path = self.base_dir / script
            if script_path.exists():
                self.run_step(name, script_path, timeout=120)
            else:
                self.log(f"⚠️ 脚本不存在: {script}", "WARN")
    
    def run_strategy_execution(self):
        """Level 4: 策略执行"""
        scripts = [
            ("CTA策略信号", "04_Strategy_Execution/CTA_Strategies_CN_Futures.py"),
        ]
        
        for name, script in scripts:
            script_path = self.base_dir / script
            if script_path.exists():
                self.run_step(name, script_path, timeout=180)
            else:
                self.log(f"⚠️ 脚本不存在: {script}", "WARN")
    
    def run_risk_management(self):
        """Level 5: 风险管理"""
        scripts = [
            ("组合风险检查", "05_Risk_Management/CTA_Portfolio_Risk_System.py"),
        ]
        
        for name, script in scripts:
            script_path = self.base_dir / script
            if script_path.exists():
                self.run_step(name, script_path, timeout=120)
            else:
                self.log(f"⚠️ 脚本不存在: {script}", "WARN")
    
    def run_backtesting(self):
        """Level 6: 回测验证"""
        scripts = [
            ("策略绩效评估", "06_Backtesting/CTA_Strategy_Evaluator.py"),
        ]
        
        for name, script in scripts:
            script_path = self.base_dir / script
            if script_path.exists():
                self.run_step(name, script_path, timeout=300)
            else:
                self.log(f"⚠️ 脚本不存在: {script}", "WARN")
    
    def run_reporting(self):
        """Level 7: 报告输出"""
        scripts = [
            ("周报生成", "07_Reporting/WeeklyAutoReport.py"),
        ]
        
        for name, script in scripts:
            script_path = self.base_dir / script
            if script_path.exists():
                self.run_step(name, script_path, args=[self.run_date], timeout=180)
            else:
                self.log(f"⚠️ 脚本不存在: {script}", "WARN")
    
    def generate_summary(self):
        """生成执行摘要"""
        total_time = (datetime.now() - self.stats['start_time']).total_seconds()
        
        summary = f"""
{'='*60}
策略框架执行完成摘要
{'='*60}
执行日期: {self.run_date}
总耗时: {total_time:.1f}秒
执行步骤: {len(self.stats['steps'])}
成功: {sum(1 for s in self.stats['steps'] if s['status'] == 'SUCCESS')}
失败: {sum(1 for s in self.stats['steps'] if s['status'] != 'SUCCESS')}

各步骤详情:
"""
        for step in self.stats['steps']:
            status_icon = "✅" if step['status'] == 'SUCCESS' else "❌"
            elapsed = step.get('elapsed', 0)
            summary += f"  {status_icon} {step['name']}: {step['status']} ({elapsed:.1f}s)\n"
        
        if self.stats['errors']:
            summary += f"\n错误列表:\n"
            for err in self.stats['errors']:
                summary += f"  - {err['step']}: {err['error'][:100]}\n"
        
        summary += f"\n结果目录: {self.results_dir}\n"
        summary += f"{'='*60}\n"
        
        self.log(summary)
        
        # 保存摘要到文件
        summary_file = self.results_dir / "execution_summary.txt"
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write(summary)
    
    def run_full_pipeline(self, args):
        """运行完整管道"""
        self.log(f"""
{'='*60}
策略框架自上而下分析管道
{'='*60}
执行日期: {self.run_date}
结果目录: {self.results_dir}
{'='*60}
""")
        
        try:
            # Level 1: 宏观分析
            if not args.skip_macro:
                self.run_macro_analysis()
            
            # Level 2: 板块分析
            if not args.skip_sector:
                self.run_sector_analysis()
            
            # Level 3: 个股选择
            if not args.skip_stock:
                self.run_stock_selection()
            
            # Level 4: 策略执行
            if not args.skip_execution:
                self.run_strategy_execution()
            
            # Level 5: 风险管理
            if not args.skip_risk:
                self.run_risk_management()
            
            # Level 6: 回测验证
            if not args.skip_backtest:
                self.run_backtesting()
            
            # Level 7: 报告输出
            if not args.skip_report:
                self.run_reporting()
            
        except KeyboardInterrupt:
            self.log("\n⚠️ 用户中断执行", "WARN")
        finally:
            self.generate_summary()


def main():
    parser = argparse.ArgumentParser(
        description='策略框架自上而下运行管道',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python run_strategy_pipeline.py                    # 完整运行
  python run_strategy_pipeline.py 2026-02-28         # 指定日期
  python run_strategy_pipeline.py --macro-only       # 仅宏观分析
  python run_strategy_pipeline.py --skip-backtest    # 跳过回测
        """
    )
    
    parser.add_argument('date', nargs='?', default=None, 
                        help='运行日期 (YYYY-MM-DD)，默认为今天')
    parser.add_argument('--macro-only', action='store_true', 
                        help='仅运行宏观分析')
    parser.add_argument('--sector-only', action='store_true', 
                        help='仅运行板块分析')
    parser.add_argument('--stock-only', action='store_true', 
                        help='仅运行个股选择')
    parser.add_argument('--skip-macro', action='store_true', 
                        help='跳过宏观分析')
    parser.add_argument('--skip-sector', action='store_true', 
                        help='跳过板块分析')
    parser.add_argument('--skip-stock', action='store_true', 
                        help='跳过个股选择')
    parser.add_argument('--skip-execution', action='store_true', 
                        help='跳过策略执行')
    parser.add_argument('--skip-risk', action='store_true', 
                        help='跳过风险检查')
    parser.add_argument('--skip-backtest', action='store_true', 
                        help='跳过回测验证')
    parser.add_argument('--skip-report', action='store_true', 
                        help='跳过报告生成')
    
    args = parser.parse_args()
    
    # 处理互斥选项
    if args.macro_only:
        args.skip_sector = True
        args.skip_stock = True
        args.skip_execution = True
        args.skip_risk = True
        args.skip_backtest = True
        args.skip_report = True
    
    if args.sector_only:
        args.skip_macro = True
        args.skip_stock = True
        args.skip_execution = True
        args.skip_risk = True
        args.skip_backtest = True
        args.skip_report = True
    
    if args.stock_only:
        args.skip_macro = True
        args.skip_sector = True
        args.skip_execution = True
        args.skip_risk = True
        args.skip_backtest = True
        args.skip_report = True
    
    # 创建并运行管道
    pipeline = StrategyPipeline(args.date)
    pipeline.run_full_pipeline(args)


if __name__ == '__main__':
    main()
