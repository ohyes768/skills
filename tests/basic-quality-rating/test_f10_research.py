"""F10 acquisition uses a real budgeted ledger mode, not legacy sector research."""

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
from research_state import REQUIRED_TOPICS, ResearchRun, check_research


class F10ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stock = {"code": "601288", "name": "农业银行", "sw_level1": "银行"}
        self.path = self.root / "research.json"
        self.run = ResearchRun(self.path)

    def init(self, **kwargs):
        return self.run.init(
            self.stock, ["direct"], research_limit=2, f10_research=True, **kwargs
        )

    def fact(self):
        return {
            "topic": "f10_data",
            "statement": "第三方F10主要指标覆盖目标期，基础财务评分可用，非官方逐项核验",
            "url": "https://datacenter.eastmoney.com/securities/api/data/v1/get",
            "locator": "RPT_F10_FINANCE_MAINFINADATA，ROEJQ及扣非指标",
            "period": "2025年度",
        }

    def test_f10_receipt_consumes_budget_and_can_complete_without_sector_topics(self):
        summary = self.init()
        self.assertEqual(summary["dimensions"]["financial"]["mode"], "f10")
        self.assertEqual(
            summary["dimensions"]["financial"]["missing_topics"], ["f10_data"]
        )
        receipt = self.run.start("financial", "获取F10包", "决定E分", "fin-1")
        self.assertEqual(receipt["action"], "search")
        self.assertEqual(self.run.status()["execution"]["research_remaining"], 1)
        self.run.result("financial", "fin-1", 1, "success", evidence=[self.fact()])
        self.run.close("financial", "complete", "已取得基础评分所需数据")
        self.init()
        self.assertEqual(self.run.status()["execution"]["research_remaining"], 1)
        self.assertEqual(self.run.status("financial")["status"], "complete")

    def test_failure_can_deliver_ungraded_and_seal_checks_financial_state(self):
        self.init()
        self.run.start("financial", "获取F10包", "决定E分", "fin-1")
        self.run.result("financial", "fin-1", 1, "failure", error={"http_status": 402})
        for key in REQUIRED_TOPICS:
            self.run.close(key, "gap", "无可用来源")
        dimensions = {key: None for key in (*REQUIRED_TOPICS, "financial")}
        self.run.seal(dimensions)
        draft = {**self.stock, "dimensions": dimensions}
        check_research(self.path, draft, self.stock, require_f10=True)
        dimensions["financial"] = 3
        with self.assertRaisesRegex(ValueError, "financial"):
            self.run.seal(dimensions)

    def test_existing_ad_ledger_can_enable_f10_without_resetting_budget(self):
        self.run.init(self.stock, ["direct"], research_limit=2)
        self.run.start("business", "核对主营", "决定A分", "b1")
        self.run.result("business", "b1", 1, "success")
        self.init()
        self.assertEqual(self.run.status()["execution"]["research_remaining"], 1)
        self.run.start("financial", "获取F10包", "决定E分", "fin-1")
        self.assertEqual(self.run.status()["execution"]["research_remaining"], 0)
        with self.assertRaises(ValueError):
            self.run.init(self.stock, ["direct"], research_limit=3, f10_research=True)

    def test_modes_are_mutually_exclusive_and_cannot_rebind_existing_sector(self):
        for mode in ("bank_research", "insurance_research"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                self.init(**{mode: True})
        self.run.init(self.stock, ["direct"], bank_research=True, research_limit=2)
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.init()
        self.assertEqual(self.path.read_bytes(), before)

    def test_f10_cannot_be_marked_complete_from_unrelated_sector_evidence(self):
        self.init()
        with self.assertRaises(ValueError):
            self.run.close("financial", "complete", "缺数据")
        fact = {**self.fact(), "topic": "capital"}
        with self.assertRaises(ValueError):
            self.run.close("financial", "complete", "错误来源主题", [fact])
        with self.assertRaises(ValueError):
            check_research(
                self.path, {**self.stock, "dimensions": {}}, require_bank=True
            )

    def test_all_sectors_use_f10_and_modes_cannot_change_after_completion(self):
        for i, sector in enumerate(("银行", "非银金融", "机械设备")):
            run = ResearchRun(self.root / f"sector-{i}.json")
            run.init({**self.stock, "sw_level1": sector}, ["direct"], f10_research=True)
            self.assertEqual(run.status("financial")["mode"], "f10")
        self.init()
        self.run.close("financial", "complete", "复用有效F10证据", [self.fact()])
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            self.run.init(self.stock, ["direct"], bank_research=True, research_limit=2)
        self.assertEqual(self.path.read_bytes(), before)

    def test_f10_cannot_bypass_exhausted_global_budget(self):
        self.init()
        self.run.start("business", "主营", "业务分", "b1")
        self.run.result("business", "b1", 1, "success")
        self.run.start("industry", "需求", "行业分", "i1")
        self.run.result("industry", "i1", 1, "success")
        self.assertEqual(
            self.run.start("financial", "获取F10", "E分", "fin-1")["action"], "stop"
        )
        self.run.close("financial", "gap", "预算耗尽，未取得基础财务数据")
        self.assertEqual(self.run.status()["execution"]["research_remaining"], 0)

    def test_f10_checked_finalization_requires_matching_closed_financial_ledger(self):
        from f10_financial import LIMITATION
        from rating_math import finalize
        from test_f10_financial import sample

        self.stock, packet = sample()
        self.run.init(self.stock, ["direct"], research_limit=2)
        for key in REQUIRED_TOPICS:
            self.run.close(key, "gap", "A-D缺证")
        dimensions = {**dict.fromkeys(REQUIRED_TOPICS), "financial": 5}
        draft = {
            **self.stock,
            "dimensions": dimensions,
            "summary": "灰色地带（证据不足，未评级）",
            "report_md": LIMITATION,
            "risks": [],
            "watch_points": [LIMITATION],
        }
        draft.pop("sw_level1")
        self.run.seal(dimensions)
        with self.assertRaisesRegex(ValueError, "f10-research"):
            finalize(
                draft,
                self.stock,
                check_financial=True,
                f10_data=packet,
                research_state=self.path,
            )
        with self.assertRaisesRegex(ValueError, "成稿"):
            self.init()

        self.run = ResearchRun(self.root / "new-f10.json")
        self.path = self.run.path
        self.init()
        for key in REQUIRED_TOPICS:
            self.run.close(key, "gap", "A-D缺证")
        with self.assertRaisesRegex(ValueError, "financial"):
            self.run.seal(dimensions)
        self.run.start("financial", "获取F10", "决定E分", "fin-1")
        self.run.result("financial", "fin-1", 1, "success", evidence=[self.fact()])
        self.run.close("financial", "complete", "基础评分核心数据齐备")
        self.run.seal(dimensions)
        result = finalize(
            draft,
            self.stock,
            check_financial=True,
            f10_data=packet,
            research_state=self.path,
        )
        self.assertEqual(result["dimensions"]["financial"], 5)
        self.assertIsNone(result["stars"])
        self.assertEqual(len(result), 11)

    def test_documented_cli_init_start_result_close(self):
        stock = self.root / "stock.json"
        stock.write_text(json.dumps(self.stock), encoding="utf-8")
        command = [sys.executable, str(SCRIPTS / "research_state.py")]

        def call(*args):
            result = subprocess.run(
                [*command, *args, "--state", str(self.path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)

        call(
            "init",
            "--stock",
            str(stock),
            "--providers",
            "direct",
            "--research-limit",
            "2",
            "--f10-research",
        )
        call(
            "start",
            "--dimension",
            "financial",
            "--question",
            "获取F10包",
            "--impact",
            "决定E分",
            "--request-id",
            "fin-1",
        )
        payload = self.root / "result.json"
        payload.write_text(
            json.dumps(
                {
                    "dimension": "financial",
                    "request_id": "fin-1",
                    "attempt": 1,
                    "outcome": "success",
                    "evidence": [self.fact()],
                }
            ),
            encoding="utf-8",
        )
        call("result", "--input", str(payload))
        closed = call(
            "close",
            "--dimension",
            "financial",
            "--status",
            "complete",
            "--reason",
            "基础指标齐备",
        )
        self.assertEqual(closed["status"], "complete")


if __name__ == "__main__":
    unittest.main()
