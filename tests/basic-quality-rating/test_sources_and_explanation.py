"""Reusable citations and score explanations preserve provenance and scoring."""

import hashlib
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
from f10_financial import score_f10
from research_progress import load_progress, make_progress, render_sources
from test_f10_financial import sample


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "progress.json"
        self.data = make_progress({"code": "601288", "name": "农业银行"})
        self.data["sources"] = [
            {
                "id": "S1",
                "title": "公司：业务|经营公告",
                "url": "https://example.com/report",
                "source_type": "official",
                "published_at": None,
                "accessed_at": "2026-10-29",
            },
            {
                "id": "S2",
                "title": "未引用来源",
                "url": "https://example.com/unused",
                "source_type": "media",
                "published_at": "2026-10-28",
                "accessed_at": "2026-10-29",
            },
        ]
        self.data["facts"] = [
            {
                "id": "F1",
                "source_id": "S1",
                "statement": "业务构成已核实",
                "locator": "经营表第1行",
                "period": "2025年度",
            },
            {
                "id": "F2",
                "source_id": "S1",
                "statement": "客户留存情况已核实",
                "locator": "客户栏目",
                "period": "2026中期",
            },
        ]
        self.data["dimensions"]["business"]["topics"] = {
            "main_business": ["F1"],
            "customers_repeat": ["F2"],
        }
        self.data["dimensions"]["moat"]["topics"] = {"advantages": ["F2"]}

    def save(self):
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        return load_progress(self.path)

    def test_one_source_is_rendered_once_with_known_periods_and_unknown_publication(
        self,
    ):
        data = self.save()
        before = self.path.read_bytes()
        table = render_sources(data)
        self.assertEqual(table.count("https://example.com/report"), 1)
        self.assertNotIn("未引用来源", table)
        self.assertIn("未标注；访问于 2026-10-29", table)
        self.assertIn("2025年度", table)
        self.assertIn("2026中期", table)
        self.assertIn("业务\\|经营公告", table)
        self.assertEqual(before, self.path.read_bytes())

    def test_missing_reference_and_invalid_date_are_rejected(self):
        self.data["facts"][0]["source_id"] = "S9"
        with self.assertRaises(ValueError):
            self.save()
        self.data["facts"][0]["source_id"] = "S1"
        self.data["sources"][0]["published_at"] = "2026-02-30"
        with self.assertRaises(ValueError):
            self.save()

    def test_legacy_inline_sources_are_readable_without_invented_titles_or_dates(self):
        self.data["schema_version"] = 1
        del self.data["sources"]
        for fact in self.data["facts"]:
            del fact["source_id"]
            fact["url"] = "https://example.com/legacy"
        table = render_sources(self.save())
        self.assertIn("标题未记录", table)
        self.assertIn("日期未记录", table)

    def test_cli_sources_combines_actual_f10_and_preserves_files(self):
        stock, packet = sample()
        identity = make_progress(stock)
        self.data.update(stock=identity["stock"], input_sha256=identity["input_sha256"])
        for kind in ("main", "balance"):
            packet["datasets"][kind]["url"] = f"https://example.com/f10/{kind}"
        self.save()
        stock_path, packet_path = (
            self.path.parent / "stock.json",
            self.path.parent / "f10.json",
        )
        stock_path.write_text(json.dumps(stock), encoding="utf-8")
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        before = self.path.read_bytes()
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "research_progress.py"),
                "sources",
                "--output",
                str(self.path),
                "--stock",
                str(stock_path),
                "--f10-data",
                str(packet_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("https://example.com/f10/main", result.stdout)
        self.assertNotIn("https://example.com/f10/balance", result.stdout)
        self.assertIn("目标期披露：2026-01-20", result.stdout)
        self.assertEqual(self.path.read_bytes(), before)
        packet["datasets"]["main"]["sha256"] = "bad"
        with self.assertRaises(ValueError):
            render_sources(self.save(), stock=stock, f10_data=packet)

    def test_shared_f10_url_reuses_registered_source_id(self):
        stock, packet = sample()
        identity = make_progress(stock)
        self.data.update(stock=identity["stock"], input_sha256=identity["input_sha256"])
        self.data["sources"][0]["source_type"] = "data_platform"
        packet["datasets"]["main"]["url"] = self.data["sources"][0]["url"]
        table = render_sources(self.save(), stock=stock, f10_data=packet)
        self.assertEqual(table.count("https://example.com/report"), 1)

    def test_invalid_source_metadata_and_duplicate_ids_are_rejected(self):
        self.data["sources"][1]["id"] = "S1"
        with self.assertRaises(ValueError):
            self.save()
        self.data["sources"][1]["id"] = "S2"
        self.data["sources"][1]["url"] = self.data["sources"][0]["url"]
        with self.assertRaises(ValueError):
            self.save()
        self.data["sources"][1]["url"] = "https://example.com/unused"
        self.data["sources"][0]["url"] = "file:///local"
        with self.assertRaises(ValueError):
            self.save()

    def test_shared_sources_work_with_checked_finalization_and_nullable_report(self):
        from f10_financial import LIMITATION
        from rating_math import finalize

        stock, packet = sample()
        identity = make_progress(stock)
        self.data.update(stock=identity["stock"], input_sha256=identity["input_sha256"])
        for dim in self.data["dimensions"].values():
            dim.update(
                status="gap", score=None, reason="核心问题未全回答", gaps=["需补证"]
            )
        self.save()
        draft = {
            "code": stock["code"],
            "name": stock["name"],
            "dimensions": {**dict.fromkeys(self.data["dimensions"]), "financial": 5},
            "summary": "灰色地带（证据不足，未评级）",
            "risks": [],
            "watch_points": [LIMITATION],
            "report_md": LIMITATION + "\n" + render_sources(self.data),
        }
        result = finalize(
            draft, stock, check_financial=True, f10_data=packet, progress=self.path
        )
        self.assertEqual(len(result), 10)
        self.assertIsNone(result["stars"])
        self.assertEqual(result["dimensions"]["financial"], 5)


class ExplanationTests(unittest.TestCase):
    def test_financial_explains_base_and_independent_caps(self):
        stock, packet = sample()
        source = packet["datasets"]["main"]
        body = json.loads(source["body"])
        for row in body["result"]["data"]:
            year = int(row["REPORT_DATE"][:4])
            if row["REPORT_DATE"].endswith("12-31"):
                row["ROEJQ"] = {2022: 19, 2023: 18, 2024: 17, 2025: 16}[year]
            if row["REPORT_DATE"] == "2025-12-31":
                row["KCFJCXSYJLR"] = 1400
        source["body"] = json.dumps(body)
        source["sha256"] = hashlib.sha256(source["body"].encode()).hexdigest()
        result = score_f10(stock, packet)
        explanation = result["explanation"]
        self.assertEqual(explanation["base_score"], 5)
        self.assertEqual(explanation["caps"]["earnings"], 3)
        self.assertEqual(explanation["caps"]["roe_trend"], 4)
        self.assertEqual(explanation["final_score"], result["score"])
        self.assertEqual(result["score"], 3)

    def test_ordinary_explanation_reuses_scorer_caps(self):
        stock, packet = sample("机械设备")
        result = score_f10(stock, packet)
        self.assertEqual(result["explanation"]["base_score"], 5)
        self.assertEqual(result["explanation"]["caps"]["debt"], 2)
        self.assertEqual(result["explanation"]["final_score"], 2)

    def test_missing_data_keeps_null_without_a_reference_score(self):
        stock, packet = sample()
        packet["report_date"] = "2026-09-30"
        explanation = score_f10(stock, packet)["explanation"]
        self.assertIsNone(explanation["final_score"])
        self.assertIn("未评级", explanation["text"])
        self.assertTrue(explanation["missing"])


if __name__ == "__main__":
    unittest.main()
