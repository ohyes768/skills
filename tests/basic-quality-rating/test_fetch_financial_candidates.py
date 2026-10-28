import copy
import hashlib
import io
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "finance-macro/basic-quality-rating/scripts"
)
sys.path.insert(0, str(SCRIPTS))
import fetch_financial_candidates as api


def stock(sector="bank"):
    return {
        "code": "600036" if sector == "bank" else "601318",
        "name": "招商银行" if sector == "bank" else "中国平安",
        "sw_level1": "银行" if sector == "bank" else "非银金融",
        "sw_level2": "银行" if sector == "bank" else "保险Ⅱ",
    }


def row(sector="bank", **updates):
    item = {
        "SECUCODE": "600036.SH" if sector == "bank" else "601318.SH",
        "SECURITY_CODE": stock(sector)["code"],
        "SECURITY_NAME_ABBR": stock(sector)["name"],
        "ORG_TYPE": "银行" if sector == "bank" else "保险",
        "REPORT_DATE": "2025-12-31 00:00:00",
        "NOTICE_DATE": "2026-03-28 00:00:00",
        "UPDATE_DATE": "2026-03-28 00:00:00",
        "CURRENCY": "CNY",
        "ROEJQ": 12.5,
        "ZZCJLL": 1.1,
        "NONPERLOAN": 0.94,
        "BLDKBBL": 385.1,
        "NEWCAPITALADER": 18.33,
        "HXYJBCZL": 14.07,
        "FIRST_ADEQUACY_RATIO": 16.59,
    }
    item.update(updates)
    return item


def body(rows):
    return json.dumps(
        {"success": True, "result": {"pages": 1, "data": rows}}, ensure_ascii=False
    ).encode()


class CandidateTests(unittest.TestCase):
    def packet(self, rows, sector="bank"):
        return api.build_candidates(
            stock(sector),
            "2026-10-28",
            rows,
            source_url=api.query_url(stock(sector), "2026-10-28"),
        )

    def test_bank_fields_keep_exact_capital_semantics_and_original_input(self):
        original = stock()
        before = copy.deepcopy(original)
        packet = self.packet([row()])
        facts = packet["observations"][0]["metrics"]
        self.assertEqual(facts["total_capital_ratio"]["value"], 18.33)
        self.assertEqual(facts["tier1_ratio"]["value"], 16.59)
        self.assertEqual(facts["cet1_ratio"]["value"], 14.07)
        self.assertEqual(facts["npl_ratio"]["source_field"], "NONPERLOAN")
        self.assertTrue(facts["roe"]["needs_confirmation"])
        self.assertFalse(packet["ready_for_scoring"])
        self.assertNotIn("reports", packet)
        self.assertEqual(original, before)

    def test_insurance_scope_unknown_and_amount_conversion(self):
        packet = self.packet(
            [
                row(
                    "insurance",
                    SOLVENCY_AR=198.1,
                    NBV_LIFE=24847000000,
                    NET_ROI=-0.8,
                    SURRENDER_RATE_LIFE=0,
                )
            ],
            "insurance",
        )
        facts = packet["observations"][0]["metrics"]
        self.assertEqual(facts["solvency_ratio_unspecified"]["value"], 198.1)
        self.assertEqual(facts["nbv"]["value"], 24847)
        self.assertEqual(facts["nbv"]["raw_value"], 24847000000)
        self.assertEqual(facts["net_investment_yield"]["value"], -0.8)
        self.assertEqual(facts["surrender_ratio"]["value"], 0)
        self.assertEqual(packet["observations"][0]["scope"], "unconfirmed")
        self.assertNotIn("core_solvency", facts)
        self.assertNotIn("group_solvency_ratio", facts)

    def test_missing_bad_numbers_and_unknown_currency_do_not_become_zero(self):
        packet = self.packet(
            [
                row(
                    "insurance",
                    ROEJQ=True,
                    SOLVENCY_AR=None,
                    NET_ROI="2.8",
                    NBV_LIFE=10,
                    CURRENCY="USD",
                )
            ],
            "insurance",
        )
        facts = packet["observations"][0]["metrics"]
        self.assertNotIn("roe", facts)
        self.assertNotIn("solvency_ratio_unspecified", facts)
        self.assertNotIn("net_investment_yield", facts)
        self.assertNotIn("nbv", facts)
        self.assertTrue(packet["issues"])

    def test_outsize_number_is_field_gap_not_loss_of_other_candidates(self):
        packet = self.packet([row(ROEJQ=10**400)])
        facts = packet["observations"][0]["metrics"]
        self.assertNotIn("roe", facts)
        self.assertEqual(facts["npl_ratio"]["value"], 0.94)
        self.assertTrue(packet["issues"])

    def test_invalid_timestamp_tail_is_rejected(self):
        packet = self.packet([row(NOTICE_DATE="2026-03-28 99:99:99")])
        self.assertEqual(packet["observations"], [])
        self.assertTrue(packet["issues"])

    def test_identity_sector_or_name_mismatch_is_fatal(self):
        for fields in (
            {"SECUCODE": "000001.SZ"},
            {"SECURITY_CODE": "000001"},
            {"SECURITY_NAME_ABBR": "别的公司"},
            {"ORG_TYPE": "证券"},
        ):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                self.packet([row(**fields)])

    def test_future_revised_missing_dates_and_invalid_quarters_are_rejected(self):
        for fields in (
            {"NOTICE_DATE": "2026-11-01"},
            {"REPORT_DATE": "2026-12-31"},
            {"UPDATE_DATE": "2026-11-01"},
            {"NOTICE_DATE": None},
            {"REPORT_DATE": "2025-02-28"},
            {"UPDATE_DATE": None},
            {"NOTICE_DATE": "2025-01-01"},
            {"REPORT_DATE": "bad"},
        ):
            with self.subTest(fields=fields):
                packet = self.packet([row(**fields)])
                self.assertEqual(packet["observations"], [])
                self.assertTrue(packet["issues"])

    def test_duplicate_periods_excluded_not_last_row_wins(self):
        first, second = row(), row(ROEJQ=5)
        for rows in ([first, second], [second, first]):
            packet = self.packet(rows)
            self.assertEqual(packet["observations"], [])
            self.assertTrue(packet["issues"])

    def test_annual_and_interim_are_not_annualized(self):
        packet = self.packet(
            [
                row(
                    REPORT_DATE="2026-06-30",
                    NOTICE_DATE="2026-08-29",
                    UPDATE_DATE="2026-08-29",
                    ROEJQ=6.71,
                ),
                row(),
            ]
        )
        self.assertEqual(packet["observations"][0]["period_type"], "interim")
        self.assertEqual(packet["observations"][0]["metrics"]["roe"]["value"], 6.71)
        self.assertEqual(packet["observations"][1]["period_type"], "annual")

    def test_url_binds_stock_period_and_limit(self):
        url = api.query_url(stock(), "2026-10-28")
        self.assertIn("pageSize=100", url)
        with self.assertRaises(ValueError):
            api.query_url(dict(stock(), code="600036)bad"), "2026-10-28")
        with self.assertRaises(ValueError):
            api.query_url(stock(), "2026-02-30")
        with self.assertRaises(ValueError):
            api.build_candidates(
                {"code": "600519", "name": "测试企业", "sw_level1": "食品饮料"},
                "2026-10-28",
                [],
                source_url="https://example.com",
            )


class ReportAlignmentTests(unittest.TestCase):
    def build(self, rows, report_date="2026-09-30"):
        return api.build_candidates(
            stock(),
            "2026-10-28",
            rows,
            source_url=api.query_url(stock(), "2026-10-28"),
            report_date=report_date,
        )

    def q3(self, **updates):
        fields = {
            "REPORT_DATE": "2026-09-30",
            "NOTICE_DATE": "2026-10-23",
            "UPDATE_DATE": "2026-10-23",
            "ROEJQ": 9.1,
        }
        fields.update(updates)
        return row(**fields)

    def h1(self):
        return row(
            REPORT_DATE="2026-06-30", NOTICE_DATE="2026-08-29", UPDATE_DATE="2026-08-29"
        )

    def test_exact_q3_is_matched_and_not_annualized(self):
        data = self.build([row(), self.q3(), self.h1()])
        align = data["report_alignment"]
        self.assertEqual(align["status"], "matched")
        self.assertEqual(align["requested_report_date"], "2026-09-30")
        self.assertEqual(align["latest_returned_report_date"], "2026-09-30")
        self.assertEqual(align["target_observation_index"], 0)
        self.assertEqual(data["observations"][0]["metrics"]["roe"]["value"], 9.1)
        self.assertFalse(data["ready_for_scoring"])

    def test_half_year_does_not_stand_in_for_q3(self):
        align = self.build([row(), self.h1()])["report_alignment"]
        self.assertEqual(align["status"], "missing_target")
        self.assertEqual(align["latest_usable_report_date"], "2026-06-30")
        self.assertIsNone(align["target_observation_index"])

    def test_rejected_q3_remains_visible_and_no_fallback(self):
        cases = [
            self.q3(NOTICE_DATE="2026-11-01", UPDATE_DATE="2026-11-01"),
            self.q3(UPDATE_DATE="2026-11-01"),
        ]
        for item in cases:
            with self.subTest(item=item):
                align = self.build([self.h1(), item])["report_alignment"]
                self.assertEqual(align["status"], "target_rejected")
                self.assertEqual(align["latest_returned_report_date"], "2026-09-30")
                self.assertEqual(align["latest_usable_report_date"], "2026-06-30")
                self.assertIsNone(align["target_observation_index"])

    def test_duplicate_q3_not_silently_resolved(self):
        align = self.build([self.q3(), self.q3(ROEJQ=10), self.h1()])[
            "report_alignment"
        ]
        self.assertEqual(align["status"], "target_rejected")
        self.assertIsNone(align["target_observation_index"])

    def test_older_explicit_target_warns_newer_returned(self):
        align = self.build([self.q3(), self.h1()], report_date="2026-06-30")[
            "report_alignment"
        ]
        self.assertEqual(align["status"], "matched")
        self.assertTrue(align["newer_report_returned"])
        self.assertEqual(align["target_observation_index"], 1)

    def test_default_does_not_claim_latest_official_period_was_confirmed(self):
        align = self.build([self.h1()], report_date=None)["report_alignment"]
        self.assertEqual(align["status"], "not_requested")
        self.assertIsNone(align["requested_report_date"])
        self.assertIsNone(align["target_observation_index"])

    def test_invalid_target_rejected_before_network(self):
        for target in ["2026-12-31", "2026-09-29", "2026Q3", "bad"]:
            with (
                self.subTest(target=target),
                tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work,
            ):
                with (
                    patch.object(api, "urlopen") as request,
                    self.assertRaises(ValueError),
                ):
                    api.fetch(stock(), "2026-10-28", work, report_date=target)
                request.assert_not_called()

    def test_same_raw_cache_can_align_multiple_report_dates_without_refetch(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            with patch.object(
                api, "urlopen", return_value=Response(body([self.q3(), self.h1()]))
            ) as request:
                first = api.fetch(stock(), "2026-10-28", work, report_date="2026-06-30")
                second = api.fetch(
                    stock(), "2026-10-28", work, report_date="2026-09-30"
                )
            self.assertEqual(request.call_count, 1)
            self.assertTrue(second["cache_hit"])
            self.assertNotEqual(
                first["report_alignment"]["target_observation_index"],
                second["report_alignment"]["target_observation_index"],
            )

    def test_cli_receipt_exposes_missing_target(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            source = Path(work) / "stock.json"
            output = Path(work) / "candidates.json"
            source.write_text(json.dumps(stock(), ensure_ascii=False), encoding="utf-8")
            with (
                patch.object(api, "urlopen", return_value=Response(body([self.h1()]))),
                patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                result = api.main(
                    [
                        "--stock",
                        str(source),
                        "--as-of",
                        "2026-10-28",
                        "--cache-dir",
                        str(Path(work) / "cache"),
                        "--report-date",
                        "2026-09-30",
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(result, 0)
            receipt = json.loads(stdout.getvalue())
            self.assertEqual(receipt["report_alignment"]["status"], "missing_target")
            self.assertFalse(receipt["ready_for_scoring"])


class Response:
    def __init__(self, data):
        self.data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, limit):
        return self.data[:limit]


class TransportTests(unittest.TestCase):
    def test_cli_cannot_overwrite_stock_and_does_not_request_in_that_case(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            path = Path(work) / "stock.json"
            text = json.dumps(stock(), ensure_ascii=False)
            path.write_text(text, encoding="utf-8")
            with (
                patch.object(api, "urlopen") as request,
                patch("sys.stderr", new_callable=io.StringIO),
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                status = api.main(
                    [
                        "--stock",
                        str(path),
                        "--as-of",
                        "2026-10-28",
                        "--cache-dir",
                        work,
                        "--output",
                        str(path),
                    ]
                )
            self.assertEqual(status, 2)
            self.assertEqual(output.getvalue(), "")
            self.assertEqual(path.read_text(encoding="utf-8"), text)
            request.assert_not_called()

    def test_success_cache_reuse_and_refresh(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            with patch.object(
                api, "urlopen", return_value=Response(body([row()]))
            ) as request:
                first = api.fetch(stock(), "2026-10-28", work)
                second = api.fetch(stock(), "2026-10-28", work)
                third = api.fetch(stock(), "2026-10-28", work, refresh=True)
            self.assertEqual(request.call_count, 2)
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertFalse(third["cache_hit"])
            self.assertEqual(len(first["response_sha256"]), 64)
            self.assertEqual(first["stock_sha256"], second["stock_sha256"])

    def test_corrupt_cache_is_error_not_silent_network_retry(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            with patch.object(api, "urlopen", return_value=Response(body([row()]))):
                api.fetch(stock(), "2026-10-28", work)
            path = next(Path(work).glob("*.json"))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["body"] += " "
            path.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(api, "urlopen") as request, self.assertRaises(ValueError):
                api.fetch(stock(), "2026-10-28", work)
            request.assert_not_called()

    def test_expired_cache_fetches_and_failed_refresh_preserves_old_file(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            with patch.object(api, "urlopen", return_value=Response(body([row()]))):
                api.fetch(stock(), "2026-10-28", work)
            path = next(Path(work).glob("*.json"))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["fetched_at"] = "2020-01-01T00:00:00+00:00"
            path.write_text(json.dumps(data), encoding="utf-8")
            before = path.read_bytes()
            with (
                patch.object(
                    api, "urlopen", side_effect=URLError("offline")
                ) as request,
                self.assertRaises(ValueError),
            ):
                api.fetch(stock(), "2026-10-28", work)
            self.assertEqual(request.call_count, 2)
            self.assertEqual(path.read_bytes(), before)

    def test_auth_quota_not_retried_and_transient_once(self):
        for code in (401, 403, 429):
            with (
                tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work,
                patch.object(
                    api,
                    "urlopen",
                    side_effect=HTTPError("https://example.com", code, "", {}, None),
                ) as request,
                self.assertRaises(ValueError),
            ):
                api.fetch(stock(), "2026-10-28", work)
            self.assertEqual(request.call_count, 1)
        with (
            tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work,
            patch.object(
                api,
                "urlopen",
                side_effect=[URLError("timeout"), Response(body([row()]))],
            ) as request,
        ):
            api.fetch(stock(), "2026-10-28", work)
            self.assertEqual(request.call_count, 2)

    def test_api_failure_malformed_oversized_and_pagination_fail(self):
        samples = [
            b"{}",
            b"<html>blocked</html>",
            b'{"success":false}',
            b'{"success":true,"result":{"pages":2,"data":[]}}',
            body([[]]),
            b"x" * (api.MAX_BYTES + 1),
        ]
        for sample in samples:
            with (
                self.subTest(size=len(sample)),
                tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work,
            ):
                with (
                    patch.object(
                        api, "urlopen", return_value=Response(sample)
                    ) as request,
                    self.assertRaises(ValueError),
                ):
                    api.fetch(stock(), "2026-10-28", work)
                self.assertEqual(list(Path(work).glob("*.json")), [])
                self.assertEqual(request.call_count, 1)

    def test_cache_for_other_query_not_accepted_even_with_valid_body_hash(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            with patch.object(api, "urlopen", return_value=Response(body([row()]))):
                api.fetch(stock(), "2026-10-28", work)
            path = next(Path(work).glob("*.json"))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["url"] = api.query_url(stock("insurance"), "2026-10-28")
            data["sha256"] = hashlib.sha256(data["body"].encode()).hexdigest()
            data["fetched_at"] = datetime.now(UTC).isoformat()
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                api.fetch(stock(), "2026-10-28", work)


if __name__ == "__main__":
    unittest.main()
