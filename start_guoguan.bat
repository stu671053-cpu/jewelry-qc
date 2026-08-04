@echo off
title 国关 - 珠宝检测AI自查大屏 (5091)
cd /d "%~dp0qc_server"
set TENANT=国关
set PORT=5091
echo ============================================
echo   国关 · 珠宝检测AI自查大屏
echo   地址: http://localhost:5091/
echo   管理: http://localhost:5091/admin
echo   健康: http://localhost:5091/api/health
echo ============================================
echo.
python -m waitress --host 0.0.0.0 --port 5091 app:app
pause
