"""
R6: 玛瑙（覆膜）备注检查（复刻 qc_web.html ruleR6）
"""
import re


class Rule:
    RULE_NAME = "R6_玛瑙覆膜检查"

    def apply(self, row: dict) -> str:
        if row.get('质检结果', '') == '不通过':
            return '正确'

        material = str(row.get('商品材质', '')).strip()
        gemstone = str(row.get('宝玉石结论', '')).strip()
        remark = str(row.get('备注', '')).strip()
        for v in [material, gemstone, remark]:
            if v.lower() in ('nan', 'none', ''): v = ''

        # Branch 1: 玛瑙/玉髓（覆膜）
        if material == '玛瑙/玉髓（覆膜）':
            if gemstone == '玛瑙' or gemstone == '玛瑙（覆膜）' or not gemstone:
                return '正确'
            if '玛瑙' in remark or '玛瑙（覆膜）' in remark:
                return '正确'
            return '需核实结论'

        # Branch 2: 商品材质包含"玛瑙"（非覆膜）
        if '玛瑙' in material:
            if gemstone == '玛瑙' or gemstone == '玉髓' or gemstone == '':
                return '正确'
            if gemstone == '玛瑙（覆膜）':
                return '应驳回'
            # P节点：备注含玛瑙(覆膜)→应驳回，含玛瑙→正确，都不含→需核实
            if '玛瑙（覆膜）' in remark or '玛瑙(覆膜)' in remark:
                return '应驳回'
            if '玛瑙' in remark:
                return '正确'
            return '需核实结论'

        # Branch 3: 其他材质（不含玛瑙）
        if gemstone == '玛瑙（覆膜）' or gemstone == '玛瑙':
            return '正确'
        if '玛瑙（覆膜）' in remark or '玛瑙(覆膜)' in remark:
            if re.search(r'[配为伴].*玛瑙[（(]覆膜[）)]', remark):
                return '正确'
            return '需核实备注'
        return '正确'
