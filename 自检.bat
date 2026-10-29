@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
title 算法档案 - 自检
if not exist "runtime\python.exe" (
    echo 缺少运行环境，请先完整解压 ZIP 或重新安装算法档案。
    pause
    exit /b 1
)
"runtime\python.exe" -X utf8 "self_check.py"
set "check_result=%errorlevel%"
echo.
if "%check_result%"=="0" (echo 自检完成。) else (echo 自检失败，请保留上方错误信息。)
pause
exit /b %check_result%
