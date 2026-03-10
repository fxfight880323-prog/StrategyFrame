#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成完整投资分析报告 Excel版
包含CTA打分和财报验证数据
"""

import pandas as pd
from datetime import datetime
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.chart import BarChart, Reference

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
neutral_fill = PatternFill(start_color="E7E6E6", end_color="E7E6E6", fill_type="solid")

thin_border = Border(
    left=Side(style='thin'),
    right=Side(style='thin'),
    top=Side(style='thin'),
    bottom=Side(style='thin')
)

def add_title(ws, title, row=1):
    ws.merge_cells(f'A{row}:G{row}')
    cell = ws.cell(row=row, column=1, value=title)
    cell.font = title_font
    cell.alignment = Alignment(horizontal='center', vertical='center')
    ws.row_dimensions[row].height = 30

def add_subtitle(ws, subtitle, row):
    ws.merge_cells(f'A{row}:G{row}')
    cell = ws.cell(row=row, column=1, value=subtitle)
    cell.font = subtitle_font
    cell.alignment = Alignment(horizontal='left', vertical='center')
    ws.row_dimensions[row].height = 25

def df_to_sheet(ws, df, start_row, header=True):
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
ws_cover.merge_cells('A4:G4')
ws_cover.cell(row=4, column=1, value="Investment Strategy Analysis Report").alignment = Alignment(horizontal='center')
ws_cover.cell(row=4, column=1).font = Font(size=14, italic=True, color="666666")

info_data = [
    ["", ""],
    ["报告日期", "2026年2月27日"],
    ["数据截止", "2026年2月27日"],
    ["分析框架", "自上而下7层决策体系 + CTA×财报交叉验证"],
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

ws_cover.column_dimensions['A'].width = 5
ws_cover.column_dimensions['B'].width = 20
ws_cover.column_dimensions['C'].width = 40

# ===== Sheet 2: CTA打分排名 =====
ws_cta = wb.create_sheet("CTA打分排名")
add_subtitle(ws_cta, "Mag7 CTA打分结果", 1)

cta_data = pd.DataFrame({
    '排名': [1, 2, 3, 4, 5, 6, 7],
    '股票': ['TSLA', 'AMZN', 'NVDA', 'META', 'MSFT', 'AAPL', 'GOOGL'],
    'CTA得分': [0.1862, 0.1844, 0.1822, 0.1791, 0.1778, 0.1775, 0.1756],
    '趋势强度': ['0.092', '0.069', '0.079', '0.062', '0.058', '0.057', '0.062'],
    '趋势信号': ['强势突破', '均值回归', '强势突破', '强势突破', '均值回归', '强势突破', '均值回归'],
    '操作建议': ['追涨做多', '逢低做多', '追涨做多', '追涨做多', '逢低做多', '追涨做多', '逢低做多'],
    '置信度': ['高', '高', '高', '高', '高', '高', '高']
})
df_to_sheet(ws_cta, cta_data, 3)

# 高亮前3名
for row in range(4, 11):
    rank = ws_cta.cell(row=row, column=1).value
    if rank and rank <= 3:
        for col in range(1, 8):
            ws_cta.cell(row=row, column=col).fill = success_fill

ws_cta.cell(row=12, column=1, value="CTA信号解读").font = Font(bold=True, size=12)
ws_cta.cell(row=13, column=1, value="强势突破 (Follow-through Long): 股价处于上升通道，可追涨")
ws_cta.cell(row=14, column=1, value="均值回归 (Mean-revert Setup): 股价超跌，等待反弹机会")

for col in range(1, 8):
    ws_cta.column_dimensions[chr(64+col)].width = 15

# ===== Sheet 3: 财报验证-AAPL =====
ws_aapl = wb.create_sheet("财报验证-AAPL")
add_subtitle(ws_aapl, "AAPL (苹果) 财报后价格走势验证", 1)

aapl_data = pd.DataFrame({
    '财报日期': ['2025-01-30', '2024-10-31', '2024-08-01'],
    'EPS惊喜': ['-6.1% (Miss)', '+0.5% (Inline)', '+20.3% (Beat)'],
    '跳空': ['-2.7%', '+0.7%', '+7.1%'],
    '日内': ['+1.4%', '+3.1%', '+2.3%'],
    '全天': ['-1.3%', '+3.9%', '+9.6%'],
    '信号得分': [-0.036, 0.011, 0.127],
    '验证结果': ['⚠️ 利空出尽', '✅ 符合预期', '✅ 强势上涨']
})
df_to_sheet(ws_aapl, aapl_data, 3)

ws_aapl.cell(row=8, column=1, value="验证结论").font = Font(bold=True, size=12)
ws_aapl.merge_cells('A9:G9')
ws_aapl.cell(row=9, column=1, value="历史财报显示，AAPL在业绩超预期后涨幅明显，但2025Q1业绩miss导致下跌。当前CTA得分0.1775(排名第6)，处于中等水平，建议观望。")
ws_aapl.cell(row=9, column=1).fill = alert_fill

for col in range(1, 8):
    ws_aapl.column_dimensions[chr(64+col)].width = 18

# ===== Sheet 4: 财报验证-NVDA =====
ws_nvda = wb.create_sheet("财报验证-NVDA")
add_subtitle(ws_nvda, "NVDA (英伟达) 财报后价格走势验证", 1)

nvda_data = pd.DataFrame({
    '财报日期': ['2025-02-26', '2024-11-20', '2024-08-28'],
    'EPS惊喜': ['+15.2% (Strong Beat)', '-11.1% (Miss)', '+9.7% (Beat)'],
    '跳空': ['-2.2%', '+2.9%', '+5.9%'],
    '日内': ['+3.0%', '+1.1%', '-0.8%'],
    '全天': ['+0.7%', '+4.0%', '+5.1%'],
    '信号得分': [0.075, -0.045, 0.065],
    '验证结果': ['⚠️ 利好出尽', '⚠️ 利空出尽', '✅ 上涨']
})
df_to_sheet(ws_nvda, nvda_data, 3)

ws_nvda.cell(row=8, column=1, value="验证结论").font = Font(bold=True, size=12)
ws_nvda.merge_cells('A9:G9')
ws_nvda.cell(row=9, column=1, value="NVDA近期出现'买预期卖事实'现象，2025Q1业绩超预期但股价高开低走。当前CTA得分0.1822(排名第3)，但需注意追高风险。")
ws_nvda.cell(row=9, column=1).fill = alert_fill

for col in range(1, 8):
    ws_nvda.column_dimensions[chr(64+col)].width = 18

# ===== Sheet 5: 板块分析 =====
ws_sector = wb.create_sheet("板块分析")
add_subtitle(ws_sector, "CTA + 财报交叉分析结果", 1)

sector_data = pd.DataFrame({
    '排名': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
    '板块': ['Utilities', 'Technology', 'Financials', 'Consumer Disc', 'Industrials', 
             'Communication', 'Materials', 'Real Estate', 'Energy', 'Consumer Staples', 'Healthcare'],
    '得分': [20.40, 15.20, 12.50, 8.30, 5.60, 4.20, 3.10, 2.80, 1.50, 0.80, 0.10],
    'CTA趋势': ['强势', '震荡', '上升', '震荡', '上升', '下降', '震荡', '下降', '震荡', '下降', '下降'],
    '财报': ['稳定', '分化', '超预期', '偏弱', '稳定', '分化', '偏弱', '偏弱', '偏弱', '偏弱', 'miss'],
    '推荐度': ['超配', '标配', '标配', '标配', '标配', '标配', '标配', '低配', '低配', '低配', '低配'],
    '推荐标的': ['NEE,D,XEL', 'AAPL,MSFT', 'JPM,BAC', 'AMZN,LOW', 'CAT,GE', 
                'META,VZ', 'NUE,LIN', 'AMT,PLD', 'XOM,CVX', 'PG,KO', '回避UNH,LLY']
})
df_to_sheet(ws_sector, sector_data, 3)

# 高亮最佳/最差
for row in range(4, 15):
    rank = ws_sector.cell(row=row, column=1).value
    if rank == 1:
        for col in range(1, 8):
            ws_sector.cell(row=row, column=col).fill = success_fill
    elif rank == 11:
        for col in range(1, 8):
            ws_sector.cell(row=row, column=col).fill = danger_fill

for col in range(1, 8):
    ws_sector.column_dimensions[chr(64+col)].width = 16

# ===== Sheet 6: 风险管理 =====
ws_risk = wb.create_sheet("风险管理")
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
    '占比': ['55.8%', '10.9%', '4.5%'],
    '风险状态': ['🔴 超限', '✅ 正常', '✅ 正常']
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

for col in range(1, 7):
    ws_risk.column_dimensions[chr(64+col)].width = 18

# ===== Sheet 7: 综合结论 =====
ws_conclusion = wb.create_sheet("综合结论")
add_subtitle(ws_conclusion, "CTA×财报交叉信号汇总", 1)

summary_data = pd.DataFrame({
    '层级': ['宏观', '板块', '个股', '技术'],
    '信号': ['流动性紧缩', '公用事业领先', 'TSLA/AMZN/NVDA', '趋势向上'],
    '权重': ['20%', '30%', '30%', '20%'],
    '得分': ['-7', '+20.40', '0.18+', '-'],
    '结论': ['🔴 看空', '🟢 看多', '🟢 看多', '🟡 中性']
})
df_to_sheet(ws_conclusion, summary_data, 3)

ws_conclusion.cell(row=9, column=1, value="加权总分").font = Font(bold=True, size=12)
ws_conclusion.cell(row=9, column=2, value="+0.05 (略微偏多)")

add_subtitle(ws_conclusion, "投资建议评级", 12)

rating_data = pd.DataFrame({
    '维度': ['大盘环境', '板块机会', '个股选择', '风险控制'],
    '评级': ['⭐⭐ (2/5)', '⭐⭐⭐⭐ (4/5)', '⭐⭐⭐ (3/5)', '⭐⭐⭐ (3/5)'],
    '说明': [
        '流动性紧缩，偏空',
        '公用事业有明确信号',
        'TSLA/AMZN/NVDA信号强',
        '有预警，需调整'
    ]
})
df_to_sheet(ws_conclusion, rating_data, 14)

add_subtitle(ws_conclusion, "操作建议", 21)
actions = [
    "【立即执行】",
    "1. 减仓铜(CU)至10%以内",
    "2. 超配公用事业 (NEE, D, XEL)",
    "",
    "【短期策略】",
    "3. TSLA: CTA排名第1，可追涨（控制仓位）",
    "4. AMZN: CTA排名第2，业绩miss后超跌反弹机会",
    "5. NVDA: CTA排名第3，注意'买预期卖事实'风险",
    "",
    "【风险对冲】",
    "6. 考虑买入VIX期权对冲尾部风险"
]
for i, text in enumerate(actions, start=23):
    cell = ws_conclusion.cell(row=i, column=1, value=text)
    if text.startswith('【'):
        cell.font = Font(bold=True)
        cell.fill = neutral_fill

for col in range(1, 4):
    ws_conclusion.column_dimensions[chr(64+col)].width = 35

# 保存文件
output_file = "投资分析报告_完整版_2026-02-27.xlsx"
wb.save(output_file)
print(f"[OK] Excel报告已生成: {output_file}")
