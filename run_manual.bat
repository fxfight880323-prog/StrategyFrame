@echo off
chcp 65001
cls
echo ==========================================
echo 手动运行美股周报生成
echo ==========================================
echo.

cd /d %~dp0

REM 检查参数
if "%~1"=="" (
    set RUN_DATE=%date:~0,4%-%date:~5,2%-%date:~8,2%
    echo 未指定日期，使用今天: %RUN_DATE%
) else (
    set RUN_DATE=%~1
    echo 使用指定日期: %RUN_DATE%
)

echo.
echo 开始生成周报...
echo.

python WeeklyAutoReport.py %RUN_DATE%

echo.
echo ==========================================
echo 周报生成完成！
echo ==========================================
echo.
echo 报告位置: Report_%RUN_DATE%/
echo.
pause
