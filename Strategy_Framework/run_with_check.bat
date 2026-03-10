@echo off
chcp 65001
echo ==========================================
echo  策略框架 - 运行并检查结果
echo ==========================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python未安装
    pause
    exit /b 1
)

REM 获取日期参数
if "%~1"=="" (
    set RUN_DATE=%date:~0,4%-%date:~5,2%-%date:~8,2%
) else (
    set RUN_DATE=%~1
)

echo 执行日期: %RUN_DATE%
echo.

REM 1. 运行策略管道
echo [Step 1/2] 执行策略分析管道...
echo.
python run_strategy_pipeline.py %RUN_DATE%
if errorlevel 1 (
    echo [警告] 管道执行可能有问题
)
echo.

REM 2. 检查结果
echo [Step 2/2] 验证执行结果...
echo.
python check_results.py %RUN_DATE%
set CHECK_RESULT=%errorlevel%

echo.
if %CHECK_RESULT%==0 (
    echo ==========================================
    echo  所有检查通过！
    echo ==========================================
) else (
    echo ==========================================
    echo  检查发现问题，请查看详情
    echo ==========================================
)

echo.
pause
