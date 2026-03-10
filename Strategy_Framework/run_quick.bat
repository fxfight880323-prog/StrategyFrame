@echo off
chcp 65001
echo 策略框架快速运行 (跳过回测)...
cd /d "%~dp0"
python run_strategy_pipeline.py --skip-backtest
pause
