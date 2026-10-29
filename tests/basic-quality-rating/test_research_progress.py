"""Lightweight evidence reuse and output consistency without per-call receipts."""

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
from rating_math import finalize
from research_progress import check_progress, make_progress
from research_state import REQUIRED_TOPICS
from validate_rating_json import validate


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stock = {"code": "000001", "name": "测试", "roe": 10}
        self.path = self.root / "progress.json"
        self.data = make_progress(self.stock)
        self.dimensions = dict.fromkeys((*REQUIRED_TOPICS, "financial"), 3)
        self.data["facts"] = [
            {
                "id": "F1",
                "statement": "实际读过的经营事实与限制",
                "url": "https://example.com/annual",
                "locator": "业务及治理栏目",
                "period": "2025年度",
            }
        ]
        for key, topics in REQUIRED_TOPICS.items():
            self.data["dimensions"][key] = {
                "status": "complete",
                "score": 3,
                "reason": "已按本维判别问题裁决",
                "topics": {topic: ["F1"] for topic in topics},
                "gaps": [],
            }

    def save(self):
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False), encoding="utf-8"
        )

    def draft(self):
        return {
            "code": self.stock["code"],
            "name": self.stock["name"],
            "dimensions": self.dimensions,
            "summary": "结论",
            "report_md": "报告",
            "risks": [],
            "watch_points": [],
        }

    def test_one_fact_reused_across_topics_and_dimensions_without_receipts(self):
        self.save()
        before = self.path.read_bytes()
        check_progress(self.path, self.dimensions, self.stock)
        result = finalize(self.draft(), self.stock, progress=self.path)
        self.assertEqual(len(result), 11)
        self.assertEqual(result["stars"], 3)
        self.assertEqual(before, self.path.read_bytes())
        self.assertNotIn("execution", self.data)

    def test_open_gap_and_score_drift(self):
        for patch in (
            {"status": "open", "score": None},
            {"score": 4},
            {"status": "gap", "score": None, "gaps": ["缺治理证据"]},
        ):
            with self.subTest(patch=patch):
                original = copy.deepcopy(self.data)
                self.data["dimensions"]["management"].update(patch)
                self.save()
                with self.assertRaises(ValueError):
                    check_progress(self.path, self.dimensions, self.stock)
                self.data = original
        self.data["dimensions"]["management"].update(
            status="gap", score=None, gaps=["治理安排未核实"]
        )
        self.dimensions["management"] = None
        self.save()
        result = finalize(self.draft(), self.stock, progress=self.path)
        self.assertIsNone(result["stars"])
        self.assertIsNone(result["weighted_score"])

    def test_wrong_input_and_invalid_evidence_rejected(self):
        self.save()
        with self.assertRaises(ValueError):
            check_progress(self.path, self.dimensions, {**self.stock, "roe": 11})
        with self.assertRaises(ValueError):
            finalize({**self.draft(), "code": "999999"}, progress=self.path)
        changes = [
            lambda: self.data["facts"].append(copy.deepcopy(self.data["facts"][0])),
            lambda: self.data["facts"][0].update(url="file:///not-a-source"),
            lambda: self.data["dimensions"]["moat"]["topics"].update(
                advantages=["missing"]
            ),
            lambda: self.data["dimensions"]["moat"]["topics"].pop("counterevidence"),
            lambda: self.data["dimensions"]["moat"].update(score=True),
            lambda: self.data["dimensions"]["moat"].update(
                status="gap", score=None, gaps=[]
            ),
        ]
        for change in changes:
            original = copy.deepcopy(self.data)
            change()
            self.save()
            with self.assertRaises((ValueError, TypeError)):
                check_progress(self.path, self.dimensions, self.stock)
            self.data = original

    def test_f10_finalization_and_readonly_validator_without_financial_ledger(self):
        from f10_financial import LIMITATION
        from test_f10_financial import sample

        self.stock, packet = sample()
        identity = make_progress(self.stock)
        self.data.update(stock=identity["stock"], input_sha256=identity["input_sha256"])
        self.dimensions["financial"] = 5
        self.save()
        draft = {**self.draft(), "report_md": LIMITATION, "watch_points": [LIMITATION]}
        result = finalize(
            draft, self.stock, check_financial=True, f10_data=packet, progress=self.path
        )
        self.assertEqual(
            validate(
                result,
                self.stock,
                check_financial=True,
                f10_data=packet,
                progress=self.path,
            )["status"],
            "passed",
        )
        with self.assertRaises(ValueError):
            finalize(draft, self.stock, progress=self.path, research_state="other.json")
        draft["dimensions"]["financial"] = 4
        with self.assertRaises(ValueError):
            finalize(
                draft,
                self.stock,
                check_financial=True,
                f10_data=packet,
                progress=self.path,
            )

    def call(self, script, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPTS / script), *map(str, args)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

    def test_cli_init_resume_and_delivery_preserve_files(self):
        stock = self.root / "stock.json"
        stock.write_text(json.dumps(self.stock), encoding="utf-8")
        init = self.call(
            "research_progress.py", "init", "--stock", stock, "--output", self.path
        )
        self.assertEqual(init.returncode, 0, init.stderr)
        self.save()
        before = self.path.read_bytes()
        resumed = self.call(
            "research_progress.py", "init", "--stock", stock, "--output", self.path
        )
        self.assertEqual(resumed.returncode, 0, resumed.stderr)
        self.assertEqual(before, self.path.read_bytes())
        stock.write_text(json.dumps({**self.stock, "roe": 11}), encoding="utf-8")
        wrong = self.call(
            "research_progress.py", "init", "--stock", stock, "--output", self.path
        )
        self.assertEqual(wrong.returncode, 2)
        self.assertEqual(before, self.path.read_bytes())
        stock.write_text(json.dumps(self.stock), encoding="utf-8")
        dims = self.root / "dimensions.json"
        dims.write_text(json.dumps(self.dimensions), encoding="utf-8")
        calc = self.call(
            "rating_math.py", "calculate", "--input", dims, "--progress", self.path
        )
        self.assertEqual(calc.returncode, 0, calc.stderr)
        self.assertEqual(json.loads(calc.stdout)["stars"], 3)
        draft = self.root / "draft.json"
        draft.write_text(json.dumps(self.draft()), encoding="utf-8")
        output = self.root / "rating.json"
        final = self.call(
            "rating_math.py",
            "finalize",
            "--input",
            draft,
            "--stock",
            stock,
            "--progress",
            self.path,
            "--output",
            output,
        )
        self.assertEqual(final.returncode, 0, final.stderr)
        self.assertEqual(json.loads(output.read_text())["stars"], 3)
        checked = self.call(
            "validate_rating_json.py", output, "--stock", stock, "--progress", self.path
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertEqual(json.loads(checked.stdout)["status"], "passed")
        protected = self.call(
            "rating_math.py",
            "finalize",
            "--input",
            draft,
            "--stock",
            stock,
            "--progress",
            self.path,
            "--output",
            self.path,
        )
        self.assertEqual(protected.returncode, 2)
        self.assertEqual(before, self.path.read_bytes())
        good = output.read_bytes()
        self.data["dimensions"]["management"].update(status="open", score=None)
        self.save()
        failed = self.call(
            "rating_math.py",
            "finalize",
            "--input",
            draft,
            "--stock",
            stock,
            "--progress",
            self.path,
            "--output",
            output,
        )
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(failed.stdout, "")
        self.assertEqual(output.read_bytes(), good)
        alias = self.call(
            "research_progress.py", "init", "--stock", stock, "--output", stock
        )
        self.assertEqual(alias.returncode, 2)

    def test_no_sources_still_delivers_explicit_ungraded_with_valid_f10(self):
        from f10_financial import LIMITATION
        from test_f10_financial import sample

        self.stock, packet = sample()
        self.data = make_progress(self.stock)
        self.data["failed_sources"] = [
            {"provider": "search_backend", "reason": "余额不足"}
        ]
        for dim in self.data["dimensions"].values():
            dim.update(status="gap", reason="无可读正文", gaps=["缺关键事实"])
        self.dimensions = {**dict.fromkeys(REQUIRED_TOPICS), "financial": 5}
        self.save()
        draft = {
            **self.draft(),
            "summary": "灰色地带（证据不足，未评级）",
            "report_md": LIMITATION,
            "watch_points": [LIMITATION, "补核A-D证据"],
        }
        result = finalize(
            draft, self.stock, check_financial=True, f10_data=packet, progress=self.path
        )
        self.assertIsNone(result["stars"])
        self.assertEqual(result["dimensions"]["financial"], 5)
        self.assertEqual(self.data["facts"], [])

    def test_corrupt_progress_never_resets_on_init(self):
        stock = self.root / "stock.json"
        stock.write_text(json.dumps(self.stock), encoding="utf-8")
        for broken in (
            "[]",
            "null",
            "{",
            '{"progress_type":"quality_rating_progress"}',
        ):
            with self.subTest(broken=broken):
                self.path.write_text(broken, encoding="utf-8")
                result = self.call(
                    "research_progress.py",
                    "init",
                    "--stock",
                    stock,
                    "--output",
                    self.path,
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(self.path.read_text(), broken)


if __name__ == "__main__":
    unittest.main()
