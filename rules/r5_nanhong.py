"""
R5: 南红备注检查（复刻 qc_web.html ruleR5）
"""
import re


class Rule:
    RULE_NAME = "R5_南红备注检查"

    def apply(self, row: dict) -> str:
        if row.get('质检结果', '') == '不通过':
            return '正确'

        gemstone = str(row.get('宝玉石结论', '')).strip()
        metal = str(row.get('贵金属结论', '')).strip()
        # 结论都为空 → 正确
        if not gemstone and not metal:
            return '正确'

        remark = str(row.get('备注', '')).strip()
        name = str(row.get('商品名称', '')).strip()
        material = str(row.get('商品材质', '')).strip()
        fitting = str(row.get('配件材质', '')).strip()

        for v in [remark, name, material, fitting]:
            if v.lower() in ('nan', 'none', ''): v = ''

        KEYWORDS = ['南红', '保山红', '凉山红', '川料红', '瓦西', '九口红', '锦红']

        # 字段(去括号后)含关键词
        def field_has(field):
            if not field:
                return False
            no_brackets = re.sub(r'[（(][^）)]*[）)]', '', field)
            return any(kw in no_brackets for kw in KEYWORDS)

        triggered = any(field_has(f) for f in [name, material, fitting])

        if triggered:
            return '正确' if '南红' in remark else '漏备注'

        # 未触发
        prefix_match = bool(re.search(r'[配为伴].*南红', remark)) or remark == ''
        if prefix_match:
            return '正确'

        # 备注不含南红
        if '南红' not in remark:
            return '正确'

        # 宝玉石结论 == 玛瑙
        if gemstone == '玛瑙':
            return '正确'

        return '核实'
