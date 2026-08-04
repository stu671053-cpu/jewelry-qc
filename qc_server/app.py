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
import threading
import time
import collections
from pathlib import Path
from datetime import datetime

from flask import Flask, render_template, request, jsonify, Response

from db import Database
from qc_service import QCService
from notifier import Notifier
from sync_service import SyncEngine
from utils import business_day_ts, business_day_range

# ---------- 日志系统 ----------
class RingBufferHandler(logging.Handler):
    """环形缓冲区日志处理器，保留最近 N 条日志"""
    def __init__(self, capacity=300):
        super().__init__()
        self.buffer = collections.deque(maxlen=capacity)

    def emit(self, record):
        entry = {
            'time': datetime.fromtimestamp(record.created).strftime('%H:%M:%S'),
            'level': record.levelname,
            'msg': self.format(record)
        }
        self.buffer.append(entry)

    def get_logs(self, count=100):
        items = list(self.buffer)
        return items[-count:] if count < len(items) else items

log_handler = RingBufferHandler(capacity=300)
log_handler.setFormatter(logging.Formatter('%(message)s'))
logger = logging.getLogger('qc_server')
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)
# 控制台输出
console = logging.StreamHandler()
console.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%H:%M:%S'))
logger.addHandler(console)
# 文件持久化（保留最近5天，每天最多1MB）
try:
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    from logging.handlers import TimedRotatingFileHandler
    file_handler = TimedRotatingFileHandler(
        log_dir / "qc_server.log", when='D', interval=1, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(file_handler)
except Exception:
    pass  # 文件日志非关键，失败不影响运行

# ---------- 初始化 ----------
BASE_DIR = Path(__file__).resolve().parent

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

# ==================== 访问控制 (P0-2) ====================
import hmac
import secrets

ACCESS_TOKEN = os.environ.get("QC_ACCESS_TOKEN", "")
if not ACCESS_TOKEN:
    # 未显式配置时自动生成，仅保证本地可用；生产环境必须通过环境变量设置固定令牌
    ACCESS_TOKEN = secrets.token_hex(16)
    print(f"[安全] QC_ACCESS_TOKEN 未设置，已自动生成(仅供本地开发): {ACCESS_TOKEN}")


@app.before_request
def _require_api_token():
    """所有 /api/* 接口必须携带有效访问令牌（Bearer 或 ?token=），/api/health 除外"""
    if not request.path.startswith("/api/"):
        return
    if request.path == "/api/health":
        return
    auth = request.headers.get("Authorization", "")
    token = auth[7:] if auth.startswith("Bearer ") else request.args.get("token", "")
    if not token or not hmac.compare_digest(token, ACCESS_TOKEN):
        return jsonify({"error": "unauthorized"}), 401


db = Database(db_path=tenant_db)
# 确保 qic_orders 表存在（sync_service._ensure_tables）

# 租户独立同步配置：中金用 config_sync.json，其他租户用 config_sync_{TENANT}.json
sync_config_map = {
    "中金": "config_sync.json",
}
sync_config_file = sync_config_map.get(TENANT, f"config_sync_{TENANT}.json")
sync_config_path = str(BASE_DIR / sync_config_file)
if not Path(sync_config_path).exists():
    # fallback: 如果租户专属配置不存在，使用默认配置
    sync_config_path = str(BASE_DIR / "config_sync.json")
    logger.info(f"[警告] {sync_config_file} 不存在，回退到 config_sync.json")

sync_engine = SyncEngine(config_path=sync_config_path, enable_qc=False)
sync_engine.db_path = str(BASE_DIR / tenant_db)
sync_engine._ensure_tables()
# Cookie 统一从环境变量读取（避免明文落盘），按租户区分，回退到通用 LOUPE_COOKIE
_TENANT_COOKIE_ENV = {"中金": "LOUPE_COOKIE_ZHONGJIN", "国关": "LOUPE_COOKIE_GUOGUAN"}
loupe_cookie = os.environ.get(_TENANT_COOKIE_ENV.get(TENANT, ""), "") or os.environ.get("LOUPE_COOKIE", "")
if loupe_cookie:
    sync_engine.loupe["auth"]["cookie"] = loupe_cookie
    sync_engine.session.headers["Cookie"] = loupe_cookie  # 同步更新 HTTP Session
notifier = Notifier(CONFIG)

# 同步状态文件
SYNC_STATE_PATH = BASE_DIR / "sync_state.json"

# 系统设置文件
SETTINGS_PATH = BASE_DIR / "settings.json"


def load_settings():
    """加载系统设置"""
    defaults = {
        "work_start": "08:00",
        "work_end": "23:00",
        "interval_seconds": 60,
        "sync_enabled": True,
        "overtime_minutes": 30 if TENANT == "中金" else 60,  # 剩余时间阈值：中金剩30min预警，国关剩60min预警
    }
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, "r") as f:
            saved = json.load(f)
            defaults.update(saved)
    return defaults


def save_settings(s):
    with open(SETTINGS_PATH, "w") as f:
        json.dump(s, f, indent=2, ensure_ascii=False)


# 全局运行时设置
runtime_settings = load_settings()
qc = QCService(overtime_seconds=runtime_settings.get("overtime_minutes", 30) * 60)

# ==================== 设置 API ====================


@app.route("/api/settings", methods=["GET"])
def api_get_settings():
    return jsonify(runtime_settings)


@app.route("/api/settings", methods=["POST"])
def api_update_settings():
    global runtime_settings
    data = request.get_json() or {}
    allowed = ["work_start", "work_end", "interval_seconds", "sync_enabled", "overtime_minutes"]
    for k in allowed:
        if k in data:
            runtime_settings[k] = data[k]
    # 兼容旧字段名
    if "work_start_hour" in data:
        runtime_settings["work_start"] = f'{int(data["work_start_hour"]):02d}:00'
    if "work_end_hour" in data:
        runtime_settings["work_end"] = f'{int(data["work_end_hour"]):02d}:00'
    if "interval_minutes" in data:
        runtime_settings["interval_seconds"] = int(data["interval_minutes"]) * 60
    # 超时阈值更新时同步到 QCService
    if "overtime_minutes" in data:
        from qc_service import QCService
        import qc_service
        qc_service.OVERTIME_SECONDS = int(data["overtime_minutes"]) * 60
    save_settings(runtime_settings)
    return jsonify({"success": True, "settings": runtime_settings})


def business_day_ts():
    """返回当前业务日时间戳（6AM-次日6AM）"""
    from datetime import timedelta
    now = datetime.now()
    today6 = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now >= today6:
        return int(today6.timestamp()), int((today6 + timedelta(days=1)).timestamp())
    return int((today6 - timedelta(days=1)).timestamp()), int(today6.timestamp())


def business_day_range():
    """返回当前业务日字符串"""
    start_ts, end_ts = business_day_ts()
    from datetime import datetime as dt
    return dt.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M:%S"), dt.fromtimestamp(end_ts).strftime("%Y-%m-%d %H:%M:%S")


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
    "sleeping": False,
    "sleep_reason": "",
    "last_cycle_at": None,  # 后台最近一轮完成的时刻（前端10s内刷新）
    # 错误追踪
    "last_error": None,
    "last_error_time": None,
    "consecutive_failures": 0,
    "api_status": "ok",
    "db_status": "ok",
}
# ==================== 错误追踪系统 ====================
# 设计原则：
#   1. 错误不中断正常业务流程（数据拉取、规则检测、页面展示各自独立容错）
#   2. 错误分级：critical（系统级） / recoverable（可恢复） / info（提示）
#   3. 连续成功一次即清零 consecutive_failures
#   4. 所有错误写入 logger + bg_status，管理端和 /api/health 可实时查看
_bg_errors = []

def _record_error(msg: str, source: str = "background", level: str = "recoverable"):
    """记录错误到 bg_status 和 logger，不中断业务流程"""
    global _bg_errors
    now_str = datetime.now().strftime("%H:%M:%S")
    bg_status["last_error"] = msg
    bg_status["last_error_time"] = now_str
    bg_status["consecutive_failures"] += 1
    _bg_errors.append({
        "time": now_str, "source": source, "level": level, "msg": msg
    })
    if len(_bg_errors) > 20:
        _bg_errors.pop(0)
    if level == "critical":
        logger.error(f"[{source}] [严重] {msg}")
    elif level == "recoverable":
        logger.warning(f"[{source}] {msg}")
    else:
        logger.info(f"[{source}] {msg}")

def _clear_error():
    """一次成功即清零失败计数"""
    bg_status["consecutive_failures"] = 0
    bg_status["last_error"] = None
    bg_status["last_error_time"] = None

# 异常数据缓存（后台刷新时返回上一周期数据，避免页面显示为0）
_anomalies_cache = None


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
    """获取本业务日异常订单（6AM~次日6AM），排除白名单"""
    global _anomalies_cache
    # 后台刷新中，返回上一周期缓存数据，避免页面显示为0
    if bg_status["running"] and _anomalies_cache is not None:
        result = jsonify(_anomalies_cache)
        result.headers["X-Data-Cached"] = "1"
        return result

    biz_start, biz_end = business_day_range()
    today_str = datetime.now().strftime("%Y-%m-%d")
    with db._conn() as conn:
        rows = conn.execute("""
            SELECT r.order_code, r.check_time, r.status,
                   r.r1_weight, r.r2_gemstone, r.r3_gold_content,
                   r.r4_net_weight, r.r5_nanhong, r.r6_agate_coating,
                   r.r7_african_jade, r.r8_cubic_zirconia,
                   r.r9_style_check, r.r10_weight_compare,
                   r.overtime_risk,
                   r.r11_material_conclusion,
                   r.r12_stone_check,
                   o.入库批次号 as batch_code, o.证书编码 as cert_code, o.操作人 as operator,
                   o.质检完成时间 as batch_time, o.状态 as order_status
            FROM qc_check_results r
            LEFT JOIN qic_orders o ON r.order_code = o.订单码
            WHERE r.status = 'anomaly'
              AND r.check_time >= ? AND r.check_time < ?
              AND r.order_code NOT IN (SELECT order_code FROM whitelist WHERE whitelist_date = ? AND length(order_code) = 10 AND order_code GLOB '[0-9]*')
              AND o.证书编码 NOT IN (SELECT order_code FROM whitelist WHERE whitelist_date = ? AND (order_code LIKE 'ZJ%' OR order_code LIKE '3126%' OR length(order_code) >= 10))
              AND o.入库批次号 NOT IN (SELECT order_code FROM whitelist WHERE whitelist_date = ? AND order_code LIKE 'A%')
              AND o.质检批次号 NOT IN (SELECT order_code FROM whitelist WHERE whitelist_date = ? AND length(order_code) = 12)
            ORDER BY r.check_time DESC
            LIMIT 200
        """, (biz_start, biz_end, today_str, today_str, today_str, today_str)).fetchall()

    rule_labels = {
        "r1_weight": "R1 重量判定", "r2_gemstone": "R2 宝玉石判定",
        "r3_gold_content": "R3 金含量备注", "r4_net_weight": "R4 足金净金重",
        "r5_nanhong": "R5 南红备注", "r6_agate_coating": "R6 玛瑙覆膜",
        "r7_african_jade": "R7 非洲翠备注", "r8_cubic_zirconia": "R8 合成立方氧化锆",
        "r9_style_check": "R9 款式核实", "r10_weight_compare": "R10 重量比对",
        "r11_material_conclusion": "R11 材质结论对应",
        "r12_stone_check": "R12 配石检查",
        "overtime_risk": "超时预警",
    }

    anomalies = []

    for row in rows:
        row = dict(row)
        items = []
        for col, label in rule_labels.items():
            val = row.get(col, "")
            if val and val not in ("正常", "正确", ""):
                items.append({"rule": label, "value": val})

        # 批次时间戳 → 时分
        raw_batch_time = row.get("batch_time", "") or ""
        batch_time_str = "-"
        # 接受 10 位（秒）或 13 位（毫秒）正整数时间戳；负数/零/空视为未填写
        s = str(raw_batch_time).lstrip("-")
        if s.isdigit():
            try:
                ts = int(raw_batch_time)
                if ts <= 0:
                    batch_time_str = "-"
                elif len(s) == 10:
                    batch_time_str = datetime.fromtimestamp(ts).strftime("%H:%M")
                elif len(s) == 13:
                    batch_time_str = datetime.fromtimestamp(ts / 1000).strftime("%H:%M")
                else:
                    batch_time_str = str(raw_batch_time)
            except (ValueError, OSError):
                batch_time_str = "-"

        # 订单状态码 → 可读文本
        status_map = {
            "100": "待处理", "200": "处理中", "301": "已完成",
            "400": "待制证", "401": "已驳回",
            "500": "质检中", "502": "异常", "503": "已完成",
        }
        raw_status = str(row.get("order_status", "") or "")
        order_status = status_map.get(raw_status, raw_status)

        anomalies.append({
            "order_code": row["order_code"],
            "cert_code": row.get("cert_code", "") or "",
            "batch_code": row.get("batch_code", "") or "",
            "operator": row.get("operator", "") or "",
            "order_status": order_status,
            "check_time": row["check_time"],
            "batch_time": batch_time_str,
            "_overtime": any(i["rule"] == "超时预警" for i in items),
            "items": items,
        })

    # 超时预警：按批次合并，一条批次一行（只显示批次号）
    overtime_items = [a for a in anomalies if any(i["rule"] == "超时预警" for i in a["items"])]
    normal_items = [a for a in anomalies if a not in overtime_items]

    if overtime_items:
        # 按入库批次号分组
        batch_groups = {}
        for a in overtime_items:
            bc = a["batch_code"] or a["order_code"]
            if bc not in batch_groups:
                batch_groups[bc] = []
            batch_groups[bc].append(a)

        merged_overtime = []
        for bc, items_list in batch_groups.items():
            # 合并所有规则项（去重 + 超时预警放前面）
            all_items = []
            seen = set()
            ot_item = None
            for a in items_list:
                for item in a["items"]:
                    if item["rule"] == "超时预警":
                        ot_item = item
                    else:
                        key = item["rule"] + item["value"]
                        if key not in seen:
                            all_items.append(item)
                            seen.add(key)
            # 超时预警排最前
            merged_items = [ot_item] + all_items if ot_item else all_items

            merged_overtime.append({
                "order_code": "-",           # 超时条目不显示具体订单码
                "cert_code": "-",             # 不显示证书编号
                "batch_code": bc,
                "order_status": items_list[0]["order_status"],
                "check_time": items_list[0]["check_time"],
                "batch_time": items_list[0]["batch_time"],
                "_overtime": True,
                "items": merged_items,
            })

        anomalies = merged_overtime + normal_items
    else:
        anomalies = normal_items

    result_obj = {
        "today": biz_start[:10],
        "total": len(anomalies),
        "anomalies": anomalies,
    }
    # 缓存本次结果（用于后台刷新时返回上一周期数据）
    if not bg_status["running"]:
        _anomalies_cache = result_obj
    return jsonify(result_obj)


# ==================== 白名单管理 API ====================

@app.route("/api/whitelist", methods=["GET"])
def api_whitelist_list():
    """获取当天白名单列表"""
    date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    items = db.get_whitelist(date)
    return jsonify({"date": date, "total": len(items), "items": items})


@app.route("/api/whitelist", methods=["POST"])
def api_whitelist_add():
    """添加订单到白名单"""
    data = request.get_json() or {}
    order_code = data.get("order_code", "").strip()
    whitelist_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    if not order_code:
        return jsonify({"success": False, "message": "订单码不能为空"}), 400
    ok = db.add_whitelist(order_code, whitelist_date)
    return jsonify({"success": ok, "message": "已添加" if ok else "已存在或添加失败"})


@app.route("/api/whitelist/<order_code>", methods=["DELETE"])
def api_whitelist_remove(order_code):
    """从白名单移除订单"""
    whitelist_date = request.args.get("date", datetime.now().strftime("%Y-%m-%d"))
    ok = db.remove_whitelist(order_code, whitelist_date)
    return jsonify({"success": ok, "message": "已移除" if ok else "移除失败"})


@app.route("/api/whitelist/detect", methods=["POST"])
def api_whitelist_detect():
    """自动识别：订单码或批次号，直接存入白名单"""
    data = request.get_json() or {}
    code = data.get("code", "").strip()
    if not code:
        return jsonify({"success": False, "message": "输入不能为空"}), 400

    whitelist_date = data.get("date", datetime.now().strftime("%Y-%m-%d"))
    # 自动识别类型
    is_cert = code.startswith("ZJ") or code.startswith("3126")
    is_batch = code.startswith("A") or (len(code) >= 12 and not is_cert)

    ok = db.add_whitelist(code, whitelist_date)
    if is_cert:
        tag = f"证书 {code}"
    elif is_batch:
        tag = f"批次 {code}"
    else:
        tag = f"订单 {code}"
    return jsonify({
        "success": ok,
        "message": f"{tag} {'已加入' if ok else '已存在'}白名单"
    })


@app.route("/api/sync", methods=["POST"])
def api_manual_sync():
    """手动触发一次全量同步"""
    try:
        ts_start, ts_end = business_day_ts()
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


# ==================== 管理员页面 ====================

# ==================== 健康检查 ====================
@app.route("/api/health")
def api_health():
    """综合健康检查：API状态 + DB状态 + 错误追踪（免token，运维友好）"""
    db_ok = True
    try:
        with db._conn() as c:
            c.execute("SELECT 1").fetchone()
    except Exception:
        db_ok = False
        bg_status["db_status"] = "error"
    else:
        bg_status["db_status"] = "ok"

    # 综合判断：db、api、后台线程三者都正常才算 ok
    if not db_ok:
        overall = "critical"
    elif bg_status["api_status"] == "error":
        overall = "degraded"
    elif bg_status["consecutive_failures"] >= 3:
        overall = "degraded"
    else:
        overall = "ok"

    return jsonify({
        "status": overall,
        "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # 各子系统状态
        "subsystems": {
            "database": {"status": "ok" if db_ok else "error", "msg": "正常" if db_ok else "数据库无法连接"},
            "api": {"status": bg_status["api_status"], "msg": "Loupe API 正常" if bg_status["api_status"] == "ok" else "Loupe API 连接异常"},
            "background": {"status": "running" if bg_status["running"] else "idle", "sleeping": bg_status["sleeping"], "sleep_reason": bg_status["sleep_reason"]},
        },
        # 错误追踪
        "last_error": bg_status["last_error"],
        "last_error_time": bg_status["last_error_time"],
        "consecutive_failures": bg_status["consecutive_failures"],
        "recent_errors": _bg_errors,
    })

@app.route("/api/logs")
def api_logs():
    """运行日志接口"""
    lines = request.args.get("lines", 100, type=int)
    lines = min(lines, 300)
    return jsonify({"logs": log_handler.get_logs(lines)})


@app.route("/admin")
def admin_page():
    return render_template("admin.html",
                           tenant=TENANT,
                           tenant_color=TENANT_COLOR,
                           qc_token=ACCESS_TOKEN)


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

    logger.info(f"[全量同步] 时间范围: {ts_start} ~ {ts_end}")

    sync_engine.loupe["search_params"]["inspectionBatchStartTime"] = ts_start
    sync_engine.loupe["search_params"]["inspectionBatchEndTime"] = ts_end

    # 先拉取数据，成功后再清空旧数据
    try:
        synced = sync_engine.sync_full()
        logger.info(f"[全量同步] 完成: {synced} 条")
    except Exception as e:
        logger.info(f"[全量同步] 失败: {e}")
        return jsonify({"message": f"API 同步失败: {e}", "checked": 0})

    # 清理已不存在的订单的旧检测结果
    with db._conn() as conn:
        conn.execute("DELETE FROM qc_check_results WHERE order_code NOT IN (SELECT 订单码 FROM qic_orders)")
        conn.commit()

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

    logger.info(f"[增量同步] 时间范围: {ts_start} ~ {ts_end}")

    sync_engine.loupe["search_params"]["inspectionBatchStartTime"] = ts_start
    sync_engine.loupe["search_params"]["inspectionBatchEndTime"] = ts_end

    try:
        synced = sync_engine.sync_full()
        logger.info(f"[增量同步] 完成: {synced} 条")
    except Exception as e:
        logger.info(f"[增量同步] 失败: {e}")
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

    logger.info(f"[检测] {len(results)} 条, 异常 {len(anomalies)} 条")
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

# ==================== 后台智能调度 ====================

def _all_orders_done():
    """检查本业务日内是否所有订单都已完成"""
    biz_start, biz_end = business_day_range()
    with db._conn() as conn:
        # 统计本业务日内有检测记录的订单
        total = conn.execute(
            """SELECT COUNT(DISTINCT o.订单码) FROM qic_orders o
               INNER JOIN qc_check_results r ON o.订单码 = r.order_code
               WHERE r.check_time >= ? AND r.check_time < ?""",
            (biz_start, biz_end)
        ).fetchone()[0]
        if total == 0:
            return False  # 没有今天的订单 = 还没拉数据，不算完成
        done = conn.execute(
            """SELECT COUNT(DISTINCT o.订单码) FROM qic_orders o
               INNER JOIN qc_check_results r ON o.订单码 = r.order_code
               WHERE r.check_time >= ? AND r.check_time < ?
               AND o.状态 IN ('301','401','503')""",
            (biz_start, biz_end)
        ).fetchone()[0]
        return done >= total


def background_checker():
    """
    后台定时任务（增量模式 + 智能调度）:
    - 8:00~23:00: 正常拉取和检测
    - 23:00后: 全部订单完成且连续3次确认后停止，否则持续运行
    - 次日8:00自动恢复
    """
    settings = runtime_settings
    interval = settings.get("interval_seconds", 60)
    if interval <= 0:
        logger.info("[后台] 定时检测已禁用")
        return

    ws = settings.get("work_start", "08:00")
    we = settings.get("work_end", "23:00")
    work_start = int(ws.split(":")[0]) * 60 + int(ws.split(":")[1])
    work_end = int(we.split(":")[0]) * 60 + int(we.split(":")[1])
    logger.info(f"[后台] 已启动，间隔 {interval}s，工作时间 {ws}-{we}")

    from datetime import timedelta

    while True:
        try:
            now = datetime.now()
            hour = now.hour
            minute = now.minute
            now_minutes = hour * 60 + minute
            settings = runtime_settings  # 读取最新设置

            # ===== 手动关闭检查 =====
            if not settings.get("sync_enabled", True):
                bg_status["sleeping"] = True
                bg_status["sleep_reason"] = "管理员已暂停同步"
                time.sleep(10)
                continue

            # ===== 重新读取工作时间（可能有更新） =====
            ws = settings.get("work_start", "08:00")
            we = settings.get("work_end", "23:00")
            work_start = int(ws.split(":")[0]) * 60 + int(ws.split(":")[1])
            work_end = int(we.split(":")[0]) * 60 + int(we.split(":")[1])

            # 早于工作开始时间：休眠
            if now_minutes < work_start:
                bg_status["sleeping"] = True
                bg_status["sleep_reason"] = f"非工作时间（{ws} 恢复）"
                wait_sec = (work_start - now_minutes) * 60
                logger.info(f"[后台] 休眠至 {ws}（{wait_sec}s）")
                time.sleep(min(wait_sec, 3600))
                continue

            bg_status["sleeping"] = False
            bg_status["sleep_reason"] = ""
            bg_status["all_done_count"] = 0

            # 晚于工作结束时间：检查是否所有订单完成
            if now_minutes >= work_end:
                if _all_orders_done():
                    bg_status["all_done_count"] = bg_status.get("all_done_count", 0) + 1
                    logger.info(f"[后台] {we}后全完成 {bg_status['all_done_count']}/3")
                    if bg_status["all_done_count"] >= 3:
                        bg_status["sleeping"] = True
                        bg_status["sleep_reason"] = f"全部完成，休眠至次日 {ws}"
                        logger.info(f"[后台] 连续3次全完成，休眠至次日 {ws}")
                        wake_h, wake_m = int(ws.split(":")[0]), int(ws.split(":")[1])
                        tomorrow_start = now.replace(hour=wake_h, minute=wake_m, second=0, microsecond=0)
                        sleep_sec = (tomorrow_start.timestamp() - now.timestamp()) + 86400
                        time.sleep(sleep_sec)
                        continue
                else:
                    bg_status["all_done_count"] = 0

            bg_status["running"] = True
            start_time = datetime.now()
            logger.info(f"\n[后台 {start_time.strftime('%H:%M:%S')}] ===== 开始增量刷新 =====")

            # 1. 设置今天业务日时间范围
            ts_start, ts_end = business_day_ts()

            sync_engine.loupe["search_params"]["inspectionBatchStartTime"] = ts_start
            sync_engine.loupe["search_params"]["inspectionBatchEndTime"] = ts_end

            # 2. 增量拉取（UPSERT，不清空）
            try:
                synced = sync_engine.sync_full()
                logger.info(f"[后台] 拉取: {synced} 条（增量）")
                bg_status["api_status"] = "ok"
            except Exception as e:
                _record_error(f"拉取失败: {e}", "sync")
                bg_status["api_status"] = "error"
                bg_status["running"] = False
                time.sleep(interval)
                continue

            bg_status["last_sync"] = start_time.strftime("%H:%M:%S")
            bg_status["last_sync_count"] = synced

            # 3. 跑未审查/已变化的订单
            total_checked = 0
            total_anomalies = 0
            try:
                while True:
                    orders = db.get_unchecked_orders(batch_size=500)
                    if not orders:
                        break
                    try:
                        results = qc.check_batch(orders)
                    except Exception as e:
                        _record_error(f"批量检测失败: {e}", "qc")
                        continue  # 跳过当前批次
                    save_list = []
                    for r in results:
                        save_list.append({
                            "order_code": r["order_code"],
                            "results": r["results"],
                            "status": r["status"],
                        })
                        if r["status"] == "anomaly":
                            total_anomalies += 1
                    try:
                        db.save_check_results_batch(save_list)
                    except Exception as e:
                        _record_error(f"保存检测结果失败: {e}", "db")
                    total_checked += len(results)
            except Exception as e:
                _record_error(f"检测循环异常: {e}", "qc")

            bg_status["last_check"] = datetime.now().strftime("%H:%M:%S")
            bg_status["last_anomalies"] = total_anomalies
            bg_status["last_cycle_at"] = int(time.time())  # 秒级时间戳，前端据此自动刷新

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.info(f"[后台] 自查: {total_checked} 条, 异常 {total_anomalies} 条, 耗时 {elapsed:.1f}s")
            _clear_error()

        except Exception as e:
            _record_error(f"后台任务异常: {e}", "background")
        finally:
            bg_status["running"] = False

        time.sleep(settings.get("interval_seconds", 60))


# ==================== API 统一错误处理 ====================
# 原则：不暴露内部细节给前端，但完整记录到日志供运维排查
@app.errorhandler(404)
def _not_found(e):
    return jsonify({"error": "not_found", "msg": "请求的接口不存在，请检查地址是否正确"}), 404

@app.errorhandler(500)
def _server_error(e):
    _record_error(f"服务器内部错误: {e}", "api", "critical")
    return jsonify({"error": "internal_error", "msg": "服务器内部错误，已自动记录，请联系管理员"}), 500

@app.errorhandler(Exception)
def _unhandled(e):
    _record_error(f"未处理异常: {e}", "api", "recoverable")
    return jsonify({"error": "unhandled", "msg": "请求处理异常，已自动记录"}), 500

# ==================== 启动 ====================

if __name__ == "__main__":
    logger.info(f"[配置] 租户: {TENANT} | 数据库: {tenant_db}")
    if loupe_cookie:
        logger.info(f"[配置] Cookie来源: 环境变量 ({len(loupe_cookie)}字符)")

    notifier.start()

    checker_thread = threading.Thread(target=background_checker, daemon=True)
    checker_thread.start()

    host = "0.0.0.0"
    port = int(os.environ.get("PORT", CONFIG.get("server", {}).get("port", 5090)))

    logger.info(f"""
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
