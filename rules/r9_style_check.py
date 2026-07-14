"""
R9: 款式核实（复刻 qc_web.html ruleR9）
"""

# JS typeWords
TYPE_WORDS = ['摆件', '吊坠', '耳饰', '挂件', '挂坠', '戒指', '链坠', '饰品', '手串', '手链', '手镯', '项链']

# JS aliasMap
ALIAS_MAP = {
    '吊坠': '项链', '挂件': '项链', '挂坠': '项链', '链坠': '项链',
    '手链': '手串'
}


class Rule:
    RULE_NAME = "R9_款式核实"

    def apply(self, row: dict) -> str:
        if row.get('质检结果', '') == '不通过':
            return '正确'

        name = str(row.get('商品名称', '')).strip()
        style = str(row.get('饰品类型', '')).strip()
        if name.lower() in ('nan', 'none', ''): name = ''
        if style.lower() in ('nan', 'none', ''): style = ''

        if not style:
            return '正确'
        if style == '饰品':
            return '正确'

        # 同步判断：商品名直接包含饰品类型
        if style in name:
            return '正确'

        # 收集商品名称中所有匹配的饰品类型词
        matched = [w for w in TYPE_WORDS if w in name]
        if not matched:
            return '正确'

        # 过滤"饰品"
        filtered = [w for w in matched if w != '饰品']
        if not filtered:
            return '正确'

        # 归一化饰品类型
        normalized_type = ALIAS_MAP.get(style, style)

        # 遍历匹配词，找归一后等于饰品类型的
        for w in filtered:
            normalized_w = ALIAS_MAP.get(w, w)
            if normalized_w == normalized_type:
                return '正确'

        return '异常'
