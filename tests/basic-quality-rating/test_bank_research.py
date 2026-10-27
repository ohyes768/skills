import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "finance-macro/basic-quality-rating/scripts"
)
sys.path.insert(0, str(SCRIPTS))
from research_state import ALL_TOPICS, REQUIRED_TOPICS, ResearchRun, check_research


class BankResearchTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.work.cleanup)
        self.run = ResearchRun(Path(self.work.name) / "research.json")
        self.stock = {"code": "000001", "name": "银行", "sw_level1": "银行"}

    def test_bank_ledger_added_without_resetting_existing_rounds_or_routes(self):
        self.run.init(self.stock, ["primary", "official"])
        self.run.start("business", "什么业务", "业务评分", "biz-1", now=1)
        self.run.result(
            "business", "biz-1", 1, "failure", error={"http_status": 402}, now=1
        )
        result = self.run.init(self.stock, ["primary", "official"], bank_research=True)
        self.assertIn("financial", result["dimensions"])
        self.assertEqual(result["dimensions"]["business"]["rounds_used"], 1)
        action = self.run.start(
            "financial", "资本要求是什么", "资本余量评分", "bank-1", now=1
        )
        self.assertEqual(action["provider"], "official")
        self.run.init(self.stock, ["primary", "official"])
        self.assertEqual(self.run.status("financial")["rounds_used"], 1)

    def test_bank_budget_shared_across_metric_questions(self):
        self.run.init(self.stock, ["official"], bank_research=True)
        for number, question in enumerate(("不良率", "资本", "流动性")):
            request_id = f"bank-{number}"
            self.run.start("financial", question, "E评分", request_id, now=1)
            self.run.result("financial", request_id, 1, "success", now=1)
        with self.assertRaises(ValueError):
            self.run.start("financial", "换个关键词再查", "E评分", "bank-4", now=1)
        self.run.close("financial", "gap", "核心资本资料无法取得")
        self.assertEqual(self.run.status("financial")["status"], "gap")

    def test_nonbank_cannot_enable_bank_mode(self):
        with self.assertRaises(ValueError):
            self.run.init(
                {**self.stock, "sw_level1": "机械设备"},
                ["official"],
                bank_research=True,
            )

    def test_checked_bank_research_requires_terminal_financial_evidence(self):
        self.run.init(self.stock, ["official"])
        draft = {**self.stock, "dimensions": {key: None for key in ALL_TOPICS}}
        for key in REQUIRED_TOPICS:
            self.run.close(key, "gap", "测试资料不足")
        with self.assertRaises(ValueError):
            check_research(self.run.path, draft, self.stock, require_bank=True)
        self.run.init(self.stock, ["official"], bank_research=True)
        with self.assertRaises(ValueError):
            check_research(self.run.path, draft, self.stock, require_bank=True)
        facts = [
            {
                "topic": topic,
                "statement": "来源已核对，具体数值见银行证据包",
                "url": "https://example.com/bank.pdf",
                "locator": "PDF p.10",
                "period": "2026-06-30",
            }
            for topic in ALL_TOPICS["financial"]
        ]
        self.run.close("financial", "complete", "四类证据已核查", facts)
        with self.assertRaises(ValueError):
            check_research(self.run.path, draft, self.stock, require_bank=True)
        draft["dimensions"]["financial"] = 4
        check_research(self.run.path, draft, self.stock, require_bank=True)


if __name__ == "__main__":
    unittest.main()
