@echo off
title 中金 - 珠宝检测AI自查大屏 (5090)
cd /d "%~dp0qc_server"
set TENANT=中金
set PORT=5090
echo ============================================
echo   中金 · 珠宝检测AI自查大屏
echo   地址: http://localhost:5090/
echo   管理: http://localhost:5090/admin
echo   健康: http://localhost:5090/api/health
echo ============================================
echo.
python -m waitress --host 0.0.0.0 --port 5090 app:app
pause
