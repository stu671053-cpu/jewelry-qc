"""
R13 沉香木带宝检查
- 商品名称 或 商品材质 含「沉香」时，必须带「木带宝」(wood_jewel) 标签
- 未带标签 → 异常「漏木带宝标签」
- 不含沉香 → 正确
"""


class Rule:
    def __init__(self):
        self.name = "沉香木带宝检查"
        self.column = "沉香木带宝检查"

    def apply(self, row: dict) -> str:
        # 全局预检（engine 已处理质检结果=不通过，这里兜底）
        if (row.get("质检结果") or "").strip() == "不通过":
            return "正确"

        product_name = (row.get("商品名称") or "").strip()
        material = (row.get("商品材质") or "").strip()

        # 是否含沉香
        has_chenxiang = ("沉香" in product_name) or ("沉香" in material)
        if not has_chenxiang:
            return "正确"

        # 含沉香 → 必须有木带宝标签
        wood_tag = (row.get("是否木带宝") or "").strip()
        # 兼容多种取值: "是" / "true" / 含 wood_jewel 的原始串
        has_wood = wood_tag in ("是", "True", "true", "1") or "wood_jewel" in wood_tag
        if has_wood:
            return "正确"

        return "漏木带宝标签"
