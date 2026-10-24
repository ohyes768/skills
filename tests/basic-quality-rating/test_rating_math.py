import importlib.util
import itertools
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "finance-macro/basic-quality-rating/scripts/rating_math.py"
)
spec = importlib.util.spec_from_file_location("rating_math", SCRIPT)
rating = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rating)


class RatingMathTests(unittest.TestCase):
    def dimensions(self, *values):
        return dict(
            zip(("business", "moat", "industry", "management", "financial"), values)
        )

    def draft(self):
        return {
            "code": "002128",
            "name": "电投能源",
            "dimensions": self.dimensions(3, 3, 3, 3, 4),
            "summary": "测试结论",
            "risks": ["测试风险"],
            "watch_points": [],
            "report_md": "# 测试报告",
        }

    def test_all_score_combinations_and_boundaries(self):
        for values in itertools.product(range(1, 6), repeat=5):
            total = sum(v * w for v, w in zip(values, (25, 25, 20, 15, 15)))
            result = rating.calculate(self.dimensions(*values))
            self.assertEqual(result["weighted_score"], total / 100)
            self.assertEqual(
                result["stars"], 1 + sum(total >= t for t in (200, 300, 400, 450))
            )
            near = min(abs(total - t) for t in (200, 300, 400, 450)) < 25
            self.assertEqual(result["boundary"] is not None, near)

    def test_actual_run_fixture(self):
        result = rating.calculate(self.dimensions(3, 3, 3, 3, 4))
        self.assertEqual(result["weighted_score"], 3.15)
        self.assertEqual(result["stars"], 3)
        self.assertIn("业务模式、护城河或行业前景降1分即降至2星", result["boundary"])
        self.assertIn("单维升1分不足以升星", result["boundary"])

    def test_thresholds_and_strict_distance(self):
        self.assertEqual(rating.calculate(self.dimensions(4, 5, 4, 5, 5))["stars"], 5)
        self.assertEqual(rating.calculate(self.dimensions(4, 4, 4, 4, 4))["stars"], 4)
        self.assertEqual(
            rating.calculate(self.dimensions(4, 5, 4, 4, 4))["boundary"], None
        )

    def test_boundary_does_not_overstate_crossing_dimensions(self):
        text = rating.calculate(self.dimensions(4, 4, 4, 4, 5))["boundary"]
        self.assertIn("业务模式、护城河或行业前景降1分即降至3星", text)
        self.assertNotIn("任一维度降1分", text)
        text = rating.calculate(self.dimensions(4, 4, 3, 4, 4))["boundary"]
        self.assertIn("业务模式、护城河或行业前景升1分即升至4星", text)

    def test_rejects_non_integer_or_wrong_dimensions(self):
        for value in (True, 3.0, "3", None, 0, 6):
            dims = self.dimensions(3, 3, 3, 3, value)
            with self.assertRaises(ValueError):
                rating.calculate(dims)
        with self.assertRaises(ValueError):
            rating.calculate({"business": 3})
        with self.assertRaises(ValueError):
            rating.calculate(dict(self.dimensions(3, 3, 3, 3, 3), extra=1))

    def test_finalize_exact_contract_and_recomputes_derived_fields(self):
        draft = dict(self.draft(), weighted_score=5, stars=5, boundary="错误边界")
        result = rating.finalize(draft, {"code": "002128", "name": "电投能源"})
        self.assertEqual(len(result), 10)
        self.assertEqual(set(result), set(rating.OUTPUT_FIELDS))
        self.assertEqual(result["weighted_score"], 3.15)
        self.assertEqual(result["stars"], 3)
        self.assertEqual(draft["stars"], 5)
        self.assertEqual(result["report_md"], draft["report_md"])

    def test_validation_rejects_identity_and_schema_mistakes(self):
        for change in (
            {"code": 2128},
            {"name": " "},
            {"report_md": " "},
            {"risks": "风险"},
            {"watch_points": [3]},
            {"unexpected": 1},
        ):
            with self.assertRaises((ValueError, TypeError)):
                rating.finalize(dict(self.draft(), **change))
        with self.assertRaises(ValueError):
            rating.finalize(self.draft(), {"code": "000001", "name": "其他公司"})

    def test_cli_outputs_only_final_json_and_rejects_nonfinite(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as work:
            path = Path(work) / "draft.json"
            path.write_text(
                json.dumps(self.draft(), ensure_ascii=False), encoding="utf-8"
            )
            run = subprocess.run(
                [sys.executable, str(SCRIPT), "finalize", "--input", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(len(json.loads(run.stdout)), 10)
            self.assertEqual(run.stderr, "")
            path.write_text('{"business":NaN}', encoding="utf-8")
            bad = subprocess.run(
                [sys.executable, str(SCRIPT), "calculate", "--input", str(path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertNotEqual(bad.returncode, 0)
            self.assertEqual(bad.stdout, "")


if __name__ == "__main__":
    unittest.main()
