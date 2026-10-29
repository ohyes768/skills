import copy
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
from financial_score import score_financial
from rating_math import finalize
from validate_rating_json import validate


def stock():
    return {
        "code": "601318",
        "name": "测试保险集团",
        "sw_level1": "非银金融",
        "sw_level2": "保险Ⅱ",
    }


def draft(financial):
    return {
        "code": "601318",
        "name": "测试保险集团",
        "dimensions": {
            "business": 4,
            "moat": 4,
            "industry": 4,
            "management": 4,
            "financial": financial,
        },
        "summary": "保险研究测试",
        "risks": [],
        "watch_points": [],
        "report_md": "保险研究测试",
    }


class InsuranceIntegrationTests(unittest.TestCase):
    def test_official_snapshot_does_not_replace_missing_legal_core_ratios(self):
        from insurance_data import make_template

        fixture = json.loads(
            (Path(__file__).parent / "fixtures/pingan_2024_summary.json").read_text(
                encoding="utf-8"
            )
        )
        original = fixture["stock"]
        evidence = make_template(original, fixture["as_of"], "group")

        def fact(value, label):
            return {
                "value": value,
                "unit": "pct",
                "basis": "point_in_time",
                "source_url": fixture["source_url"],
                "locator": f"PDF p.6, {label}, 2024-12-31 column",
            }

        evidence["reports"] = [
            {
                "period_end": fixture["period_end"],
                "published_at": fixture["published_at"],
                "period_type": "annual",
                "scope": "group",
                "metrics": {
                    "group_solvency_ratio": fact(
                        fixture["group_solvency_ratio"], "group"
                    )
                },
            }
        ]
        for id_, name in (("life", "平安寿险"), ("property", "平安产险")):
            evidence["entities"].append(
                {
                    "id": id_,
                    "name": name,
                    "kind": id_,
                    "scope": "solo",
                    "latest": {
                        "period_end": fixture["period_end"],
                        "published_at": fixture["published_at"],
                        "metrics": {
                            "comprehensive_solvency": fact(
                                fixture[f"{id_}_comprehensive_solvency"], name
                            )
                        },
                    },
                    "annuals": [],
                    "assessments": {},
                }
            )
        result = score_financial(original, insurance_data=evidence)
        self.assertIsNone(result["score"])
        self.assertEqual(result["status"], "insufficient_data")
        checks = {check["rule"]: check for check in result["checks"]}
        self.assertEqual(
            checks["group_solvency"]["input"]["group_solvency_ratio"]["value"], 204.1
        )
        self.assertEqual(
            checks["life.comprehensive_solvency"]["input"]["comprehensive_solvency"][
                "value"
            ],
            189.2,
        )
        self.assertNotIn("life.core_solvency", checks)
        self.assertTrue(any("core_solvency" in issue for issue in result["issues"]))

    def test_missing_insurance_data_is_missing_not_inapplicable(self):
        result = score_financial(stock())
        self.assertIsNone(result["score"])
        self.assertEqual(result["status"], "insufficient_data")

    def test_explicit_sidecar_must_not_be_ignored_or_cross_sector(self):
        with self.assertRaises(ValueError):
            finalize(draft(None), stock(), insurance_data={})
        with self.assertRaises(ValueError):
            score_financial(
                {**stock(), "sw_level1": "银行", "sw_level2": "股份制银行"},
                insurance_data={},
            )
        with self.assertRaises(ValueError):
            score_financial(stock(), insurance_data={}, bank_data={})

    def test_valid_packet_flows_through_checked_finalization(self):
        from test_insurance_financial import packet

        original = stock()
        evidence = packet(original, insurance_type="group")
        before = copy.deepcopy(original)
        score = score_financial(original, insurance_data=evidence)["score"]
        self.assertIsInstance(score, int)
        output = finalize(
            draft(score), original, check_financial=True, insurance_data=evidence
        )
        self.assertEqual(len(output), 11)
        self.assertEqual(
            validate(output, original, check_financial=True, insurance_data=evidence)[
                "status"
            ],
            "passed",
        )
        self.assertEqual(original, before)
        with self.assertRaises(ValueError):
            finalize(
                draft(1 if score != 1 else 5),
                original,
                check_financial=True,
                insurance_data=evidence,
            )

    def test_cli_sidecar_presence_errors_and_real_full_flow(self):
        from test_insurance_financial import packet

        original = stock()
        evidence = packet(original, insurance_type="group")
        score = score_financial(original, insurance_data=evidence)["score"]
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            for name, data in (
                ("stock", original),
                ("insurance", evidence),
                ("null", None),
                ("draft", draft(score)),
            ):
                (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")

            def cli(script, *args):
                return subprocess.run(
                    [sys.executable, str(SCRIPTS / script), *map(str, args)],
                    capture_output=True,
                    encoding="utf-8",
                    text=True,
                    check=False,
                )

            result = cli(
                "rating_math.py",
                "financial",
                "--input",
                root / "stock.json",
                "--insurance-data",
                root / "insurance.json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["score"], score)
            result = cli(
                "rating_math.py",
                "finalize",
                "--input",
                root / "draft.json",
                "--stock",
                root / "stock.json",
                "--check-financial",
                "--insurance-data",
                root / "insurance.json",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            (root / "rating.json").write_text(result.stdout, encoding="utf-8")
            result = cli(
                "validate_rating_json.py",
                root / "rating.json",
                "--stock",
                root / "stock.json",
                "--check-financial",
                "--insurance-data",
                root / "insurance.json",
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            for flags in (
                ("--insurance-data", root / "null.json"),
                (
                    "--insurance-data",
                    root / "insurance.json",
                    "--bank-data",
                    root / "insurance.json",
                ),
            ):
                result = cli(
                    "rating_math.py", "finalize", "--input", root / "draft.json", *flags
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
