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


def bank_stock():
    return {
        "code": "000001",
        "name": "测试银行",
        "sw_level1": "银行",
        "debt_asset_ratio": 93,
    }


def packet_for(stock):
    from bank_financial import make_template

    packet = make_template(stock, "2026-10-27")
    packet["requirements_period_end"] = "2026-06-30"
    packet["requirements_published_at"] = "2026-08-28"

    def metric(value, basis="point_in_time"):
        return {
            "value": value,
            "source_url": "https://example.com/bank-report.pdf",
            "locator": "PDF p. 10, group table, current period column",
            "basis": basis,
        }

    for year in (2023, 2024, 2025):
        packet["reports"].append(
            {
                "period_end": f"{year}-12-31",
                "published_at": f"{year + 1}-03-28",
                "period_type": "annual",
                "scope": "group",
                "metrics": {
                    "roe": metric(18, "period"),
                    "roa": metric(1.2, "period"),
                    "npl_ratio": metric(0.9),
                },
            }
        )
    packet["reports"].append(
        {
            "period_end": "2026-06-30",
            "published_at": "2026-08-28",
            "period_type": "interim",
            "scope": "group",
            "metrics": {
                key: metric(value)
                for key, value in {
                    "npl_ratio": 0.9,
                    "provision_coverage": 350,
                    "cet1_ratio": 13,
                    "tier1_ratio": 15,
                    "total_capital_ratio": 18,
                    "lcr": 180,
                    "nsfr": 150,
                }.items()
            },
        }
    )
    packet["requirements"] = {
        key: metric(value)
        for key, value in {
            "cet1_ratio": 8,
            "tier1_ratio": 9.5,
            "total_capital_ratio": 11.5,
        }.items()
    }
    return packet


def draft_for(stock, financial):
    return {
        "code": stock["code"],
        "name": stock["name"],
        "dimensions": {
            "business": 4,
            "moat": 4,
            "industry": 4,
            "management": 4,
            "financial": financial,
        },
        "summary": "银行财务测试",
        "risks": [],
        "watch_points": [],
        "report_md": "# 银行财务测试\n研究规则评分，不代表监管评级。",
    }


class BankIntegrationTests(unittest.TestCase):
    def test_real_official_snapshot_preserves_facts_without_inventing_annuals_or_breach(
        self,
    ):
        from bank_financial import make_template

        fixture = json.loads(
            (
                Path(__file__).parent / "fixtures/minsheng_2025_h1_snapshot.json"
            ).read_text(encoding="utf-8")
        )
        stock = fixture["stock"]
        packet = make_template(stock, fixture["as_of"])

        def sourced(rows):
            return {
                key: {
                    "value": row["value"],
                    "source_url": fixture["source_url"],
                    "locator": f"PDF p.{row['pdf_page']}, group, 2025-06-30 column",
                    "basis": "point_in_time",
                }
                for key, row in rows.items()
            }

        packet["reports"] = [
            {
                "period_end": fixture["period_end"],
                "published_at": fixture["published_at"],
                "period_type": "interim",
                "scope": "group",
                "metrics": sourced(fixture["snapshot"]),
            }
        ]
        packet["requirements"] = sourced(fixture["requirements"])
        packet["requirements_period_end"] = fixture["period_end"]
        packet["requirements_published_at"] = fixture["published_at"]
        result = score_financial(stock, bank_data=packet)
        self.assertIsNone(result["score"])
        self.assertTrue(any("2024" in issue for issue in result["issues"]))
        checks = {check["rule"]: check for check in result["checks"]}
        self.assertEqual(
            checks["bank_capital_buffer"]["input"]["surplus_pp"]["cet1_ratio"], 1.75
        )
        self.assertEqual(checks["bank_provision_coverage"]["cap"], 2)
        self.assertFalse(
            any("低于适用" in risk or "低于证据包" in risk for risk in result["risks"])
        )

    def test_bank_missing_sidecar_means_insufficient_not_inapplicable(self):
        result = score_financial(bank_stock())
        self.assertEqual(result["status"], "insufficient_data")
        self.assertIsNone(result["score"])

    def test_explicit_sidecar_checked_without_mutating_original(self):
        stock = bank_stock()
        before = copy.deepcopy(stock)
        packet = packet_for(stock)
        scored = score_financial(stock, bank_data=packet)
        self.assertEqual(scored["score"], 5, scored)
        rated = finalize(
            draft_for(stock, 5), stock, check_financial=True, bank_data=packet
        )
        self.assertEqual(len(rated), 10)
        self.assertEqual(rated["stars"], 4)
        self.assertEqual(
            validate(rated, stock, check_financial=True, bank_data=packet)["status"],
            "passed",
        )
        self.assertEqual(stock, before)
        with self.assertRaises(ValueError):
            finalize(draft_for(stock, 4), stock, check_financial=True, bank_data=packet)

    def test_sidecar_cannot_be_silently_ignored(self):
        stock = bank_stock()
        packet = packet_for(stock)
        with self.assertRaises(ValueError):
            finalize(draft_for(stock, 5), stock, bank_data=packet)
        other = {**stock, "sw_level1": "机械设备"}
        with self.assertRaises(ValueError):
            score_financial(other, bank_data=packet)

    def test_corrupt_or_mismatched_packet_never_creates_total(self):
        stock = bank_stock()
        packet = packet_for(stock)
        packet["code"] = "600000"
        result = score_financial(stock, bank_data=packet)
        self.assertIsNone(result["score"])
        rated = finalize(
            draft_for(stock, None), stock, check_financial=True, bank_data=packet
        )
        self.assertIsNone(rated["weighted_score"])
        self.assertIsNone(rated["stars"])

    def test_real_cli_financial_finalize_validator_and_flag_errors(self):
        stock = bank_stock()
        packet = packet_for(stock)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            for name, data in (
                ("stock", stock),
                ("bank", packet),
                ("draft", draft_for(stock, 5)),
            ):
                (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")

            def cli(script, *args):
                return subprocess.run(
                    [sys.executable, str(SCRIPTS / script), *map(str, args)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    check=False,
                )

            common = ["--bank-data", root / "bank.json"]
            scored = cli(
                "rating_math.py", "financial", "--input", root / "stock.json", *common
            )
            self.assertEqual(scored.returncode, 0, scored.stderr)
            self.assertEqual(json.loads(scored.stdout)["score"], 5)
            result = cli(
                "rating_math.py",
                "finalize",
                "--input",
                root / "draft.json",
                "--stock",
                root / "stock.json",
                "--check-financial",
                *common,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(json.loads(result.stdout)), 10)
            (root / "rating.json").write_text(result.stdout, encoding="utf-8")
            checked = cli(
                "validate_rating_json.py",
                root / "rating.json",
                "--stock",
                root / "stock.json",
                "--check-financial",
                *common,
            )
            self.assertEqual(checked.returncode, 0, checked.stdout)
            for args in (
                ("calculate", "--input", root / "draft.json", *common),
                (
                    "finalize",
                    "--input",
                    root / "draft.json",
                    "--stock",
                    root / "stock.json",
                    *common,
                ),
            ):
                bad = cli("rating_math.py", *args)
                self.assertEqual(bad.returncode, 2)
                self.assertEqual(bad.stdout, "")
            (root / "null.json").write_text("null", encoding="utf-8")
            bad = cli(
                "rating_math.py",
                "finalize",
                "--input",
                root / "draft.json",
                "--bank-data",
                root / "null.json",
            )
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(bad.stdout, "")
            bad = cli(
                "validate_rating_json.py",
                root / "rating.json",
                "--bank-data",
                root / "null.json",
            )
            self.assertEqual(bad.returncode, 2)


if __name__ == "__main__":
    unittest.main()
