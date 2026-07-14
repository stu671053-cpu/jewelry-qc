"""
R10: 重量比对（复刻 qc_web.html ruleR10 + SKU优先）
"""
import re


class Rule:
    RULE_NAME = "R10_重量比对"

    def apply(self, row: dict) -> str:
        if row.get('质检结果', '') == '不通过':
            return '正确'

        # 优先 SKU质量，其次商品质量
        sku_weight = str(row.get('SKU质量', '')).strip()
        product_weight = str(row.get('商品质量', '')).strip()
        quality_weight = sku_weight if sku_weight else product_weight
        weight = str(row.get('重量', '')).strip()
        material = str(row.get('商品材质', '')).strip()
        inlay = str(row.get('镶嵌材质', '')).strip()
        fitting = str(row.get('配件材质', '')).strip()

        for v in [quality_weight, weight, material, inlay, fitting]:
            if v.lower() in ('nan', 'none', ''): v = ''

        # 非贵金属不检查
        all_mats = material + inlay + fitting
        if not re.search(r'[金铂银]', all_mats):
            return '正确'

        # 商品质量提取单纯克重
        q_match = re.match(r'^(\d{1,5}(?:\.\d{1,2})?)\s*(g|克)$', quality_weight)
        if not q_match:
            return '正确'
        q_val = float(q_match.group(1))

        # 重量提取
        w_match = re.search(r'(\d{1,5}(?:\.\d{1,2})?)\s*(g|克)', weight)
        if not w_match:
            return '正确'
        w_val = float(w_match.group(1))

        if w_val >= q_val:
            return '正确'

        diff = round(abs(q_val - w_val), 2)
        if '银' in all_mats:
            return '异常' if diff > 0.1 else '正常'
        return '异常' if diff > 0.01 else '正常'
