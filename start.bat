@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title AlgoArchive - Local Contest Manager
if not exist "runtime\python.exe" (
    echo Runtime is missing. Please extract the entire ZIP before starting.
    pause
    exit /b 1
)
if /I "%~1"=="--create-shortcut" (
    if not exist "scripts\create-desktop-shortcut.ps1" (
        echo Shortcut support is missing from this package.
        pause
        exit /b 1
    )
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\create-desktop-shortcut.ps1" -IncludeStartMenu
    if errorlevel 1 (
        echo Failed to create the shortcuts.
        pause
        exit /b 1
    )
)
"runtime\python.exe" -X utf8 "app.py"
if errorlevel 1 (
    echo.
    echo Startup failed. Please keep this window and read the error above.
    pause
)
endlocal
