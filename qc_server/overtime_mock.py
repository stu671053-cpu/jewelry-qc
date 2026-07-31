"""
超时预警 Mock 模块 — 本地测试用
模拟外部时效 API，随机给部分异常订单标注超时等级
"""
import sqlite3
import random
from pathlib import Path
from datetime import datetime


def mock_sync(db_path: str, risk_ratio: float = 0.15):
    """
    随机抽取部分异常订单标注超时等级
    risk_ratio: 标注比例（默认 15%）
    同时更新 check_time 确保出现在当日异常列表
    """
    levels = ["高风险", "中风险", "低风险"]
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        # 清除旧超时标记
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
        print(f"[Mock超时] {count}/{len(anomaly_orders)} 个异常订单标注了超时预警")
    finally:
        conn.close()

    return count


if __name__ == "__main__":
    import os, sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from qc_server.db import Database

    db = Database()
    mock_sync(db.db_path)
