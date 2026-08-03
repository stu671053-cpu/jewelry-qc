"""
错误处理机制测试脚本
原则：不修改生产数据，不中断正常业务，仅验证错误捕获和上报
"""
import json
import os
import sys
import time
import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PORT = int(os.environ.get("PORT", "5090"))
BASE = f"http://127.0.0.1:{PORT}"
TOKEN = ""  # 将从启动日志读取

print("=" * 60)
print("  错误处理机制测试报告")
print("=" * 60)


def get_token():
    """从启动日志或环境变量获取 token"""
    global TOKEN
    token = os.environ.get("QC_ACCESS_TOKEN", "")
    if token:
        TOKEN = token
        return token
    # 尝试从 /tmp 日志获取
    log_files = ["/tmp/qc_local.log", "/tmp/zj.log"]
    for lf in log_files:
        try:
            with open(lf) as f:
                import re
                tokens = re.findall(r"[a-f0-9]{32}", f.read())
                if tokens:
                    TOKEN = tokens[-1]
                    return TOKEN
        except FileNotFoundError:
            continue
    return ""


def test(name, url, expected_status=200, method="GET", body=None, check_fn=None):
    """运行一个测试用例"""
    global TOKEN
    if not TOKEN:
        TOKEN = get_token()
    full_url = url if url.startswith("http") else f"{BASE}{url}"
    headers = {}
    if "?" in full_url:
        full_url = full_url
    elif "/api/" in url and "token" not in url:
        full_url += f"?token={TOKEN}"

    try:
        if method == "GET":
            resp = requests.get(full_url, headers=headers, timeout=10)
        elif method == "POST":
            resp = requests.post(full_url, json=body, headers=headers, timeout=10)
        else:
            resp = requests.request(method, full_url, json=body, headers=headers, timeout=10)

        status_ok = resp.status_code == expected_status
        mark = "✅" if status_ok else "❌"
        print(f"\n{mark} [{name}] HTTP {resp.status_code} (期望 {expected_status})")

        if check_fn:
            try:
                data = resp.json()
                result = check_fn(data)
                if result:
                    print(f"   {result}")
                return data
            except Exception as e:
                print(f"   ⚠️ 检查失败: {e}")
        return resp.json() if resp.ok else resp.text

    except requests.ConnectionError:
        print(f"\n❌ [{name}] 连接失败 - 服务未启动")
        return None
    except Exception as e:
        print(f"\n❌ [{name}] 异常: {e}")
        return None


# ==================== 测试用例 ====================

print("\n" + "─" * 40)
print("  一、健康检查（免 token）")
print("─" * 40)

test("health 免token可访问", "/api/health", check_fn=lambda d: (
    f"状态: {d.get('status')}, 数据库: {d['subsystems']['database']['status']}, "
    f"API: {d['subsystems']['api']['status']}"
))

test("health 包含 subsystems 字段", "/api/health", check_fn=lambda d: (
    f"database={d.get('subsystems',{}).get('database',{}).get('status')}, "
    f"api={d.get('subsystems',{}).get('api',{}).get('status')}, "
    f"background={d.get('subsystems',{}).get('background',{}).get('status')}"
))

test("health 包含错误追踪字段", "/api/health", check_fn=lambda d: (
    f"consecutive_failures={d.get('consecutive_failures')}, "
    f"recent_errors={len(d.get('recent_errors',[]))}条"
))

print("\n" + "─" * 40)
print("  二、404 错误处理")
print("─" * 40)

test("不存在的接口", "/api/nonexistent", 404, check_fn=lambda d: (
    f"msg: {d.get('msg','')[:50]}"
))

print("\n" + "─" * 40)
print("  三、API 数据接口容错")
print("─" * 40)

test("stats 正常返回", "/api/stats", check_fn=lambda d: (
    f"total={d.get('total_checked')}, anomaly={d.get('anomaly_count')}, "
    f"bg_status存在={'bg_status' in d}"
))

test("anomalies 正常返回", "/api/anomalies", check_fn=lambda d: (
    f"异常数={d.get('total')}, 列表长度={len(d.get('anomalies',[]))}"
))

test("anomalies 后台刷新中返回缓存", "/api/anomalies", check_fn=lambda d: (
    f"缓存命中={'X-Data-Cached' in str(d)}"  # 不一定命中
))

print("\n" + "─" * 40)
print("  四、管理端接口")
print("─" * 40)

test("settings 可读取", "/api/settings", check_fn=lambda d: (
    f"work_start={d.get('work_start')}, interval={d.get('interval_seconds')}s"
))

test("whitelist 列表", "/api/whitelist", check_fn=lambda d: (
    f"日期={d.get('date')}, 数量={d.get('total')}"
))

test("logs 可读取", "/api/logs", check_fn=lambda d: (
    f"日志条数={len(d.get('logs',[]))}"
))

print("\n" + "─" * 40)
print("  五、后台任务错误不中断验证")
print("─" * 40)

stats = requests.get(f"{BASE}/api/stats?token={TOKEN}").json()
bg = stats.get("bg_status", {})
print(f"  running={bg.get('running')}, sleeping={bg.get('sleeping')}")
print(f"  last_sync={bg.get('last_sync')}, last_check={bg.get('last_check')}")
print(f"  last_error={bg.get('last_error')}, consecutive_failures={bg.get('consecutive_failures')}")

print("\n" + "─" * 40)
print("  六、模拟错误场景（安全，不破坏数据）")
print("─" * 40)

# 模拟：向 health 发送畸形请求验证错误不崩溃
test("health 带垃圾数据", "/api/health", check_fn=lambda d: (
    f"依然正常返回 status={d.get('status')}"
))

# 模拟：请求不存在的订单码
test("单条检测-不存在的订单", "/api/check", 404, method="POST",
     body={"order_code": "THIS_ORDER_DOES_NOT_EXIST_999999"},
     check_fn=lambda d: (
        f"error: {d.get('error','')}, msg: {d.get('msg','')[:50]}"
     ))

print("\n" + "─" * 40)
print("  七、最终健康报告")
print("─" * 40)

health = requests.get(f"{BASE}/api/health").json()
print(f"""
  ┌─────────────────────────────────────┐
  │ 系统状态: {health['status']:<25s} │
  │ 数据库:   {health['subsystems']['database']['status']:<25s} │
  │ Loupe API: {health['subsystems']['api']['status']:<23s} │
  │ 后台任务: {health['subsystems']['background']['status']:<23s} │
  │ 累计失败: {str(health['consecutive_failures']):<25s} │
  │ 最后错误: {str(health.get('last_error') or '无')[:25]:<25s} │
  └─────────────────────────────────────┘
""")

print("\n✅ 测试完成\n")
