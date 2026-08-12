import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts import calculate_bond_index as bond


class BondAssessmentTests(unittest.TestCase):
    def test_missing_core_signal_makes_assessment_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = bond.run_assessment(skills_root=Path(tmp), today=date(2026, 5, 22))

        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["bond"]["score"])
        self.assertEqual(result["bond"]["tone"], "不可用")
        self.assertTrue(result["data_quality"]["blocking_errors"])

    def test_complete_signals_include_details_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            fixtures = {
                "monetary-policy-skill": {
                    "dimension": "monetary_policy",
                    "score": 70,
                    "conclusion": "偏宽松",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"dr007": 1.5, "lpr_1y": 3.0},
                },
                "money-supply-skill": {
                    "dimension": "money_supply",
                    "score": 62,
                    "conclusion": "信用中性",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"m2_yoy": 8.5, "m1_yoy": 5.1},
                },
                "entity-economy-skill": {
                    "dimension": "entity_economy",
                    "score": 52,
                    "conclusion": "平稳",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"electricity_yoy": 3.5},
                },
                "inflation-skill": {
                    "dimension": "inflation",
                    "score": 95,
                    "conclusion": "温和",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"cpi_yoy": 1.2, "ppi_yoy": 2.8},
                },
                "exchange-rate-skill": {
                    "dimension": "exchange_rate",
                    "score": 50,
                    "conclusion": "外部中性",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"dollar_index": 119.0, "usd_cny": 6.8},
                },
                "risk-appetite-skill": {
                    "dimension": "risk_appetite",
                    "score": 75,
                    "conclusion": "偏热",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"turnover_rate": 2.1},
                },
            }
            for folder, payload in fixtures.items():
                path = skills_root / folder
                path.mkdir()
                (path / "macro_signal.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            result = bond.run_assessment(skills_root=skills_root, today=date(2026, 5, 22))

        self.assertEqual(result["status"], "available")
        self.assertIn(result["bond"]["tone"], {"中性", "偏利好", "偏不利", "明显利好", "明显不利"})
        self.assertEqual(
            set(result["bond_data_details"].keys()),
            {"货币政策", "信用扩张", "经济运行", "通胀环境", "外部压力", "市场情绪"},
        )
        self.assertEqual(result["bond_data_details"]["货币政策"]["指标明细"]["dr007"], 1.5)
        self.assertIn("债市底色", result["summary"])


if __name__ == "__main__":
    unittest.main()
