#!/bin/bash
# ============================================
# 珠宝质检AI自查大屏 - 阿里云一键部署脚本
# 服务器 IP: 8.138.139.199
# ============================================

set -e

echo "===== 1. 安装依赖 ====="
apt update
apt install -y python3 python3-pip git nginx

echo ""
echo "===== 2. 克隆代码 ====="
cd /root
if [ -d "jewelry-qc" ]; then
    cd jewelry-qc
    git pull
else
    git clone https://github.com/stu671053-cpu/jewelry-qc.git
    cd jewelry-qc
fi

echo ""
echo "===== 3. 安装 Python 依赖 ====="
pip3 install flask requests pyyaml

echo ""
echo "===== 4. 配置数据库 ====="
mkdir -p data
cp data/schema.sql data/schema.sql.bak 2>/dev/null || true

echo ""
echo "===== 5. 杀掉旧进程 ====="
pkill -f "qc_server/app.py" 2>/dev/null || true
sleep 2

echo ""
echo "===== 6. 启动中金 (端口 5090) ====="
TENANT="中金" PORT="5090" nohup python3 qc_server/app.py > /var/log/jewelry_zhongjin.log 2>&1 &
echo "中金 PID: $!"

echo ""
echo "===== 7. 启动国关 (端口 5091) ====="
TENANT="国关" PORT="5091" \
LOUPE_COOKIE="sid_guard_loupe=c8722179097fdc8b052a1214be3600cf%7C1758958093%7C5183999%7CWed%2C+26-Nov-2025+07%3A28%3A12+GMT; s_v_web_id=verify_mpnyuo0l_mJQOKAss_h2av_4ZWB_8yC4_rEyG54usGskn; _tea_utm_cache_370412=undefined; _tea_utm_cache_486645=undefined; _tea_utm_cache_518298=undefined; qic_operation_session_v2=MTc4MzE0Mzk3OXxOd3dBTkZWV1dWazFWa1V6V1VkV1RWSk9WVXBYU1ZsVk5FUlFVVmMzTlZKUlZVWlpValZWTlZKWFNWTmFWa0pMUlZFMlR6ZFBVVUU9fOzz1w2ubD_6Pwuzus8hMUTJS4tqi1IYO549v8UZPA2U; msToken=YPrKMftnG5fYYkYkJKFdoz4f7ntdnR0lguLWEe4ovQ5LOkXiq0X9Q6sZFDJrUKpNHzBDN4N8B86bVoOgmhlQCUJ3Mp9TsaIZaSekMM0C4TLDQ4EJWc0IEho=" \
nohup python3 qc_server/app.py > /var/log/jewelry_guoguan.log 2>&1 &
echo "国关 PID: $!"

sleep 5

echo ""
echo "===== 8. 验证 ====="
echo -n "中金: "
curl -s http://localhost:5090/api/stats | python3 -c "import sys,json;s=json.load(sys.stdin);print(f'HTTP OK, {sum(v for v in s.get(\"status_distribution\",{}).values())}条订单')" 2>/dev/null || echo "启动失败"

echo -n "国关: "
curl -s http://localhost:5091/api/stats | python3 -c "import sys,json;s=json.load(sys.stdin);print(f'HTTP OK, {sum(v for v in s.get(\"status_distribution\",{}).values())}条订单')" 2>/dev/null || echo "启动失败"

echo ""
echo "===== 部署完成 ====="
echo "中金: http://8.138.139.199:5090"
echo "国关: http://8.138.139.199:5091"
echo ""
echo "⚠️  阿里云防火墙需开放 5090 和 5091 端口"
echo "   控制台 → 实例 → 防火墙 → 添加规则"
echo "   协议: TCP | 端口: 5090 | 来源: 0.0.0.0/0"
echo "   协议: TCP | 端口: 5091 | 来源: 0.0.0.0/0"
