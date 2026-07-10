#!/bin/bash
# ============================================================
# 域骉珠宝质检 - TV 大屏部署脚本（适用于树莓派 / Linux）
# ============================================================
set -e

echo "========================================"
echo " 域骉珠宝质检 TV 大屏部署"
echo "========================================"
echo ""

# 配置
USER="${USER:-pi}"
HOME_DIR="/home/$USER"
APP_DIR="$HOME_DIR/jewelry_qc"
LOG_DIR="$HOME_DIR/jewelry_qc/logs"

# 1. 安装依赖
echo "[1/5] 安装 Python 依赖..."
pip3 install flask pyyaml openpyxl requests apscheduler --quiet

# 2. 创建日志目录
echo "[2/5] 创建目录..."
mkdir -p "$LOG_DIR"

# 3. 部署 systemd 服务
echo "[3/5] 部署服务..."
sudo cp "$(dirname "$0")/qc_server/jewelry-qc.service" /etc/systemd/system/
sudo sed -i "s|/home/pi|$HOME_DIR|g" /etc/systemd/system/jewelry-qc.service
sudo sed -i "s|User=pi|User=$USER|g" /etc/systemd/system/jewelry-qc.service
sudo systemctl daemon-reload
sudo systemctl enable jewelry-qc.service
sudo systemctl restart jewelry-qc.service

# 4. 检查状态
echo "[4/5] 检查服务状态..."
sleep 2
sudo systemctl status jewelry-qc.service --no-pager | head -10

# 5. 获取 IP
IP=$(hostname -I | awk '{print $1}')
echo ""
echo "[5/5] 部署完成！"
echo ""
echo "========================================"
echo "  访问地址："
echo ""
echo "  PC 版:    http://$IP:5090/"
echo "  TV 大屏:  http://$IP:5090/tv"
echo ""
echo "  TV 使用方式："
echo "    1. 打开 Android TV 浏览器"
echo "    2. 输入 http://$IP:5090/tv"
echo "    3. 设为全屏模式"
echo "========================================"
echo ""
