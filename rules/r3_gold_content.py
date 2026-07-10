"""
R3 金含量备注检查规则

前置条件: 质检结果 = 空值 或 "通过"
触发条件(至少一个): 5字段含独立999 / 贵金属结论="足金" / 备注含"金含量≥999‰"
核验条件(必须全满足): 独立999 + 贵金属结论="足金" + 备注含"金含量≥999‰"

注意: 独立999排除"足银"带来的999
"""

import re


# 需要检查999的5个字段
FIELDS_999 = ["商品名称", "商品材质", "镶嵌材质", "商品质量", "配件材质"]


class Rule:
    """金含量备注检查"""

    def apply(self, row: dict) -> str:
        qc_result = str(row.get("质检结果", "")).strip().replace("\t", "")
        remark = str(row.get("备注", "")).strip().replace("\t", "")
        precious_metal = str(row.get("贵金属结论", "")).strip().replace("\t", "")

        if qc_result in ("nan", "NaN", ""):
            qc_result = ""
        if remark in ("nan", "NaN", ""):
            remark = ""
        if precious_metal in ("nan", "NaN", ""):
            precious_metal = ""

        # 前置条件: 质检结果=空 或 "通过"
        if qc_result and qc_result != "通过":
            return "正常"

        # 触发条件: 5个字段中有独立的999
        has_999 = self._has_standalone_999(row)

        if not has_999:
            return "正常"  # 没有独立999，不触发R3

        # 核验条件(必须全满足): 贵金属结论="足金" + 备注含"金含量≥999‰"
        is_zujin = (precious_metal == "足金")
        has_gold_content = ("金含量≥999‰" in remark)

        missing = []
        if not is_zujin:
            missing.append("贵金属结论非足金")
        if not has_gold_content:
            missing.append("备注缺金含量≥999‰")

        if missing:
            return "异常(" + "; ".join(missing) + ")"

        return "正常"

    @staticmethod
    def _has_standalone_999(row: dict) -> bool:
        """检查5个字段中是否有独立的999（排除足银）"""
        for field in FIELDS_999:
            val = str(row.get(field, "")).strip().replace("\t", "")
            if val in ("nan", "NaN", ""):
                continue
            # 排除足银999
            if "足银" in val and "999" in val:
                continue
            # 独立999: 前后不是数字
            if re.search(r'(?<!\d)999(?!\d)', val):
                return True
        return False
