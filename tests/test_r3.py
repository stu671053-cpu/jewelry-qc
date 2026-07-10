"""R3 金含量备注检查 - Golden 测试"""

import json
import pytest
from pathlib import Path
from rules.r3_gold_content import Rule


@pytest.fixture
def rule():
    return Rule()


@pytest.fixture
def cases():
    path = Path(__file__).parent / "golden_cases.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("r3_gold_content", [])


def test_r3_golden(rule, cases):
    failures = []
    for i, case in enumerate(cases):
        result = rule.apply(case["input"])
        if result != case["expected"]:
            failures.append((i, case, result))
    assert not failures, "\n".join(
        f"  用例#{i}: 输入={c['input']}, 期望={c['expected']}, 实际={r}"
        for i, c, r in failures
    )
