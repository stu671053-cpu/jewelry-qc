"""
R2: 宝玉石判定（复刻 qc_web.html ruleR2）
"""
import re

# JS NEGATIVE_WORDS
NEGATIVE_WORDS = ['含其他矿物', '颜色成因未定', '颜色成因未做分析', '成因未做分析', '充填', '修补']


def _has_neg_in_bracket(remark: str) -> bool:
    """检查负面词是否在括号内"""
    brackets = re.findall(r'[（(]([^）)]*)[）)]', remark)
    return any(any(w in b for w in NEGATIVE_WORDS) for b in brackets)


class Rule:
    RULE_NAME = "R2_宝玉石判定"

    def apply(self, row: dict) -> str:
        if row.get('质检结果', '') == '不通过':
            return '正确'

        gemstone = str(row.get('宝玉石结论', '')).strip()
        remark = str(row.get('备注', '')).strip()
        if gemstone.lower() in ('nan', 'none', ''): gemstone = ''
        if remark.lower() in ('nan', 'none', ''): remark = ''

        has_amark = '翡翠(A货)' in remark or '翡翠（A货）' in remark

        if '翡翠' not in gemstone:
            return '多备注' if has_amark else '正确'

        # 宝玉石结论 = 翡翠
        if has_amark:
            cui_bracket = re.search(r'翡翠[（(][Aa]货[）)]', remark)
            if not cui_bracket:
                return '多备注' if any(w in remark for w in NEGATIVE_WORDS) else '正确'
            cui_start = cui_bracket.start()
            cui_end = cui_start + len(cui_bracket.group(0))
            # 负面词是否在翡翠(A货)之外的括号内
            other_brackets = re.findall(r'[（(]([^）)]*)[）)]', remark)
            full_brackets = re.finditer(r'[（(][^）)]*[）)]', remark)
            neg_in_other = False
            for fb in full_brackets:
                if fb.start() != cui_start:
                    if any(w in fb.group() for w in NEGATIVE_WORDS):
                        neg_in_other = True
                        break
            if neg_in_other:
                return '正确'
            return '多备注' if any(w in remark for w in NEGATIVE_WORDS) else '正确'

        # 无翡翠(A货)
        return '漏备注' if _has_neg_in_bracket(remark) else '正确'
