"""
R8: 合成立方氧化锆备注检查（复刻 qc_web.html ruleR8 + 配为/伴格式校验）
"""
import re


class Rule:
    RULE_NAME = "R8_合成立方氧化锆备注检查"

    def apply(self, row: dict) -> str:
        # 质检结果不通过 → 正确（不做校验）
        if row.get('质检结果', '') == '不通过':
            return '正确'

        # 读取并清理空值字段（nan/none/空 统一为空字符串）
        material = str(row.get('商品材质', '')).strip()
        fitting = str(row.get('配件材质', '')).strip()
        gemstone = str(row.get('宝玉石结论', '')).strip()
        remark = str(row.get('备注', '')).strip()
        material, fitting, gemstone, remark = [
            '' if v.lower() in ('nan', 'none', '') else v
            for v in (material, fitting, gemstone, remark)
        ]

        CUBIC = '合成立方氧化锆'
        has_cubic_field = CUBIC in material or CUBIC in fitting  # 商详/配件含
        has_cubic_gem = CUBIC in gemstone                          # 结论含（包含）
        remark_has = CUBIC in remark                               # 备注含

        # 商详/配件 或 结论 出现立方氧化锆
        if has_cubic_field or has_cubic_gem:
            if not remark_has:
                return '漏备注'
            # 备注含立方氧化锆，还需检查是否用"配为/伴"格式（配/为/伴在立方氧化锆前面）
            if re.search(r'[配为伴].*' + CUBIC, remark):
                return '正确'
            return '多备注'

        # 商详/配件/结论 都没有立方氧化锆
        if remark_has:
            return '漏备注'
        return '正确'
