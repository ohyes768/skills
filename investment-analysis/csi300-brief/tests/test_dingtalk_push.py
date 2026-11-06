import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dingtalk_push.py"
spec = importlib.util.spec_from_file_location("dingtalk_push", SCRIPT)
dingtalk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dingtalk)

WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=secret-token"


def reply(errcode=0, errmsg="ok"):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"errcode": errcode, "errmsg": errmsg}).encode()
    return Response()


class SendTests(unittest.TestCase):
    @patch.object(dingtalk, "urlopen")
    def test_success_posts_markdown_and_returns_sent(self, urlopen):
        urlopen.return_value = reply()
        outcome = dingtalk.send(WEBHOOK, "沪深300 ETF 简况", "正文")
        self.assertEqual(outcome["status"], dingtalk.SENT)
        body = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(body["msgtype"], "markdown")
        self.assertEqual(body["markdown"], {"title": "沪深300 ETF 简况", "text": "正文"})
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 10)

    @patch.object(dingtalk, "urlopen")
    def test_keyword_rejection_is_its_own_status(self, urlopen):
        urlopen.return_value = reply(310000, "关键词不匹配")
        outcome = dingtalk.send(WEBHOOK, "标题", "正文")
        self.assertEqual(outcome["status"], dingtalk.KEYWORD_MISSING)
        self.assertEqual(outcome["errcode"], 310000)

    @patch.object(dingtalk, "urlopen")
    def test_invalid_token_is_rejected(self, urlopen):
        urlopen.return_value = reply(300001, "token is not exist")
        outcome = dingtalk.send(WEBHOOK, "沪深300 ETF", "正文")
        self.assertEqual(outcome["status"], dingtalk.REJECTED)
        self.assertEqual(outcome["errcode"], 300001)

    @patch.object(dingtalk, "urlopen")
    def test_network_failure_is_unknown_and_never_silently_retried(self, urlopen):
        urlopen.side_effect = URLError("offline")
        outcome = dingtalk.send(WEBHOOK, "沪深300 ETF", "正文")
        self.assertEqual(outcome["status"], dingtalk.UNKNOWN)
        self.assertIn("可能已送达", outcome["errmsg"])

    @patch.object(dingtalk, "urlopen")
    def test_timeout_is_unknown(self, urlopen):
        urlopen.side_effect = TimeoutError()
        self.assertEqual(dingtalk.send(WEBHOOK, "沪深300 ETF", "正文")["status"], dingtalk.UNKNOWN)

    @patch.object(dingtalk, "urlopen")
    def test_http_error_body_is_parsed_instead_of_guessed(self, urlopen):
        urlopen.side_effect = HTTPError(
            "u", 400, "bad", {},
            io.BytesIO(b'{"errcode":310000,"errmsg":"keyword not matched"}'))
        self.assertEqual(dingtalk.send(WEBHOOK, "标题", "正文")["status"], dingtalk.KEYWORD_MISSING)

    @patch.object(dingtalk, "urlopen")
    def test_non_json_response_is_rejected(self, urlopen):
        urlopen.return_value = reply()
        urlopen.return_value.read = lambda: b"<html>gateway</html>"
        self.assertEqual(dingtalk.send(WEBHOOK, "沪深300 ETF", "正文")["status"], dingtalk.REJECTED)

    @patch.object(dingtalk, "urlopen")
    def test_result_never_leaks_the_token(self, urlopen):
        urlopen.side_effect = URLError("offline")
        self.assertNotIn("secret-token", json.dumps(dingtalk.send(WEBHOOK, "沪深300 ETF", "正文")))

    def test_invalid_webhook_url_is_a_config_error(self):
        with self.assertRaises(ValueError):
            dingtalk.send("ftp://oapi.dingtalk.com/robot/send", "沪深300 ETF", "正文")


class ConfigTests(unittest.TestCase):
    def test_env_file_parsing_ignores_comments_blanks_and_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('\ufeff# comment\n\nDINGTALK_WEBHOOK="https://e/x?a=1"\n'
                            "DINGTALK_KEYWORD=ETF\nempty=\n", encoding="utf-8")
            values = dingtalk.read_env_file(path)
            self.assertEqual(values["DINGTALK_WEBHOOK"], "https://e/x?a=1")
            self.assertEqual(values["DINGTALK_KEYWORD"], "ETF")
            self.assertEqual(values["empty"], "")

    def test_process_env_wins_over_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("DINGTALK_KEYWORD=FILE\n", encoding="utf-8")
            with patch.dict(dingtalk.os.environ, {"DINGTALK_KEYWORD": "PROCESS"}):
                self.assertEqual(dingtalk.resolve_keyword(None, path), "PROCESS")
            with patch.dict(dingtalk.os.environ, {}, clear=True):
                self.assertEqual(dingtalk.resolve_keyword(None, path), "FILE")

    def test_missing_webhook_fails_loudly_without_leaking(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(dingtalk.os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as raised:
                dingtalk.resolve_webhook(None, Path(directory) / ".env")
        self.assertIn("DINGTALK_WEBHOOK", str(raised.exception))

    def test_keyword_matching_is_exact_substring(self):
        self.assertTrue(dingtalk.keyword_present("沪深300 ETF", "", "ETF"))
        self.assertTrue(dingtalk.keyword_present("", "行业 ETF 一览", "ETF"))
        self.assertFalse(dingtalk.keyword_present("沪深300", "正文", "ETF"))
        self.assertFalse(dingtalk.keyword_present("沪深300 etf", "正文", "ETF"))
        self.assertTrue(dingtalk.keyword_present("无关键词要求", "正文", ""))


class CliTests(unittest.TestCase):
    def run_cli(self, argv, *, env_file=None, stdin=""):
        from contextlib import redirect_stdout, redirect_stderr
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch.object(dingtalk.sys, "stdin", io.StringIO(stdin)):
            code = dingtalk.main(["--env-file", str(env_file), *argv] if env_file else argv)
        return code, out.getvalue()

    def write_env(self, directory, webhook=WEBHOOK, keyword="ETF"):
        path = Path(directory) / ".env"
        path.write_text(f"DINGTALK_WEBHOOK={webhook}\nDINGTALK_KEYWORD={keyword}\n", encoding="utf-8")
        return path

    @patch.object(dingtalk, "urlopen")
    def test_keyword_missing_stops_before_any_http_call(self, urlopen):
        with tempfile.TemporaryDirectory() as directory:
            code, out = self.run_cli(["--title", "沪深300简况", "--text", "正文"],
                                     env_file=self.write_env(directory))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["status"], dingtalk.KEYWORD_MISSING)
        urlopen.assert_not_called()

    def test_dry_run_sends_nothing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(dingtalk, "urlopen") as urlopen:
            code, out = self.run_cli(["--title", "沪深300 ETF", "--text", "正文", "--dry-run"],
                                     env_file=self.write_env(directory))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], dingtalk.DRY_RUN)
        urlopen.assert_not_called()

    def test_missing_env_reports_not_configured(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(dingtalk.os.environ, {}, clear=True):
            code, out = self.run_cli(["--title", "沪深300 ETF", "--text", "正文"],
                                     env_file=Path(directory) / "missing.env")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["status"], dingtalk.NOT_CONFIGURED)

    @patch.object(dingtalk, "urlopen")
    def test_stdin_text_is_supported(self, urlopen):
        urlopen.return_value = reply()
        with tempfile.TemporaryDirectory() as directory:
            code, out = self.run_cli(["--title", "沪深300 ETF", "--file", "-"],
                                     env_file=self.write_env(directory), stdin="来自 stdin 的 ETF 正文")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], dingtalk.SENT)
        self.assertIn("stdin", json.loads(urlopen.call_args.args[0].data)["markdown"]["text"])

    @patch.object(dingtalk, "urlopen")
    def test_unknown_exit_code_is_three(self, urlopen):
        urlopen.side_effect = URLError("offline")
        with tempfile.TemporaryDirectory() as directory:
            code, out = self.run_cli(["--title", "沪深300 ETF", "--text", "正文"],
                                     env_file=self.write_env(directory))
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["status"], dingtalk.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
