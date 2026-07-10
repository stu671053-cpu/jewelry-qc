"""
R10: 重量比对

逻辑:
- 质检结果=不通过 → 正确（引擎层全局预检）
- 商品材质+镶嵌材质+配件材质 不含"金"或"铂"或"银" → 正确（非贵金属不检查）
- 商品质量必须为单纯克重（严格匹配 数字+g/克，不含mm/cm/ct/克拉/括号）
- 重量提取首个数字+g/克模式
- 商品质量不是单纯克重 → 正确
- 重量无法解析为克重 → 正确（无法比对）
- 重量克重 >= 商品质量克重 → 正确（实重≥标重即合格）
- 差值计算：
  - 材质含"银" → 差值>0.1g → 异常
  - 镶嵌材质+配件材质含"金"或"铂" → 差值>0.01g → 异常
  - 其他 → 差值>0.01g → 异常
"""

import re


class Rule:
    """重量比对"""
    RULE_NAME = "R10_重量比对"

    def apply(self, row: dict) -> str:
        quality_weight = str(row.get('商品质量', '')).strip()
        weight = str(row.get('重量', '')).strip()
        material = str(row.get('商品材质', '')).strip()
        inlay_mat = str(row.get('镶嵌材质', '')).strip()
        fitting = str(row.get('配件材质', '')).strip()

        # 清洗NaN值
        for field in (quality_weight, weight, material, inlay_mat, fitting):
            if field.lower() in ('nan', 'none', ''):
                field = ''

        quality_weight = quality_weight.strip()
        weight = weight.strip()
        material = material.strip()
        inlay_mat = inlay_mat.strip()
        fitting = fitting.strip()

        # 第一步：商品材质+镶嵌材质+配件材质 含"金"或"铂"或"银"？
        all_materials = material + inlay_mat + fitting
        if not re.search(r'[金铂银]', all_materials):
            return '正确'

        # 商品质量提取单纯克重：严格匹配 数字+g/克
        quality_grams = self._extract_quality_gram(quality_weight)

        # 重量提取首个数字+g/克模式
        weight_grams = self._extract_weight_gram(weight)

        # 商品质量不是单纯克重 → 正确
        if quality_grams is None:
            return '正确'

        # 重量无法解析为克重 → 正确
        if weight_grams is None:
            return '正确'

        # 重量克重 >= 商品质量克重 → 正确
        if weight_grams >= quality_grams:
            return '正确'

        diff = round(abs(quality_grams - weight_grams), 2)

        # 材质含"银" → 容差0.1g
        if '银' in all_materials:
            return '异常' if diff > 0.1 else '正常'

        # 镶嵌材质+配件材质 含"金"或"铂" → 容差0.01g
        inlay_and_fitting = inlay_mat + fitting
        if re.search(r'[金铂]', inlay_and_fitting):
            return '异常' if diff > 0.01 else '正常'

        return '异常' if diff > 0.01 else '正常'

    @staticmethod
    def _extract_quality_gram(s: str):
        """商品质量必须为单纯克重：严格匹配 数字+g/克，不能含mm/cm/ct/克拉/括号"""
        if not s:
            return None
        if re.search(r'mm|cm|m\b|ct|克拉|[（(]', s):
            return None
        m = re.match(r'^(\d{1,5}(?:\.\d{1,2})?)\s*(g|克)$', s)
        return float(m.group(1)) if m else None

    @staticmethod
    def _extract_weight_gram(s: str):
        """重量只需包含单纯克重：从字符串中提取首个数字+g/克模式"""
        if not s:
            return None
        m = re.search(r'(\d{1,5}(?:\.\d{1,2})?)\s*(g|克)', s)
        return float(m.group(1)) if m else None
