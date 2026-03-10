"""
历史报告查看工具
===============
查看所有生成的周报和历史数据对比
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


def list_all_reports():
    """列出所有历史报告"""
    base_dir = Path(".")
    
    # 查找所有Report_开头的文件夹
    report_dirs = sorted([d for d in base_dir.iterdir() 
                         if d.is_dir() and d.name.startswith("Report_")])
    
    if not report_dirs:
        print("\n没有找到历史报告")
        return []
    
    print("\n" + "="*80)
    print("历史报告列表")
    print("="*80)
    print(f"\n{'序号':<6} {'日期':<12} {'报告文件夹':<25} {'状态':<10}")
    print("-"*80)
    
    for i, report_dir in enumerate(report_dirs, 1):
        date_str = report_dir.name.replace("Report_", "")
        
        # 检查报告完整性
        has_cta = (report_dir / "01_CTA技术分析.xlsx").exists()
        has_summary = list(report_dir.glob("周报摘要_*.md"))
        
        if has_cta and has_summary:
            status = "✅ 完整"
        elif has_cta:
            status = "⚠️ 部分"
        else:
            status = "❌ 缺失"
        
        print(f"{i:<6} {date_str:<12} {report_dir.name:<25} {status:<10}")
    
    print("-"*80)
    print(f"共找到 {len(report_dirs)} 份报告")
    print("="*80)
    
    return report_dirs


def view_report_detail(report_dir):
    """查看报告详情"""
    print(f"\n{'='*80}")
    print(f"报告详情: {report_dir.name}")
    print(f"{'='*80}")
    
    # 列出所有文件
    files = list(report_dir.rglob("*"))
    
    print(f"\n文件列表:")
    print("-"*80)
    
    for file in sorted(files):
        if file.is_file():
            rel_path = file.relative_to(report_dir)
            size = file.stat().st_size
            size_str = f"{size/1024:.1f} KB" if size > 1024 else f"{size} B"
            print(f"  {rel_path:<50} {size_str:>10}")
    
    print("-"*80)
    
    # 读取周报摘要
    summary_files = list(report_dir.glob("周报摘要_*.md"))
    if summary_files:
        print(f"\n周报摘要预览:")
        print("-"*80)
        with open(summary_files[0], 'r', encoding='utf-8') as f:
            content = f.read()
            # 只显示前1000字符
            print(content[:1000])
            if len(content) > 1000:
                print("\n... (内容已截断)")
        print("-"*80)


def compare_reports(report_dirs):
    """对比多份报告"""
    if len(report_dirs) < 2:
        print("\n需要至少2份报告才能对比")
        return
    
    print("\n" + "="*80)
    print("报告对比")
    print("="*80)
    
    # 读取最新的两份报告
    latest = report_dirs[-1]
    previous = report_dirs[-2]
    
    print(f"\n对比: {previous.name} vs {latest.name}")
    
    # 这里可以添加更多对比逻辑
    # 例如对比排名变化、信号变化等
    
    print("\n对比功能开发中...")
    print("="*80)


def open_report_folder(report_dir):
    """打开报告文件夹"""
    import subprocess
    
    print(f"\n正在打开文件夹: {report_dir.absolute()}")
    
    if sys.platform == 'win32':
        subprocess.run(['explorer', str(report_dir.absolute())])
    elif sys.platform == 'darwin':
        subprocess.run(['open', str(report_dir.absolute())])
    else:
        subprocess.run(['xdg-open', str(report_dir.absolute())])


def main():
    """主函数"""
    print("="*80)
    print("历史报告查看工具")
    print("="*80)
    
    while True:
        report_dirs = list_all_reports()
        
        if not report_dirs:
            input("\n按Enter退出...")
            break
        
        print("\n操作选项:")
        print("  [1-N] 输入序号查看详情")
        print("  [C]   对比最近两份报告")
        print("  [O]   打开文件夹")
        print("  [Q]   退出")
        print()
        
        choice = input("请输入选项: ").strip().upper()
        
        if choice == 'Q':
            break
        elif choice == 'C':
            compare_reports(report_dirs)
        elif choice == 'O':
            idx = input("请输入要打开的文件夹序号: ").strip()
            if idx.isdigit() and 1 <= int(idx) <= len(report_dirs):
                open_report_folder(report_dirs[int(idx)-1])
        elif choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(report_dirs):
                view_report_detail(report_dirs[idx-1])
                
                # 查看后询问是否打开
                open_choice = input("\n是否打开文件夹? (Y/N): ").strip().upper()
                if open_choice == 'Y':
                    open_report_folder(report_dirs[idx-1])
            else:
                print("\n无效序号")
        else:
            print("\n无效选项")
        
        input("\n按Enter继续...")
        print("\n" + "="*80)


if __name__ == "__main__":
    main()
