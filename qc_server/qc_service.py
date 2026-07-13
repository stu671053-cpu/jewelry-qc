"""
QC 规则执行服务
- 封装 engine.py 的调用
- 字段名与 QIC 完全一致，无需映射
- 返回结构化检测结果
"""

import sys
from pathlib import Path

# 将项目根目录加入 sys.path，以便导入 engine 和 rules
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from engine import QCEngine


class QCService:
    """质检规则执行服务"""

    # 判定结果中的"正常"、"正确"关键词
    NORMAL_KEYWORDS = {"正常", "正确", "质检通过", "备注无误", ""}

    def __init__(self):
        self.engine = QCEngine()
        self.rule_names = [r["name"] for r in self.engine.rules]
        self.rule_columns = [r["column"] for r in self.engine.rules]
        print(f"[QC] 引擎已加载 {len(self.rule_names)} 条规则: {self.rule_names}")

    def check_order(self, order: dict) -> dict:
        """
        检测单条订单
        order: 数据库行（dict），字段名与规则引擎一致
        返回: { results: {列名: 判定}, status: 'ok'|'anomaly'|'skipped', anomalies: [...] }
        """
        # 未完成的订单不审查
        status = str(order.get("状态", "")).strip()
        if status and status != "503":
            results = {}
            for rule in self.engine.rules:
                results[rule["column"]] = "正确"
            return {
                "results": results,
                "status": "ok",
                "anomalies": [],
            }

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

        return {
            "results": results,
            "status": "anomaly" if anomalies else "ok",
            "anomalies": anomalies,
        }

    def check_batch(self, orders: list) -> list:
        """
        批量检测订单（非503订单标记为跳过，避免重复拉取）
        返回: [{ order_code, results, status, anomalies }]
        """
        output = []
        skipped = 0
        for order in orders:
            order_code = order.get("订单码", "")

            # 跳过未完成的订单（标记为skipped，不再重复检查）
            status = str(order.get("状态", "")).strip()
            if status and status != "503":
                skipped += 1
                output.append({
                    "order_code": order_code,
                    "order": order,
                    "results": {},
                    "status": "skipped",
                    "anomalies": [],
                })
                continue

            result = self.check_order(order)
            output.append({
                "order_code": order_code,
                "order": order,
                **result,
            })

        if skipped:
            print(f"[QC] 跳过 {skipped} 条未完成订单（状态 != 503）")
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
