"""Controlled research exhaustion and final-version delivery regressions."""

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
from rating_math import finalize
from research_state import REQUIRED_TOPICS, ResearchRun


class ExecutionControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "research.json"
        self.stock = {"code": "000001", "name": "测试公司"}
        self.run = ResearchRun(self.state)
        self.run.init(self.stock, ["primary", "backup"], research_limit=2)
        self.draft = {
            **self.stock,
            "dimensions": {key: 4 for key in (*REQUIRED_TOPICS, "financial")},
            "summary": "测试报告",
            "risks": [],
            "watch_points": [],
            "report_md": "# 测试",
        }

    def close_from_cache(self):
        for key, topics in REQUIRED_TOPICS.items():
            self.run.close(
                key,
                "complete",
                "复用已核对事实",
                [
                    {
                        "topic": topic,
                        "statement": "已核实的测试事实",
                        "url": "https://example.com/report",
                        "locator": "业务栏目",
                        "period": "2025",
                    }
                    for topic in topics
                ],
            )

    def test_fallbacks_share_global_budget_and_replays_do_not_charge(self):
        first = self.run.start("business", "核对客户", "影响3/4分", "b1", now=1)
        self.assertEqual(first["provider"], "primary")
        self.run.start("business", "核对客户", "影响3/4分", "b1", now=1)
        self.assertEqual(self.run.status()["execution"]["research_remaining"], 1)
        fallback = self.run.result(
            "business", "b1", 1, "failure", error={"http_status": 402}, now=2
        )
        self.assertEqual(fallback["provider"], "backup")
        self.run.result("business", "b1", 2, "success", now=3)
        self.assertEqual(
            self.run.start("industry", "核对需求", "影响行业分", "i1")["action"], "stop"
        )
        self.run.init(self.stock, ["primary", "backup"], research_limit=2)
        self.assertEqual(self.run.status()["execution"]["research_remaining"], 0)
        with self.assertRaises(ValueError):
            self.run.init(self.stock, ["primary", "backup"], research_limit=20)

    def test_new_calls_after_reopen_do_not_reset_budget(self):
        self.close_from_cache()
        self.run.seal(self.draft["dimensions"])
        self.run.reopen("business", "发现收入构成冲突", "影响业务评分")
        self.assertEqual(
            self.run.start("business", "核对新公告", "影响业务评分", "b2")["action"],
            "search",
        )
        self.assertEqual(self.run.status()["execution"]["research_remaining"], 1)
        with self.assertRaises(ValueError):
            finalize(self.draft, self.stock, research_state=self.state)

    def test_missing_or_stale_snapshot_rejected_even_when_stars_unchanged(self):
        self.close_from_cache()
        self.draft["dimensions"].update(industry=3, management=2)
        with self.assertRaisesRegex(ValueError, "快照"):
            finalize(self.draft, self.stock, research_state=self.state)
        self.run.seal(self.draft["dimensions"])
        self.assertEqual(
            finalize(self.draft, self.stock, research_state=self.state)[
                "weighted_score"
            ],
            3.5,
        )
        with self.assertRaises(ValueError):
            self.run.start("business", "再确认一下", "复查", "b1")
        self.draft["dimensions"]["business"] = 3
        with self.assertRaisesRegex(ValueError, "快照"):
            finalize(self.draft, self.stock, research_state=self.state)
        self.run.seal(self.draft["dimensions"])
        self.assertEqual(
            finalize(self.draft, self.stock, research_state=self.state)[
                "weighted_score"
            ],
            3.25,
        )

    def test_exhaustion_still_allows_gap_and_delivery(self):
        self.run.start("business", "核对业务", "影响评分", "b1")
        self.run.result("business", "b1", 1, "failure", error={"http_status": 402})
        self.run.result("business", "b1", 2, "success")
        for key in REQUIRED_TOPICS:
            self.run.close(key, "gap", "预算内缺核心证据")
            self.draft["dimensions"][key] = None
        self.run.seal(self.draft["dimensions"])
        self.assertIsNone(
            finalize(self.draft, self.stock, research_state=self.state)["stars"]
        )
        self.run.reopen("business", "材料冲突", "无法确定分档")
        self.assertEqual(
            self.run.start("business", "核对冲突", "影响评分", "b2")["action"], "stop"
        )
        self.run.close("business", "gap", "预算耗尽，冲突保留")
        self.run.seal(self.draft["dimensions"])

    def test_unfinished_research_cannot_be_sealed_and_legacy_cannot_be_backfilled(self):
        with self.assertRaises(ValueError):
            self.run.seal(self.draft["dimensions"])
        legacy = ResearchRun(self.root / "legacy.json")
        legacy.init(self.stock, ["primary"])
        with self.assertRaises(ValueError):
            legacy.init(self.stock, ["primary"], research_limit=24)

    def test_cli_snapshot_and_atomic_final_output(self):
        self.close_from_cache()
        stock_file, dims, draft, output = [
            self.root / f
            for f in ("stock.json", "dimensions.json", "draft.json", "rating.json")
        ]
        stock_file.write_text(json.dumps(self.stock), encoding="utf-8")
        dims.write_text(json.dumps(self.draft["dimensions"]), encoding="utf-8")
        draft.write_text(json.dumps(self.draft), encoding="utf-8")
        command = [sys.executable, str(SCRIPTS / "rating_math.py")]
        final = [
            *command,
            "finalize",
            "--input",
            str(draft),
            "--stock",
            str(stock_file),
            "--research-state",
            str(self.state),
            "--output",
            str(output),
        ]
        failed = subprocess.run(final, check=False, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(failed.stdout, "")
        self.assertFalse(output.exists())
        calculated = subprocess.run(
            [
                *command,
                "calculate",
                "--input",
                str(dims),
                "--research-state",
                str(self.state),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(calculated.returncode, 0, calculated.stderr)
        delivered = subprocess.run(final, check=False, capture_output=True, text=True)
        self.assertEqual(delivered.returncode, 0, delivered.stderr)
        self.assertEqual(output.read_text(), delivered.stdout)
        self.assertEqual(len(json.loads(delivered.stdout)), 11)
        old = output.read_bytes()
        self.draft["dimensions"]["business"] = 3
        draft.write_text(json.dumps(self.draft), encoding="utf-8")
        failed = subprocess.run(final, check=False, capture_output=True, text=True)
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(failed.stdout, "")
        self.assertEqual(output.read_bytes(), old)
        protected = subprocess.run(
            final[:-1] + [str(stock_file)], check=False, capture_output=True, text=True
        )
        self.assertEqual(protected.returncode, 2)
        self.assertEqual(json.loads(stock_file.read_text()), self.stock)


if __name__ == "__main__":
    unittest.main()
