"""
R8: 合成立方氧化锆备注检查

规则（按业务流程图）：
前提条件：
  ① 质检结果 = 不通过 → 不判断（正确）
  ② 质检结果 = 通过或空值，且宝玉石结论、贵金属结论同时为空 → 不判断（正确）

分支：
  1. 配件材质含「合成立方氧化锆」：
     - 结论或备注也含「合成立方氧化锆」→ 正确
     - 结论和备注都不含 → 漏备注
  2. 配件材质不含「合成立方氧化锆」：
     - 备注含「合成立方氧化锆」且「配/为/伴」在它前面 → 正确
     - 备注含「合成立方氧化锆」但「配/为/伴」不在前面 → 多备注
     - 备注不含 → 正确
"""
import re


class Rule:
    RULE_NAME = "R8_合成立方氧化锆备注检查"

    def apply(self, row: dict) -> str:
        # 前提①：质检结果不通过 → 不判断
        if row.get('质检结果', '') == '不通过':
            return '正确'

        # 读取字段
        fitting = str(row.get('配件材质', '')).strip()
        gemstone = str(row.get('宝玉石结论', '')).strip()
        metal_conclusion = str(row.get('贵金属结论', '')).strip()
        remark = str(row.get('备注', '')).strip()

        # 清理空值（nan/none/空 → ''）
        fitting, gemstone, metal_conclusion, remark = [
            '' if v.lower() in ('nan', 'none', '') else v
            for v in (fitting, gemstone, metal_conclusion, remark)
        ]

        # 前提②：质检结果通过/空 且 宝玉石结论、贵金属结论同时为空 → 不判断
        qc_result = str(row.get('质检结果', '')).strip()
        if qc_result.lower() in ('nan', 'none', ''):
            qc_result = ''
        if (qc_result in ('', '通过')) and not gemstone and not metal_conclusion:
            return '正确'

        CUBIC = '合成立方氧化锆'

        # 分支1：配件材质含「合成立方氧化锆」
        if CUBIC in fitting:
            if CUBIC in gemstone or CUBIC in remark:
                return '正确'
            return '漏备注'

        # 分支2：配件材质不含「合成立方氧化锆」
        if CUBIC in remark:
            if re.search(r'[配为伴].*' + CUBIC, remark):
                return '正确'
            return '多备注'
        return '正确'
