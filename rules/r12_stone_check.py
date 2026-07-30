"""
R12: 配石检查
检查备注项 - 当出现"配石未"时，配石前必须有修饰词，否则为漏备注
"""
import re


class Rule:
    RULE_NAME = "R12_配石检查"

    def apply(self, row: dict) -> str:
        if row.get('质检结果', '') == '不通过':
            return '正确'

        remark = str(row.get('备注', '')).strip()
        if not remark or '配石未' not in remark:
            return '正确'

        # 按分隔符拆分备注，逐段检查"配石"前是否有修饰词
        segments = re.split(r'[,，;；。、\s]+', remark)
        for seg in segments:
            if not seg:
                continue
            idx = seg.find('配石')
            if idx >= 0 and '未' in seg[idx:idx + 4]:
                before = seg[:idx].strip()
                if not before:
                    return '漏备注'

        # 所有"配石"前都有修饰词
        return '正确'
