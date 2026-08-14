"""
域骉控股珠宝质检规则引擎
- 统一加载、执行所有规则
- 每条规则实现 apply(row: dict) -> str 接口
- 运行前自动校验 Golden 测试集
"""

import importlib
import yaml
import json
import sys
from pathlib import Path


class QCEngine:
    """质检规则引擎"""

    # 规则字段依赖声明 — 与 qc_web.html ruleSourceFields 完全一致
    FIELD_DEPS = {
        "r1_weight": {"质检结果", "重量", "状态"},
        "r2_gemstone": {"质检结果", "宝玉石结论", "备注"},
        "r3_gold_content": {"质检结果", "商品名称", "商品材质", "镶嵌材质", "商品质量", "配件材质", "贵金属结论", "备注", "宝玉石结论"},
        "r4_net_weight": {"质检结果", "商品材质", "宝玉石结论", "贵金属结论", "重量", "备注"},
        "r5_nanhong": {"质检结果", "商品名称", "商品材质", "配件材质", "宝玉石结论", "备注"},
        "r6_agate_coating": {"质检结果", "商品材质", "宝玉石结论", "备注"},
        "r7_african_jade": {"质检结果", "商品名称", "商品材质", "配件材质", "宝玉石结论", "备注"},
        "r8_cubic_zirconia": {"质检结果", "配件材质", "宝玉石结论", "贵金属结论", "备注"},
        "r9_style_check": {"质检结果", "商品名称", "饰品类型"},
        "r10_weight_compare": {"质检结果", "商品质量", "SKU质量", "重量", "商品材质", "镶嵌材质", "配件材质"},
        "r11_material_conclusion": {"质检结果", "商品材质", "镶嵌材质", "配件材质", "贵金属结论", "宝玉石结论", "备注"},
        "r12_stone_check": {"质检结果", "备注"},
    }

    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        self.config = self._load_config(config_path)
        self.rules = self._load_rules()
        self._validate_field_isolation()

    def _load_config(self, path) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _load_rules(self) -> list:
        """根据配置动态加载规则模块"""
        loaded = []
        for rule_cfg in self.config["rules"]:
            if not rule_cfg.get("enabled", False):
                continue
            module = importlib.import_module(f"rules.{rule_cfg['id']}")
            rule_cls = getattr(module, "Rule")
            loaded.append({
                "id": rule_cfg["id"],
                "name": rule_cfg["name"],
                "column": rule_cfg["column"],
                "priority": rule_cfg["priority"],
                "instance": rule_cls(),
            })
        # 按优先级排序
        loaded.sort(key=lambda r: r["priority"])
        return loaded

    def _validate_field_isolation(self):
        """验证规则间字段依赖不冲突（输出列不重叠）"""
        output_cols = set()
        for rule in self.rules:
            col = rule["column"]
            if col in output_cols:
                raise ValueError(f"规则输出列冲突: {col} 被多条规则使用")
            output_cols.add(col)

    def apply_row(self, row: dict) -> dict:
        """对单行数据应用所有规则，返回 {列名: 判定结果}
        
        每条规则只接收其声明的依赖字段（隔离机制），
        防止规则意外读取或依赖其他规则的输出。
        
        全局预检：质检结果=不通过 → 所有规则输出"正确"
        """
        results = {}
        
        # 全局预检：质检结果=不通过 → 所有规则输出"正确"
        if (row.get('质检结果') or '').strip() == '不通过':
            for rule in self.rules:
                results[rule["column"]] = "正确"
            return results
        
        for rule in self.rules:
            rule_id = rule["id"]
            # 字段隔离: 只传入该规则声明的字段
            deps = self.FIELD_DEPS.get(rule_id, set())
            filtered_row = {k: v for k, v in row.items() if k in deps}
            try:
                result = rule["instance"].apply(filtered_row)
            except Exception as e:
                result = f"ERROR: {e}"
            results[rule["column"]] = result
        return results

    def apply_dataframe(self, df) -> "pd.DataFrame":
        """对整个DataFrame应用所有规则，返回带判定列的DataFrame"""
        import pandas as pd

        # 清洗所有字段
        df = df.map(self._clean_field)

        # 逐行应用规则
        result_cols = {rule["column"]: [] for rule in self.rules}
        for _, row in df.iterrows():
            row_dict = row.to_dict()
            results = self.apply_row(row_dict)
            for rule in self.rules:
                result_cols[rule["column"]].append(results[rule["column"]])

        # 追加判定列
        for col_name, values in result_cols.items():
            df[col_name] = values

        return df

    @staticmethod
    def _clean_field(val) -> str:
        """统一清洗字段值"""
        val = str(val).strip().replace("\t", "")
        if val in ("nan", "NaN", "None", ""):
            return ""
        return val

    def run_golden_tests(self, golden_path: str = None) -> dict:
        """运行 Golden 测试集，返回通过率"""
        if golden_path is None:
            golden_path = Path(__file__).parent / "tests" / "golden_cases.json"
        with open(golden_path, "r", encoding="utf-8") as f:
            cases = json.load(f)

        total = 0
        passed = 0
        failures = []

        for rule in self.rules:
            rule_id = rule["id"]
            rule_cases = cases.get(rule_id, [])
            for i, case in enumerate(rule_cases):
                total += 1
                result = rule["instance"].apply(case["input"])
                expected = case["expected"]
                if result == expected:
                    passed += 1
                else:
                    failures.append({
                        "rule": rule_id,
                        "case_index": i,
                        "input": case["input"],
                        "expected": expected,
                        "actual": result,
                    })

        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "pass_rate": f"{passed/total*100:.1f}%" if total > 0 else "N/A",
            "failures": failures,
        }

    def run_isolation_tests(self, golden_path: str = None) -> dict:
        """运行规则隔离性测试
        
        验证: 每条规则在完整行数据上运行时，结果与只传依赖字段时一致。
        如果不一致，说明规则偷偷读了未声明的字段，存在耦合风险。
        """
        if golden_path is None:
            golden_path = Path(__file__).parent / "tests" / "golden_cases.json"
        with open(golden_path, "r", encoding="utf-8") as f:
            cases = json.load(f)

        # 构造一个"全字段行"（所有Golden用例的input合并+额外字段）
        full_row = {}
        for rule_id, rule_cases in cases.items():
            for case in rule_cases:
                full_row.update(case["input"])
        # 补充一些无关字段
        full_row.update({
            "订单码": "TEST001",
            "证书编码": "CERT001",
            "商品价格": "199.00",
            "店铺名称": "测试店铺",
            "饰品类型": "吊坠",
        })

        results = {
            "total_checks": 0,
            "passed": 0,
            "leaks": [],
        }

        for rule in self.rules:
            rule_id = rule["id"]
            rule_cases = cases.get(rule_id, [])
            for i, case in enumerate(rule_cases):
                # 用完整行跑（但只有该规则声明的字段有真实值，其他用默认值）
                # 关键: 输入只包含声明的字段
                filtered_input = case["input"]  # Golden用例本身就只含依赖字段
                
                # 构造完整行版本: 把case的值填入full_row
                full_row_with_case = dict(full_row)
                full_row_with_case.update(case["input"])
                
                # 过滤版本: 只传声明的字段
                deps = self.FIELD_DEPS.get(rule_id, set())
                filtered_row = {k: v for k, v in full_row_with_case.items() if k in deps}
                
                # 两个版本结果应该一致
                result_full = rule["instance"].apply(full_row_with_case)
                result_filtered = rule["instance"].apply(filtered_row)
                
                results["total_checks"] += 1
                if result_full == result_filtered:
                    results["passed"] += 1
                else:
                    results["leaks"].append({
                        "rule": rule_id,
                        "case_index": i,
                        "input": case["input"],
                        "full_row_result": result_full,
                        "filtered_row_result": result_filtered,
                    })

        results["failed"] = results["total_checks"] - results["passed"]
        results["pass_rate"] = f"{results['passed']/results['total_checks']*100:.1f}%" if results["total_checks"] > 0 else "N/A"
        return results


def verify_golden_tests(engine: QCEngine) -> bool:
    """运行Golden测试，全部通过返回True，否则打印失败详情并返回False"""
    result = engine.run_golden_tests()
    print(f"Golden 测试结果: {result['passed']}/{result['total']} 通过 ({result['pass_rate']})")
    if result["failures"]:
        print("\n失败用例:")
        for f in result["failures"]:
            print(f"  [{f['rule']}] 用例#{f['case_index']}")
            print(f"    输入: {f['input']}")
            print(f"    期望: {f['expected']}")
            print(f"    实际: {f['actual']}")
        return False
    return True


def verify_isolation_tests(engine: QCEngine) -> bool:
    """运行隔离性测试，全部通过返回True"""
    result = engine.run_isolation_tests()
    print(f"隔离测试结果: {result['passed']}/{result['total_checks']} 通过 ({result['pass_rate']})")
    if result["leaks"]:
        print("\n字段泄露! 以下规则在完整行和过滤行上结果不一致:")
        for leak in result["leaks"]:
            print(f"  [{leak['rule']}] 用例#{leak['case_index']}")
            print(f"    输入: {leak['input']}")
            print(f"    完整行结果: {leak['full_row_result']}")
            print(f"    过滤行结果: {leak['filtered_row_result']}")
        return False
    return True
