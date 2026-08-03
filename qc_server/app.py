"""
QC Server - Flask 主入口

策略:
- 后台定时增量同步: 每 N 分钟从 Loupe API 拉取新增/变化订单
- 增量检测: 只对新增/变化订单执行规则审查
- 看板: 纯读 DB，不触发 API 调用
- 手动刷新: 提供全量同步入口（调试/应急用）
"""

import json
import logging
import collections
import threading
import time
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify, Response

from db import Database
from qc_service import QCService
from notifier import Notifier
from sync_service import SyncEngine

# ---------- 初始化 ----------
BASE_DIR = Path(__file__).parent

# 租户环境变量（必须在初始化前读取）
import os
TENANT = os.environ.get("TENANT", "域骉控股")
TENANT_COLOR = os.environ.get("TENANT_COLOR", "#1a1a2e")

with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

# 租户独立数据库（中金用原有数据库，其他租户新库）
if TENANT == "中金":
    tenant_db = "../data/qic_quality.db"
else:
    tenant_db = f"../data/{TENANT}_qic_quality.db"
CONFIG["database"]["path"] = tenant_db

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))

# ---------- 日志系统 ----------
class RingBufferHandler(logging.Handler):
    def __init__(self, capacity=300):
        super().__init__()
        self.buffer = collections.deque(maxlen=capacity)
    def emit(self, record):
        self.buffer.append({
            'time': datetime.fromtimestamp(record.created).strftime('%H:%M:%S'),
            'level': record.levelname,
            'msg': self.format(record)
        })
    def get_logs(self, count=100):
        items = list(self.buffer)
        return items[-count:] if count < len(items) else items

log_handler = RingBufferHandler()
log_handler.setFormatter(logging.Formatter('%(message)s'))
logger = logging.getLogger('qc_server')
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)
console = logging.StreamHandler()
console.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
logger.addHandler(console)

# ---------- 访问控制 ----------
import hmac
import secrets
ACCESS_TOKEN = os.environ.get("QC_ACCESS_TOKEN", "") or secrets.token_hex(16)

@app.before_request
def _require_api_token():
    if not request.path.startswith("/api/"):
        return
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.args.get("token", "")
    if not token or not hmac.compare_digest(token, ACCESS_TOKEN):
        return jsonify({"error": "unauthorized"}), 401

db = Database(db_path=tenant_db)
# 确保 qic_orders 表存在（sync_service._ensure_tables）
if TENANT == "国关":
    sync_engine = SyncEngine(config_path="config_sync_国关.json", enable_qc=False)
else:
    sync_engine = SyncEngine(enable_qc=False)
sync_engine.db_path = str(BASE_DIR / tenant_db)
sync_engine._ensure_tables()
loupe_cookie = os.environ.get("LOUPE_COOKIE", "")
if loupe_cookie:
    sync_engine.loupe["auth"]["cookie"] = loupe_cookie
    sync_engine.session.headers["Cookie"] = loupe_cookie  # 同步更新 HTTP Session
qc = QCService()
notifier = Notifier(CONFIG)

# 同步状态文件
SYNC_STATE_PATH = BASE_DIR / "sync_state.json"

# 系统设置
SETTINGS_PATH = BASE_DIR / "settings.json"

def load_settings():
    defaults = {"work_start": "08:00", "work_end": "23:00", "interval_seconds": 60, "sync_enabled": True}
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, "r") as f:
            defaults.update(json.load(f))
    return defaults

def save_settings(s):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)

runtime_settings = load_settings()

# 创建白名单表
with db._conn() as _c:
    _c.execute("CREATE TABLE IF NOT EXISTS whitelist (id INTEGER PRIMARY KEY AUTOINCREMENT, order_code TEXT NOT NULL, whitelist_date TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(order_code, whitelist_date))")
    _c.commit()


def business_day_range():
    """返回当前业务日：凌晨6点到次日凌晨6点"""
    from datetime import timedelta
    now = datetime.now()
    today6 = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now >= today6:
        start = today6
        end = today6 + timedelta(days=1)
    else:
        end = today6
        start = today6 - timedelta(days=1)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def load_sync_state() -> dict:
    if SYNC_STATE_PATH.exists():
        with open(SYNC_STATE_PATH, "r") as f:
            return json.load(f)
    return {"last_sync_time": 0, "last_sync_count": 0}


def save_sync_state(state: dict):
    with open(SYNC_STATE_PATH, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


# 后台状态
bg_status = {
    "running": False,
    "last_check": None,
    "last_sync": None,
    "last_sync_count": 0,
    "last_anomalies": 0,
    "total_synced_today": 0,
}


# ==================== Dashboard 页面 ====================

@app.route("/")
def dashboard():
    return render_template("dashboard.html",
                           tenant=TENANT,
                           tenant_color=TENANT_COLOR,
                           qc_token=ACCESS_TOKEN)


@app.route("/tv")
def tv_dashboard():
    return render_template("dashboard.html",
                           tenant=TENANT,
                           tenant_color=TENANT_COLOR,
                           qc_token=ACCESS_TOKEN)


# ==================== API 接口 ====================

@app.route("/api/stats")
def api_stats():
    stats = db.get_stats()
    stats["bg_status"] = bg_status
    stats["server_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(stats)


@app.route("/api/anomalies")
def api_anomalies():
    """获取本业务日异常订单（6AM~次日6AM）"""
    biz_start, biz_end = business_day_range()
    with db._conn() as conn:
        rows = conn.execute("""
            SELECT r.order_code, r.check_time, r.status,
                   r.r1_weight, r.r2_gemstone, r.r3_gold_content,
                   r.r4_net_weight, r.r5_nanhong, r.r6_agate_coating,
                   r.r7_african_jade, r.r8_cubic_zirconia,
                   r.r9_style_check, r.r10_weight_compare,
                   r.r11_material_conclusion,
                   o.证书编码 as cert_code, o.入库批次号 as batch_code,
                   o.状态 as order_status, o.质检完成时间 as batch_time
            FROM qc_check_results r
            LEFT JOIN qic_orders o ON r.order_code = o.订单码
            WHERE r.status = 'anomaly'
              AND r.check_time >= ? AND r.check_time < ?
            ORDER BY r.check_time DESC
            LIMIT 200
        """, (biz_start, biz_end)).fetchall()

    rule_labels = {
        "r1_weight": "R1 重量判定", "r2_gemstone": "R2 宝玉石判定",
        "r3_gold_content": "R3 金含量备注", "r4_net_weight": "R4 足金净金重",
        "r5_nanhong": "R5 南红备注", "r6_agate_coating": "R6 玛瑙覆膜",
        "r7_african_jade": "R7 非洲翠备注", "r8_cubic_zirconia": "R8 合成立方氧化锆",
        "r9_style_check": "R9 款式核实", "r10_weight_compare": "R10 重量比对",
        "r11_material_conclusion": "R11 材质结论对应",
    }

    status_map = {"100": "待处理", "200": "处理中", "301": "已完成",
                  "400": "待制证", "401": "已驳回", "500": "质检中", "502": "异常", "503": "已完成"}

    anomalies = []
    for row in rows:
        row = dict(row)
        items = []
        for col, label in rule_labels.items():
            val = row.get(col, "")
            if val and val not in ("正常", "正确", ""):
                items.append({"rule": label, "value": val})

        # 质检完成时间 → 时分
        raw_batch_time = row.get("batch_time", "")
        if raw_batch_time and str(raw_batch_time).lstrip("-").isdigit():
            ts = int(raw_batch_time)
            if ts <= 0:
                batch_time_str = "-"
            else:
                s = str(ts)
                if len(s) == 10:
                    batch_time_str = datetime.fromtimestamp(ts).strftime("%H:%M")
                elif len(s) == 13:
                    batch_time_str = datetime.fromtimestamp(ts / 1000).strftime("%H:%M")
                else:
                    batch_time_str = "-"
        else:
            batch_time_str = "-"

        anomalies.append({
            "order_code": row["order_code"],
            "cert_code": row.get("cert_code", "") or "",
            "batch_code": row.get("batch_code", "") or "",
            "order_status": status_map.get(str(row.get("order_status", "") or ""), str(row.get("order_status", "") or "")),
            "check_time": row["check_time"],
            "batch_time": batch_time_str,
            "items": items,
        })

    return jsonify({
        "today": biz_start[:10],
        "total": len(anomalies),
        "anomalies": anomalies,
    })


@app.route("/api/check", methods=["POST"])
def api_check():
    """
    手动触发检测
    - force=true: 全量从 API 拉取 + 清空重检（调试用）
    - 默认: 增量同步 + 检测未审查订单
    """
    data = request.get_json() or {}
    force = data.get("force", False)
    notify = data.get("notify", False)

    if force:
        return _do_full_sync()

    # 增量模式
    return _do_incremental_sync_and_check(notify)


def _do_full_sync():
    """全量同步（清空 DB → 拉取今日 → 全量检测）"""
    today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = datetime.now()
    ts_start = int(today_start.timestamp())
    ts_end = int(today_end.timestamp())

    print(f"[全量同步] 时间范围: {ts_start} ~ {ts_end}")

    sync_engine.loupe["search_params"]["inspectionBatchStartTime"] = ts_start
    sync_engine.loupe["search_params"]["inspectionBatchEndTime"] = ts_end

    with db._conn() as conn:
        conn.execute("DELETE FROM qc_check_results")
        conn.execute("DELETE FROM qic_orders")
        conn.commit()

    try:
        synced = sync_engine.sync_full()
        print(f"[全量同步] 完成: {synced} 条")
    except Exception as e:
        print(f"[全量同步] 失败: {e}")
        return jsonify({"message": f"API 同步失败: {e}", "checked": 0})

    # 全量检测
    return _check_unchecked()


def _do_incremental_sync_and_check(notify: bool = False):
    """增量同步 + 检测"""
    state = load_sync_state()
    last_sync = state.get("last_sync_time", 0)

    # 用上次同步时间作为起始（首次同步从今天0点开始）
    if last_sync == 0:
        ts_start = int(datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    else:
        ts_start = max(0, last_sync - 600)  # 往前推10分钟防漏
    ts_end = int(datetime.now().timestamp())

    print(f"[增量同步] 时间范围: {ts_start} ~ {ts_end}")

    sync_engine.loupe["search_params"]["inspectionBatchStartTime"] = ts_start
    sync_engine.loupe["search_params"]["inspectionBatchEndTime"] = ts_end

    try:
        synced = sync_engine.sync_full()
        print(f"[增量同步] 完成: {synced} 条")
    except Exception as e:
        print(f"[增量同步] 失败: {e}")
        return jsonify({"message": f"增量同步失败: {e}", "checked": 0})

    # 更新同步状态
    state["last_sync_time"] = ts_end
    state["last_sync_count"] = synced
    save_sync_state(state)

    bg_status["last_sync"] = datetime.now().strftime("%H:%M:%S")
    bg_status["last_sync_count"] = synced

    # 检测未审查订单
    return _check_unchecked(notify)


def _check_unchecked(notify: bool = False):
    """检测所有未审查订单（分批处理）"""
    batch_size = CONFIG.get("qc", {}).get("batch_size", 200)
    orders = db.get_unchecked_orders(batch_size=batch_size)

    if not orders:
        return jsonify({"message": "没有需要检测的订单", "checked": 0})

    results = qc.check_batch(orders)
    save_list = []
    anomalies = []
    for r in results:
        save_list.append({
            "order_code": r["order_code"],
            "results": r["results"],
            "status": r["status"],
        })
        if r["status"] == "anomaly":
            anomalies.append(r)

    db.save_check_results_batch(save_list)

    if notify and anomalies:
        notifier.send_batch_alert(anomalies)
        db.mark_notified([a["order_code"] for a in anomalies])

    print(f"[检测] {len(results)} 条, 异常 {len(anomalies)} 条")
    return jsonify({
        "message": f"检测完成: {len(results)} 条",
        "checked": len(results),
        "anomalies": len(anomalies),
    })


@app.route("/api/check-single", methods=["POST"])
def api_check_single():
    """单条订单检测"""
    data = request.get_json() or {}
    order_code = data.get("order_code", "")
    if not order_code:
        return jsonify({"error": "缺少 order_code"}), 400

    order = db.get_order_by_code(order_code)
    if not order:
        return jsonify({"error": f"订单 {order_code} 不存在"}), 404

    result = qc.check_order(order)
    db.save_check_result(order_code, result["results"], result["status"])

    return jsonify({
        "order_code": order_code,
        "status": result["status"],
        "results": result["results"],
        "anomalies": [
            {"rule": a["rule_name"], "value": a["value"]}
            for a in result["anomalies"]
        ],
    })


@app.route("/api/events")
def api_events():
    """SSE 实时推送"""
    def event_stream():
        last_check = None
        while True:
            stats = db.get_stats()
            current = stats.get("total_checked", 0)
            if last_check is not None and current != last_check:
                yield f"data: {json.dumps({'type': 'update', 'stats': stats})}\n\n"
            last_check = current
            time.sleep(5)
    return Response(event_stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ==================== 后台定时全量刷新 ====================

def background_checker():
    """
    后台定时任务（全量刷新模式）:
    1. 清空数据库
    2. 从 Loupe API 拉取当天全部数据
    3. 对所有订单执行规则自查
    4. 显示到大屏
    """
    interval = CONFIG.get("qc", {}).get("check_interval_minutes", 1) * 60
    if interval <= 0:
        print("[后台] 定时检测已禁用")
        return
    print(f"[后台] 全量刷新已启动，间隔 {interval // 60} 分钟")

    from datetime import timedelta

    while True:
        try:
            bg_status["running"] = True
            start_time = datetime.now()
            print(f"\n[后台 {start_time.strftime('%H:%M:%S')}] ===== 开始全量刷新 =====")

            # 1. 设置今天业务日时间范围
            now = datetime.now()
            today6 = now.replace(hour=6, minute=0, second=0, microsecond=0)
            if now >= today6:
                ts_start = int(today6.timestamp())
                ts_end = int((today6 + timedelta(days=1)).timestamp())
            else:
                ts_start = int((today6 - timedelta(days=1)).timestamp())
                ts_end = int(today6.timestamp())

            sync_engine.loupe["search_params"]["inspectionBatchStartTime"] = ts_start
            sync_engine.loupe["search_params"]["inspectionBatchEndTime"] = ts_end

            # 2. 清空旧数据
            with db._conn() as conn:
                conn.execute("DELETE FROM qc_check_results")
                conn.execute("DELETE FROM qic_orders")
                conn.commit()

            # 3. 全量拉取
            try:
                synced = sync_engine.sync_full()
                print(f"[后台] 拉取: {synced} 条")
            except Exception as e:
                print(f"[后台] 拉取失败: {e}")
                time.sleep(interval)
                continue

            bg_status["last_sync"] = start_time.strftime("%H:%M:%S")
            bg_status["last_sync_count"] = synced

            # 4. 全部跑自查
            total_checked = 0
            total_anomalies = 0
            while True:
                orders = db.get_unchecked_orders(batch_size=500)
                if not orders:
                    break
                results = qc.check_batch(orders)
                save_list = []
                for r in results:
                    save_list.append({
                        "order_code": r["order_code"],
                        "results": r["results"],
                        "status": r["status"],
                    })
                    if r["status"] == "anomaly":
                        total_anomalies += 1

                db.save_check_results_batch(save_list)
                total_checked += len(results)

            bg_status["last_check"] = datetime.now().strftime("%H:%M:%S")
            bg_status["last_anomalies"] = total_anomalies

            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"[后台] 自查: {total_checked} 条, 异常 {total_anomalies} 条, 耗时 {elapsed:.1f}s")

        except Exception as e:
            print(f"[后台] 异常: {e}")
        finally:
            bg_status["running"] = False

        time.sleep(interval)


# ==================== 启动 ====================

# ==================== 设置 API ====================
@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(runtime_settings)

@app.route("/api/settings", methods=["POST"])
def api_update_settings():
    global runtime_settings
    data = request.get_json() or {}
    for k in ["work_start", "work_end", "interval_seconds", "sync_enabled"]:
        if k in data:
            runtime_settings[k] = data[k]
    save_settings(runtime_settings)
    return jsonify({"success": True, "settings": runtime_settings})

# ==================== 白名单 API ====================
@app.route("/api/whitelist", methods=["GET"])
def api_whitelist_list():
    date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    items = db.get_whitelist(date)
    return jsonify({"date": date, "total": len(items), "items": items})

@app.route("/api/whitelist", methods=["POST"])
def api_whitelist_add():
    data = request.get_json() or {}
    order_code = data.get("order_code", "").strip()
    whitelist_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    if not order_code:
        return jsonify({"success": False, "message": "订单码不能为空"}), 400
    ok = db.add_whitelist(order_code, whitelist_date)
    return jsonify({"success": ok, "message": "已添加" if ok else "已存在或添加失败"})

@app.route("/api/whitelist/<order_code>", methods=["DELETE"])
def api_whitelist_remove(order_code):
    whitelist_date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    ok = db.remove_whitelist(order_code, whitelist_date)
    return jsonify({"success": ok, "message": "已移除" if ok else "移除失败"})

@app.route("/api/whitelist/detect", methods=["POST"])
def api_whitelist_detect():
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"success": False, "message": "输入不能为空"}), 400
    whitelist_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    ok = db.add_whitelist(code, whitelist_date)
    return jsonify({"success": ok, "message": f"{code} {'已加入' if ok else '已存在'}白名单"})

# ==================== 手动同步 API ====================
@app.route("/api/sync", methods=["POST"])
def api_manual_sync():
    try:
        biz_start, biz_end = business_day_range()
        ts_start = int(datetime.strptime(biz_start, "%Y-%m-%d %H:%M:%S").timestamp())
        ts_end = int(datetime.strptime(biz_end, "%Y-%m-%d %H:%M:%S").timestamp())
        sync_engine.loupe["search_params"]["inspectionBatchStartTime"] = ts_start
        sync_engine.loupe["search_params"]["inspectionBatchEndTime"] = ts_end
        synced = sync_engine.sync_full()
        total_checked = 0
        while True:
            orders = db.get_unchecked_orders(batch_size=500)
            if not orders:
                break
            results = qc.check_batch(orders)
            save_list = [{"order_code": r["order_code"], "results": r["results"], "status": r["status"]} for r in results]
            db.save_check_results_batch(save_list)
            total_checked += len(results)
        return jsonify({"success": True, "synced": synced, "checked": total_checked})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ==================== 日志 / 管理页面 ====================
@app.route("/api/logs")
def api_logs():
    lines = request.args.get("lines", 100, type=int)
    lines = min(lines, 300)
    return jsonify({"logs": log_handler.get_logs(lines)})

@app.route("/admin")
def admin_page():
    return render_template("admin.html",
                           tenant=TENANT,
                           tenant_color=TENANT_COLOR,
                           qc_token=ACCESS_TOKEN)

if __name__ == "__main__":
    print(f"[配置] 租户: {TENANT} | 数据库: {tenant_db}")
    if loupe_cookie:
        print(f"[配置] Cookie来源: 环境变量 ({len(loupe_cookie)}字符)")

    notifier.start()

    checker_thread = threading.Thread(target=background_checker, daemon=True)
    checker_thread.start()

    host = "0.0.0.0"
    port = int(os.environ.get("PORT", CONFIG.get("server", {}).get("port", 5090)))

    print(f"""
╔══════════════════════════════════════════════╗
║      珠宝检测AI自查大屏                      ║
╠══════════════════════════════════════════════╣
║  Dashboard: http://0.0.0.0:{port}            ║
║  规则数量:  {len(qc.rule_names)} 条
║  同步策略:  增量（仅拉新增/变化）
║  检测策略:  增量（仅检未审查）
║  同步间隔:  每 {CONFIG.get('qc', {}).get('check_interval_minutes', 5)} 分钟
╚══════════════════════════════════════════════╝
""")

    app.run(host=host, port=port, debug=CONFIG.get("server", {}).get("debug", False))
