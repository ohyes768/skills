import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "finance-macro/basic-quality-rating/scripts"
)
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "rating_validator", SCRIPTS / "validate_rating_json.py"
)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
import rating_math


class RatingValidationTests(unittest.TestCase):
    def payload(self, scores=(4, 3, 3, 2, 2)):
        return rating_math.finalize(
            {
                "code": "000001",
                "name": "虚构测试公司",
                "dimensions": dict(zip(rating_math.WEIGHTS, scores)),
                "summary": "经营特征待按来源核实",
                "risks": [],
                "watch_points": [],
                "report_md": "# 基本面评级：虚构测试公司（000001）\n\n"
                "本报告不含目标价，不提供加仓或减仓建议。\n毛利率为 2.95%。\n"
                "业务核实\n五维：业务模式、护城河、行业前景、管理层、财务质量\n"
                "星级与边界\n结论与风险\n证据来源：https://example.com/annual.pdf",
            }
        )

    def test_canonical_grouped_boundary_and_disclaimer_pass(self):
        data = self.payload()
        self.assertIn("任一维度", data["boundary"])
        self.assertEqual(data["weighted_score"], 2.95)
        result = validator.validate(data)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["errors"], [])

    def test_null_contract_is_valid_and_requires_unrated_label_advisory(self):
        data = self.payload((4, None, 3, 2, 2))
        result = validator.validate(data)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["warnings"])
        for key in rating_math.DERIVED:
            self.assertIsNone(data[key])

    def test_stale_derived_values_fail_without_rewriting(self):
        data = self.payload((4, None, 3, 2, 2))
        for key, value in (
            ("weighted_score", 2.95),
            ("stars", 2),
            ("boundary", "旧边界"),
        ):
            changed = dict(data, **{key: value})
            before = json.dumps(changed, ensure_ascii=False)
            result = validator.validate(changed)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(json.dumps(changed, ensure_ascii=False), before)

    def test_wrong_types_schema_or_boundary_fail(self):
        data = self.payload()
        for changes in (
            {"stars": True},
            {"stars": 2.0},
            {"weighted_score": True},
            {"weighted_score": float("nan")},
            {"weighted_score": 10**400},
            {"weighted_score": "2.95"},
            {"boundary": "任一维度加两分升星"},
            {"risks": "无"},
            {"watch_points": [None]},
            {"report_md": " "},
            {"extra": 1},
        ):
            self.assertEqual(
                validator.validate(dict(data, **changes))["status"], "failed"
            )
        changed = self.payload()
        del changed["stars"]
        self.assertEqual(validator.validate(changed)["status"], "failed")
        self.assertEqual(validator.validate([])["status"], "failed")

    def test_identity_is_checked_only_against_supplied_stock(self):
        data = self.payload()
        self.assertEqual(
            validator.validate(data, {"code": "000001", "name": "虚构测试公司"})[
                "status"
            ],
            "passed",
        )
        self.assertEqual(
            validator.validate(data, {"code": "000002", "name": "别家公司"})["status"],
            "failed",
        )

    def test_unrelated_numbers_do_not_trigger_total_leak_failure(self):
        data = self.payload()
        data["report_md"] += (
            "\n资产增速 0.95%，ROE 为 2.95%。建议买入的措辞需人工复核。"
        )
        result = validator.validate(data)
        self.assertEqual(result["status"], "passed")
        self.assertTrue(result["warnings"])

    def test_cli_read_only_and_nonfinite_rejection(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            path = Path(work) / "rating.json"
            good = json.dumps(self.payload(), ensure_ascii=False)
            for raw, expected_exit in (
                (good, 0),
                ('{"weighted_score":NaN}', 2),
                ("{", 2),
            ):
                path.write_text(raw, encoding="utf-8")
                run = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPTS / "validate_rating_json.py"),
                        str(path),
                    ],
                    capture_output=True,
                    check=False,
                    text=True,
                    encoding="utf-8",
                )
                self.assertEqual(run.returncode, expected_exit, run.stderr)
                result = json.loads(run.stdout)
                self.assertEqual(
                    result["status"], "passed" if expected_exit == 0 else "failed"
                )
                self.assertEqual(path.read_text(encoding="utf-8"), raw)


if __name__ == "__main__":
    unittest.main()
