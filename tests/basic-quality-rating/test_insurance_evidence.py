import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from test_bank_evidence import sample_pdf

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "finance-macro/basic-quality-rating/scripts"
sys.path.insert(0, str(SCRIPTS))
import pdf_evidence as pdf
from bank_evidence import find_bank_candidates


class InsuranceEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            "insurance_evidence", SCRIPTS / "insurance_evidence.py"
        )
        cls.insurance = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.insurance)

    def setUp(self):
        self.work = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.addCleanup(self.work.cleanup)
        self.root = Path(self.work.name)
        self.requests = []
        self.body = sample_pdf(
            [
                (
                    "集团综合偿付能力充足率 193.3% 204.1%\n"
                    "平安寿险核心偿付能力充足率 125.3% 130.2%\n"
                    "综合偿付能力充足率 185.0% 189.2%\n"
                    "新业务价值 36,897 28,534 人民币百万元\n"
                    "新业务合同服务边际 36,688\n合同服务边际余额 725,119\n"
                ),
                (
                    "综合成本率 96.8% 98.3%\n净投资收益率 3.7% 3.8%\n"
                    "综合投资收益率 6.3%\n总投资收益率 6.1%\n"
                    "保险合同准备金 123,456 人民币百万元\n"
                    "退保率 1.52%\n13个月保单继续率 97.4%\n"
                    "核心一级资本充足率 13.5%\n"
                ),
                "",
            ]
        )

        def respond(request):
            self.requests.append(str(request.url))
            return httpx.Response(200, content=self.body)

        self.client = httpx.Client(transport=httpx.MockTransport(respond))
        self.addCleanup(self.client.close)

    def prepare(self):
        return pdf.prepare_pdf(
            "https://example.test/insurance.pdf",
            self.root / "cache",
            client=self.client,
        )["document_dir"]

    def test_candidates_reuse_cache_and_keep_ambiguous_raw_strings(self):
        directory = self.prepare()
        with patch.object(pdf, "_load_tools", side_effect=AssertionError("cache only")):
            result = self.insurance.find_insurance_candidates(directory)
        self.assertEqual(len(self.requests), 1)
        self.assertTrue(result["needs_confirmation"])
        self.assertEqual(len(result["source"]["sha256"]), 64)
        labels = {item["metric"] for item in result["items"]}
        self.assertTrue(
            {
                "group_solvency_ratio",
                "core_solvency",
                "comprehensive_solvency",
                "nbv",
                "new_business_csm",
                "csm_balance",
                "combined_ratio",
                "net_investment_yield",
                "total_investment_yield",
            }
            <= labels
        )
        nbv = next(item for item in result["items"] if item["metric"] == "nbv")
        self.assertIn("36,897", nbv["numeric_strings"])
        self.assertIn("28,534", nbv["numeric_strings"])
        self.assertNotIn("value", nbv)
        self.assertNotIn("period_end", nbv)
        self.assertTrue(any("no OCR" in warning for warning in result["warnings"]))

    def test_long_group_label_does_not_become_entity_solvency(self):
        self.body = sample_pdf(["集团综合偿付能力充足率193.3%"])
        result = self.insurance.find_insurance_candidates(self.prepare())
        self.assertEqual(
            [item["metric"] for item in result["items"]], ["group_solvency_ratio"]
        )

    def test_whitespace_and_insurance_entity_labels_remain_unaccepted(self):
        self.body = sample_pdf(
            ["核 心 偿 付 能 力 充 足 率125.3%\n新 业 务 价 值36,897"]
        )
        result = self.insurance.find_insurance_candidates(self.prepare())
        self.assertEqual(
            {item["metric"] for item in result["items"]}, {"core_solvency", "nbv"}
        )
        self.assertTrue(all(item["needs_confirmation"] for item in result["items"]))

    def test_bounded_cursor_reconstructs_and_cannot_cross_bank_mode(self):
        directory = self.prepare()
        whole = self.insurance.find_insurance_candidates(directory, max_chars=12000)
        seen = []
        cursor = None
        while True:
            result = self.insurance.find_insurance_candidates(
                directory, max_chars=128, cursor=cursor
            )
            self.assertLessEqual(result["text_chars"], 128)
            seen.extend(
                (item["metric"], item["page"], item["text"]) for item in result["items"]
            )
            cursor = result["next_cursor"]
            if not cursor:
                break
            self.assertLess(len(seen), 150)
        for item in whole["items"]:
            text = "".join(
                text
                for key, page, text in seen
                if key == item["metric"] and page == item["page"]
            )
            self.assertEqual(text, item["text"])
        token = self.insurance.find_insurance_candidates(directory, max_chars=128)[
            "next_cursor"
        ]
        with self.assertRaisesRegex(ValueError, "cursor"):
            find_bank_candidates(directory, cursor=token)

    def test_no_hit_and_corrupt_source_do_not_invent_values(self):
        self.body = sample_pdf(["普通业务介绍", ""])
        directory = Path(self.prepare())
        result = self.insurance.find_insurance_candidates(directory)
        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["items"], [])
        self.assertTrue(result["warnings"])
        with self.assertRaises(ValueError):
            self.insurance.find_insurance_candidates(directory, max_chars=0)
        file = directory / "pages.jsonl"
        file.write_bytes(file.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.insurance.find_insurance_candidates(directory)

    def test_cli_json_and_error_without_partial_stdout(self):
        directory = self.prepare()
        args = [
            sys.executable,
            "-X",
            "utf8",
            str(SCRIPTS / "insurance_evidence.py"),
            "--document-dir",
        ]
        good = subprocess.run(
            args + [directory],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertTrue(json.loads(good.stdout)["needs_confirmation"])
        bad = subprocess.run(
            args + [str(self.root / "missing")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(bad.returncode, 2)
        self.assertEqual(bad.stdout, "")
        self.assertIn("insurance_evidence", bad.stderr)


if __name__ == "__main__":
    unittest.main()
