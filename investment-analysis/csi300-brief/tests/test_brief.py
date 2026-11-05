import importlib.util
import io
import json
from contextlib import redirect_stdout
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


if __name__ == "__main__":
    unittest.main()
