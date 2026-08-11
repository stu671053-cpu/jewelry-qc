@echo off
chcp 65001 >nul
title Jewelry QC Server

cd /d "%~dp0"

echo.
echo   ============================================
echo     Jewelry QC AI Inspection Server
echo   ============================================

:: ---- Step 1: Check Python ----
echo.
echo   [*] Checking environment...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] Python not found!
    echo.
    echo   Please install Python 3.9+ from:
    echo   https://www.python.org/downloads/
    echo.
    echo   IMPORTANT: Check "Add Python to PATH" during installation!
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do echo   [+] Python %%v found

:: ---- Step 2: Check & install pip packages ----
echo.
echo   [*] Checking dependencies...

set NEED_INSTALL=0

python -c "import waitress" 2>nul || set NEED_INSTALL=1
python -c "import flask" 2>nul || set NEED_INSTALL=1
python -c "import requests" 2>nul || set NEED_INSTALL=1
python -c "import yaml" 2>nul || set NEED_INSTALL=1
python -c "import websocket" 2>nul || set NEED_INSTALL=1

if %NEED_INSTALL%==1 (
    echo   [*] Installing missing packages...
    pip install waitress flask requests pyyaml websocket-client -q
    if %errorlevel% neq 0 (
        echo   [ERROR] Package install failed! Try running: pip install -r requirements.txt
        pause
        exit /b 1
    )
    echo   [+] Dependencies installed
) else (
    echo   [+] All dependencies OK
)

:: ---- Step 3: Launch both services ----
echo.
echo   [*] Starting services...

:: Zhongjin (5090)
start "JewelryQC-Zhongjin" cmd /c "cd /d %~dp0 && set TENANT=Zhongjin&& set PORT=5090&& python qc_server\app.py"
echo   [+] Zhongjin started on port 5090

:: Guoguan (5091)
start "JewelryQC-Guoguan" cmd /c "cd /d %~dp0 && set TENANT=Guoguan&& set PORT=5091&& python qc_server\app.py"
echo   [+] Guoguan started on port 5091

:: ---- Done ----
echo.
echo   ============================================
echo     All services running!
echo.
echo     Dashboard:  http://localhost:5090/   (Zhongjin)
echo     Dashboard:  http://localhost:5091/   (Guoguan)
echo     Admin:      http://localhost:5090/login
echo   ============================================
echo.
echo   [TIP] Close this window to stop all services.
echo.
pause >nul
