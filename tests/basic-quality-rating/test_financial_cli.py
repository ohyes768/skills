import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "finance-macro/basic-quality-rating/scripts"
)


class FinancialCliTests(unittest.TestCase):
    def stock(self):
        return {
            "code": "000001",
            "name": "虚构测试公司",
            "sw_level1": "电子",
            "roe_avg_3y": 18,
            "roe_year": 2025,
            "annual_profit_year": 2025,
            "roe_history": [
                {"year": 2023, "value": 16},
                {"year": 2024, "value": 18},
                {"year": 2025, "value": 20},
            ],
            "debt_asset_ratio": 30,
            "net_profit_ex_non_recurring_yoy": 5,
            "previous_quarter_yoy_pct": 3,
            "previous_quarter_label": "2026Q1",
            "latest_quarter_yoy_pct": 2,
            "latest_quarter_label": "2026Q2",
        }

    def test_financial_command_and_finalization_verify_original_input(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            root = Path(work)
            stock = self.stock()
            (root / "stock.json").write_text(
                json.dumps(stock, ensure_ascii=False), encoding="utf-8"
            )
            command = [sys.executable, str(SCRIPTS / "rating_math.py")]
            run = subprocess.run(
                command + ["financial", "--input", str(root / "stock.json")],
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result["score"], 5)
            self.assertTrue(result["checks"])
            draft = {
                "code": stock["code"],
                "name": stock["name"],
                "dimensions": {
                    "business": 4,
                    "moat": 4,
                    "industry": 3,
                    "management": 4,
                    "financial": 5,
                },
                "summary": "测试",
                "risks": [],
                "watch_points": [],
                "report_md": "# 测试",
            }
            path = root / "draft.json"
            for score, expected in ((5, 0), (4, 2), (None, 2)):
                draft["dimensions"]["financial"] = score
                path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
                run = subprocess.run(
                    command
                    + [
                        "finalize",
                        "--input",
                        str(path),
                        "--stock",
                        str(root / "stock.json"),
                        "--check-financial",
                    ],
                    capture_output=True,
                    check=False,
                    text=True,
                    encoding="utf-8",
                )
                self.assertEqual(run.returncode, expected, run.stderr)
                if expected == 0:
                    self.assertEqual(
                        json.loads(run.stdout)["dimensions"]["financial"], 5
                    )
                else:
                    self.assertEqual(run.stdout, "")

    def test_checked_finalization_requires_stock(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            path = Path(work) / "draft.json"
            path.write_text("{}", encoding="utf-8")
            run = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "rating_math.py"),
                    "finalize",
                    "--input",
                    str(path),
                    "--check-financial",
                ],
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(run.returncode, 2)
            self.assertEqual(run.stdout, "")
            self.assertIn("--stock", run.stderr)


if __name__ == "__main__":
    unittest.main()
