import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "finance-macro/basic-quality-rating/scripts"
sys.path.insert(0, str(SCRIPTS))
import pdf_evidence as pdf

SPEC = importlib.util.spec_from_file_location(
    "bank_evidence", SCRIPTS / "bank_evidence.py"
)


def sample_pdf(texts):
    doc = pymupdf.open()
    for text in texts:
        page = doc.new_page()
        if text:
            page.insert_textbox(
                pymupdf.Rect(30, 30, 560, 780), text, fontname="china-s", fontsize=10
            )
    body = doc.tobytes()
    doc.close()
    return body


class BankEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = importlib.util.module_from_spec(SPEC)
        SPEC.loader.exec_module(cls.bank)

    def setUp(self):
        self.work = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.requests = []
        self.body = sample_pdf(
            [
                (
                    "2025年度 2024年度\n核心一级资本充足率 14.16% 14.86%\n"
                    "一级资本充足率 16.02% 16.24%\n资本充足率 18.24% 18.93%\n"
                    "不良贷款率 0.94% 0.95%\n拨备覆盖率 391.79% 411.98%\n"
                    "流动性覆盖率 160.3% 150.2%\n净稳定资金比例 128.6% 126.4%"
                ),
                (
                    "加权平均净资产收益率 14.20% 15.00%\n平均总资产收益率 1.2%\n"
                    "贷款拨备率 3.68%\n净息差 1.87%\n关注类贷款 1.25%\n"
                    "逾期90天以上贷款 123亿元\n"
                ),
                "",
            ]
        )

        def transport(request):
            self.requests.append(str(request.url))
            return httpx.Response(200, content=self.body)

        self.client = httpx.Client(transport=httpx.MockTransport(transport))
        self.addCleanup(self.client.close)
        self.url = "https://example.test/bank.pdf"

    def prepare(self):
        return pdf.prepare_pdf(self.url, self.root / "cache", client=self.client)

    def test_candidates_reuse_integrity_checked_cache_and_are_never_scored_values(self):
        directory = self.prepare()["document_dir"]
        with patch.object(
            pdf, "_load_tools", side_effect=AssertionError("must reuse cache")
        ):
            result = self.bank.find_bank_candidates(directory)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(result["source"]["requested_url"], self.url)
        self.assertEqual(len(result["source"]["sha256"]), 64)
        self.assertTrue(result["needs_confirmation"])
        self.assertGreaterEqual(result["candidate_count"], 12)
        self.assertEqual({item["page"] for item in result["items"]}, {1, 2})
        for item in result["items"]:
            self.assertTrue(item["needs_confirmation"])
            self.assertNotIn("value", item)
            self.assertTrue(all(isinstance(n, str) for n in item["numeric_strings"]))
        self.assertIn("列", " ".join(result["warnings"]))
        self.assertTrue(any("no OCR" in warning for warning in result["warnings"]))

    def test_nested_capital_labels_do_not_count_as_other_capital_metrics(self):
        self.body = sample_pdf(["核心一级资本充足率 14.16%"])
        result = self.bank.find_bank_candidates(self.prepare()["document_dir"])
        self.assertEqual([item["metric"] for item in result["items"]], ["cet1_ratio"])
        self.assertIn("14.16%", result["items"][0]["numeric_strings"])

    def test_label_whitespace_and_directly_adjacent_number_are_preserved(self):
        self.body = sample_pdf(["不 良 贷 款 率0.94%"])
        result = self.bank.find_bank_candidates(self.prepare()["document_dir"])
        self.assertEqual(result["items"][0]["metric"], "npl_ratio")
        self.assertIn("0.94%", result["items"][0]["numeric_strings"])

    def test_scanned_pdf_does_not_invent_metrics(self):
        doc = pymupdf.open()
        page = doc.new_page()
        image = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
        image.clear_with(255)
        page.insert_image(page.rect, pixmap=image)
        self.body = doc.tobytes()
        doc.close()
        result = self.bank.find_bank_candidates(self.prepare()["document_dir"])
        self.assertEqual(result["items"], [])
        self.assertTrue(any("no OCR" in warning for warning in result["warnings"]))

    def test_context_keeps_multiple_columns_and_units_ambiguous(self):
        result = self.bank.find_bank_candidates(self.prepare()["document_dir"])
        item = next(item for item in result["items"] if item["metric"] == "npl_ratio")
        self.assertIn("0.94%", item["numeric_strings"])
        self.assertIn("0.95%", item["numeric_strings"])
        self.assertNotIn("period_end", item)
        self.assertNotIn("accepted", item)

    def test_continuation_is_bounded_complete_and_source_bound(self):
        directory = self.prepare()["document_dir"]
        full = self.bank.find_bank_candidates(directory, max_chars=12000)
        seen = []
        cursor = None
        while True:
            packet = self.bank.find_bank_candidates(
                directory, max_chars=128, cursor=cursor
            )
            self.assertLessEqual(packet["text_chars"], 128)
            self.assertLessEqual(sum(len(i["text"]) for i in packet["items"]), 128)
            seen.extend((i["metric"], i["page"], i["text"]) for i in packet["items"])
            cursor = packet["next_cursor"]
            if not cursor:
                break
            self.assertLess(len(seen), 100)
        for item in full["items"]:
            reconstructed = "".join(
                text
                for metric, page, text in seen
                if metric == item["metric"] and page == item["page"]
            )
            self.assertEqual(reconstructed, item["text"])
        token = self.bank.find_bank_candidates(directory, max_chars=128)["next_cursor"]
        self.body = sample_pdf(["不良贷款率 1.25% " * 20])
        other = pdf.prepare_pdf(
            "https://example.test/other.pdf", self.root / "cache", client=self.client
        )["document_dir"]
        with self.assertRaisesRegex(ValueError, "cursor"):
            self.bank.find_bank_candidates(other, cursor=token)

    def test_corruption_no_hit_and_limits_fail_without_fabricated_metrics(self):
        self.body = sample_pdf(["普通业务概况", ""])
        directory = Path(self.prepare()["document_dir"])
        result = self.bank.find_bank_candidates(directory)
        self.assertEqual(result["items"], [])
        self.assertEqual(result["candidate_count"], 0)
        self.assertIsNone(result["next_cursor"])
        self.assertTrue(result["warnings"])
        for value in (0, 63, 12001, True):
            with self.assertRaises(ValueError):
                self.bank.find_bank_candidates(directory, max_chars=value)
        with self.assertRaises(ValueError):
            self.bank.find_bank_candidates(directory, cursor="invalid")
        page_file = directory / "pages.jsonl"
        page_file.write_bytes(page_file.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.bank.find_bank_candidates(directory)

    def test_cli_single_json_and_error_stderr(self):
        directory = self.prepare()["document_dir"]
        command = [sys.executable, "-X", "utf8", str(SCRIPTS / "bank_evidence.py")]
        good = subprocess.run(
            command + ["--document-dir", directory],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertTrue(json.loads(good.stdout)["needs_confirmation"])
        self.assertEqual(good.stderr, "")
        bad = subprocess.run(
            command + ["--document-dir", str(self.root / "missing")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(bad.stdout, "")
        self.assertIn("bank_evidence", bad.stderr)


if __name__ == "__main__":
    unittest.main()
