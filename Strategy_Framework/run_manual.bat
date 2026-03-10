@echo off
chcp 65001
cls
echo ==========================================
echo  策略框架 - 手动运行分析
echo ==========================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python未安装
    pause
    exit /b 1
)

echo Python版本:
python --version
echo.

REM 显示菜单
:MENU
echo 请选择运行模式:
echo.
echo  [1] 完整分析管道 (全部7层)
echo  [2] 仅宏观分析 (Level 1)
echo  [3] 仅板块分析 (Level 2)
echo  [4] 仅个股选择 (Level 3)
echo  [5] 跳过回测 (快速模式)
echo  [6] 指定日期运行
echo  [7] 查看历史报告
echo  [8] 退出
echo.
set /p choice="请输入选项 (1-8): "

if "%choice%"=="1" goto FULL
if "%choice%"=="2" goto MACRO
if "%choice%"=="3" goto SECTOR
if "%choice%"=="4" goto STOCK
if "%choice%"=="5" goto QUICK
if "%choice%"=="6" goto CUSTOM_DATE
if "%choice%"=="7" goto VIEW_REPORTS
if "%choice%"=="8" goto EXIT
echo 无效选项，请重新输入
echo.
goto MENU

:FULL
echo.
echo ==========================================
echo 开始完整分析管道...
echo ==========================================
echo.
python run_strategy_pipeline.py
goto END

:MACRO
echo.
echo ==========================================
echo 开始宏观分析...
echo ==========================================
echo.
python run_strategy_pipeline.py --macro-only
goto END

:SECTOR
echo.
echo ==========================================
echo 开始板块分析...
echo ==========================================
echo.
python run_strategy_pipeline.py --sector-only
goto END

:STOCK
echo.
echo ==========================================
echo 开始个股选择...
echo ==========================================
echo.
python run_strategy_pipeline.py --stock-only
goto END

:QUICK
echo.
echo ==========================================
echo 开始快速分析 (跳过回测)...
echo ==========================================
echo.
python run_strategy_pipeline.py --skip-backtest
goto END

:CUSTOM_DATE
echo.
set /p run_date="请输入日期 (YYYY-MM-DD): "
echo.
echo ==========================================
echo 开始分析，日期: %run_date%
echo ==========================================
echo.
python run_strategy_pipeline.py %run_date%
goto END

:VIEW_REPORTS
echo.
echo ==========================================
echo 历史报告列表
echo ==========================================
echo.
if exist "Results" (
    dir /b /ad "Results\" 2>nul | findstr /r "Report_" || echo 暂无历史报告
) else (
    echo 暂无历史报告
)
echo.
pause
goto MENU

:END
echo.
echo ==========================================
echo 分析完成！
echo ==========================================
echo.
if exist "Results" (
    echo 查看结果:
    dir /b /ad "Results\" 2>nul | sort /r | findstr /r "Report_" | head -1
)
echo.
pause

:EXIT
