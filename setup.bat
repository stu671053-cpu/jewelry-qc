@echo off
chcp 65001 >nul
title Jewelry QC - Setup

cd /d "%~dp0"

echo   ============================================
echo     Jewelry QC - Install Dependencies
echo   ============================================
echo.
echo   This will install required Python packages.
echo   Run this ONLY ONCE after first download.
echo.

pip install waitress flask requests pyyaml websocket-client
if %errorlevel% neq 0 (
    echo.
    echo   [ERROR] pip install failed!
    echo   Make sure Python is installed:
    echo   1. Download: https://www.python.org/downloads/
    echo   2. Install with "Add Python to PATH" checked
    echo   3. Re-run this script
    echo.
    pause
    exit /b 1
)

echo.
echo   ============================================
echo     Setup complete!
echo     Now double-click "start.bat" to launch.
echo   ============================================
echo.
pause
