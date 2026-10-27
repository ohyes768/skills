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
SCRIPT = ROOT / "finance-macro/basic-quality-rating/scripts/pdf_evidence.py"
spec = importlib.util.spec_from_file_location("pdf_evidence", SCRIPT)
pdf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pdf)


def pdf_bytes():
    doc = pymupdf.open()
    for text in (
        "Revenue growth and customer retention " * 18,
        "Governance audit record",
        "",
    ):
        page = doc.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(30, 30, 550, 700), text, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


class PdfEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.requests = []
        self.body = pdf_bytes()

        def transport(request):
            self.requests.append(str(request.url))
            return httpx.Response(200, content=self.body)

        self.client = httpx.Client(transport=httpx.MockTransport(transport))
        self.addCleanup(self.client.close)
        self.url = "https://example.test/annual.pdf"

    def prepare(self, **kwargs):
        return pdf.prepare_pdf(
            self.url, self.root / "cache", client=self.client, **kwargs
        )

    def test_real_pdf_download_index_and_cache_reuse(self):
        first = self.prepare()
        self.assertEqual(first["page_count"], 3)
        self.assertFalse(first["reused"])
        with patch.object(
            pdf, "_load_tools", side_effect=AssertionError("must not parse")
        ):
            second = self.prepare()
            found = pdf.search_pdf(first["document_dir"], ["Revenue", "audit"])
        self.assertTrue(second["reused"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual({item["page"] for item in found["items"]}, {1, 2})
        self.assertEqual(found["source"]["requested_url"], self.url)
        self.assertEqual(len(found["source"]["sha256"]), 64)
        self.assertTrue(any("3" in warning for warning in found["warnings"]))

    def test_read_continuation_delivers_exact_text_with_page_citations(self):
        prepared = self.prepare()
        cursor = None
        text = ""
        packets = 0
        while True:
            result = pdf.read_pdf(
                prepared["document_dir"], "1", max_chars=128, cursor=cursor
            )
            self.assertLessEqual(sum(len(x["text"]) for x in result["items"]), 128)
            self.assertTrue(all(x["page"] == 1 for x in result["items"]))
            text += "".join(x["text"] for x in result["items"])
            packets += 1
            cursor = result["next_cursor"]
            if cursor is None:
                break
            self.assertLess(packets, 30)
        full = pdf.read_pdf(prepared["document_dir"], "1", max_chars=12000)
        self.assertEqual(text, full["items"][0]["text"])
        self.assertGreater(packets, 1)

    def test_search_continuation_is_bounded_and_deterministic(self):
        prepared = self.prepare()
        directory = prepared["document_dir"]
        result = pdf.search_pdf(directory, ["Revenue"], max_chars=128)
        self.assertTrue(result["items"])
        self.assertIsNotNone(result["next_cursor"])
        with self.assertRaises(ValueError):
            pdf.search_pdf(directory, ["audit"], cursor=result["next_cursor"])
        with self.assertRaises(ValueError):
            pdf.read_pdf(directory, "2", cursor=result["next_cursor"])

    def test_corrupted_source_or_index_is_not_silently_served(self):
        directory = Path(self.prepare()["document_dir"])
        pagefile = directory / "pages.jsonl"
        original = pagefile.read_bytes()
        pagefile.write_bytes(original.replace(b"Revenue", b"Changed"))
        for action in (lambda: self.prepare(), lambda: pdf.read_pdf(directory, "1")):
            with self.assertRaises(ValueError):
                action()
        pagefile.write_bytes(original)
        sourcefile = directory / "source.pdf"
        sourcefile.write_bytes(sourcefile.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            pdf.search_pdf(directory, ["Revenue"])

    def test_refresh_rebuilds_and_failed_refresh_preserves_good_cache(self):
        first = self.prepare()
        directory = Path(first["document_dir"])
        self.body = b"not a PDF"
        fetch, _ = pdf._load_tools(str(pdf.DEFAULT_TOOLS))
        with self.assertRaises(fetch.FetchError):
            self.prepare(refresh=True)
        self.assertTrue(pdf.read_pdf(directory, "2")["items"])
        self.body = pdf_bytes()
        refreshed = self.prepare(refresh=True)
        self.assertFalse(refreshed["reused"])
        self.assertEqual(len(self.requests), 3)

    def test_empty_page_and_invalid_query_page_cursor_limits(self):
        directory = self.prepare()["document_dir"]
        empty = pdf.read_pdf(directory, "3")
        self.assertEqual(empty["items"][0]["text"], "")
        self.assertTrue(empty["warnings"])
        for pages in ("0", "4", "2-1", "1-999999999", "1,a", "", "1.5"):
            with self.assertRaises(ValueError, msg=pages):
                pdf.read_pdf(directory, pages)
        for queries in ([], [""], [" "], [123]):
            with self.assertRaises(ValueError):
                pdf.search_pdf(directory, queries)
        for value in (0, -1, 10000000, True):
            with self.assertRaises(ValueError):
                pdf.read_pdf(directory, "1", max_chars=value)
        for cursor in ("bad", "999999", "-1"):
            with self.assertRaises(ValueError):
                pdf.read_pdf(directory, "1", cursor=cursor)
        with self.assertRaises(ValueError):
            pdf.prepare_pdf("file:///tmp/other.pdf", self.root)

    def test_missing_dependencies_metadata_tampering_and_stale_cursor(self):
        with self.assertRaisesRegex(ValueError, "dependency scripts unavailable"):
            self.prepare(tools_dir=self.root / "missing-tools")
        directory = Path(self.prepare()["document_dir"])
        token = pdf.read_pdf(directory, "1", max_chars=128)["next_cursor"]
        doc = pymupdf.open()
        doc.new_page().insert_text((30, 30), "Replacement source with changed evidence")
        self.body = doc.tobytes()
        doc.close()
        self.prepare(refresh=True)
        with self.assertRaisesRegex(ValueError, "stale cursor"):
            pdf.read_pdf(directory, "1", cursor=token)
        source_json = directory / "source.json"
        source = json.loads(source_json.read_text(encoding="utf-8"))
        source["requested_url"] = "https://example.test/wrong.pdf"
        source_json.write_text(json.dumps(source), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash mismatch for source.json"):
            pdf.search_pdf(directory, ["Replacement"])

    def test_scanned_page_is_explicitly_flagged(self):
        doc = pymupdf.open()
        page = doc.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
        pix.clear_with(255)
        page.insert_image(page.rect, pixmap=pix)
        self.body = doc.tobytes()
        doc.close()
        directory = self.prepare()["document_dir"]
        result = pdf.read_pdf(directory, "1")
        self.assertEqual(result["items"][0]["text"], "")
        self.assertIn("no OCR", result["warnings"][0])

    def test_cli_emits_one_json_object_and_nonzero_errors(self):
        directory = self.prepare()["document_dir"]
        run = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(SCRIPT),
                "read",
                "--document-dir",
                directory,
                "--pages",
                "2",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["items"][0]["page"], 2)
        self.assertEqual(run.stderr, "")
        bad = subprocess.run(
            [
                sys.executable,
                "-X",
                "utf8",
                str(SCRIPT),
                "read",
                "--document-dir",
                directory,
                "--pages",
                "99",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertNotEqual(bad.returncode, 0)
        self.assertEqual(bad.stdout, "")
        self.assertIn("pdf_evidence", bad.stderr)


if __name__ == "__main__":
    unittest.main()
