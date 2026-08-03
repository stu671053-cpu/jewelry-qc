"""
数据库访问层
- 连接 SQLite 数据库
- 读取质检订单
- 写入检测结果
"""

import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from utils import business_day_range


class Database:
    """QIC 质检数据库操作"""

    def __init__(self, db_path: str = None):
        if db_path is None:
            config_path = Path(__file__).parent / "config.json"
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
            db_path = config["database"]["path"]

        # 支持相对路径
        if not Path(db_path).is_absolute():
            db_path = str(Path(__file__).parent / db_path)

        # 确保目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        # 启用 WAL 模式（提升并发性能）
        try:
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.close()
        except Exception:
            pass
        self._ensure_check_table()
        self._ensure_whitelist_table()

    @contextmanager
    def _conn(self):
        """线程安全的连接上下文"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _ensure_check_table(self):
        """确保检测结果表存在"""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS qc_check_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_code TEXT NOT NULL,
                    cert_code TEXT,
                    check_time TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'ok',
                    r1_weight TEXT,
                    r2_gemstone TEXT,
                    r3_gold_content TEXT,
                    r4_net_weight TEXT,
                    r5_nanhong TEXT,
                    r6_agate_coating TEXT,
                    r7_african_jade TEXT,
                    r8_cubic_zirconia TEXT,
                    r9_style_check TEXT,
                    r10_weight_compare TEXT,
                    r11_material_conclusion TEXT,
                    r12_stone_check TEXT,
                    overtime_risk TEXT DEFAULT '',
                    raw_data TEXT,
                    notified INTEGER DEFAULT 0
                )
            """)
            try:
                conn.execute("ALTER TABLE qc_check_results ADD COLUMN r11_material_conclusion TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE qc_check_results ADD COLUMN r12_stone_check TEXT")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE qc_check_results ADD COLUMN overtime_risk TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass
            # 唯一索引：每个订单最多一条检测结果
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_qc_results_unique ON qc_check_results(order_code)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_qc_results_time ON qc_check_results(check_time)")
            conn.commit()

    def _ensure_whitelist_table(self):
        """确保白名单表存在"""
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS whitelist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_code TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                    whitelist_date TEXT NOT NULL
                )
            """)
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_whitelist_date_order ON whitelist(whitelist_date, order_code)")
            conn.commit()

    def add_whitelist(self, order_code: str, whitelist_date: str = None) -> bool:
        """添加白名单，当天不再提示此订单异常"""
        if whitelist_date is None:
            whitelist_date = datetime.now().strftime("%Y-%m-%d")
        with self._conn() as conn:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO whitelist (order_code, whitelist_date) VALUES (?, ?)",
                    (order_code, whitelist_date)
                )
                conn.commit()
                return conn.total_changes > 0
            except sqlite3.OperationalError:
                return False

    def remove_whitelist(self, order_code: str, whitelist_date: str = None) -> bool:
        """移除白名单"""
        if whitelist_date is None:
            whitelist_date = datetime.now().strftime("%Y-%m-%d")
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM whitelist WHERE order_code = ? AND whitelist_date = ?",
                (order_code, whitelist_date)
            )
            conn.commit()
            return conn.total_changes > 0

    def get_whitelist(self, whitelist_date: str = None) -> list:
        """获取当天白名单订单码列表"""
        if whitelist_date is None:
            whitelist_date = datetime.now().strftime("%Y-%m-%d")
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT order_code, created_at FROM whitelist WHERE whitelist_date = ? ORDER BY created_at DESC",
                (whitelist_date,)
            ).fetchall()
            return [{"order_code": r["order_code"], "created_at": r["created_at"]} for r in rows]

    def get_whitelist_codes(self, whitelist_date: str = None) -> set:
        """获取当天白名单订单码集合（用于快速过滤）"""
        if whitelist_date is None:
            whitelist_date = datetime.now().strftime("%Y-%m-%d")
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT order_code FROM whitelist WHERE whitelist_date = ?",
                (whitelist_date,)
            ).fetchall()
            return {r["order_code"] for r in rows}

    def get_unchecked_orders(self, batch_size: int = 200) -> list:
        """获取未检测的订单"""
        with self._conn() as conn:
            try:
                rows = conn.execute("""
                    SELECT * FROM qic_orders
                    WHERE 订单码 NOT IN (SELECT order_code FROM qc_check_results)
                    ORDER BY 质检完成时间 DESC
                    LIMIT ?
                """, (batch_size,)).fetchall()
                return [dict(row) for row in rows]
            except sqlite3.OperationalError as e:
                print(f"[DB] 读取订单失败: {e}")
                return []

    def get_order_by_code(self, order_code: str) -> dict:
        """按订单码获取单条订单"""
        with self._conn() as conn:
            try:
                row = conn.execute(
                    "SELECT * FROM qic_orders WHERE 订单码 = ?", (order_code,)
                ).fetchone()
                return dict(row) if row else None
            except sqlite3.OperationalError:
                return None

    def get_recent_orders(self, limit: int = 100) -> list:
        """获取最近订单（含检测结果）"""
        with self._conn() as conn:
            try:
                rows = conn.execute("""
                    SELECT o.*, r.status as check_status,
                           r.r1_weight, r.r2_gemstone, r.r3_gold_content,
                           r.r4_net_weight, r.r5_nanhong, r.r6_agate_coating,
                           r.r7_african_jade, r.r8_cubic_zirconia,
                           r.r9_style_check, r.r10_weight_compare,
                           r.r11_material_conclusion,
                           r.check_time, r.notified
                    FROM qic_orders o
                    LEFT JOIN qc_check_results r ON o.订单码 = r.order_code
                    ORDER BY o.质检完成时间 DESC
                    LIMIT ?
                """, (limit,)).fetchall()
                return [dict(row) for row in rows]
            except sqlite3.OperationalError as e:
                print(f"[DB] 读取订单失败: {e}")
                return []

    def get_all_orders(self) -> list:
        """获取所有订单（含检测结果）"""
        with self._conn() as conn:
            try:
                rows = conn.execute("""
                    SELECT o.*, r.status as check_status,
                           r.r1_weight, r.r2_gemstone, r.r3_gold_content,
                           r.r4_net_weight, r.r5_nanhong, r.r6_agate_coating,
                           r.r7_african_jade, r.r8_cubic_zirconia,
                           r.r9_style_check, r.r10_weight_compare,
                           r.r11_material_conclusion,
                           r.check_time, r.notified
                    FROM qic_orders o
                    LEFT JOIN qc_check_results r ON o.订单码 = r.order_code
                    ORDER BY o.质检完成时间 DESC
                """).fetchall()
                return [dict(row) for row in rows]
            except sqlite3.OperationalError as e:
                print(f"[DB] 读取订单失败: {e}")
                return []

    def save_check_result(self, order_code: str, results: dict, status: str):
        """保存单条检测结果（INSERT OR REPLACE，依赖唯一索引防重复）"""
        with self._conn() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("""
                INSERT OR REPLACE INTO qc_check_results
                (order_code, check_time, status,
                 r1_weight, r2_gemstone, r3_gold_content, r4_net_weight,
                 r5_nanhong, r6_agate_coating, r7_african_jade, r8_cubic_zirconia,
                 r9_style_check, r10_weight_compare, r11_material_conclusion,
                 raw_data)
                VALUES (?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?,
                        ?)
            """, (
                order_code, now, status,
                results.get("重量判定", ""),
                results.get("宝玉石判定", ""),
                results.get("金含量备注检查", ""),
                results.get("足金净金重检查", ""),
                results.get("南红备注检查", ""),
                results.get("玛瑙覆膜检查", ""),
                results.get("非洲翠备注检查", ""),
                results.get("合成立方氧化锆备注检查", ""),
                results.get("款式核实", ""),
                results.get("重量比对", ""),
                results.get("材质结论对应", ""),
                json.dumps(results, ensure_ascii=False),
            ))
            conn.commit()

    def save_check_results_batch(self, results_list: list):
        """批量保存检测结果（INSERT OR REPLACE，依赖唯一索引防重复）"""
        with self._conn() as conn:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for item in results_list:
                order_code = item["order_code"]
                results = item["results"]
                status = item["status"]
                conn.execute("""
                    INSERT OR REPLACE INTO qc_check_results
                    (order_code, check_time, status,
                     r1_weight, r2_gemstone, r3_gold_content, r4_net_weight,
                     r5_nanhong, r6_agate_coating, r7_african_jade, r8_cubic_zirconia,
                     r9_style_check, r10_weight_compare, r11_material_conclusion,
                     r12_stone_check, overtime_risk, raw_data)
                    VALUES (?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?, ?,
                            ?, ?, ?)
                """, (
                    order_code, now, status,
                    results.get("重量判定", ""),
                    results.get("宝玉石判定", ""),
                    results.get("金含量备注检查", ""),
                    results.get("足金净金重检查", ""),
                    results.get("南红备注检查", ""),
                    results.get("玛瑙覆膜检查", ""),
                    results.get("非洲翠备注检查", ""),
                    results.get("合成立方氧化锆备注检查", ""),
                    results.get("款式核实", ""),
                    results.get("重量比对", ""),
                    results.get("材质结论对应", ""),
                    results.get("配石检查", ""),
                    results.get("超时预警", ""),
                    json.dumps(results, ensure_ascii=False),
                ))
            conn.commit()

    def get_stats(self) -> dict:
        """获取检测统计（业务日：6AM~次日6AM）"""
        with self._conn() as conn:
            try:
                # 业务日范围
                biz_start, biz_end = business_day_range()

                total = conn.execute(
                    "SELECT COUNT(*) FROM qc_check_results"
                ).fetchone()[0]
                anomaly = conn.execute(
                    "SELECT COUNT(*) FROM qc_check_results WHERE status = 'anomaly'"
                ).fetchone()[0]
                notified = conn.execute(
                    "SELECT COUNT(*) FROM qc_check_results WHERE notified = 1"
                ).fetchone()[0]

                # 本业务日统计
                today_checked = conn.execute(
                    "SELECT COUNT(*) FROM qc_check_results WHERE check_time >= ? AND check_time < ?",
                    (biz_start, biz_end)
                ).fetchone()[0]
                today_anomaly = conn.execute(
                    "SELECT COUNT(*) FROM qc_check_results WHERE status = 'anomaly' AND check_time >= ? AND check_time < ?",
                    (biz_start, biz_end)
                ).fetchone()[0]

                # 订单状态分布（仅统计今日已检测的订单）
                status_dist = {}
                try:
                    rows = conn.execute(
                        """SELECT CAST(o.状态 AS TEXT), COUNT(DISTINCT o.订单码)
                           FROM qic_orders o
                           INNER JOIN qc_check_results r ON o.订单码 = r.order_code
                           WHERE r.check_time >= ? AND r.check_time < ?
                           GROUP BY CAST(o.状态 AS TEXT)""",
                        (biz_start, biz_end)
                    ).fetchall()
                    status_dist = {r[0]: r[1] for r in rows}
                except:
                    pass

                rules = ["r1_weight", "r2_gemstone", "r3_gold_content",
                         "r4_net_weight", "r5_nanhong", "r6_agate_coating",
                         "r7_african_jade", "r8_cubic_zirconia",
                         "r9_style_check", "r10_weight_compare",
                         "r11_material_conclusion", "r12_stone_check", "overtime_risk"]
                rule_stats = {}
                for r in rules:
                    total_r = conn.execute(
                        f"SELECT COUNT(*) FROM qc_check_results WHERE {r} != '' AND {r} != '正常' AND {r} != '正确'"
                    ).fetchone()[0]
                    rule_stats[r] = total_r

                return {
                    "total_checked": total,
                    "anomaly_count": anomaly,
                    "notified_count": notified,
                    "today_checked": today_checked,
                    "today_anomaly": today_anomaly,
                    "status_distribution": status_dist,
                    "rule_stats": rule_stats,
                }
            except sqlite3.OperationalError:
                return {
                    "total_checked": 0,
                    "anomaly_count": 0,
                    "notified_count": 0,
                    "today_checked": 0,
                    "today_anomaly": 0,
                    "status_distribution": {},
                    "rule_stats": {},
                }

    def mark_notified(self, order_codes: list):
        """标记已通知"""
        with self._conn() as conn:
            for code in order_codes:
                conn.execute(
                    "UPDATE qc_check_results SET notified = 1 WHERE order_code = ?",
                    (code,)
                )
            conn.commit()

    # ==================== 白名单 ====================
    def get_whitelist(self, date):
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT order_code, whitelist_date, created_at FROM whitelist WHERE whitelist_date = ? ORDER BY created_at DESC",
                (date,)
            ).fetchall()
            return [{"order_code": r[0], "date": r[1], "created_at": r[2]} for r in rows]

    def add_whitelist(self, order_code, date):
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO whitelist (order_code, whitelist_date) VALUES (?, ?)",
                    (order_code, date)
                )
                conn.commit()
            return True
        except Exception:
            return False

    def remove_whitelist(self, order_code, date):
        try:
            with self._conn() as conn:
                conn.execute(
                    "DELETE FROM whitelist WHERE order_code = ? AND whitelist_date = ?",
                    (order_code, date)
                )
                conn.commit()
            return True
        except Exception:
            return False
