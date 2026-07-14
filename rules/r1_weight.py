"""
R1: 重量判定（复刻 qc_web.html ruleR1）
"""
import re


class Rule:
    RULE_NAME = "R1_重量判定"

    def apply(self, row: dict) -> str:
        # 质检不通过 → 正确
        if row.get('质检结果', '') == '不通过':
            return '正确'

        weight = str(row.get('重量', '')).strip()
        if weight.lower() in ('nan', 'none', ''):
            weight = ''
        if not weight:
            return ''

        # 去掉括号内的额外说明
        cleaned = re.sub(r'[（(][^）)]*[）)]', '', weight).strip()

        # 判断1: 去掉括号后只有 g或克（无数值）
        if cleaned in ('g', '克'):
            return '正确' if str(row.get('状态', '')).strip() == '质检中' else '错误'

        # 判断2: 格式检查 — 两位小数+g或克
        if not re.match(r'^(\d{1,5})\.(\d{2})(g|克)$', cleaned):
            return '错误'

        return '正确'
