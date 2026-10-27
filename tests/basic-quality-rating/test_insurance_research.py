import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "finance-macro/basic-quality-rating/scripts"
)
sys.path.insert(0, str(SCRIPTS))
from research_state import REQUIRED_TOPICS, ResearchRun, check_research


class InsuranceResearchTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.work.cleanup)
        self.run = ResearchRun(Path(self.work.name) / "state.json")
        self.stock = {
            "code": "601318",
            "name": "测试保险",
            "sw_level1": "非银金融",
            "sw_level2": "保险",
        }

    def test_append_insurance_mode_preserves_budgets_and_prevents_wrong_mode(self):
        self.run.init(self.stock, ["primary", "official"])
        self.run.start("business", "主业是什么", "A评分", "biz-1", now=1)
        self.run.result(
            "business", "biz-1", 1, "failure", error={"http_status": 402}, now=1
        )
        result = self.run.init(
            self.stock, ["primary", "official"], insurance_research=True
        )
        self.assertEqual(result["dimensions"]["business"]["rounds_used"], 1)
        self.assertIn("solvency", result["dimensions"]["financial"]["missing_topics"])
        self.assertEqual(
            self.run.start("financial", "资本够吗", "E评分", "ins-1", now=1)[
                "provider"
            ],
            "official",
        )
        self.run.init(self.stock, ["primary", "official"])
        self.assertEqual(self.run.status("financial")["rounds_used"], 1)
        with self.assertRaises(ValueError):
            self.run.init(self.stock, ["primary", "official"], bank_research=True)

    def test_financial_ledger_topics_and_gate(self):
        self.run.init(self.stock, ["official"], insurance_research=True)
        draft = {
            **self.stock,
            "dimensions": {key: None for key in (*REQUIRED_TOPICS, "financial")},
        }
        for key in REQUIRED_TOPICS:
            self.run.close(key, "gap", "资料缺口")
        with self.assertRaises(ValueError):
            check_research(self.run.path, draft, self.stock, require_insurance=True)
        facts = [
            {
                "topic": topic,
                "statement": "已核对资料，数据见保险包",
                "url": "https://example.com/insurance.pdf",
                "locator": "PDF p.10",
                "period": "2026-06-30",
            }
            for topic in (
                "profitability",
                "solvency",
                "insurance_business",
                "asset_liability",
            )
        ]
        self.run.close("financial", "complete", "已核对四类证据", facts)
        draft["dimensions"]["financial"] = 4
        check_research(self.run.path, draft, self.stock, require_insurance=True)
        with self.assertRaises(ValueError):
            check_research(self.run.path, draft, self.stock, require_bank=True)


if __name__ == "__main__":
    unittest.main()
