@echo off
chcp 65001 >nul
title Jewelry QC - Zhongjin (5090)

cd /d C:\jewelry_qc

set TENANT=Zhongjin
set PORT=5090

echo ============================================
echo   Jewelry QC - Zhongjin (Port 5090)
echo   http://localhost:5090/
echo ============================================

python qc_server\app.py

pause
