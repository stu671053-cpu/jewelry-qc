#!/usr/bin/env python3
"""
数据库初始化脚本
创建 qic_orders 表（对标 Loupe QIC 导出格式）

用法: python init_db.py
"""

import sqlite3
from pathlib import Path

DB_DIR = Path(__file__).parent / "data"
DB_PATH = DB_DIR / "qic_quality.db"

DB_DIR.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# 读取并执行 schema.sql
schema_sql = (Path(__file__).parent / "data" / "schema.sql").read_text("utf-8")
cursor.executescript(schema_sql)

conn.commit()
conn.close()

print(f"✅ 数据库初始化完成: {DB_PATH}")
print("   表: qic_orders, qc_check_results")
