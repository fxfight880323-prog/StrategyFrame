#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成投资分析报告 Excel版
"""

import pandas as pd
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows

# 创建Excel工作簿
wb = Workbook()

# 定义样式
header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
header_font = Font(color="FFFFFF", bold=True, size=12)
title_font = Font(bold=True, size=16)
subtitle_font = Font(bold=True, size=14)
alert_fill = PatternFill(start_color="FFE699", end_color="FFE699", fill_type="solid")
danger_fill = PatternFill(start_color="FF6B6B", end_color="FF6B6B", fill_type="solid")
success_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")

thin_border = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)

def add_title(ws, title, row=1):
    """添加标题"""
    ws.merge_cells(f'A{row}:F{row}')
    cell = ws.cell(row=row, column=1, value=title)
    cell.font = title_font
    cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[row].height = 30

def add_subtitle(ws, subtitle, row):
    """添加子标题"""
    ws.merge_cells(f'A{row}:F{row}')
    cell = ws.cell(row=row, column=1, value=subtitle)
    cell.font = subtitle_font
    cell.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[row].height = 25

def df_to_sheet(ws, df, start_row, header=True):
    """DataFrame写入工作表"""
    for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=header), start_row):
        for c_idx, value in enumerate(row, 1):
            cell = ws.cell(row=r_idx, column=c_idx, value=value)
            cell.border = thin_border
            if r_idx == start_row and header:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')

# ===== Sheet 1: 封面 =====
ws_cover = wb.active
ws_cover.title = "封面"

add_title(ws_cover, "投资策略分析报告", 2)
ws_cover.merge_cells('A4:F4')
ws_cover.cell(row=4, column=1, value="Investment Strategy Analysis Report").alignment = Alignment(horizontal='center')
ws_cover.cell(row=4, column=1).font = Font(size=14, italic=True, color="666666")

info_data = [
    ["", ""],
    ["报告日期", "2026年2月27日"],
    ["数据截止", "2026年2月27日"],
    ["分析框架", "自上而下7层决策体系"],
    ["生成时间", datetime.now().strftime('%Y-%m-%d %H:%M:%S')],
    ["", ""],
    ["执行摘要", ""],
    ["总执行时间", "26.7秒"],
    ["成功步骤", "7/7"],
    ["风险等级", "中等（需关注）"],
    ["整体建议", "谨慎乐观"],
]

for i, (label, value) in enumerate(info_data, start=7):
    if label:
        ws_cover.cell(row=i, column=2, value=label).font = Font(bold=True)
        ws_cover.cell(row=i, column=3, value=value)

# 调整列宽
ws_cover.column_dimensions['A'].width = 5
ws_cover.column_dimensions['B'].width = 20
ws_cover.column_dimensions['C'].width = 30

# ===== Sheet 2: 宏观分析 =====
ws_macro = wb.create_sheet("1-宏观分析")
add_subtitle(ws_macro, "美联储流动性状态", 1)

macro_data = pd.DataFrame({
    '指标': ['净流动性得分', '10Y TIPS', '综合判断'],
    '数值': ['-7', '1.77%', '流动性挤压 (Liquidity Squeeze)'],
    '判断': ['⚠️ 流动性紧缩', '实际利率偏高', '🔴 看空']
})
df_to_sheet(ws_macro, macro_data, 3)

ws_macro.cell(row=8, column=1, value="宏观结论").font = Font(bold=True, size=12)
ws_macro.merge_cells('A9:F9')
ws_macro.cell(row=9, column=1, value="流动性环境偏紧，建议控制仓位，增加防御性配置")
ws_macro.cell(row=9, column=1).fill = alert_fill

for col in range(1, 4):
    ws_macro.column_dimensions[chr(64+col)].width = 25

# ===== Sheet 3: 板块分析 =====
ws_sector = wb.create_sheet("2-板块分析")
add_subtitle(ws_sector, "CTA + 财报交叉分析", 1)

ws_sector.cell(row=3, column=1, value="分析日期: 2024-12-31 | 覆盖板块: 11个GICS行业板块")

sector_data = pd.DataFrame({
    '排名': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    '板块': ['Utilities', 'Technology', 'Financials', 'Consumer Disc', 'Industrials', 
             'Communication', 'Materials', 'Real Estate', 'Energy', 'Consumer Staples', 'Healthcare'],
    '得分': [20.40, 15.20, 12.50, 8.30, 5.60, 4.20, 3.10, 2.80, 1.50, 0.80, 0.10],
    '推荐度': ['超配', '超配', '标配', '标配', '标配', '标配', '标配', '标配', '标配', '低配', '低配'],
    '推荐标的': ['NEE,D,XEL', 'AAPL,MSFT', 'JPM,BAC', 'AMZN,LOW', 'CAT,GE', 
                'META,VZ', 'NUE,LIN', 'AMT,PLD', 'XOM,CVX', 'PG,KO', '回避UNH,LLY']
})
df_to_sheet(ws_sector, sector_data, 5)

# 高亮最佳/最差
for row in range(6, 17):
    rank = ws_sector.cell(row=row, column=1).value
    if rank == 1:
        for col in range(1, 6):
            ws_sector.cell(row=row, column=col).fill = success_fill
    elif rank == 11:
        for col in range(1, 6):
            ws_sector.cell(row=row, column=col).fill = danger_fill

for col in range(1, 6):
    ws_sector.column_dimensions[chr(64+col)].width = 18

# ===== Sheet 4: 风险管理 =====
ws_risk = wb.create_sheet("3-风险管理")
add_subtitle(ws_risk, "组合风控检查结果", 1)

risk_summary = pd.DataFrame({
    '指标': ['现金', '总市值', '保证金占用', '保证金比例', '风险等级'],
    '数值': ['500,000', '1,290,900', '181,500', '14.1%', '黄色'],
    '状态': ['✅', '-', '✅', '✅', '⚠️']
})
df_to_sheet(ws_risk, risk_summary, 3)

add_subtitle(ws_risk, "持仓明细", 10)

positions = pd.DataFrame({
    '品种': ['CU (铜)', 'RB (螺纹)', 'SC (原油)'],
    '方向': ['LONG', 'SHORT', 'LONG'],
    '手数': [10, 20, 5],
    '盈亏': ['+20,000', '+2,000', '+1,500'],
    '占比': ['55.8%', '10.9%', '4.5%']
})
df_to_sheet(ws_risk, positions, 12)

add_subtitle(ws_risk, "⚠️ 风险警告", 18)
ws_risk.cell(row=20, column=1, value="1. CU仓位超限: 55.8% > 10.0% (单品种最大仓位)")
ws_risk.cell(row=20, column=1).fill = danger_fill
ws_risk.cell(row=21, column=1, value="2. 金属板块超限: 55.8% > 30.0% (板块最大仓位)")
ws_risk.cell(row=21, column=1).fill = danger_fill

add_subtitle(ws_risk, "风控建议", 24)
advice = [
    "1. 减仓CU至10%以内",
    "2. 分散金属板块风险", 
    "3. 密切关注市场波动"
]
for i, text in enumerate(advice, start=26):
    ws_risk.cell(row=i, column=1, value=text)

for col in range(1, 6):
    ws_risk.column_dimensions[chr(64+col)].width = 20

# ===== Sheet 5: 综合结论 =====
ws_conclusion = wb.create_sheet("4-综合结论")
add_subtitle(ws_conclusion, "投资决策金字塔", 1)

pyramid_data = [
    ["层级", "模块", "状态"],
    ["Level 7", "报告输出", "✅ 完成"],
    ["Level 6", "回测验证", "⏭️ 跳过"],
    ["Level 5", "风险管理", "⚠️ 中等风险"],
    ["Level 4", "策略执行", "✅ CTA信号正常"],
    ["Level 3", "个股选择", "⚠️ 数据受限"],
    ["Level 2", "板块分析", "✅ 公用事业最佳"],
    ["Level 1", "宏观分析", "🔴 流动性紧缩"],
]

for i, row_data in enumerate(pyramid_data, start=3):
    for j, value in enumerate(row_data, start=1):
        cell = ws_conclusion.cell(row=i, column=j, value=value)
        cell.border = thin_border
        if i == 3:
            cell.fill = header_fill
            cell.font = header_font

add_subtitle(ws_conclusion, "投资建议评级", 13)

rating_data = pd.DataFrame({
    '维度': ['大盘环境', '板块机会', '个股选择', '风险控制'],
    '评级': ['⭐⭐ (2/5)', '⭐⭐⭐⭐ (4/5)', '⭐⭐ (2/5)', '⭐⭐⭐ (3/5)'],
    '说明': [
        '流动性紧缩，偏空',
        '公用事业有明确信号',
        '数据受限，建议观望',
        '有预警，需调整'
    ]
})
df_to_sheet(ws_conclusion, rating_data, 15)

add_subtitle(ws_conclusion, "操作建议", 22)
actions = [
    "1. 【短期策略】防御为主，超配公用事业",
    "2. 【仓位管理】减仓铜(CU)至合理水平",
    "3. 【风险对冲】考虑买入VIX期权对冲",
    "4. 【数据补充】手动获取Mag7最新数据"
]
for i, text in enumerate(actions, start=24):
    cell = ws_conclusion.cell(row=i, column=1, value=text)
    cell.fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")

for col in range(1, 4):
    ws_conclusion.column_dimensions[chr(64+col)].width = 30

# 保存文件
output_file = "投资分析报告_2026-02-27.xlsx"
wb.save(output_file)
print(f"[OK] Excel报告已生成: {output_file}")
