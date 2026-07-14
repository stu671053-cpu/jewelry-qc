"""
R4: 足金净金重检查（复刻 qc_web.html ruleR4）
"""
import re


class Rule:
    RULE_NAME = "R4_足金净金重检查"

    def apply(self, row: dict) -> str:
        if row.get('质检结果', '') == '不通过':
            return '正确'

        material = str(row.get('商品材质', '')).strip()
        gemstone = str(row.get('宝玉石结论', '')).strip()
        precious = str(row.get('贵金属结论', '')).strip()
        weight = str(row.get('重量', '')).strip()
        remark = str(row.get('备注', '')).strip()
        for v in [material, gemstone, precious, weight, remark]:
            if v.lower() in ('nan', 'none', ''): v = ''

        # 材质不含金 → 正确
        if '金' not in material:
            return '正确'

        # 贵金属结论必须为足金
        if precious != '足金':
            return '正确'

        # 提取净金重
        net_match = re.search(r'净金重[：:]*\s*(\d+(?:\.\d{1,2})?)\s*(?:g|克)', weight)
        if not net_match:
            return '正确'
        
        net_val = net_match.group(1)
        
        # 宝玉石结论为空且材质仅含金
        if gemstone:
            return '正确'

        # 备注检查
        remark_ok = '净金重' in remark and net_val in remark
        return '正确' if remark_ok else '漏备注净金重'
