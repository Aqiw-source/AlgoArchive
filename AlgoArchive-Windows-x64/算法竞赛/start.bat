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
"runtime\python.exe" -X utf8 "app.py"
if errorlevel 1 (
    echo.
    echo Startup failed. Please keep this window and read the error above.
    pause
)
endlocal
