import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts import calculate_macro_index as macro


class MacroAssessmentTests(unittest.TestCase):
    def test_missing_core_signal_makes_assessment_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            result = macro.run_assessment(skills_root=skills_root, today=date(2026, 5, 22))

        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["macro"]["score"])
        self.assertEqual(result["macro"]["tone"], "不可用")
        self.assertIn("monetary_policy", result["data_quality"]["missing_dimensions"])
        self.assertIn("money_supply", result["data_quality"]["missing_dimensions"])
        self.assertTrue(result["data_quality"]["blocking_errors"])

    def test_complete_signals_separate_macro_and_market_sentiment(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills_root = Path(tmp)
            fixtures = {
                "monetary-policy-skill": {
                    "dimension": "monetary_policy",
                    "score": 80,
                    "conclusion": "偏宽松",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"dr007": 1.6, "lpr_1y": 3.0},
                },
                "money-supply-skill": {
                    "dimension": "money_supply",
                    "score": 70,
                    "conclusion": "信用扩张",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"m2_yoy": 8.8, "m1_yoy": 5.8},
                },
                "entity-economy-skill": {
                    "dimension": "entity_economy",
                    "score": 55,
                    "conclusion": "温和修复",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"electricity_yoy": 5.0},
                },
                "inflation-skill": {
                    "dimension": "inflation",
                    "score": 50,
                    "conclusion": "温和",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"cpi_yoy": 1.2, "ppi_yoy": 2.8},
                },
                "exchange-rate-skill": {
                    "dimension": "exchange_rate",
                    "score": 60,
                    "conclusion": "外部压力中性",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"dollar_index": 99.0, "usd_cny": 7.1},
                },
                "risk-appetite-skill": {
                    "dimension": "risk_appetite",
                    "score": 82,
                    "conclusion": "偏热",
                    "data_date": "2026-05-20",
                    "errors": [],
                    "details": {"turnover_score": 80, "margin_score": 55},
                },
            }
            for folder, payload in fixtures.items():
                path = skills_root / folder
                path.mkdir()
                (path / "macro_signal.json").write_text(
                    json.dumps(payload, ensure_ascii=False), encoding="utf-8"
                )

            result = macro.run_assessment(skills_root=skills_root, today=date(2026, 5, 22))

        self.assertEqual(result["status"], "available")
        self.assertEqual(result["macro"]["tone"], "偏利好")
        self.assertEqual(result["sentiment"]["temperature"], "偏热")
        self.assertIn("短期追高风险上升", result["summary"])
        self.assertNotIn("risk_appetite", result["macro"]["weights"])
        self.assertEqual(
            set(result["macro_data_details"].keys()),
            {"货币政策", "信用扩张", "经济运行", "通胀环境", "外部压力", "市场情绪"},
        )
        self.assertEqual(result["macro_data_details"]["货币政策"]["指标明细"]["dr007"], 1.6)
        self.assertEqual(result["macro_data_details"]["市场情绪"]["指标明细"]["margin_score"], 55)


if __name__ == "__main__":
    unittest.main()
