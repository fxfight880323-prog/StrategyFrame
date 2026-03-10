@echo off
chcp 65001
cls
echo ==========================================
echo  策略框架 - 设置每周自动化任务
echo ==========================================
echo.

REM 获取当前目录
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo 当前目录: %SCRIPT_DIR%
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python未安装，请先安装Python
    pause
    exit /b 1
)

echo [1/4] Python已安装
python --version
echo.

REM 检查主脚本是否存在
if not exist "run_strategy_pipeline.py" (
    echo [错误] run_strategy_pipeline.py 不存在
    pause
    exit /b 1
)

echo [2/4] 检查主脚本... 通过
echo.

REM 获取用户输入的执行时间
set /p TASK_HOUR="请输入执行小时 (0-23, 默认8): "
if "!TASK_HOUR!"=="" set TASK_HOUR=8

set /p TASK_MINUTE="请输入执行分钟 (0-59, 默认0): "
if "!TASK_MINUTE!"=="" set TASK_MINUTE=0

REM 格式化时间
if %TASK_HOUR% LSS 10 set TASK_HOUR=0%TASK_HOUR%
if %TASK_MINUTE% LSS 10 set TASK_MINUTE=0%TASK_MINUTE%
set TASK_TIME=%TASK_HOUR%:%TASK_MINUTE%

echo.
echo [3/4] 任务执行时间: 每周一 %TASK_TIME%
echo.

REM 删除旧任务（如果存在）
schtasks /delete /tn "策略框架_每周分析" /f >nul 2>&1

REM 创建每周一运行的任务
echo [4/4] 创建定时任务...
echo.

schtasks /create ^
    /tn "策略框架_每周分析" ^
    /tr "python \"%SCRIPT_DIR%run_strategy_pipeline.py\"" ^
    /sc weekly ^
    /d MON ^
    /st %TASK_TIME% ^
    /f ^
    /rl HIGHEST

if errorlevel 1 (
    echo [错误] 创建任务失败
    echo.
    echo 可能原因:
    echo   1. 请以管理员身份运行此脚本
    echo   2. 右键点击此文件，选择"以管理员身份运行"
    echo.
    pause
    exit /b 1
)

echo ✅ 定时任务创建成功！
echo.
echo ==========================================
echo 任务详情:
echo   - 任务名称: 策略框架_每周分析
echo   - 执行时间: 每周一 %TASK_TIME%
echo   - 执行命令: python "%SCRIPT_DIR%run_strategy_pipeline.py"
echo   - 执行目录: %SCRIPT_DIR%
echo   - 运行方式: 最高权限
echo ==========================================
echo.
echo 任务已添加到Windows计划任务中。
echo.
echo 其他操作:
echo   - 查看任务: 任务计划程序 ^> 任务计划程序库 ^> 策略框架_每周分析
echo   - 手动运行: 运行 run_manual.bat
echo   - 删除任务: schtasks /delete /tn "策略框架_每周分析" /f
echo.
pause
