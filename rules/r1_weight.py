"""
R1 重量判定规则

标准格式: 数字(必须有小数点) + g，括号内可有任意文字(中英文括号)
异常类型:
  - 格式异常: 缺g / g前有其他字母 / 乱码 / 逗号代小数点 / 0开头没点
  - 重量极低: <0.1g 且无括号备注
"""

import re


class Rule:
    """重量判定"""

    def apply(self, row: dict) -> str:
        weight = row.get("重量", "")
        if not weight:
            return ""

        weight = str(weight).strip().replace("\t", "")
        if weight in ("nan", "NaN", ""):
            return ""

        # 有括号(中英文) → 认为有备注
        has_bracket = bool(re.search(r'[（(]', weight))

        # 1. 检查格式异常
        format_error = self._check_format(weight)
        if format_error:
            return f"格式异常({format_error})"

        # 2. 提取数值
        num_match = re.search(r'(\d+\.?\d*)', weight)
        if not num_match:
            return "格式异常(无数值)"

        num_val = float(num_match.group(1))

        # 3. 重量极低检查
        if num_val < 0.1 and not has_bracket:
            return "重量极低"

        return "正常"

    def _check_format(self, weight: str) -> str:
        """返回异常描述，正常返回空字符串"""
        # 检查是否包含g
        if "g" not in weight:
            return "缺少g"

        # 提取g前面的部分(去掉括号内容)
        g_pos = weight.index("g")
        before_g = weight[:g_pos]

        # 去掉括号内容后检查
        before_g_clean = re.sub(r'[（(][^）)]*[）)]', '', before_g)

        # g前有其他字母(排除g本身)
        letter_match = re.search(r'[a-zA-Z]', before_g_clean)
        if letter_match:
            return "g前含字母"

        # 0开头后面没有点 (如 0123g)
        num_part = re.search(r'(\d+\.?\d*)', weight)
        if num_part:
            num_str = num_part.group(1)
            # 检查是否以0开头但不是0.开头
            if re.match(r'^0\d+', num_str) and not num_str.startswith('0.'):
                return "0开头无小数点"

        # 用逗号代替小数点
        if re.search(r'\d+,\d+g', weight):
            return "逗号代小数点"

        # 是否有小数点 (标准格式必须有小数点)
        num_part = re.search(r'(\d+\.?\d*)', weight)
        if num_part and '.' not in num_part.group(1):
            return "无小数点"

        return ""
