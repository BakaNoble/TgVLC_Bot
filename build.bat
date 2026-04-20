@echo off
chcp 65001 > nul
echo ========================================
echo   TgVLC_Bot 打包工具
echo ========================================
echo.

echo [1/3] 正在清理旧文件...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
echo       完成清理
echo.

echo [2/3] 正在打包程序...
pyinstaller TgVLC_Bot.spec --clean
echo.

if %ERRORLEVEL% EQU 0 (
    echo [3/3] 正在整理输出文件...

    REM 将 config.yaml 复制到 exe 同目录（而非 _internal）
    copy /Y "config.yaml" "dist\TgVLC_Bot\config.yaml" > nul

    echo       打包完成！
    echo.
    echo ========================================
    echo   打包成功！
    echo ========================================
    echo.
    echo 可执行文件位置:
    echo   dist\TgVLC_Bot\TgVLC_Bot.exe
    echo.
    echo 使用说明:
    echo   1. 将 dist\TgVLC_Bot 文件夹完整复制到目标电脑
    echo   2. 编辑 TgVLC_Bot.exe 同目录下的 config.yaml 配置文件
    echo   3. 确保目标电脑已安装 VLC Media Player
    echo   4. 双击 TgVLC_Bot.exe 运行程序
    echo.
    echo 注意事项:
    echo   - config.yaml 位于 exe 同目录，可直接编辑
    echo   - VLC Media Player 路径需在 config.yaml 中正确配置
    echo   - Telegram Bot Token 需要在配置文件中设置
    echo.
    pause
) else (
    echo.
    echo ========================================
    echo   打包失败！请检查错误信息
    echo ========================================
    echo.
    pause
)
