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

:: ---- Step 3: Launch both services (output redirected to log files) ----
echo.
echo   [*] Starting services...

:: Zhongjin (5090) -> output to zj.log
start "JewelryQC-Zhongjin" cmd /c "cd /d %~dp0 && set TENANT=Zhongjin&& set PORT=5090&& python qc_server\app.py > zj.log 2>&1"

:: Guoguan (5091) -> output to gg.log
start "JewelryQC-Guoguan" cmd /c "cd /d %~dp0 && set TENANT=Guoguan&& set PORT=5091&& python qc_server\app.py > gg.log 2>&1"

:: ---- Step 4: Wait and verify ports are actually listening ----
echo   [*] Waiting for services to bind ports...
timeout /t 8 >nul

python -c "import socket; [print(('  [+] port %d listening' if socket.socket().connect_ex(('127.0.0.1',p))==0 else '  [X] port %d NOT listening') % (p,p)) for p in (5090,5091)]"

echo.
echo   ============================================
echo     Service status:
echo   ============================================

:: Check each port; if not listening, dump the corresponding log so the user sees the real error
python -c "import socket; exit(0 if socket.socket().connect_ex(('127.0.0.1',5090))==0 else 1)" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo   [ERROR] Zhongjin (5090) failed to start! Last 40 lines of zj.log:
    echo   ------------------------------------------------------------
    if exist zj.log (powershell -command "Get-Content zj.log -Tail 40") else (echo   zj.log not found)
    echo   ------------------------------------------------------------
)

python -c "import socket; exit(0 if socket.socket().connect_ex(('127.0.0.1',5091))==0 else 1)" 2>nul
if %errorlevel% neq 0 (
    echo.
    echo   [ERROR] Guoguan (5091) failed to start! Last 40 lines of gg.log:
    echo   ------------------------------------------------------------
    if exist gg.log (powershell -command "Get-Content gg.log -Tail 40") else (echo   gg.log not found)
    echo   ------------------------------------------------------------
)

:: If both ports OK, print success banner
python -c "import socket; s=lambda p: socket.socket().connect_ex(('127.0.0.1',p))==0; exit(0 if s(5090) and s(5091) else 1)" 2>nul
if %errorlevel% equ 0 (
    echo.
    echo     All services running!
    echo.
    echo     Dashboard:  http://localhost:5090/   (Zhongjin)
    echo     Dashboard:  http://localhost:5091/   (Guoguan)
    echo     Admin:      http://localhost:5090/login
) else (
    echo.
    echo   [!] Some services failed. See log output above. Fix the error and re-run start.bat.
)

echo.
echo   [TIP] Close this window to stop all services. Logs: zj.log / gg.log
echo.
pause >nul
