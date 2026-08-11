@echo off
chcp 65001 >nul
title Jewelry QC - Guoguan (5091)

cd /d C:\jewelry_qc

set TENANT=Guoguan
set PORT=5091

echo ============================================
echo   Jewelry QC - Guoguan (Port 5091)
echo   http://localhost:5091/
echo ============================================

python qc_server\app.py

pause
