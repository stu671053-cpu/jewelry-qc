"""
QC 规则执行服务
- 封装 engine.py 的调用
- 字段名与 QIC 完全一致，无需映射
- 返回结构化检测结果
"""

import os
import sys
import time
from pathlib import Path

# 将项目根目录加入 sys.path，以便导入 engine 和 rules
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from engine import QCEngine

TENANT = os.environ.get("TENANT", "")
OVERTIME_THRESHOLD = 3.5 * 3600  # 3.5小时 = 12600秒


class QCService:
    """质检规则执行服务"""

    # 判定结果中的"正常"、"正确"关键词
    NORMAL_KEYWORDS = {"正常", "正确", "质检通过", "备注无误", ""}

    def __init__(self):
        self.engine = QCEngine()
        self.rule_names = [r["name"] for r in self.engine.rules]
        self.rule_columns = [r["column"] for r in self.engine.rules]
        print(f"[QC] 引擎已加载 {len(self.rule_names)} 条规则: {self.rule_names}")

    def _check_overtime(self, order: dict) -> str:
        """
        超时预警判断（仅中金租户）
        批次生成时间距今 > 3.5小时 且状态未完成 → 预警
        返回: 空字符串（无需预警）或 预警消息文本
        """
        if TENANT != "中金":
            return ""

        batch_time_raw = order.get("批次生成时间", "")
        order_status = str(order.get("状态", "") or "")
        finish_time_raw = str(order.get("质检完成时间", "") or "")

        # 已完成（status=503）→ 不预警
        if order_status == "503":
            return ""

        # 质检已完成（质检完成时间 ≤ 当前时间）→ 不预警
        try:
            finish_ts = int(finish_time_raw.lstrip("-"))
            if finish_ts > 0 and finish_ts <= int(time.time()):
                return ""
        except (ValueError, TypeError):
            pass

        # 解析批次生成时间（支持10位秒/13位毫秒）
        try:
            ts = int(str(batch_time_raw).lstrip("-"))
            if ts <= 0:
                return ""
            if len(str(ts)) == 13:
                ts = ts // 1000
        except (ValueError, TypeError):
            return ""

        elapsed = int(time.time()) - ts
        if elapsed <= OVERTIME_THRESHOLD:
            return ""

        return "异常"

    def check_order(self, order: dict) -> dict:
        """
        检测单条订单（全状态都过一遍规则）
        order: 数据库行（dict），字段名与规则引擎一致
        返回: { results: {列名: 判定}, status: 'ok'|'anomaly', anomalies: [...] }
        """
        results = self.engine.apply_row(order)

        # 收集异常
        anomalies = []
        for rule in self.engine.rules:
            col = rule["column"]
            val = results.get(col, "")
            if val and val not in self.NORMAL_KEYWORDS:
                anomalies.append({
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "column": col,
                    "value": val,
                })

        # 中金专属：超时预警（服务层伪规则）
        overtime_msg = self._check_overtime(order)
        results["超时预警"] = overtime_msg or "正常"
        if overtime_msg:
            anomalies.append({
                "rule_id": "overtime",
                "rule_name": "超时预警",
                "column": "overtime_risk",
                "value": overtime_msg,
            })

        return {
            "results": results,
            "status": "anomaly" if anomalies else "ok",
            "anomalies": anomalies,
        }

    def check_batch(self, orders: list) -> list:
        """
        批量检测全部订单（不分状态）
        单条失败不影响其他订单，返回: [{ order_code, results, status, anomalies }]
        """
        output = []
        for order in orders:
            try:
                order_code = order.get("订单码", "")
                result = self.check_order(order)
                output.append({
                    "order_code": order_code,
                    "order": order,
                    **result,
                })
            except Exception as e:
                # 单条失败不中断整个批次，返回 error 状态
                order_code = order.get("订单码", "unknown")
                output.append({
                    "order_code": order_code,
                    "order": order,
                    "results": {"错误": str(e)[:200]},
                    "status": "error",
                    "anomalies": [],
                })
        return output

    def format_anomaly_message(self, check_result: dict) -> str:
        """
        格式化异常消息（用于通知）
        """
        order_code = check_result.get("order_code", "")
        anomalies = check_result.get("anomalies", [])
        order = check_result.get("order", {})

        lines = [f"## ⚠️ 质检异常提醒"]
        lines.append(f"**订单码**: {order_code}")
        lines.append(f"**商品名称**: {order.get('商品名称', '')}")
        lines.append(f"**质检结果**: {order.get('质检结果', '')}")
        lines.append("")
        lines.append("**异常项**:")
        for a in anomalies:
            lines.append(f"- **{a['rule_name']}**: {a['value']}")

        return "\n".join(lines)
