"""
R8: 合成立方氧化锆备注检查

逻辑:
- 配件材质包含"合成立方氧化锆" → A=True
- 宝玉石结论包含"合成立方氧化锆" → B=True
- 备注包含"合成立方氧化锆" → C=True
- 备注中"合成立方氧化锆"前面有"配/为/伴" → D=True

判断:
1. A=True,  B=True,  C任意      → 正确
2. A=True,  B=False, C=True     → 正确
3. A=True,  B=False, C=False    → 漏备注
4. A=False, B=False, C=False    → 正确
5. A=False, B=False, C=True, D=True   → 正确
6. A=False, B=False, C=True, D=False  → 多备注
"""

import re


class Rule:
    RULE_NAME = "R8_合成立方氧化锆备注检查"

    def apply(self, row: dict) -> str:
        accessory = str(row.get('配件材质', '')).strip()
        gemstone = str(row.get('宝玉石结论', '')).strip()
        remark = str(row.get('备注', '')).strip()

        # 清洗NaN值
        for field in (accessory, gemstone, remark):
            if field.lower() in ('nan', 'none', ''):
                field = ''

        a = '合成立方氧化锆' in accessory
        b = '合成立方氧化锆' in gemstone
        c = '合成立方氧化锆' in remark
        d = bool(re.search(r'[配为伴].*合成立方氧化锆', remark))

        if a:
            # 配件材质包含
            if b:
                return '正确'      # 情况1
            else:
                # 宝玉石结论不包含
                if c:
                    return '正确'  # 情况2
                else:
                    return '漏备注'  # 情况3
        else:
            # 配件材质不包含
            if c:
                if d:
                    return '正确'  # 情况5
                else:
                    return '多备注'  # 情况6
            else:
                return '正确'      # 情况4
