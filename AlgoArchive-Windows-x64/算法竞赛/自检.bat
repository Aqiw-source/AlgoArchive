@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title AlgoArchive - Self Check
if not exist "runtime\python.exe" (
    echo Runtime is missing. Please extract the entire ZIP first.
    pause
    exit /b 1
)
"runtime\python.exe" -X utf8 "self_check.py"
set "check_result=%errorlevel%"
echo.
if "%check_result%"=="0" (echo All checks passed.) else (echo Some checks failed. Please keep the error output.)
pause
exit /b %check_result%
