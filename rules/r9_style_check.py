"""
R9: 款式核实

逻辑:
- 质检结果=不通过 → 正确（引擎层全局预检）
- 饰品类型为空 → 正确
- 饰品类型=="饰品" → 正确（过于泛化，无法核对）
- 商品名称直接包含饰品类型 → 正确
- 收集商品名称中所有匹配的饰品类型词
- 不含饰品类型词 → 正确
- 过滤掉"饰品"（过于泛化）
- 别名映射：吊坠/挂件/挂坠/链坠 → 项链，手链 → 手串
- 遍历匹配词，归一后与饰品类型一致 → 正确
- 否则 → 异常
"""

import re


# 饰品类型词列表
TYPE_WORDS = ['摆件', '吊坠', '耳饰', '挂件', '挂坠', '戒指', '链坠', '饰品', '手串', '手链', '手镯', '项链']

# 别名映射
ALIAS_MAP = {
    '吊坠': '项链', '挂件': '项链', '挂坠': '项链', '链坠': '项链',
    '手链': '手串',
}


class Rule:
    """款式核实"""
    RULE_NAME = "R9_款式核实"

    def apply(self, row: dict) -> str:
        name = str(row.get('商品名称', '')).strip()
        jewelry_type = str(row.get('饰品类型', '')).strip()

        # 清洗NaN值
        if name.lower() in ('nan', 'none', ''):
            name = ''
        if jewelry_type.lower() in ('nan', 'none', ''):
            jewelry_type = ''

        # 饰品类型为空 → 正确
        if not jewelry_type:
            return '正确'

        # 饰品类型=="饰品"过于泛化，无法核对 → 正确
        if jewelry_type == '饰品':
            return '正确'

        # 商品名称直接包含饰品类型文字 → 正确
        if jewelry_type in name:
            return '正确'

        # 收集商品名称中所有匹配的饰品类型词
        matched_words = [w for w in TYPE_WORDS if w in name]

        # 不含饰品类型词 → 正确
        if not matched_words:
            return '正确'

        # 过滤掉"饰品"（过于泛化）
        filtered = [w for w in matched_words if w != '饰品']
        if not filtered:
            return '正确'

        # 归一化饰品类型
        normalized_type = ALIAS_MAP.get(jewelry_type, jewelry_type)

        # 遍历所有匹配词，只要有一个归一后与饰品类型一致即正确
        for w in filtered:
            normalized_word = ALIAS_MAP.get(w, w)
            if normalized_word == normalized_type:
                return '正确'

        return '异常'
