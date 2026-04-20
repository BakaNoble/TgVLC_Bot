@echo off
chcp 65001 >nul
echo ========================================
echo   VLC 远程控制系统 - 启动脚本
echo ========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 未安装或未添加到 PATH
    echo 请先安装 Python 3.8 或更高版本
    pause
    exit /b 1
)

echo ✅ Python 已安装

REM 检查依赖是否安装
echo.
echo 检查依赖包...
python -c "import telegram" >nul 2>&1
if errorlevel 1 (
    echo 📦 正在安装 Python 依赖包...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ❌ 依赖安装失败
        pause
        exit /b 1
    )
    echo ✅ 依赖安装完成
) else (
    echo ✅ 依赖已安装
)

REM 检查配置文件
echo.
if not exist "config.py" (
    echo ❌ config.py 配置文件不存在
    pause
    exit /b 1
)

echo ✅ 配置文件存在

REM 检查 VLC 路径
echo.
echo 检查 VLC 安装...
python -c "import os; os.path.exists(r'%VLC_PATH%')" >nul 2>&1
setlocal enabledelayedexpansion
set "vlc_check_path=C:\Program Files\VideoLAN\VLC\vlc.exe"
if not exist "!vlc_check_path!" (
    echo ⚠️ 警告：未在默认路径找到 VLC
    echo 请确保已在 config.py 中配置正确的 VLC 路径
) else (
    echo ✅ VLC 已安装
)
endlocal

echo.
echo ========================================
echo   准备启动 VLC 远程控制系统...
echo ========================================
echo.
echo 提示：
echo 1. 确保 Telegram Bot Token 已配置
echo 2. 确保视频目录已设置
echo 3. 按 Ctrl+C 可停止程序
echo.
echo 按任意键启动...
pause >nul

echo.
python main.py
