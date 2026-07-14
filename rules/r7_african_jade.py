"""
R7: 非洲翠备注检查（复刻 qc_web.html ruleR7）
"""


class Rule:
    RULE_NAME = "R7_非洲翠备注检查"

    def apply(self, row: dict) -> str:
        if row.get('质检结果', '') == '不通过':
            return '正确'

        name = str(row.get('商品名称', '')).strip()
        material = str(row.get('商品材质', '')).strip()
        fitting = str(row.get('配件材质', '')).strip()
        remark = str(row.get('备注', '')).strip()
        for v in [name, material, fitting, remark]:
            if v.lower() in ('nan', 'none', ''): v = ''

        has_african = '非洲翠' in name or '非洲翠' in material or '非洲翠' in fitting
        remark_has = '非洲翠' in remark

        if has_african:
            return '正确' if remark_has else '漏备注'
        if remark_has:
            return '正确' if has_african else '漏备注'
        return '正确'
