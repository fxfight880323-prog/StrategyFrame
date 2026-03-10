"""
美股周报自动化系统
==================
每周一早上自动运行：
1. CTA技术分析选股
2. 财报预期分析
3. 美联储流动性分析
4. 回测验证
5. 生成周报并保存到日期文件夹

使用方法:
1. 手动运行: python WeeklyAutoReport.py
2. 定时任务: 每周一早上8:00自动运行
"""

import sys
import os
import shutil
import logging
from datetime import date, datetime, timedelta
from pathlib import Path
import subprocess

# 设置日期
if len(sys.argv) > 1:
    RUN_DATE = sys.argv[1]  # 可以从命令行传入日期
else:
    RUN_DATE = date.today().strftime("%Y-%m-%d")

# 创建以日期命名的文件夹
OUTPUT_BASE_DIR = "."
REPORT_DIR = os.path.join(OUTPUT_BASE_DIR, f"Report_{RUN_DATE}")

# 确保文件夹存在
os.makedirs(REPORT_DIR, exist_ok=True)
os.makedirs(os.path.join(REPORT_DIR, "data"), exist_ok=True)
os.makedirs(os.path.join(REPORT_DIR, "charts"), exist_ok=True)

# 设置日志
LOG_FILE = os.path.join(REPORT_DIR, f"run_log_{RUN_DATE}.txt")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


def run_script(script_name, description):
    """运行子脚本并捕获输出"""
    logger.info(f"\n{'='*60}")
    logger.info(f"开始执行: {description}")
    logger.info(f"{'='*60}")
    
    try:
        # 运行脚本并捕获输出
        result = subprocess.run(
            [sys.executable, script_name],
            capture_output=True,
            text=True,
            timeout=600  # 10分钟超时
        )
        
        # 记录输出
        if result.stdout:
            logger.info(result.stdout)
        if result.stderr:
            logger.error(result.stderr)
        
        # 检查返回码
        if result.returncode == 0:
            logger.info(f"✅ {description} 执行成功")
            return True
        else:
            logger.error(f"❌ {description} 执行失败 (返回码: {result.returncode})")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"⏰ {description} 执行超时")
        return False
    except Exception as e:
        logger.error(f"💥 {description} 执行异常: {e}")
        return False


def move_files_to_report_dir():
    """将生成的文件移动到报告目录"""
    logger.info(f"\n{'='*60}")
    logger.info("整理报告文件...")
    logger.info(f"{'='*60}")
    
    files_to_move = {
        # CTA分析文件
        "mag7_cta_analysis.xlsx": "01_CTA技术分析.xlsx",
        "mag7_cta_analysis.csv": "data/cta_rankings.csv",
        "cta_rankings.csv": "data/cta_rankings.csv",
        
        # 财报分析文件
        "us_stocks_earnings_expectation.xlsx": "02_财报预期分析.xlsx",
        "us_stocks_earnings_expectation.csv": "data/earnings_expectation.csv",
        "expectation_analysis.csv": "data/expectation_analysis.csv",
        "summary.csv": "data/summary.csv",
        
        # 美联储流动性文件
        "fed_liquidity_analysis.xlsx": "03_美联储流动性分析.xlsx",
        "net_liquidity.csv": "data/net_liquidity.csv",
        
        # 期权策略文件
        "options_earnings_analysis.xlsx": "04_财报期权策略分析.xlsx",
        "options_analysis.csv": "data/options_analysis.csv",
        
        # 回测文件
        "cta_backtest_results.csv": "data/backtest_results.csv",
        
        # 综合分析文件
        "integrated_strategy_analysis.xlsx": "05_CTA财报综合分析.xlsx",
    }
    
    moved_count = 0
    for source, target in files_to_move.items():
        if os.path.exists(source):
            target_path = os.path.join(REPORT_DIR, target)
            try:
                shutil.move(source, target_path)
                logger.info(f"✅ 移动: {source} -> {target}")
                moved_count += 1
            except Exception as e:
                logger.error(f"❌ 移动失败 {source}: {e}")
        else:
            logger.warning(f"⚠️ 文件不存在: {source}")
    
    logger.info(f"\n共移动 {moved_count} 个文件到 {REPORT_DIR}")
    return moved_count


def generate_summary_report():
    """生成周报摘要"""
    logger.info(f"\n{'='*60}")
    logger.info("生成周报摘要...")
    logger.info(f"{'='*60}")
    
    summary_file = os.path.join(REPORT_DIR, f"周报摘要_{RUN_DATE}.md")
    
    # 读取CTA排名数据
    cta_file = os.path.join(REPORT_DIR, "data", "cta_rankings.csv")
    
    summary_content = f"""# 美股周报摘要 - {RUN_DATE}

## 📅 报告日期
- **生成时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- **数据截止日期**: {RUN_DATE}

## 📊 本周市场概况

### CTA技术分析信号分布
- **看涨(BUY)**: 待生成
- **中性(HOLD)**: 待生成  
- **看跌(SELL)**: 待生成

### 美联储流动性环境
- **净流动性**: 待生成
- **政策环境**: 待生成

### 财报季动态
- **本周公布财报**: 待生成
- **超预期个股**: 待生成

### 财报期权策略
- **卖波动机会**: 待生成 (IV高+市场预期过高)
- **买波动机会**: 待生成 (市场预期过低)
- **高风险标的**: NVDA等，谨慎卖波动

## 🎯 本周重点推荐

### 强烈看涨 (Top 5)
1. 待生成
2. 待生成
3. 待生成
4. 待生成
5. 待生成

### 建议回避 (Bottom 5)
1. 待生成
2. 待生成
3. 待生成
4. 待生成
5. 待生成

## 💼 持仓建议更新

### 当前推荐配置
- **核心持仓(60%)**: 
  - NVDA (AI芯片龙头)
  - TSM (代工龙头)
  - ASML (设备龙头)
- **卫星持仓(30%)**: 
  - 待更新
- **现金(10%)**: 保留灵活性

## ⚠️ 风险提示
1. 美联储政策不确定性
2. 地缘政治风险
3. 科技股估值压力

## 📁 详细数据
详细分析数据请查看:
- `01_CTA技术分析.xlsx` - CTA选股排名
- `02_财报预期分析.xlsx` - 财报预期数据
- `03_美联储流动性分析.xlsx` - 宏观流动性
- `04_财报期权策略分析.xlsx` - 期权交易策略
- `05_CTA财报综合分析.xlsx` - 技术面+基本面交叉分析
- `data/` 文件夹 - 原始数据CSV

---
*本报告由自动化系统生成，仅供参考，不构成投资建议。*
"""
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write(summary_content)
    
    logger.info(f"✅ 周报摘要已生成: {summary_file}")
    return summary_file


def create_readme():
    """创建README说明文件"""
    readme_file = os.path.join(REPORT_DIR, "README.txt")
    
    readme_content = f"""美股周报自动化报告 - {RUN_DATE}
================================

📁 文件说明:
------------

📊 Excel报告:
- 01_CTA技术分析.xlsx       - CTA技术指标选股排名
- 02_财报预期分析.xlsx       - 财报披露后市场反应分析
- 03_美联储流动性分析.xlsx   - 宏观流动性环境分析
- 04_财报期权策略分析.xlsx   - 期权交易策略
- 05_CTA财报综合分析.xlsx   - 技术面+基本面交叉策略

📄 数据文件 (data/):
- cta_rankings.csv          - CTA排名原始数据
- expectation_analysis.csv  - 财报分析原始数据
- net_liquidity.csv         - 流动性数据

📈 图表文件 (charts/):
- 待生成

📋 报告文件:
- 周报摘要_{RUN_DATE}.md     - 本周市场摘要
- run_log_{RUN_DATE}.txt     - 运行日志

🎯 使用建议:
------------
1. 先看"05_CTA财报综合分析"获取交叉策略信号
2. 打开"01_CTA技术分析.xlsx"查看选股排名
3. 查看"周报摘要"了解本周重点
4. 参考"02_财报预期分析"调整持仓
5. 结合"03_美联储流动性"判断宏观环境
6. 财报季参考"04_期权策略分析"

⚠️ 免责声明:
------------
本报告仅供参考，不构成投资建议。
投资有风险，入市需谨慎。

🔄 自动化信息:
--------------
- 生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
- 数据日期: {RUN_DATE}
- 下次运行: 下周一早上8:00

有问题请联系系统管理员。
"""
    
    with open(readme_file, 'w', encoding='utf-8') as f:
        f.write(readme_content)
    
    logger.info(f"✅ README已生成: {readme_file}")


def send_notification():
    """发送完成通知(可选)"""
    logger.info(f"\n{'='*60}")
    logger.info("发送完成通知...")
    logger.info(f"{'='*60}")
    
    # 这里可以集成邮件、钉钉、企业微信等通知
    # 示例: 生成一个通知文件
    notification_file = os.path.join(REPORT_DIR, "notification.txt")
    with open(notification_file, 'w', encoding='utf-8') as f:
        f.write(f"美股周报已生成 - {RUN_DATE}\n")
        f.write(f"报告路径: {os.path.abspath(REPORT_DIR)}\n")
        f.write(f"请查看周报摘要和投资建议\n")
    
    logger.info(f"✅ 通知文件已生成")


def main():
    """主函数"""
    logger.info("="*60)
    logger.info("美股周报自动化系统")
    logger.info(f"运行日期: {RUN_DATE}")
    logger.info(f"报告目录: {REPORT_DIR}")
    logger.info("="*60)
    
    start_time = datetime.now()
    
    # 执行各个分析模块
    results = {}
    
    # 1. CTA技术分析
    results['CTA'] = run_script("Mag7CTAAnalyzer.py", "CTA技术分析")
    
    # 2. 财报预期分析 (使用已有数据)
    if os.path.exists("Mag7Tracker_EarningsExpectation.py"):
        results['Earnings'] = run_script("Mag7Tracker_EarningsExpectation.py", "财报预期分析")
    else:
        logger.warning("财报分析模块不存在，跳过")
    
    # 3. 美联储流动性分析
    if os.path.exists("FedLiquidityAnalyzer.py"):
        results['Fed'] = run_script("FedLiquidityAnalyzer.py", "美联储流动性分析")
    else:
        logger.warning("流动性分析模块不存在，跳过")
    
    # 4. 财报期权策略分析
    if os.path.exists("OptionsEarningsAnalyzer.py"):
        results['Options'] = run_script("OptionsEarningsAnalyzer.py", "财报期权策略分析")
    else:
        logger.warning("期权分析模块不存在，跳过")
    
    # 5. 回测验证
    if os.path.exists("CTABacktester.py"):
        results['Backtest'] = run_script("CTABacktester.py", "回测验证")
    else:
        logger.warning("回测模块不存在，跳过")
    
    # 整理文件
    move_files_to_report_dir()
    
    # 生成摘要
    generate_summary_report()
    
    # 创建README
    create_readme()
    
    # 发送通知
    send_notification()
    
    # 完成统计
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    logger.info(f"\n{'='*60}")
    logger.info("周报生成完成！")
    logger.info(f"{'='*60}")
    logger.info(f"运行时间: {duration:.1f} 秒")
    logger.info(f"报告目录: {os.path.abspath(REPORT_DIR)}")
    logger.info(f"模块执行结果:")
    for module, success in results.items():
        status = "✅ 成功" if success else "❌ 失败"
        logger.info(f"  - {module}: {status}")
    logger.info(f"\n请查看 {REPORT_DIR} 文件夹获取完整报告")
    logger.info("="*60)


if __name__ == "__main__":
    main()
