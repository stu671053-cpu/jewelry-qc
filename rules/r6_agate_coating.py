"""
R6: 玛瑙（覆膜）备注检查
严格按照用户JSON逻辑图实现（2026-06-09）

逻辑节点:
A: 开始 → B
B: 商品材质 精确等于 "玛瑙/玉髓（覆膜）"？
   - 是 → C
   - 否 → G
C: 宝玉石结论=玛瑙 / =玛瑙（覆膜）？
   - 是 → D（正确）
   - 否 → E
E: 备注=玛瑙 / =玛瑙（覆膜）？
   - 是 → D（正确）
   - 否 → F（需核实结论）
G: 商品材质 包含 "玛瑙"？
   - 是 → M
   - 否 → H
H: 宝玉石结论≠玛瑙 并且 ≠玛瑙（覆膜）？
   - 是 → I
   - 否 → M
I: 备注文本内包含 玛瑙（覆膜）？
   - 是 → J
   - 否 → D（正确）
J: "玛瑙（覆膜）"前面存在文字：配/为/伴？
   - 是 → D（正确）
   - 否 → L（需核实备注）
M: 宝玉石结论 精确等于 玛瑙 或者 玉髓 或者为 空值？
   - 是 → D（正确）
   - 否 → N
N: 宝玉石结论 精确等于 玛瑙（覆膜）？
   - 是 → O（应驳回）
   - 否 → P
P: 备注文本内包含 玛瑙（覆膜）？
   - 是 → O（应驳回）
   - 否 → 备注文本内包含 玛瑙？
      - 是 → F（需核实结论）
      - 否 → D（正确）
"""

import re


class Rule:
    RULE_NAME = "R6_玛瑙覆膜检查"

    def apply(self, row: dict) -> str:
        material = str(row.get('商品材质', '')).strip()
        gemstone = str(row.get('宝玉石结论', '')).strip()
        remark = str(row.get('备注', '')).strip()

        # 清洗NaN值
        if material.lower() in ('nan', 'none', ''):
            material = ''
        if gemstone.lower() in ('nan', 'none', ''):
            gemstone = ''
        if remark.lower() in ('nan', 'none', ''):
            remark = ''

        # ========== A → B: 商品材质 精确等于 "玛瑙/玉髓（覆膜）"？ ==========
        if material == '玛瑙/玉髓（覆膜）':
            # B=是 → C: 宝玉石结论=玛瑙 / =玛瑙（覆膜）？
            if gemstone == '玛瑙' or gemstone == '玛瑙（覆膜）':
                return '正确'  # C=是 → D
            else:
                # C=否 → E: 备注=玛瑙 / =玛瑙（覆膜）？
                if remark == '玛瑙' or remark == '玛瑙（覆膜）':
                    return '正确'  # E=是 → D
                else:
                    return '需核实结论'  # E=否 → F
        else:
            # B=否 → G: 商品材质 包含 "玛瑙"？
            if '玛瑙' in material:
                # G=是 → M: 宝玉石结论 精确等于 玛瑙 或者 玉髓 或者为 空值？
                if gemstone in ('玛瑙', '玉髓', ''):
                    return '正确'  # M=是 → D
                else:
                    # M=否 → N: 宝玉石结论 精确等于 玛瑙（覆膜）？
                    if gemstone == '玛瑙（覆膜）':
                        return '应驳回'  # N=是 → O
                    else:
                        # N=否 → P: 备注文本内包含 玛瑙（覆膜）？
                        if '玛瑙（覆膜）' in remark or '玛瑙(覆膜)' in remark:
                            return '应驳回'  # P=是 → O
                        # P：备注文本内包含 玛瑙？
                        elif '玛瑙' in remark:
                            return '需核实结论'  # 备注重 → 需核实
                        else:
                            return '正确'  # 都不含 → 正确
            else:
                # G=否 → H: 宝玉石结论≠玛瑙 并且 ≠玛瑙（覆膜）？
                if gemstone != '玛瑙' and gemstone != '玛瑙（覆膜）':
                    # H=是 → I: 备注文本内包含 玛瑙（覆膜）？
                    if '玛瑙（覆膜）' in remark or '玛瑙(覆膜)' in remark:
                        # I=是 → J: "玛瑙（覆膜）"前面存在文字：配/为/伴？
                        if re.search(r'[配为伴].*玛瑙[（(]覆膜[）)]', remark):
                            return '正确'  # J=是 → D
                        else:
                            return '需核实备注'  # J=否 → L
                    else:
                        return '正确'  # I=否 → D
                else:
                    # H=否 → M: 宝玉石结论 精确等于 玛瑙 或者 玉髓 或者为 空值？
                    if gemstone in ('玛瑙', '玉髓', ''):
                        return '正确'  # M=是 → D
                    else:
                        # M=否 → N: 宝玉石结论 精确等于 玛瑙（覆膜）？
                        # 此处H=否，说明gemstone一定是'玛瑙（覆膜）'
                        return '应驳回'  # N=是 → O
