"""
QC Server - Flask 主入口

策略:
- 后台定时增量同步: 每 N 分钟从 Loupe API 拉取新增/变化订单
- 增量检测: 只对新增/变化订单执行规则审查
- 看板: 纯读 DB，不触发 API 调用
- 手动刷新: 提供全量同步入口（调试/应急用）
"""

import json
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

with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"))

db = Database()
qc = QCService()
notifier = Notifier(CONFIG)

# 同步引擎（用于从 Loupe API 拉取数据）
sync_engine = SyncEngine(enable_qc=False)

# 同步状态文件
SYNC_STATE_PATH = BASE_DIR / "sync_state.json"


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
                           tenant_color=TENANT_COLOR)


@app.route("/tv")
def tv_dashboard():
    return render_template("dashboard.html",
                           tenant=TENANT,
                           tenant_color=TENANT_COLOR)


# ==================== API 接口 ====================

@app.route("/api/stats")
def api_stats():
    stats = db.get_stats()
    stats["bg_status"] = bg_status
    stats["server_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return jsonify(stats)


@app.route("/api/anomalies")
def api_anomalies():
    """获取今日异常订单（仅读 DB，不触发 API）"""
    today = datetime.now().strftime("%Y-%m-%d")
    with db._conn() as conn:
        rows = conn.execute("""
            SELECT r.order_code, r.check_time, r.status,
                   r.r1_weight, r.r2_gemstone, r.r3_gold_content,
                   r.r4_net_weight, r.r5_nanhong, r.r6_agate_coating,
                   r.r7_african_jade, r.r8_cubic_zirconia,
                   r.r9_style_check, r.r10_weight_compare,
                   r.r11_material_conclusion,
                   o.质检批次号 as batch_code, o.操作人 as operator
            FROM qc_check_results r
            LEFT JOIN qic_orders o ON r.order_code = o.订单码
            WHERE r.status = 'anomaly'
              AND r.check_time >= ?
            ORDER BY r.check_time DESC
            LIMIT 200
        """, (today,)).fetchall()

    rule_labels = {
        "r1_weight": "R1 重量判定", "r2_gemstone": "R2 宝玉石判定",
        "r3_gold_content": "R3 金含量备注", "r4_net_weight": "R4 足金净金重",
        "r5_nanhong": "R5 南红备注", "r6_agate_coating": "R6 玛瑙覆膜",
        "r7_african_jade": "R7 非洲翠备注", "r8_cubic_zirconia": "R8 合成立方氧化锆",
        "r9_style_check": "R9 款式核实", "r10_weight_compare": "R10 重量比对",
        "r11_material_conclusion": "R11 材质结论对应",
    }

    anomalies = []
    for row in rows:
        row = dict(row)
        items = []
        for col, label in rule_labels.items():
            val = row.get(col, "")
            if val and val not in ("正常", "正确", ""):
                items.append({"rule": label, "value": val})

        anomalies.append({
            "order_code": row["order_code"],
            "batch_code": row.get("batch_code", "") or "",
            "operator": row.get("operator", "") or "",
            "check_time": row["check_time"],
            "items": items,
        })

    return jsonify({
        "today": today,
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

    # 用上次同步时间作为起始，防止漏数据（往前推 10 分钟保险）
    ts_start = max(0, last_sync - 600)
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


# ==================== 后台定时增量检测 ====================

def background_checker():
    """
    后台定时任务:
    1. 增量同步 Loupe API (只拉新增/变化)
    2. 检测未审查订单
    3. 异常通知
    """
    interval = CONFIG.get("qc", {}).get("check_interval_minutes", 5) * 60
    if interval <= 0:
        print("[后台] 定时检测已禁用")
        return
    print(f"[后台] 增量检测已启动，间隔 {interval // 60} 分钟")

    while True:
        try:
            bg_status["running"] = True

            # 1. 增量同步
            state = load_sync_state()
            last_sync = state.get("last_sync_time", 0)
            ts_start = max(0, last_sync - 600)  # 往前推 10 分钟防漏
            ts_end = int(datetime.now().timestamp())

            sync_engine.loupe["search_params"]["inspectionBatchStartTime"] = ts_start
            sync_engine.loupe["search_params"]["inspectionBatchEndTime"] = ts_end

            try:
                synced = sync_engine.sync_full()
                if synced > 0:
                    print(f"[后台] 增量同步: {synced} 条新订单")
            except Exception as e:
                print(f"[后台] 同步失败: {e}")
                time.sleep(interval)
                continue

            state["last_sync_time"] = ts_end
            state["last_sync_count"] = synced
            save_sync_state(state)

            bg_status["last_sync"] = datetime.now().strftime("%H:%M:%S")
            bg_status["last_sync_count"] = synced

            # 2. 检测未审查订单（分批）
            total_checked = 0
            total_anomalies = 0
            for _ in range(5):  # 最多 5 批
                orders = db.get_unchecked_orders(batch_size=200)
                if not orders:
                    break
                results = qc.check_batch(orders)
                save_list = []
                batch_anomalies = []
                for r in results:
                    save_list.append({
                        "order_code": r["order_code"],
                        "results": r["results"],
                        "status": r["status"],
                    })
                    if r["status"] == "anomaly":
                        batch_anomalies.append(r)

                db.save_check_results_batch(save_list)
                total_checked += len(results)
                total_anomalies += len(batch_anomalies)

                if batch_anomalies:
                    notifier.send_batch_alert(batch_anomalies)
                    db.mark_notified([a["order_code"] for a in batch_anomalies])

            bg_status["last_check"] = datetime.now().strftime("%H:%M:%S")
            bg_status["last_anomalies"] = total_anomalies

            if total_checked > 0:
                print(f"[后台] 检测: {total_checked} 条, 异常 {total_anomalies} 条")

        except Exception as e:
            print(f"[后台] 异常: {e}")
        finally:
            bg_status["running"] = False

        time.sleep(interval)


# ==================== 启动 ====================

if __name__ == "__main__":
    # Render 环境变量支持
    import os
    loupe_cookie = os.environ.get("LOUPE_COOKIE", "")
    if loupe_cookie:
        sync_engine.loupe["auth"]["cookie"] = loupe_cookie
        print("[配置] 已从环境变量加载 Cookie")

    # 租户配置
    TENANT = os.environ.get("TENANT", "域骉控股")
    TENANT_COLOR = os.environ.get("TENANT_COLOR", "#1a1a2e")
    print(f"[配置] 租户: {TENANT}")

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
