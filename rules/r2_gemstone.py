"""
R2 宝玉石判定规则

规则1 - 少备注: 宝玉石结论含"翡翠" → 备注必须含 翡翠(A货)/含其他矿物/颜色成因未定/颜色成因未做分析 之一
规则2 - 多备注(来源不匹配): 宝玉石结论不含"翡翠" → 但备注含 翡翠(A货)
规则3 - 多备注(重复): 括号外关键词至多出现一次，括号内不计入

判定优先级: 规则1(少备注) → 规则3(重复) → 规则2(来源不匹配)
重复比来源不匹配更具体，优先报告
"""

import re


# 需要检查的关键词（中英文括号两种形式，视为同一组）
KEYWORD_PAIRS = [
    ("翡翠(A货)", "翡翠（A货）"),  # 中英文括号视为同一个关键词
    ("含其他矿物", None),
    ("颜色成因未定", None),
    ("颜色成因未做分析", None),
]


class Rule:
    """宝玉石判定"""

    def apply(self, row: dict) -> str:
        gemstone = str(row.get("宝玉石结论", "")).strip().replace("\t", "")
        remark = str(row.get("备注", "")).strip().replace("\t", "")

        if gemstone in ("nan", "NaN", ""):
            gemstone = ""
        if remark in ("nan", "NaN", ""):
            remark = ""

        # 规则1: 少备注（最高优先级）
        if "翡翠" in gemstone:
            has_required = self._has_any_keyword(remark)
            if not has_required:
                return "少备注"

        # 规则3: 多备注(重复) — 括号外的关键词至多出现一次（优先于来源不匹配）
        if self._has_duplicate_outside(remark):
            return "多备注(重复)"

        # 规则2: 多备注(来源不匹配)
        if "翡翠" not in gemstone:
            if "翡翠(A货)" in remark or "翡翠（A货）" in remark:
                return "多备注(来源不匹配)"

        return "正常"

    @staticmethod
    def _has_any_keyword(remark: str) -> bool:
        """备注中是否包含任一关键词（中英文括号都识别）"""
        for kw, kw_alt in KEYWORD_PAIRS:
            if kw in remark:
                return True
            if kw_alt and kw_alt in remark:
                return True
        return False

    @staticmethod
    def _has_duplicate_outside(remark: str) -> bool:
        """检查括号外是否有关键词出现超过一次"""
        # 标记括号内的位置范围
        inside_positions = set()
        for m in re.finditer(r'[(（][^)）]*[)）]', remark):
            for i in range(m.start(), m.end()):
                inside_positions.add(i)

        for kw, kw_alt in KEYWORD_PAIRS:
            # 统一处理：中英文括号形式都视为同一个关键词
            count = 0
            for search_kw in [kw, kw_alt] if kw_alt else [kw]:
                start = 0
                while True:
                    pos = remark.find(search_kw, start)
                    if pos == -1:
                        break
                    # 关键词起始位置不在括号内 → 计入
                    if pos not in inside_positions:
                        count += 1
                    start = pos + len(search_kw)
            if count > 1:
                return True
        return False
