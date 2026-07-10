"""
R5: 南红备注检查
按用户流程图实现（2026-06-08）

优先级0（最高）: 质检结果=不通过 → 正确（跳过后续）
正常流程:
1. 【商品名称、商品材质、配件材质】中包含
   【南红、保山红、凉山红、川料红、瓦西、九口红、锦红】字样（不被括号包裹）？
   - 是（触发）→ 备注有南红？是→正确 / 否→漏备注
   - 否（未触发）→ 继续

2. 【宝玉石结论】为玛瑙？
   - 是 → 备注有南红？
     - 格式匹配（配/为/伴+任一关键词：南红、保山红、凉山红等）→ 正确
     - 格式不匹配（孤立南红）→ 需核实
     - 无南红 → 正确
   - 否 → 继续

3. 【备注】包含【配/为/伴】【其他文字】【南红】或【备注】为空？
   - 是 → 正确
   - 否 → 多备注

注意: 空值=正确，不额外区分空分类
"""
import re

# 南红相关关键词
NANHONG_KEYWORDS = [
    '南红', '保山红', '凉山红', '川料红', '瓦西', '九口红', '锦红',
]

# 配/为/伴 + 关键词 的格式正则
_FORMAT_PATTERN = re.compile(r'[配为伴].*(?:' + '|'.join(NANHONG_KEYWORDS) + r')')

# 触发检查的字段
TRIGGER_FIELDS = ['商品名称', '商品材质', '配件材质']


class Rule:
    RULE_NAME = "R5_南红备注检查"

    def apply(self, row: dict) -> str:
        remark = str(row.get('备注', '')).strip()
        gemstone = str(row.get('宝玉石结论', '')).strip()
        qc_result = str(row.get('质检结果', '')).strip()

        # 清洗NaN值
        if remark.lower() in ('nan', 'none', ''):
            remark = ''
        if gemstone.lower() in ('nan', 'none', ''):
            gemstone = ''
        if qc_result.lower() in ('nan', 'none', ''):
            qc_result = ''

        # ========== 优先级0（最高）: 质检结果=不通过 → 正确 ==========
        if qc_result == '不通过':
            return '正确'

        # ========== 判断1: 触发条件 - 关键字检查 ==========
        triggered = self._check_trigger(row)

        if triggered:
            # ========== 触发分支: 备注有南红？ ==========
            if '南红' in remark:
                return '正确'
            else:
                return '漏备注'

        # ========== 未触发分支 ==========
        # ========== 判断2: 宝玉石结论为玛瑙？ ==========
        if gemstone == '玛瑙':
            if self._has_any_keyword(remark):
                # 格式匹配（配/为/伴+任一关键词）→ 正确
                if _FORMAT_PATTERN.search(remark):
                    return '正确'
                # 格式不匹配 → 需核实
                return '需核实'
            else:
                return '正确'  # 玛瑙但与南红无关

        # ========== 判断3: 备注格式检查 ==========
        if not self._has_any_keyword(remark):
            return '正确'  # 无关数据 → 正确

        # 备注包含"配/为/伴"+其他文字+"南红" → 正确
        # 例如: "配玛瑙（南红）"、"红色部分商称为南红玛瑙"
        if _FORMAT_PATTERN.search(remark):
            return '正确'

        # 备注含南红但不符合格式 → 多备注
        return '多备注'

    def _has_any_keyword(self, text: str) -> bool:
        """检查文本是否包含任一南红相关关键词"""
        for kw in NANHONG_KEYWORDS:
            if kw in text:
                return True
        return False

    def _check_trigger(self, row: dict) -> bool:
        """检查是否触发：三个字段之一包含南红相关关键词（不被括号包裹）"""
        for field in TRIGGER_FIELDS:
            val = str(row.get(field, '')).strip()
            if val.lower() in ('nan', 'none', ''):
                continue

            # 移除所有括号内容（包括中英括号），再检查关键词
            text_no_brackets = re.sub(r'[（(][^）)]*[）)]', '', val)

            for kw in NANHONG_KEYWORDS:
                if kw in text_no_brackets:
                    return True

        return False
