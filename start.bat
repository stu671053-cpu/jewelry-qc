@echo off
chcp 65001 >nul
title Jewelry QC Server

cd /d "%~dp0"

echo.
echo   ============================================
echo     Jewelry QC AI Inspection Server
echo   ============================================
echo.
echo   [*] Starting services...
echo.

:: Start Zhongjin
start "JewelryQC-Zhongjin" cmd /c "set TENANT=Zhongjin&& set PORT=5090&& python qc_server\app.py"
echo   [+] Zhongjin started on port 5090

:: Start Guoguan
start "JewelryQC-Guoguan" cmd /c "set TENANT=Guoguan&& set PORT=5091&& python qc_server\app.py"
echo   [+] Guoguan started on port 5091

echo.
echo   ============================================
echo     Services running!
echo.
echo     Zhongjin: http://localhost:5090/
echo     Guoguan:  http://localhost:5091/
echo     Admin:    http://localhost:5090/login
echo   ============================================
echo.
echo   Close this window to stop all services.
pause >nul
