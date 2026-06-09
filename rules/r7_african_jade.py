"""
R7: 非洲翠备注检查

逻辑:
- 商品名称、商品材质、配件材质 中任一包含"非洲翠" → has_in_fields = True
- 备注包含"非洲翠" → has_in_remark = True

判断:
- has_in_fields=True,  has_in_remark=True  → 正确
- has_in_fields=True,  has_in_remark=False → 漏备注
- has_in_fields=False, has_in_remark=True  → 多备注
- has_in_fields=False, has_in_remark=False → 正确
"""


class Rule:
    RULE_NAME = "R7_非洲翠备注检查"

    def apply(self, row: dict) -> str:
        name = str(row.get('商品名称', '')).strip()
        material = str(row.get('商品材质', '')).strip()
        accessory = str(row.get('配件材质', '')).strip()
        remark = str(row.get('备注', '')).strip()

        # 清洗NaN值
        for field in (name, material, accessory, remark):
            if field.lower() in ('nan', 'none', ''):
                field = ''

        # 检查字段中是否包含"非洲翠"
        fields_text = name + material + accessory
        has_in_fields = '非洲翠' in fields_text

        # 检查备注中是否包含"非洲翠"
        has_in_remark = '非洲翠' in remark

        if has_in_fields:
            if has_in_remark:
                return '正确'
            else:
                return '漏备注'
        else:
            if has_in_remark:
                return '多备注'
            else:
                return '正确'
