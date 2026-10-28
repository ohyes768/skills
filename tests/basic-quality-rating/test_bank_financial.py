import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "finance-macro/basic-quality-rating/scripts"
)
sys.path.insert(0, str(SCRIPTS))

try:
    import bank_financial as bank
except ImportError:
    bank = None


def stock():
    return {
        "code": "000001",
        "name": "测试银行",
        "sw_level1": "银行",
        "debt_asset_ratio": 93,
    }


def metric(value, basis="point_in_time"):
    return {
        "value": value,
        "basis": basis,
        "source_url": "https://bank.example/annual.pdf",
        "locator": "PDF p.12, 集团口径",
    }


def packet():
    data = bank.make_template(stock(), "2026-10-27")
    for year, roe, roa in ((2023, 16, 1.1), (2024, 17, 1.2), (2025, 18, 1.3)):
        data["reports"].append(
            {
                "period_end": f"{year}-12-31",
                "published_at": f"{year + 1}-03-25",
                "period_type": "annual",
                "scope": "group",
                "metrics": {
                    "roe": metric(roe, "period"),
                    "roa": metric(roa, "period"),
                    "npl_ratio": metric(0.9),
                },
            }
        )
    data["reports"].append(
        {
            "period_end": "2026-06-30",
            "published_at": "2026-08-25",
            "period_type": "interim",
            "scope": "group",
            "metrics": {
                "npl_ratio": metric(0.9),
                "provision_coverage": metric(350),
                "cet1_ratio": metric(12),
                "tier1_ratio": metric(14),
                "total_capital_ratio": metric(17),
                "lcr": metric(150, "quarter_average"),
                "nsfr": metric(140),
            },
        }
    )
    data["requirements"] = {
        "cet1_ratio": metric(8),
        "tier1_ratio": metric(9),
        "total_capital_ratio": metric(11),
    }
    data["requirements_period_end"] = "2026-06-30"
    data["requirements_published_at"] = "2026-08-25"
    return data


class BankFinancialTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(bank, "bank financial scorer must be implemented")

    def test_complete_bank_and_no_input_mutation(self):
        original = stock()
        data = packet()
        saved = copy.deepcopy((original, data))
        result = bank.score_bank(original, data)
        self.assertEqual(
            (result["score"], result["status"], result["sector"]), (5, "scored", "bank")
        )
        self.assertEqual((original, data), saved)
        self.assertEqual(result["issues"], [])
        self.assertEqual("bank-research-v2", result["policy"])
        self.assertTrue(result["checks"])
        json.dumps(result, allow_nan=False)

    def test_missing_liquidity_pair_is_scored_without_assuming_a_pass(self):
        data = packet()
        for key in ("lcr", "nsfr"):
            del data["reports"][-1]["metrics"][key]
        before = copy.deepcopy(data)
        result = bank.score_bank(stock(), data)
        self.assertEqual((result["score"], result["status"]), (5, "scored"))
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["liquidity_status"], "unverified")
        self.assertTrue(
            any("流动性未验证" in warning for warning in result["warnings"])
        )
        self.assertFalse(any("流动性" in risk for risk in result["risks"]))
        check = next(c for c in result["checks"] if c["rule"] == "bank_liquidity")
        self.assertIsNone(check["cap"])
        self.assertEqual(check["input"], {})
        self.assertEqual(data, before)

    def test_liquidity_null_is_missing_but_zero_is_a_real_weakness(self):
        for missing in (None, {"value": None}):
            data = packet()
            data["reports"][-1]["metrics"].update(lcr=missing, nsfr=missing)
            self.assertEqual(bank.score_bank(stock(), data)["score"], 5)
        data = packet()
        data["reports"][-1]["metrics"].update(lcr=None, nsfr=metric(0))
        result = bank.score_bank(stock(), data)
        self.assertEqual(result["score"], 1)
        self.assertEqual(result["liquidity_status"], "partial")
        self.assertTrue(any("100%监管底线" in risk for risk in result["risks"]))

    def test_single_liquidity_metric_still_caps_and_discloses_missing_counterpart(self):
        for known, missing in (("lcr", "nsfr"), ("nsfr", "lcr")):
            for value, cap in ((150, 5), (120, 4), (110, 3), (100, 2), (99, 1)):
                data = packet()
                del data["reports"][-1]["metrics"][missing]
                data["reports"][-1]["metrics"][known] = metric(value)
                with self.subTest(known=known, value=value):
                    result = bank.score_bank(stock(), data)
                    self.assertEqual(result["score"], cap)
                    self.assertEqual(result["liquidity_status"], "partial")
                    self.assertTrue(
                        any(missing in warning for warning in result["warnings"])
                    )
                    check = next(
                        c for c in result["checks"] if c["rule"] == "bank_liquidity"
                    )
                    self.assertEqual(set(check["input"]), {known})

    def test_optional_liquidity_does_not_relax_other_core_gaps(self):
        for core in ("npl_ratio", "provision_coverage", *bank.CAPITAL_METRICS):
            data = packet()
            for key in ("lcr", "nsfr", core):
                del data["reports"][-1]["metrics"][key]
            with self.subTest(core=core):
                self.assertIsNone(bank.score_bank(stock(), data)["score"])

    def test_missing_bank_data_is_not_poor_quality(self):
        result = bank.score_bank(stock(), None)
        self.assertIsNone(result["score"])
        self.assertEqual(result["status"], "insufficient_data")

    def test_core_gaps_preserve_known_weakness(self):
        data = packet()
        data["reports"][-1]["metrics"]["npl_ratio"] = metric(4)
        del data["reports"][-1]["metrics"]["tier1_ratio"]
        result = bank.score_bank(stock(), data)
        self.assertIsNone(result["score"])
        self.assertTrue(any("不良" in risk for risk in result["risks"]))
        self.assertTrue(any("tier1_ratio" in issue for issue in result["issues"]))

    def test_partial_safety_data_preserves_verified_breach(self):
        data = packet()
        data["reports"][-1]["metrics"]["cet1_ratio"] = metric(7)
        data["reports"][-1]["metrics"]["nsfr"] = metric(90)
        del data["reports"][-1]["metrics"]["tier1_ratio"]
        del data["reports"][-1]["metrics"]["lcr"]
        result = bank.score_bank(stock(), data)
        self.assertIsNone(result["score"])
        self.assertTrue(any("资本充足率低于" in risk for risk in result["risks"]))
        self.assertTrue(any("100%监管底线" in risk for risk in result["risks"]))

    def test_invalid_metric_does_not_erase_other_known_risks(self):
        data = packet()
        data["reports"][-1]["metrics"]["npl_ratio"] = metric(4)
        data["reports"][-1]["metrics"]["lcr"] = metric("bad")
        result = bank.score_bank(stock(), data)
        self.assertIsNone(result["score"])
        self.assertTrue(any("不良" in risk for risk in result["risks"]))
        self.assertTrue(any("lcr" in issue for issue in result["issues"]))

    def test_bad_identity_hash_or_future_disclosure_blocks(self):
        for mutate in (
            lambda d: d.update(code="600000"),
            lambda d: d.update(stock_sha256="0" * 64),
            lambda d: d["reports"][-1].update(published_at="2026-11-01"),
            lambda d: d["reports"][-1].update(scope="bank"),
            lambda d: d["reports"][-1].update(period_end="2026-05-31"),
            lambda d: d.update(as_of="2026-13-01"),
        ):
            data = packet()
            mutate(data)
            with self.subTest(data=data):
                self.assertIsNone(bank.score_bank(stock(), data)["score"])

    def test_old_or_missing_latest_annual_not_backfilled(self):
        data = packet()
        data["reports"] = [
            r for r in data["reports"] if r["period_end"] != "2025-12-31"
        ]
        old = copy.deepcopy(data["reports"][0])
        old.update(period_end="2022-12-31", published_at="2023-03-25")
        data["reports"].append(old)
        self.assertIsNone(bank.score_bank(stock(), data)["score"])

    def test_before_may_accepts_available_annual_or_previous_year_window(self):
        data = packet()
        data["as_of"] = "2026-03-01"
        data["reports"] = data["reports"][:2]
        old = copy.deepcopy(data["reports"][0])
        old.update(period_end="2022-12-31", published_at="2023-03-25")
        data["reports"].insert(0, old)
        data["reports"][-1]["metrics"].update(
            copy.deepcopy(packet()["reports"][-1]["metrics"])
        )
        snapshot = copy.deepcopy(packet()["reports"][-1])
        snapshot.update(
            period_end="2025-09-30", published_at="2025-10-25", period_type="quarter"
        )
        data["reports"].append(snapshot)
        data["requirements_period_end"] = "2025-09-30"
        data["requirements_published_at"] = "2025-10-25"
        self.assertEqual(bank.score_bank(stock(), data)["score"], 5)

    def test_duplicate_period_and_stale_snapshot_rejected(self):
        data = packet()
        data["reports"].append(copy.deepcopy(data["reports"][-1]))
        self.assertIsNone(bank.score_bank(stock(), data)["score"])
        data = packet()
        data["as_of"] = "2028-01-01"
        self.assertIsNone(bank.score_bank(stock(), data)["score"])

    def test_finite_numeric_provenance_and_basis(self):
        for value in (True, "150", math.nan, math.inf, -1):
            data = packet()
            data["reports"][-1]["metrics"]["lcr"]["value"] = value
            with self.subTest(value=value):
                self.assertIsNone(bank.score_bank(stock(), data)["score"])
        for key, value in (
            ("source_url", "file:///secret"),
            ("locator", ""),
            ("basis", "period"),
        ):
            data = packet()
            data["reports"][-1]["metrics"]["npl_ratio"][key] = value
            self.assertIsNone(bank.score_bank(stock(), data)["score"])

    def test_capital_actual_surplus_not_one_universal_minimum(self):
        for requirement, expected in (
            (8, 5),
            (9.5, 4),
            (10.5, 3),
            (11.5, 2),
            (12.1, 1),
        ):
            data = packet()
            data["requirements"]["cet1_ratio"] = metric(requirement)
            data["requirements"]["tier1_ratio"] = metric(requirement + 1)
            data["requirements"]["total_capital_ratio"] = metric(requirement + 3)
            with self.subTest(requirement=requirement):
                self.assertEqual(bank.score_bank(stock(), data)["score"], expected)

    def test_liquidity_and_quality_caps(self):
        for field, values in (
            ("nsfr", ((130, 5), (120, 4), (110, 3), (100, 2), (99.9, 1))),
            ("npl_ratio", ((1, 5), (1.5, 4), (2, 3), (3, 2), (3.01, 1))),
            ("provision_coverage", ((300, 5), (200, 4), (150, 3), (120, 2), (119, 1))),
        ):
            for value, expected in values:
                data = packet()
                data["reports"][-1]["metrics"][field] = metric(value)
                with self.subTest(field=field, value=value):
                    self.assertEqual(bank.score_bank(stock(), data)["score"], expected)

    def test_coverage_quality_is_not_legal_violation(self):
        data = packet()
        data["reports"][-1]["metrics"]["provision_coverage"] = metric(140)
        result = bank.score_bank(stock(), data)
        self.assertEqual(result["score"], 2)
        self.assertFalse(
            any("低于适用拨备监管要求" in risk for risk in result["risks"])
        )
        data["requirements"]["provision_coverage"] = metric(145)
        result = bank.score_bank(stock(), data)
        self.assertEqual(result["score"], 1)
        self.assertTrue(any("低于适用拨备监管要求" in risk for risk in result["risks"]))

    def test_missing_optional_data_does_not_cap(self):
        self.assertEqual(bank.score_bank(stock(), packet())["score"], 5)
        data = packet()
        data["reports"][-1]["metrics"]["loan_provision_ratio"] = metric(3.15)
        self.assertEqual(bank.score_bank(stock(), data)["score"], 5)
        data["reports"][-1]["metrics"]["loan_provision_ratio"] = metric(1.5)
        self.assertIsNone(bank.score_bank(stock(), data)["score"])

    def test_annual_profitability_and_trend_not_industrial_short_quarter(self):
        data = packet()
        for row, value in zip(data["reports"][:3], (18, 17, 16)):
            row["metrics"]["roe"] = metric(value, "period")
        self.assertEqual(bank.score_bank(stock(), data)["score"], 4)
        data = packet()
        data["reports"][2]["metrics"]["npl_ratio"] = metric(1.4)
        self.assertEqual(bank.score_bank(stock(), data)["score"], 2)
        data = packet()
        for row in data["reports"][:3]:
            row["metrics"]["roe"] = metric(0, "period")
        self.assertEqual(bank.score_bank(stock(), data)["score"], 1)

    def test_zero_npl_and_unsupported_liquidity_regime(self):
        data = packet()
        data["reports"][-1]["metrics"]["npl_ratio"] = metric(0)
        self.assertEqual(bank.score_bank(stock(), data)["score"], 5)
        data["liquidity_regime"] = "small_bank_hqla"
        self.assertIsNone(bank.score_bank(stock(), data)["score"])

    def test_unsupported_liquidity_regime_preserves_facts_without_breach_or_cap(self):
        data = packet()
        data["liquidity_regime"] = "small_bank_hqla"
        data["reports"][-1]["metrics"]["lcr"] = metric(90)
        result = bank.score_bank(stock(), data)
        self.assertIsNone(result["score"])
        self.assertFalse(any("100%监管底线" in risk for risk in result["risks"]))
        liquidity = [
            check for check in result["checks"] if check["rule"] == "bank_liquidity"
        ]
        self.assertEqual(len(liquidity), 1)
        self.assertIsNone(liquidity[0]["cap"])
        self.assertEqual(liquidity[0]["input"]["lcr"]["value"], 90)

    def test_requirement_period_missing_or_mismatch_cannot_establish_breach(self):
        for declared in (None, "2025-12-31"):
            data = packet()
            if declared is None:
                del data["requirements_period_end"]
            else:
                data["requirements_period_end"] = declared
            data["reports"][-1]["metrics"]["cet1_ratio"] = metric(7)
            data["reports"][-1]["metrics"]["provision_coverage"] = metric(140)
            data["requirements"]["provision_coverage"] = metric(145)
            result = bank.score_bank(stock(), data)
            with self.subTest(declared=declared):
                self.assertIsNone(result["score"])
                self.assertFalse(
                    any("低于" in risk and "要求" in risk for risk in result["risks"])
                )
                self.assertFalse(
                    any(
                        check["rule"]
                        in ("bank_capital_buffer", "bank_regulatory_provision_coverage")
                        and check["cap"] is not None
                        for check in result["checks"]
                    )
                )
                self.assertTrue(
                    any(
                        "requirements_period_end" in issue for issue in result["issues"]
                    )
                )

    def test_requirement_disclosure_must_be_available_by_as_of(self):
        for published in (None, "2026-11-01", "2026-02-30"):
            data = packet()
            data["requirements_published_at"] = published
            data["reports"][-1]["metrics"]["cet1_ratio"] = metric(7)
            result = bank.score_bank(stock(), data)
            with self.subTest(published=published):
                self.assertIsNone(result["score"])
                self.assertFalse(
                    any("资本充足率低于" in risk for risk in result["risks"])
                )
                self.assertTrue(
                    any(
                        "requirements_published_at" in issue
                        for issue in result["issues"]
                    )
                )
        data = packet()
        data["requirements_published_at"] = "2024-01-01"
        self.assertEqual(bank.score_bank(stock(), data)["score"], 5)

    def test_peer_comparison_requires_same_period_group_and_sources(self):
        data = packet()
        data["peer_group"] = "股份行"
        data["peers"] = [
            {
                "code": "600000",
                "peer_group": "股份行",
                "scope": "group",
                "period_end": "2026-06-30",
                "published_at": "2026-08-27",
                "metrics": {"npl_ratio": metric(1.2)},
            }
        ]
        result = bank.score_bank(stock(), data)
        self.assertEqual(result["score"], 5)
        self.assertTrue(any(c["rule"] == "peer_comparison" for c in result["checks"]))
        data["peers"][0]["period_end"] = "2025-12-31"
        result = bank.score_bank(stock(), data)
        self.assertEqual(result["score"], 5)
        self.assertTrue(any("peer" in warning for warning in result["warnings"]))

    def test_real_cli_template_validation_and_error_contract(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            stock_file, packet_file = root / "stock.json", root / "bank.json"
            stock_file.write_text(json.dumps(stock()), encoding="utf-8")
            command = [sys.executable, "-X", "utf8", str(SCRIPTS / "bank_financial.py")]
            result = subprocess.run(
                [
                    *command,
                    "template",
                    "--stock",
                    str(stock_file),
                    "--as-of",
                    "2026-10-27",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                json.loads(result.stdout)["stock_sha256"], packet()["stock_sha256"]
            )
            packet_file.write_text(json.dumps(packet()), encoding="utf-8")
            args = [
                *command,
                "validate",
                "--stock",
                str(stock_file),
                "--input",
                str(packet_file),
            ]
            result = subprocess.run(
                args, capture_output=True, text=True, encoding="utf-8", check=False
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "ready")
            data = packet()
            data["requirements"] = {}
            packet_file.write_text(json.dumps(data), encoding="utf-8")
            result = subprocess.run(
                args, capture_output=True, text=True, encoding="utf-8", check=False
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)["status"], "insufficient_data")
            packet_file.write_text('{"invalid":NaN}', encoding="utf-8")
            result = subprocess.run(
                args, capture_output=True, text=True, encoding="utf-8", check=False
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")
            self.assertIn("bank_financial", result.stderr)


if __name__ == "__main__":
    unittest.main()
