"""
R3: 金含量备注检查（复刻 qc_web.html ruleR3）
"""
import re


def _has_standalone_999(val: str) -> bool:
    """检查字段中是否有独立的999（前后不是数字）"""
    if not val:
        return False
    # 含"足银"则跳过
    if '足银' in val and '999' in val:
        return False
    return bool(re.search(r'(?<!\d)999(?!\d)', val))


def _has_zujin_field(val: str) -> bool:
    """检查是否含足金关键词"""
    keywords = ['足金', '足金999', '足金9999', '足金（金含量≥999‰）',
                '足金（金含量999‰）', '足金（金含量≥999.9‰）', '足金（金含量999.9‰）']
    return any(k in val for k in keywords)


class Rule:
    RULE_NAME = "R3_金含量备注检查"

    def apply(self, row: dict) -> str:
        if row.get('质检结果', '') == '不通过':
            return '正确'

        name = str(row.get('商品名称', '')).strip()
        material = str(row.get('商品材质', '')).strip()
        inlay = str(row.get('镶嵌材质', '')).strip()
        fitting = str(row.get('配件材质', '')).strip()
        precious = str(row.get('贵金属结论', '')).strip()
        remark = str(row.get('备注', '')).strip()
        quality = str(row.get('商品质量', '')).strip()

        for v in [name, material, inlay, fitting, precious, remark, quality]:
            if v.lower() in ('nan', 'none', ''): v = ''

        precious_ok = precious == '足金'
        remark_ok = '金含量≥999‰' in remark
        has_999 = _has_standalone_999(name) or _has_standalone_999(material) or \
                  _has_standalone_999(inlay) or _has_standalone_999(quality) or \
                  _has_standalone_999(fitting)

        # 路径1：结论字段都为空
        gstone = str(row.get('宝玉石结论', '')).strip()
        if not precious and not gstone:
            return '核实是否为复检' if '金含量≥999‰' in remark else '正确'

        # 路径2：有独立999
        if has_999:
            has_zujin = _has_zujin_field(name) or _has_zujin_field(material) or \
                        _has_zujin_field(inlay) or _has_zujin_field(quality) or \
                        _has_zujin_field(fitting)
            if has_zujin:
                if precious_ok:
                    return '正确' if remark_ok else '漏备注'
                else:
                    return '正确'
            else:
                if precious_ok:
                    return '正确'
                else:
                    return '多备注' if remark_ok else '正确'
        else:
            # 路径3：无独立999
            has_zujin = _has_zujin_field(name) or _has_zujin_field(material) or \
                        _has_zujin_field(inlay) or _has_zujin_field(quality) or \
                        _has_zujin_field(fitting)
            if has_zujin:
                if precious_ok:
                    return '正确'
                else:
                    return '需核实结论'
            else:
                if precious_ok:
                    return '需再次核对确认' if remark_ok else '正确'
                else:
                    return '多备注' if remark_ok else '正确'
