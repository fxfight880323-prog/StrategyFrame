#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
策略框架执行结果检查工具
用于验证每次运行后的输出结果
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List
import pandas as pd

# 设置编码
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

class ResultChecker:
    """结果检查器"""
    
    def __init__(self, check_date: str = None):
        self.check_date = check_date or datetime.now().strftime('%Y-%m-%d')
        self.base_dir = Path(__file__).parent
        self.results_dir = self.base_dir / "Results" / f"Report_{self.check_date}"
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        prefix = {"INFO": "  ", "PASS": "[OK]", "FAIL": "[FAIL]", "WARN": "[WARN]"}.get(level, "  ")
        print(f"{prefix} {message}")
    
    def check_file_exists(self, filename: str, required: bool = True) -> bool:
        """检查文件是否存在"""
        filepath = self.results_dir / filename
        if filepath.exists():
            self.log(f"文件存在: {filename}", "PASS")
            self.passed += 1
            return True
        else:
            if required:
                self.log(f"缺少文件: {filename}", "FAIL")
                self.failed += 1
            else:
                self.log(f"可选文件不存在: {filename}", "WARN")
                self.warnings += 1
            return False
    
    def check_directory_structure(self):
        """检查目录结构"""
        print("\n" + "="*60)
        print("检查目录结构")
        print("="*60)
        
        if not self.results_dir.exists():
            self.log(f"结果目录不存在: {self.results_dir}", "FAIL")
            self.failed += 1
            return False
        
        self.log(f"结果目录存在: {self.results_dir}", "PASS")
        self.passed += 1
        
        # 列出目录内容
        files = list(self.results_dir.iterdir())
        self.log(f"目录包含 {len(files)} 个文件/目录")
        
        return True
    
    def check_execution_log(self):
        """检查执行日志"""
        print("\n" + "="*60)
        print("检查执行日志")
        print("="*60)
        
        log_file = self.results_dir / "execution_log.txt"
        if not log_file.exists():
            self.log("execution_log.txt 不存在", "FAIL")
            self.failed += 1
            return
        
        # 读取日志内容
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        # 检查关键信息
        checks = [
            ("美联储流动性分析" in content, "美联储流动性分析记录"),
            ("CTA+财报板块分析" in content, "板块分析记录"),
            ("执行完成摘要" in content, "执行摘要记录"),
        ]
        
        for check, desc in checks:
            if check:
                self.log(f"找到: {desc}", "PASS")
                self.passed += 1
            else:
                self.log(f"缺失: {desc}", "WARN")
                self.warnings += 1
        
        # 统计成功/失败
        success_count = content.count("✅")
        fail_count = content.count("❌")
        
        self.log(f"执行统计: {success_count} 成功, {fail_count} 失败")
        
        if fail_count == 0:
            self.log("所有步骤执行成功", "PASS")
            self.passed += 1
        else:
            self.log(f"有 {fail_count} 个步骤失败", "WARN")
            self.warnings += 1
    
    def check_macro_results(self):
        """检查宏观分析结果"""
        print("\n" + "="*60)
        print("检查宏观分析结果")
        print("="*60)
        
        # 检查Excel文件
        excel_files = list(self.results_dir.glob("*liquidity*.xlsx"))
        if excel_files:
            self.log(f"流动性分析文件: {excel_files[0].name}", "PASS")
            self.passed += 1
        else:
            self.log("流动性分析文件不存在", "WARN")
            self.warnings += 1
    
    def check_sector_results(self):
        """检查板块分析结果"""
        print("\n" + "="*60)
        print("检查板块分析结果")
        print("="*60)
        
        # 检查CSV或Excel
        sector_files = list(self.results_dir.glob("*sector*.csv")) + list(self.results_dir.glob("*sector*.xlsx"))
        if sector_files:
            self.log(f"板块分析文件: {sector_files[0].name}", "PASS")
            self.passed += 1
        else:
            self.log("板块分析文件不存在（可能在父目录）", "WARN")
            self.warnings += 1
    
    def check_mag7_results(self):
        """检查Mag7分析结果"""
        print("\n" + "="*60)
        print("检查Mag7分析结果")
        print("="*60)
        
        mag7_files = list(self.results_dir.glob("*Mag7*.xlsx"))
        if mag7_files:
            self.log(f"Mag7分析文件: {mag7_files[0].name}", "PASS")
            self.passed += 1
            
            # 尝试读取Excel
            try:
                df = pd.read_excel(mag7_files[0], sheet_name='Signals')
                self.log(f"Mag7数据行数: {len(df)}", "PASS")
                self.passed += 1
                
                if 'Ticker' in df.columns:
                    tickers = df['Ticker'].tolist()
                    self.log(f"股票列表: {', '.join(tickers)}")
                
                if 'Signal' in df.columns:
                    signals = df['Signal'].value_counts().to_dict()
                    self.log(f"信号分布: {signals}")
                    
            except Exception as e:
                self.log(f"读取Mag7文件失败: {e}", "WARN")
                self.warnings += 1
        else:
            self.log("Mag7分析文件不存在", "WARN")
            self.warnings += 1
    
    def check_risk_results(self):
        """检查风险分析结果"""
        print("\n" + "="*60)
        print("检查风险管理结果")
        print("="*60)
        
        risk_files = list(self.results_dir.glob("*risk*.txt")) + list(self.results_dir.glob("*risk*.json"))
        if risk_files:
            self.log(f"风险报告文件: {risk_files[0].name}", "PASS")
            self.passed += 1
        else:
            self.log("风险报告文件不存在（输出可能在控制台）", "WARN")
            self.warnings += 1
    
    def check_weekly_report(self):
        """检查周报"""
        print("\n" + "="*60)
        print("检查周报")
        print("="*60)
        
        weekly_files = list(self.results_dir.glob("*weekly*.xlsx")) + list(self.results_dir.glob("*report*.xlsx"))
        parent_dir = self.results_dir.parent.parent  # Strategy_Framework
        weekly_in_parent = list(parent_dir.glob(f"Report_{self.check_date}/*.xlsx"))
        
        if weekly_files:
            self.log(f"周报文件: {weekly_files[0].name}", "PASS")
            self.passed += 1
        elif weekly_in_parent:
            self.log(f"周报在父目录: {weekly_in_parent[0].name}", "PASS")
            self.passed += 1
        else:
            self.log("周报文件不存在", "WARN")
            self.warnings += 1
    
    def generate_summary(self):
        """生成检查摘要"""
        print("\n" + "="*60)
        print("检查结果摘要")
        print("="*60)
        
        total = self.passed + self.failed + self.warnings
        
        print(f"\n检查日期: {self.check_date}")
        print(f"结果目录: {self.results_dir}")
        print(f"\n统计:")
        print(f"  通过: {self.passed}")
        print(f"  失败: {self.failed}")
        print(f"  警告: {self.warnings}")
        print(f"  总计: {total}")
        
        if self.failed == 0:
            print(f"\n[状态] 检查通过")
            if self.warnings > 0:
                print(f"[提示] 有 {self.warnings} 个警告，建议查看")
            return 0
        else:
            print(f"\n[状态] 检查失败，有 {self.failed} 个问题需要修复")
            return 1
    
    def run_all_checks(self):
        """运行所有检查"""
        print("\n" + "="*60)
        print("策略框架执行结果检查")
        print("="*60)
        print(f"检查日期: {self.check_date}")
        print(f"检查时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        self.check_directory_structure()
        self.check_execution_log()
        self.check_macro_results()
        self.check_sector_results()
        self.check_mag7_results()
        self.check_risk_results()
        self.check_weekly_report()
        
        return self.generate_summary()


def main():
    parser = argparse.ArgumentParser(description='策略框架执行结果检查')
    parser.add_argument('date', nargs='?', default=None, 
                        help='检查日期 (YYYY-MM-DD)，默认为今天')
    
    args = parser.parse_args()
    
    checker = ResultChecker(args.date)
    exit_code = checker.run_all_checks()
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
