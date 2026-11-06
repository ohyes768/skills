import importlib.util
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "brief.py"
spec = importlib.util.spec_from_file_location("brief", SCRIPT)
brief = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brief)


def snapshot():
    return {
        "available": True, "model_kind": "trailing_10y_weekly",
        "price_as_of": "2026-11-04", "close": 4101.34,
        "position_pct": 38.56, "region": "middle",
        "lower": 3274.36, "mid": 4346.8233, "upper": 5419.2867,
        "data_status": {"state": "ok"},
        "valuation": {"state": "ok", "as_of": "2026-10-30",
                      "target_date": "2026-10-30", "pe_ttm": 12.86,
                      "percentile_pct": 53.1},
    }


class BriefTests(unittest.TestCase):
    def test_normal_summary_preserves_dates_units_and_rounding(self):
        text = brief.summarize(snapshot())
        for value in ("2026-11-04", "2026-10-30", "4101.34", "38.6%",
                      "4346.82", "12.86倍", "53.1%", "近10年周线通道中部"):
            self.assertIn(value, text)
        self.assertLess(len(text), 200)

    def test_zero_and_breakouts_are_not_missing_or_clamped(self):
        for position in (-12.3, 0, 112.3):
            data = snapshot()
            data["position_pct"] = position
            data["valuation"]["percentile_pct"] = 0
            text = brief.summarize(data)
            self.assertIn(f"{position:.1f}%", text)
            self.assertIn("分位0.0%", text)

    def test_missing_or_nonfinite_numbers_are_not_fabricated(self):
        data = snapshot()
        data["close"] = None
        data["position_pct"] = float("nan")
        data["mid"] = True
        data["valuation"]["pe_ttm"] = float("inf")
        data["valuation"]["percentile_pct"] = None
        text = brief.summarize(data)
        self.assertIn("收盘价暂无数据", text)
        self.assertIn("通道位置暂无数据", text)
        self.assertIn("轨道数据不完整", text)
        self.assertIn("PE-TTM暂无数据", text)
        self.assertNotIn("nan", text)
        self.assertNotIn("inf", text)

    def test_unavailable_channel_does_not_hide_valuation(self):
        text = brief.summarize({"available": False, "reason": "model_not_ready",
                                "valuation": snapshot()["valuation"]})
        self.assertIn("模型尚未就绪", text)
        self.assertIn("12.86倍", text)

    def test_valuation_degradation_and_market_staleness(self):
        labels = {"stale": "估值滞后", "error": "估值更新失败",
                  "empty": "估值暂无数据", "disabled": "估值未启用",
                  "unexpected": "估值状态未确认"}
        for state, label in labels.items():
            with self.subTest(state=state):
                data = snapshot()
                data["data_status"]["state"] = "stale"
                data["valuation"]["state"] = state
                self.assertIn(label, brief.summarize(data))
                self.assertIn("行情滞后", brief.summarize(data))
        data["valuation"] = None
        self.assertIn("估值状态未确认", brief.summarize(data))

    def test_since_inception_and_missing_dates(self):
        data = snapshot()
        data["model_kind"] = "since_inception_weekly"
        data.pop("price_as_of")
        data["valuation"].pop("as_of")
        text = brief.summarize(data)
        self.assertIn("上市以来周线通道", text)
        self.assertIn("行情日期未提供", text)
        self.assertIn("估值日期未提供", text)

    @patch.object(brief, "urlopen")
    def test_request_path_model_timeout_and_read_only(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps(snapshot()).encode()
        data = brief.fetch("http://localhost:8100/api/", "since_inception_weekly", 7)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.full_url,
                         "http://localhost:8100/api/indices/000300/status?model=since_inception_weekly")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 7)
        self.assertTrue(data["available"])

    @patch.object(brief, "urlopen")
    def test_invalid_responses_fail(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        for payload in (b"not json", b"[]", b"{}", b'{"available":"true"}'):
            response.read.return_value = payload
            with self.assertRaises(ValueError):
                brief.fetch(brief.DEFAULT_BASE_URL, "trailing_10y_weekly", 1)

    def test_cli_failures_are_short_and_nonzero(self):
        for error in (TimeoutError(), URLError("offline"),
                      HTTPError("url", 503, "unavailable", {}, None), ValueError()):
            output = io.StringIO()
            with patch.object(brief, "fetch", side_effect=error), redirect_stdout(output):
                code = brief.main([])
            self.assertEqual(code, 1)
            self.assertIn("沪深300数据暂时获取失败", output.getvalue())
            self.assertNotIn("Traceback", output.getvalue())

    def test_cli_success_prints_summary_and_preserves_degraded_state(self):
        data = snapshot()
        data["valuation"]["state"] = "error"
        output = io.StringIO()
        with patch.object(brief, "fetch", return_value=data), redirect_stdout(output):
            self.assertEqual(brief.main(["--model", "since_inception_weekly"]), 0)
        self.assertIn("估值更新失败，以下为缓存值", output.getvalue())

    def test_timeout_rejects_nonpositive_and_nonfinite_values(self):
        for value in ("0", "-1", "nan", "inf", "abc"):
            with self.assertRaises(brief.argparse.ArgumentTypeError):
                brief.positive_timeout(value)
        self.assertEqual(brief.positive_timeout("2.5"), 2.5)


class PushTests(unittest.TestCase):
    def test_default_title_carries_keyword_and_price_date(self):
        title = brief.push_title(snapshot())
        self.assertIn("ETF", title)
        self.assertIn("2026-11-04", title)

    def test_default_title_falls_back_to_today(self):
        data = snapshot()
        data.pop("price_as_of")
        self.assertRegex(brief.push_title(data), r"沪深300 ETF 简况 · \d{4}-\d{2}-\d{2}")

    def test_missing_keyword_blocks_the_request(self):
        outcome = brief.push("沪深300概况，不含关键词", "沪深300简况", keyword="ETF")
        self.assertEqual(outcome["status"], "keyword_missing")
        self.assertIn("ETF", outcome["errmsg"])

    def test_cli_push_keeps_stdout_text_and_reports_to_stderr(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(brief, "fetch", return_value=snapshot()), \
                patch.object(brief, "push", return_value={"status": "sent"}) as push, \
                redirect_stdout(output), redirect_stderr(errors):
            code = brief.main(["--push"])
        self.assertEqual(code, 0)
        self.assertIn("沪深300", output.getvalue())
        self.assertNotIn("status", output.getvalue())
        self.assertIn("沪深300 ETF 简况 · 2026-11-04", push.call_args.args[1])
        self.assertIn('"sent"', errors.getvalue())

    def test_cli_without_push_flag_never_sends(self):
        with patch.object(brief, "fetch", return_value=snapshot()), \
                patch.object(brief, "push") as push, redirect_stdout(io.StringIO()):
            self.assertEqual(brief.main([]), 0)
        push.assert_not_called()

    def test_push_status_maps_to_exit_code(self):
        for status, code in (("unknown", 3), ("rejected", 4),
                             ("keyword_missing", 2), ("not_configured", 2)):
            with self.subTest(status=status), \
                    patch.object(brief, "fetch", return_value=snapshot()), \
                    patch.object(brief, "push", return_value={"status": status}), \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(brief.main(["--push"]), code)

    def test_push_timeout_rejects_nonpositive_values(self):
        for value in ("0", "-3", "nan", "inf"):
            with self.assertRaises(brief.argparse.ArgumentTypeError):
                brief.positive_timeout(value)


class TlsTests(unittest.TestCase):
    def test_default_context_still_verifies_certificates(self):
        context = brief.tls_context()
        self.assertEqual(context.verify_mode, brief.ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)

    def test_insecure_is_opt_in_only(self):
        context = brief.tls_context(insecure=True)
        self.assertEqual(context.verify_mode, brief.ssl.CERT_NONE)
        self.assertFalse(context.check_hostname)

    @patch.object(brief, "urlopen")
    def test_fetch_passes_the_context_through(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = json.dumps(snapshot()).encode()
        context = brief.tls_context(insecure=True)
        brief.fetch(brief.DEFAULT_BASE_URL, "trailing_10y_weekly", 5, context)
        self.assertIs(urlopen.call_args.kwargs["context"], context)

    def test_unreadable_ca_file_fails_short_without_requesting(self):
        output = io.StringIO()
        with patch.object(brief, "fetch") as fetch, redirect_stdout(output):
            code = brief.main(["--ca-file", str(Path(__file__).with_name("missing-ca.pem"))])
        self.assertEqual(code, 1)
        self.assertIn("证书", output.getvalue())
        fetch.assert_not_called()


class MarkdownTests(unittest.TestCase):
    def test_markdown_emphasises_the_numbers_that_matter(self):
        text = brief.render_markdown(snapshot())
        for value in ("### 沪深300 ETF 简况 · 2026-11-04",
                      "**近10年周线通道** **中部**",
                      "通道位置 **38.6%**",
                      "- 收盘 **4101.34** 点",
                      "3274.36 / **4346.82** / 5419.29",
                      "PE-TTM **12.86 倍**",
                      "近10年分位 **53.1%**",
                      "（估值 2026-10-30）"):
            self.assertIn(value, text)
        self.assertIn("不构成买卖建议", text)

    def test_markdown_keeps_market_warning_on_its_own_line(self):
        data = snapshot()
        data["data_status"]["state"] = "stale"
        text = brief.render_markdown(data)
        self.assertIn("⚠️ **行情滞后，以上为缓存值**", text)
        self.assertIn("行情滞后", brief.summarize(data))

    def test_markdown_keeps_stale_valuation_target_date(self):
        data = snapshot()
        data["valuation"]["state"] = "stale"
        data["valuation"]["target_date"] = "2026-11-07"
        self.assertIn("⚠️ **估值滞后，目标日期2026-11-07**", brief.render_markdown(data))

    def test_markdown_does_not_fabricate_missing_values(self):
        data = snapshot()
        data["available"] = False
        data["reason"] = "model_not_ready"
        data["valuation"]["pe_ttm"] = None
        data["valuation"]["percentile_pct"] = None
        text = brief.render_markdown(data)
        self.assertIn("**周线通道暂不可用（模型尚未就绪）**", text)
        self.assertIn("PE-TTM 暂无数据", text)
        for bad in ("None", "nan", "inf"):
            self.assertNotIn(bad, text)

    def test_valuation_disabled_and_unavailable_states_are_labelled(self):
        for state, label in (("disabled", "**估值未启用**"), ("empty", "**估值暂无数据**")):
            with self.subTest(state=state):
                data = snapshot()
                data["valuation"]["state"] = state
                self.assertIn(label, brief.render_markdown(data))

    def test_cli_pushes_markdown_while_stdout_stays_plain(self):
        output, errors = io.StringIO(), io.StringIO()
        with patch.object(brief, "fetch", return_value=snapshot()), \
                patch.object(brief, "push", return_value={"status": "sent"}) as push, \
                redirect_stdout(output), redirect_stderr(errors):
            self.assertEqual(brief.main(["--push"]), 0)
        sent_markdown = push.call_args.args[0]
        self.assertIn("### 沪深300 ETF 简况 · 2026-11-04", sent_markdown)
        self.assertNotIn("###", output.getvalue())
        self.assertIn("沪深300截至2026-11-04", output.getvalue())


if __name__ == "__main__":
    unittest.main()
