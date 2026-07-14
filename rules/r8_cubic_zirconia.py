"""
R8: 合成立方氧化锆备注检查（复刻 qc_web.html ruleR8）
"""


class Rule:
    RULE_NAME = "R8_合成立方氧化锆备注检查"

    def apply(self, row: dict) -> str:
        if row.get('质检结果', '') == '不通过':
            return '正确'

        material = str(row.get('商品材质', '')).strip()
        fitting = str(row.get('配件材质', '')).strip()
        gemstone = str(row.get('宝玉石结论', '')).strip()
        remark = str(row.get('备注', '')).strip()
        for v in [material, fitting, gemstone, remark]:
            if v.lower() in ('nan', 'none', ''): v = ''

        CUBIC = '合成立方氧化锆'
        has_cubic_field = CUBIC in material or CUBIC in fitting
        has_cubic_gem = gemstone == CUBIC
        remark_has = CUBIC in remark

        if has_cubic_field or has_cubic_gem:
            return '正确' if remark_has else '漏备注'
        if remark_has:
            return '正确' if (has_cubic_field or has_cubic_gem) else '漏备注'
        return '正确'
