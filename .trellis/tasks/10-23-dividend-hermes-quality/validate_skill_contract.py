"""Offline compatibility check against the Web consumer, without importing its app.

Run from the skills repository:
python -X utf8 .trellis/tasks/10-23-dividend-hermes-quality/validate_skill_contract.py
"""

import ast
import itertools
import json
from pathlib import Path
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


ROOT = Path(__file__).resolve().parents[3]
CONSUMER = ROOT.parent / "personal-web/backend/dividend-select/src/services/quality_service.py"
SKILL = ROOT / "finance-macro/basic-quality-rating/SKILL.md"


def main():
    text = SKILL.read_text(encoding="utf-8")
    source = ast.parse(CONSUMER.read_text(encoding="utf-8"))
    names = {
        "DIMENSION_WEIGHTS", "SCORE_TOLERANCE", "_stars_for", "QualityScore",
        "_FENCE_RE", "parse_quality_output",
    }
    selected = []
    for node in source.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names:
            selected.append(node)
        elif isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in names for target in node.targets
        ):
            selected.append(node)
    namespace = {
        "json": json, "re": re, "Optional": Optional,
        "BaseModel": BaseModel, "Field": Field,
        "field_validator": field_validator, "model_validator": model_validator,
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(CONSUMER), "exec"), namespace)
    parse = namespace["parse_quality_output"]
    model = namespace["QualityScore"]
    sample = json.loads(re.search(r"```json\n(.*?)\n```", text, re.S)[1])
    assert set(sample) == set(model.model_fields), "Output fields drifted from consumer"
    result = parse(json.dumps(sample, ensure_ascii=False), sample["code"], sample["name"])
    assert result.code == "000001", "Leading zeros lost"
    assert result.weighted_score == 3.8 and result.stars == 3

    builder = next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name == "build_stock_payload")
    returned = next(n.value for n in ast.walk(builder) if isinstance(n, ast.Return))
    input_keys = [key.value for key in returned.keys]
    assert all(re.search(r"\b" + re.escape(key) + r"\b", text) for key in input_keys), "Input field missing"

    for scores in itertools.product(range(1, 6), repeat=5):
        total = sum(score * weight for score, weight in zip(scores, (25, 25, 20, 15, 15)))
        stars = 1 + sum(total >= threshold for threshold in (200, 300, 400, 450))
        payload = dict(sample, dimensions=dict(zip(sample["dimensions"], scores)),
                       weighted_score=total / 100, stars=stars)
        parsed = parse(json.dumps(payload), sample["code"], sample["name"])
        assert parsed.stars == stars

    for changes in ({"weighted_score": 4.0}, {"stars": 5}, {"report_md": " "},
                    {"dimensions": {"business": 4}}):
        try:
            parse(json.dumps(dict(sample, **changes)), sample["code"], sample["name"])
        except ValueError:
            pass
        else:
            raise AssertionError(f"Consumer accepted invalid fixture: {changes}")
    print(f"PASS: {len(input_keys)} input fields, 11 output fields, example JSON, leading zeros")
    print("PASS: all 3,125 dimension combinations accepted by actual Web scoring validator")
    print("PASS: wrong sum, wrong stars, blank report and missing dimension rejected")
    print("Scope: numeric/schema compatibility only; not live-model research/report validation")


if __name__ == "__main__":
    main()
