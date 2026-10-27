@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title 创建 AlgoArchive 桌面快捷方式

if not exist "runtime\python.exe" (
    echo 未找到完整运行环境。请先完整解压程序目录，不要只下载快捷方式。
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create-desktop-shortcut.ps1"
if errorlevel 1 (
    echo.
    echo 桌面快捷方式创建失败。也可以直接双击“启动.bat”运行程序。
    pause
    exit /b 1
)

echo.
echo 创建完成。桌面上的“算法档案”快捷方式现在可以使用。
pause
endlocal
