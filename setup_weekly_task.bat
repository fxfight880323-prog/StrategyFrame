@echo off
chcp 65001
cls
echo ==========================================
echo 设置美股周报自动化任务
echo ==========================================
echo.

REM 获取当前目录
set SCRIPT_DIR=%~dp0
cd /d %SCRIPT_DIR%

echo 当前目录: %SCRIPT_DIR%
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python未安装，请先安装Python
    pause
    exit /b 1
)

echo [1/3] Python已安装
python --version
echo.

REM 检查脚本文件是否存在
if not exist "WeeklyAutoReport.py" (
    echo [错误] WeeklyAutoReport.py 不存在
    pause
    exit /b 1
)

echo [2/3] 检查脚本文件... 通过
echo.

REM 创建每周一早上8:00运行的任务
echo [3/3] 创建定时任务...
echo.

schtasks /create /tn "美股周报自动化" /tr "python \"%SCRIPT_DIR%WeeklyAutoReport.py\"" /sc weekly /d MON /st 08:00 /f

if errorlevel 1 (
    echo [错误] 创建任务失败，尝试以管理员身份运行
    echo.
    echo 请右键点击此文件，选择"以管理员身份运行"
    pause
    exit /b 1
)

echo ✅ 定时任务创建成功！
echo.
echo 任务详情:
echo   - 任务名称: 美股周报自动化
echo   - 执行时间: 每周一早上 8:00
echo   - 执行命令: python "%SCRIPT_DIR%WeeklyAutoReport.py"
echo   - 执行目录: %SCRIPT_DIR%
echo.
echo 任务已添加到Windows计划任务中。
echo.
echo 如需修改时间，请打开"任务计划程序"进行修改。
echo.
pause
