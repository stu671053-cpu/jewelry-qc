"""
R4: 足金净金重检查
严格按用户流程图实现（2026-06-06）

流程图逻辑:
1. 重量含"净金重"？
   - 否 → 有括号？ → 无括号→漏备注（仅足金）/ 有括号→正确
   - 是 → 含"不/不含"？ → 是→正确 / 否→继续
2. 贵金属结论=足金？
   - 否 → 多备注净金重
   - 是 → 继续
3. 宝玉石结论为空？
   - 否 → 多备注净金重
   - 是 → 继续
4. 备注仅含金含量≥999‰/---/空值？
   - 否 → 多备注净金重
   - 是 → 继续
5. 重量是否"纯净金重"格式？
   - 否 → 多备注净金重
   - 是 → 正确

"纯净金重"格式定义：
  - 只有括号包裹的净金重，如：(净金重) / （净金重）
  - 如果同时包含"克重"和"净金重备注" → 多备注
  - 例：0.23g(净金重) → 多备注（不纯）
  - 例：1.35g（净金重） → 多备注（不纯）

2026-06-06 更新：重量为空 且 宝玉石为空 且 贵金属=足金 → 正确
"""
import re


class Rule:
    RULE_NAME = "R4_足金净金重检查"

    def apply(self, row: dict) -> str:
        pm = str(row.get('贵金属结论', '')).strip()
        gemstone = str(row.get('宝玉石结论', '')).strip()
        weight = str(row.get('重量', '')).strip()
        remark = str(row.get('备注', '')).strip()

        # 清洗NaN值
        if gemstone.lower() in ('nan', 'none', ''):
            gemstone = ''
        if remark.lower() in ('nan', 'none', ''):
            remark = ''

        has_net = '净金重' in weight

        # ========== 判断1: 【重量】含"净金重"？ ==========
        if not has_net:
            # n分支: 重量不含净金重
            has_paren = bool(re.search(r'[（(]', weight))
            if not has_paren:
                # 无括号
                if weight == '':
                    # 2026-06-06 更新：重量为空 且 宝玉石为空 且 贵金属=足金 → 正确
                    if pm == '足金' and gemstone == '':
                        return '正确'
                    return '正确'
                if re.match(r'^\d+\.?\d*g$', weight):
                    # 纯克重格式（如1.35g）
                    if pm == '足金':
                        # 检查备注是否包含"未检"
                        # 包含"未检" → 说明有项目未检测，不需要备注净金重
                        if '未检' in remark:
                            return '正确'
                        return '漏备注净金重'  # 案例4
                    return '正确'  # 非足金不需要备注
                return '正确'
            else:
                # 有括号 → 正确
                return '正确'  # 案例9: 1.35g（含绳）

        # y分支: 含净金重
        # ========== 判断2: 含"不/不含"？ ==========
        if '不' in weight:
            return '正确'  # 案例7: 含"不含链"

        # ========== 判断3: 【贵金属结论】为足金？ ==========
        if pm != '足金':
            return '多备注净金重'  # 案例10

        # y分支: pm == '足金'
        # ========== 判断4: 【宝玉石结论】为空？ ==========
        if gemstone:
            return '多备注净金重'  # 案例8

        # y分支: 宝玉石结论为空
        # ========== 2026-06-06 更新：重量为空 → 正确 ==========
        if weight == '':
            return '正确'

        # ========== 判断5: 【备注】仅含金含量≥999‰/---/空值？ ==========
        remark_valid = remark == '' or remark == '---' or '金含量≥999‰' in remark
        if not remark_valid:
            return '多备注净金重'  # 案例3

        # yes分支: 备注正常
        # ========== 判断5.5: 【备注】包含"未检"？ ==========
        # 包含"未检" → 说明有项目未检测，不需要备注净金重
        if '未检' in remark:
            if has_net:
                return '多备注净金重'
            else:
                return '正确'
        
        # ========== 判断6: 【重量】括号内是否仅含"净金重"？ ==========
        # 正确格式: 括号内容只有"净金重"（可以有多个括号，每个都必须是"净金重"）
        # 错误格式: 括号内有其他内容（如"含绳"、"含链"等）
        # 注意：括号外面可以有克重（如1.35g），不影响判断
        
        # 提取所有括号内容
        content_list = re.findall(r'[（(]([^）)]*)[）)]', weight)
        
        if not content_list:
            # 没有括号内容（不应该到这里，因为has_net=True）
            return '多备注净金重'
        
        # 检查所有括号内容是否都只有"净金重"
        all_pure = True
        for content in content_list:
            content_clean = content.replace('、', '').replace(',', '').strip()
            if content_clean != '净金重':
                all_pure = False
                break
        
        if all_pure:
            return '正确'  # 案例0,1,2：括号内容只有"净金重"
        else:
            return '多备注净金重'  # 案例5,6：括号内有其他内容
