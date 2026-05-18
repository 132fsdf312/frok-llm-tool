@echo off
chcp 65001 >nul 2>&1
title Frok Code
cd /d "%~dp0"

echo ========================================
echo   Frok Code Starting...
echo ========================================
echo.

where python >nul 2>&1
if %errorlevel%==0 (
    set "PY=python"
    goto :found
)
where python3 >nul 2>&1
if %errorlevel%==0 (
    set "PY=python3"
    goto :found
)
where py >nul 2>&1
if %errorlevel%==0 (
    set "PY=py"
    goto :found
)

echo [ERROR] Python not found. Please install Python 3.8+
echo Download: https://www.python.org/downloads/
echo.
pause
exit /b 1

:found
echo Python: %PY%
echo.
%PY% frok/main.py
echo.
pause
