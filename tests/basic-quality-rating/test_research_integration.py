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
from validate_rating_json import validate


class ResearchIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.state = self.root / "research.json"
        self.stock = {"code": "000001", "name": "虚构公司"}
        self.run = ResearchRun(self.state)
        self.run.init(self.stock, ["primary", "backup"])
        self.draft = {
            **self.stock,
            "dimensions": {key: 4 for key in (*REQUIRED_TOPICS, "financial")},
            "summary": "测试",
            "risks": [],
            "watch_points": [],
            "report_md": "# 测试",
        }

    def gap_all(self):
        for key in REQUIRED_TOPICS:
            self.run.close(key, "gap", "来源受限，缺乏可靠事实")
            self.draft["dimensions"][key] = None

    def test_unfinished_state_blocks_and_gap_state_keeps_ten_fields(self):
        # Legacy unflagged path stays compatible.
        self.assertEqual(len(finalize(self.draft, self.stock)), 10)
        with self.assertRaises(ValueError):
            finalize(self.draft, self.stock, research_state=self.state)
        self.gap_all()
        rated = finalize(self.draft, self.stock, research_state=self.state)
        self.assertEqual(len(rated), 10)
        self.assertIsNone(rated["stars"])
        self.assertEqual(
            validate(rated, self.stock, research_state=self.state)["status"], "passed"
        )
        rated["dimensions"]["business"] = 3
        self.assertEqual(
            validate(rated, self.stock, research_state=self.state)["status"], "failed"
        )

    def test_cli_gate_blocks_unfinished_research_without_partial_stdout(self):
        draft_file, stock_file = self.root / "draft.json", self.root / "stock.json"
        stock_file.write_text(json.dumps(self.stock), encoding="utf-8")
        command = [
            sys.executable,
            str(SCRIPTS / "rating_math.py"),
            "finalize",
            "--input",
            str(draft_file),
            "--stock",
            str(stock_file),
            "--research-state",
            str(self.state),
        ]
        draft_file.write_text(json.dumps(self.draft), encoding="utf-8")
        run = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", check=False
        )
        self.assertEqual(run.returncode, 2)
        self.assertEqual(run.stdout, "")
        self.gap_all()
        draft_file.write_text(json.dumps(self.draft), encoding="utf-8")
        run = subprocess.run(
            command, capture_output=True, text=True, encoding="utf-8", check=False
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        rating_file = self.root / "rating.json"
        rating_file.write_text(run.stdout, encoding="utf-8")
        run = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "validate_rating_json.py"),
                str(rating_file),
                "--stock",
                str(stock_file),
                "--research-state",
                str(self.state),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(run.returncode, 0, run.stdout or run.stderr)
        self.assertEqual(json.loads(run.stdout)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
