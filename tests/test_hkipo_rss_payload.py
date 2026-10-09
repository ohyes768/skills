import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "hk-ipo-research" / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RelayPayloadTests(unittest.TestCase):
    def test_final_report_defaults_and_overrides(self):
        module = load("push_rss")
        with tempfile.TemporaryDirectory(dir=SCRIPTS.parent.parent / ".tmp") as directory:
            report = Path(directory) / "report.md"
            report.write_text(module.REPORT_START_MARKER + "\n# 今日内容\n\n正文 markdown", encoding="utf-8")
            for extra, channel, source in [
                ([], "hkipo", "hk-ipo-research"),
                (["--report-type", "backtest", "--source", "hk-ipo-backtest"], "hkipo", "hk-ipo-backtest"),
                (["--channel", "custom", "--source", "my-bot", "--url", "https://example.com"], "custom", "my-bot"),
            ]:
                with self.subTest(extra=extra), patch.object(sys, "argv", ["push_rss.py", str(report), "--title", "今日内容", "--allow-duplicate", *extra]), patch.object(module.httpx, "post") as post, patch("builtins.print"):
                    post.return_value.json.return_value = {"id": "test-id"}
                    self.assertEqual(module.main(), 0)
                    self.assertEqual(post.call_args.kwargs["json"], {
                        "title": "今日内容", "content": "# 今日内容\n\n正文 markdown",
                        "channel": channel, "source": source,
                        "url": "https://example.com" if channel == "custom" else "",
                    })

    def test_daily_report_payload(self):
        module = load("daily_rss_report")
        with patch.object(module.httpx, "post") as post:
            module.push_report("https://example.com", "今日内容", "# 今日内容\n\n正文 markdown", "my-bot")
            self.assertEqual(post.call_args.kwargs["json"], {
                "title": "今日内容", "content": "# 今日内容\n\n正文 markdown",
                "channel": "hkipo", "source": "my-bot", "url": "",
            })


if __name__ == "__main__":
    unittest.main()

