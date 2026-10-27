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
try:
    import insurance_data as schema
    import insurance_financial as insurance
except ImportError:
    schema = insurance = None


def stock():
    return {
        "code": "601318",
        "name": "测试保险集团",
        "sw_level1": "非银金融",
        "sw_level2": "保险Ⅱ",
        "debt_asset_ratio": 91,
    }


def metric(value, unit="pct", basis="period"):
    return {
        "value": value,
        "unit": unit,
        "basis": basis,
        "source_url": "https://insurer.example/annual.pdf",
        "locator": "PDF p.10, current period, stated scope",
    }


def assessment(status="supported", period="2026-06-30"):
    return {
        "status": status,
        "statement": "Relevant source documents liability matching and reserve evidence for this entity, including stress analysis.",
        "period_end": period,
        "published_at": "2026-08-25",
        "source_url": "https://insurer.example/annual.pdf",
        "locator": "PDF p.20, matching and reserves table",
    }


def entity(kind="life", id_="life"):
    result = {
        "id": id_,
        "name": "测试寿险" if kind == "life" else "测试产险",
        "kind": kind,
        "scope": "solo",
        "latest": {
            "period_end": "2026-06-30",
            "published_at": "2026-08-25",
            "metrics": {
                "core_solvency": metric(160, basis="point_in_time"),
                "comprehensive_solvency": metric(300, basis="point_in_time"),
            },
        },
        "risk_rating": {
            "value": "AA",
            "period_end": "2026-03-31",
            "published_at": "2026-05-25",
            "source_url": "https://insurer.example/solvency.pdf",
            "locator": "PDF p.3, risk comprehensive rating",
        },
        "annuals": [],
        "assessments": {"asset_liability": assessment(), "reserves": assessment()},
    }
    if kind == "life":
        result["value_metric"] = "nbv"
    for year in (2023, 2024, 2025):
        values = (
            {
                "net_investment_yield": metric(4.2),
                "nbv": metric(1000 + (year - 2023) * 100, "cny_million"),
            }
            if kind == "life"
            else {"combined_ratio": metric(94)}
        )
        result["annuals"].append(
            {
                "period_end": f"{year}-12-31",
                "published_at": f"{year + 1}-03-25",
                "period_type": "annual",
                "scope": "solo",
                "comparability_id": "harmonized-2025-definition",
                "metrics": values,
            }
        )
    return result


def packet(original_stock=None, insurance_type="group"):
    kind = original_stock if isinstance(original_stock, str) else insurance_type
    original = original_stock if isinstance(original_stock, dict) else stock()
    data = schema.make_template(original, "2026-10-27", kind)
    for year in (2023, 2024, 2025):
        data["reports"].append(
            {
                "period_end": f"{year}-12-31",
                "published_at": f"{year + 1}-03-25",
                "period_type": "annual",
                "scope": "group",
                "metrics": {"roe": metric(18)},
            }
        )
    data["reports"].append(
        {
            "period_end": "2026-06-30",
            "published_at": "2026-08-25",
            "period_type": "interim",
            "scope": "group",
            "metrics": {"group_solvency_ratio": metric(300, basis="point_in_time")}
            if kind == "group"
            else {},
        }
    )
    data["entities"] = (
        [entity("life", "life"), entity("property", "property")]
        if kind == "group"
        else [entity(kind, kind)]
    )
    data["coverage"] = {
        **assessment(),
        "entity_ids": [e["id"] for e in data["entities"]],
        "other_segments": [],
    }
    return data


class InsuranceFinancialTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(
            insurance, "insurance evidence/scoring must be implemented"
        )

    def test_all_issuer_types_and_immutable_input(self):
        for kind in ("life", "property", "group"):
            data = packet(kind)
            original = copy.deepcopy(data)
            result = insurance.score_insurance(stock(), data)
            self.assertEqual(result["score"], 5, result)
            self.assertEqual(result["sector"], "insurance")
            self.assertEqual(data, original)

    def test_missing_packet_not_low_quality(self):
        result = insurance.score_insurance(stock(), None)
        self.assertIsNone(result["score"])
        self.assertEqual(result["status"], "insufficient_data")
        self.assertEqual(result["risks"], [])

    def test_roe_zero_negative_and_thresholds(self):
        for value, expected in ((-1, 1), (0, 1), (5, 2), (8, 3), (12, 4), (15, 5)):
            data = packet()
            for row in data["reports"][:3]:
                row["metrics"]["roe"]["value"] = value
            self.assertEqual(
                insurance.score_insurance(stock(), data)["score"], expected
            )

    def test_invalid_shapes_never_raise_or_create_score(self):
        for value in (None, [], False, 1, "unknown"):
            for field in ("reports", "entities", "coverage", "insurance_type"):
                data = packet()
                data[field] = value
                self.assertIsNone(insurance.score_insurance(stock(), data)["score"])

    def test_future_assessment_does_not_clear_known_other_weakness(self):
        data = packet()
        member = data["entities"][0]
        member["latest"]["metrics"]["core_solvency"]["value"] = 45
        member["assessments"]["reserves"]["published_at"] = "2026-12-01"
        result = insurance.score_insurance(stock(), data)
        self.assertIsNone(result["score"])
        self.assertTrue(any("50%" in risk for risk in result["risks"]))

    def test_numerical_solvency_and_assessment_boundary(self):
        for core, comprehensive, expected in (
            (50, 100, 1),
            (75, 120, 2),
            (100, 150, 3),
            (120, 200, 4),
            (150, 250, 5),
        ):
            data = packet("life")
            member = data["entities"][0]
            member["latest"]["metrics"]["core_solvency"]["value"] = core
            member["latest"]["metrics"]["comprehensive_solvency"]["value"] = (
                comprehensive
            )
            result = insurance.score_insurance(stock(), data)
            self.assertEqual(result["score"], expected)
            self.assertFalse(any("低于指定" in risk for risk in result["risks"]))
        data = packet("life")
        data["entities"][0]["assessments"]["asset_liability"]["status"] = "adverse"
        self.assertEqual(insurance.score_insurance(stock(), data)["score"], 2)

    def test_negative_solvency_is_known_capital_weakness_not_missing(self):
        data = packet("life")
        member = data["entities"][0]
        member["latest"]["metrics"]["core_solvency"]["value"] = -20
        member["latest"]["metrics"]["comprehensive_solvency"]["value"] = -10
        result = insurance.score_insurance(stock(), data)
        self.assertEqual(result["score"], 1, result)
        self.assertTrue(any("50%" in risk for risk in result["risks"]))
        self.assertTrue(any("100%" in risk for risk in result["risks"]))
        data = packet()
        data["reports"][-1]["metrics"]["group_solvency_ratio"]["value"] = -5
        result = insurance.score_insurance(stock(), data)
        self.assertEqual(result["score"], 1, result)
        self.assertTrue(any("集团偿付能力" in risk for risk in result["risks"]))

    def test_signed_solvency_still_rejects_strings_and_inconsistent_capital(self):
        data = packet("life")
        member = data["entities"][0]
        member["latest"]["metrics"]["core_solvency"]["value"] = "-20"
        self.assertIsNone(insurance.score_insurance(stock(), data)["score"])
        member["latest"]["metrics"]["core_solvency"]["value"] = -10
        member["latest"]["metrics"]["comprehensive_solvency"]["value"] = -20
        result = insurance.score_insurance(stock(), data)
        self.assertIsNone(result["score"])
        self.assertFalse(any("低于指定" in risk for risk in result["risks"]))

    def test_identity_or_future_disclosure_rejects_facts(self):
        for field, value in (("code", "000001"), ("stock_sha256", "0" * 64)):
            data = packet()
            data[field] = value
            result = insurance.score_insurance(stock(), data)
            self.assertIsNone(result["score"])
            self.assertEqual(result["risks"], [])
        data = packet()
        data["entities"][0]["latest"]["published_at"] = "2026-12-31"
        data["entities"][0]["latest"]["metrics"]["core_solvency"]["value"] = 10
        result = insurance.score_insurance(stock(), data)
        self.assertIsNone(result["score"])
        self.assertFalse(any("50%" in r for r in result["risks"]))

    def test_each_subsidiary_matters_no_average(self):
        data = packet()
        data["entities"][0]["latest"]["metrics"]["core_solvency"]["value"] = 49
        data["entities"][1]["latest"]["metrics"]["core_solvency"]["value"] = 500
        data["entities"][1]["latest"]["metrics"]["comprehensive_solvency"]["value"] = (
            600
        )
        result = insurance.score_insurance(stock(), data)
        self.assertEqual(result["score"], 1)
        self.assertTrue(any("50%" in r for r in result["risks"]))

    def test_risk_comprehensive_rating_is_not_numeric_stars(self):
        for value, score in (
            ("BBB", 4),
            ("B", 4),
            ("C", 1),
            ("D", 1),
            ("AAA", 5),
            ("AA", 5),
        ):
            data = packet()
            data["entities"][0]["risk_rating"]["value"] = value
            self.assertEqual(insurance.score_insurance(stock(), data)["score"], score)
        data = packet()
        data["entities"][0]["risk_rating"]["value"] = 1
        self.assertIsNone(insurance.score_insurance(stock(), data)["score"])

    def test_rating_lag_and_entity_scope(self):
        for mutation in ("lag", "scope", "period"):
            data = packet()
            member = data["entities"][0]
            if mutation == "lag":
                member["risk_rating"]["period_end"] = "2025-06-30"
            elif mutation == "scope":
                member["scope"] = "group"
            else:
                member["latest"]["period_end"] = "2025-12-31"
            self.assertIsNone(insurance.score_insurance(stock(), data)["score"])

    def test_group_cannot_omit_material_entity_or_group_solvency(self):
        for mutation in ("roster", "group_ratio", "kind"):
            data = packet()
            if mutation == "roster":
                data["coverage"]["entity_ids"] = ["life"]
            elif mutation == "group_ratio":
                data["reports"][-1]["metrics"] = {}
            else:
                data["entities"] = [data["entities"][0]]
                data["coverage"]["entity_ids"] = ["life"]
            self.assertIsNone(insurance.score_insurance(stock(), data)["score"])

    def test_units_nonfinite_bool_and_partial_fact_retention(self):
        for value in (True, "150", float("nan"), float("inf")):
            data = packet()
            data["entities"][0]["latest"]["metrics"]["comprehensive_solvency"][
                "value"
            ] = value
            data["entities"][0]["latest"]["metrics"]["core_solvency"]["value"] = 49
            result = insurance.score_insurance(stock(), data)
            self.assertIsNone(result["score"])
            self.assertTrue(any("50%" in r for r in result["risks"]), result)
        data = packet()
        data["entities"][0]["annuals"][-1]["metrics"]["nbv"]["unit"] = "pct"
        self.assertIsNone(insurance.score_insurance(stock(), data)["score"])

    def test_comparability_and_history_gaps(self):
        for mutation in ("id", "missing", "duplicate", "roe"):
            data = packet()
            if mutation == "id":
                data["entities"][0]["annuals"][-1]["comparability_id"] = (
                    "new-definition"
                )
            elif mutation == "missing":
                data["entities"][0]["annuals"].pop()
            elif mutation == "duplicate":
                data["reports"].append(copy.deepcopy(data["reports"][0]))
            else:
                data["reports"][2]["metrics"].pop("roe")
            self.assertIsNone(insurance.score_insurance(stock(), data)["score"])

    def test_negative_comprehensive_yield_is_valid_auxiliary_fact(self):
        for key in ("total_investment_yield", "comprehensive_investment_yield"):
            data = packet("life")
            data["entities"][0]["annuals"][-1]["metrics"][key] = metric(-2.5)
            result = insurance.score_insurance(stock(), data)
            self.assertEqual(result["score"], 5, result)
            normalized = schema.validate_insurance_data(stock(), data)
            self.assertEqual(
                normalized["entities"][0]["annuals"][-1]["metrics"][key]["value"], -2.5
            )

    def test_conflicting_annual_value_has_no_order_dependent_weakness(self):
        for reversed_ in (False, True):
            data = packet("life")
            rows = data["entities"][0]["annuals"]
            alternative = copy.deepcopy(rows[-1])
            alternative["metrics"]["nbv"]["value"] = 0
            rows.append(alternative)
            if reversed_:
                rows.reverse()
            data["entities"][0]["latest"]["metrics"]["core_solvency"]["value"] = 45
            result = insurance.score_insurance(stock(), data)
            self.assertIsNone(result["score"])
            self.assertFalse(any("nbv" in risk for risk in result["risks"]))
            self.assertFalse(
                any(check["rule"].endswith("life_value") for check in result["checks"])
            )
            self.assertTrue(any("50%" in risk for risk in result["risks"]))

    def test_conflicting_listed_roe_is_not_selected_by_input_order(self):
        for reversed_ in (False, True):
            data = packet()
            alternative = copy.deepcopy(data["reports"][2])
            alternative["metrics"]["roe"]["value"] = -100
            data["reports"].append(alternative)
            if reversed_:
                data["reports"].reverse()
            result = insurance.score_insurance(stock(), data)
            self.assertIsNone(result["score"])
            self.assertFalse(
                any(
                    check["rule"] == "insurance_profitability"
                    for check in result["checks"]
                )
            )
            self.assertFalse(any("三年盈利能力" in risk for risk in result["risks"]))

    def test_life_value_decline_zero_and_prior_zero(self):
        for prior, latest, expected in (
            (1000, 800, 2),
            (1000, 900, 3),
            (1000, 0, 2),
            (1000, -1, 2),
            (0, 100, 5),
        ):
            data = packet("life")
            data["entities"][0]["annuals"][-2]["metrics"]["nbv"]["value"] = prior
            data["entities"][0]["annuals"][-1]["metrics"]["nbv"]["value"] = latest
            result = insurance.score_insurance(stock(), data)
            self.assertEqual(result["score"], expected, result)

    def test_new_business_csm_alternative_and_auxiliary_missing(self):
        data = packet("life")
        data["entities"][0]["value_metric"] = "new_business_csm"
        for row in data["entities"][0]["annuals"]:
            row["metrics"]["new_business_csm"] = row["metrics"].pop("nbv")
        self.assertEqual(insurance.score_insurance(stock(), data)["score"], 5)
        data["entities"][0]["annuals"][-1]["metrics"]["csm_balance"] = metric(
            10000, "cny_million", "point_in_time"
        )
        self.assertEqual(insurance.score_insurance(stock(), data)["score"], 5)

    def test_property_combined_ratio_quality_not_legal_breach(self):
        for value, score in ((95, 5), (98, 4), (100, 3), (101, 2), (106, 1)):
            data = packet("property")
            for row in data["entities"][0]["annuals"]:
                row["metrics"]["combined_ratio"]["value"] = value
            result = insurance.score_insurance(stock(), data)
            self.assertEqual(result["score"], score, result)
            self.assertFalse(any("违规" in risk for risk in result["risks"]))

    def test_assessments_unknown_vs_adverse_and_material_other_segment(self):
        for status, expected in (("supported", 5), ("unknown", None), ("adverse", 1)):
            data = packet()
            data["entities"][0]["assessments"]["reserves"]["status"] = status
            self.assertEqual(
                insurance.score_insurance(stock(), data)["score"], expected
            )
        for status, expected in (("supported", 5), ("unknown", None), ("adverse", 2)):
            data = packet()
            data["coverage"]["other_segments"] = [
                {**assessment(status), "name": "银行分部", "kind": "bank"}
            ]
            self.assertEqual(
                insurance.score_insurance(stock(), data)["score"], expected
            )

    def test_stale_snapshot_and_future_assessment(self):
        data = packet()
        data["as_of"] = "2027-10-27"
        self.assertIsNone(insurance.score_insurance(stock(), data)["score"])
        data = packet()
        data["entities"][0]["assessments"]["reserves"]["published_at"] = "2026-12-01"
        data["entities"][0]["assessments"]["reserves"]["status"] = "adverse"
        result = insurance.score_insurance(stock(), data)
        self.assertIsNone(result["score"])
        self.assertFalse(any("准备金" in r for r in result["risks"]))

    def test_cli_template_validate_and_malformed(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            root = Path(directory)
            (root / "stock.json").write_text(json.dumps(stock()), encoding="utf-8")
            (root / "packet.json").write_text(json.dumps(packet()), encoding="utf-8")
            base = [sys.executable, str(SCRIPTS / "insurance_financial.py")]
            result = subprocess.run(
                [
                    *base,
                    "template",
                    "--stock",
                    str(root / "stock.json"),
                    "--as-of",
                    "2026-10-27",
                    "--type",
                    "group",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["insurance_type"], "group")
            result = subprocess.run(
                [
                    *base,
                    "validate",
                    "--stock",
                    str(root / "stock.json"),
                    "--input",
                    str(root / "packet.json"),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout or result.stderr)
            (root / "packet.json").write_text("{bad", encoding="utf-8")
            result = subprocess.run(
                [
                    *base,
                    "validate",
                    "--stock",
                    str(root / "stock.json"),
                    "--input",
                    str(root / "packet.json"),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
