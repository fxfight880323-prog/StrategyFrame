"""
快速查看图表
==============
自动打开生成的可视化图表
"""

import os
import sys
import glob
from datetime import date

def find_latest_report():
    """找到最新的报告目录"""
    report_dirs = glob.glob("Report_*")
    if not report_dirs:
        return None
    
    # 按日期排序，取最新的
    report_dirs.sort(reverse=True)
    return report_dirs[0]

def main():
    print("="*60)
    print("策略可视化图表查看器")
    print("="*60)
    
    # 查找报告目录
    report_dir = find_latest_report()
    
    if report_dir is None:
        print("\n❌ 未找到报告目录")
        print("请先运行: python Strategy_Visualization.py")
        return
    
    charts_dir = os.path.join(report_dir, "charts")
    html_report = os.path.join(report_dir, "integrated_report.html")
    
    print(f"\n找到报告目录: {report_dir}")
    
    # 检查文件
    if os.path.exists(charts_dir):
        charts = [f for f in os.listdir(charts_dir) if f.endswith('.png')]
        print(f"✓ 图表文件: {len(charts)} 个")
        for chart in sorted(charts):
            print(f"  - {chart}")
    
    if os.path.exists(html_report):
        print(f"✓ HTML报告: {os.path.basename(html_report)}")
    
    # 询问打开方式
    print("\n" + "="*60)
    print("选择打开方式:")
    print("1. 打开图表目录")
    print("2. 打开HTML报告")
    print("3. 打开所有图表")
    print("4. 退出")
    print("="*60)
    
    try:
        choice = input("\n请输入选项 (1-4): ").strip()
    except:
        choice = "2"  # 默认打开HTML报告
    
    if choice == "1":
        print(f"\n打开目录: {charts_dir}")
        os.startfile(os.path.abspath(charts_dir))
        
    elif choice == "2":
        if os.path.exists(html_report):
            print(f"\n打开报告: {html_report}")
            os.startfile(os.path.abspath(html_report))
        else:
            print("\n❌ HTML报告不存在")
            
    elif choice == "3":
        if os.path.exists(charts_dir):
            for chart in sorted(charts):
                chart_path = os.path.join(charts_dir, chart)
                print(f"打开: {chart}")
                os.startfile(os.path.abspath(chart_path))
        
    else:
        print("\n退出")
        return
    
    print("\n✅ 完成")

if __name__ == "__main__":
    main()
