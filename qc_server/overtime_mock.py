"""
超时预警 Mock 模块 — 本地测试用
- 国关：随机给部分异常订单标注等级
- 中金：选N个订单标注"接近超时(剩余X分钟)"，展示时按批次合并
"""
import sqlite3
import random
from pathlib import Path
from datetime import datetime


def mock_sync(db_path: str, risk_ratio: float = 0.15):
    """国关模式：随机标注订单级别超时等级"""
    levels = ["高风险", "中风险", "低风险"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn.execute("UPDATE qc_check_results SET overtime_risk = '' WHERE overtime_risk != ''")
        conn.commit()

        anomaly_orders = conn.execute(
            "SELECT order_code FROM qc_check_results WHERE status = 'anomaly'"
        ).fetchall()

        if not anomaly_orders:
            conn.close()
            return 0

        count = 0
        for row in anomaly_orders:
            if random.random() < risk_ratio:
                level = random.choice(levels)
                conn.execute(
                    "UPDATE qc_check_results SET overtime_risk = ?, check_time = ? WHERE order_code = ?",
                    (level, now, row["order_code"])
                )
                count += 1

        conn.commit()
        print(f"[Mock超时-国关] {count}/{len(anomaly_orders)} 个异常订单标注了超时预警")
    finally:
        conn.close()

    return count


def mock_batch_sync(db_path: str, batch_count: int = 3):
    """中金模式：随机选N个异常订单标注"接近超时"，显示时按批次合并"""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        conn.execute("UPDATE qc_check_results SET overtime_risk = '' WHERE overtime_risk != ''")
        conn.commit()

        anomaly_orders = conn.execute(
            "SELECT order_code FROM qc_check_results WHERE status = 'anomaly'"
        ).fetchall()

        if not anomaly_orders:
            conn.close()
            return 0

        count = 0
        for row in anomaly_orders:
            if random.random() < 0.1:  # 10% 选中率
                remaining = random.randint(10, 45)
                label = f"接近超时(剩余{remaining}分钟)"
                conn.execute(
                    "UPDATE qc_check_results SET overtime_risk = ?, check_time = ? WHERE order_code = ?",
                    (label, now, row["order_code"])
                )
                count += 1

        conn.commit()
        print(f"[Mock超时-中金] {count}/{len(anomaly_orders)} 个订单标注超时预警")
    finally:
        conn.close()

    return count


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from qc_server.db import Database

    db = Database()
    mock_sync(db.db_path)
