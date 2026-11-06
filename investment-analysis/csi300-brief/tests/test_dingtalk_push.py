import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "dingtalk_push.py"
spec = importlib.util.spec_from_file_location("dingtalk_push", SCRIPT)
dingtalk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dingtalk)

WEBHOOK = "https://oapi.dingtalk.com/robot/send?access_token=secret-token"

# The module is a delegation shim over the public dingtalk-push CLI; a stub
# CLI records argv/webhook-env/stdin and returns a scripted public result.
STUB_CLI = '''#!/usr/bin/env python3
import json, os, sys
log = os.environ.get("STUB_LOG")
if log:
    with open(log, "w", encoding="utf-8") as f:
        json.dump({"argv": sys.argv[1:],
                   "webhook_env": os.environ.get("DINGTALK_WEBHOOK"),
                   "stdin": sys.stdin.read()}, f, ensure_ascii=False)
status = os.environ.get("STUB_STATUS", "sent")
code = os.environ.get("STUB_ERRCODE")
print(json.dumps({"schema_version": 1, "status": status,
                  "errcode": int(code) if code else (0 if status in ("sent", "duplicate", "preview") else None),
                  "errmsg": os.environ.get("STUB_ERRMSG", "ok"),
                  "dedupe_key": "auto:x", "verification": "none",
                  "error": {"code": os.environ.get("STUB_ERROR_CODE"), "message": None}
                  if os.environ.get("STUB_ERROR_CODE") else None}, ensure_ascii=False))
sys.exit({"sent": 0, "duplicate": 0, "preview": 0, "failed": 2, "unknown": 3, "conflict": 4}.get(status, 2))
'''


class StubPublicCli:
    def __init__(self, tmpdir, *, status="sent", errcode=None, error_code=None, errmsg=None):
        scripts = Path(tmpdir) / "scripts"
        scripts.mkdir(parents=True, exist_ok=True)
        (scripts / "dingtalk_send.py").write_text(STUB_CLI, encoding="utf-8")
        self.dir = str(tmpdir)
        self.log = Path(tmpdir) / "stub-log.json"
        self.env = {"DINGTALK_PUSH_SKILL_DIR": self.dir, "STUB_LOG": str(self.log),
                    "STUB_STATUS": status, "STUB_ERROR_CODE": error_code or "",
                    "STUB_ERRCODE": str(errcode) if errcode is not None else ""}
        if errmsg:
            self.env["STUB_ERRMSG"] = errmsg

    def recorded(self):
        return json.loads(self.log.read_text(encoding="utf-8"))


def run_send(**stub_kwargs):
    directory = tempfile.mkdtemp(prefix="dingtalk-delegate-")
    stub = StubPublicCli(directory, **stub_kwargs)
    with patch.dict(os.environ, stub.env, clear=False), \
            patch.dict(os.environ, {"DINGTALK_WEBHOOK": "", "DINGTALK_KEYWORD": ""}, clear=False):
        os.environ.pop("DINGTALK_WEBHOOK", None)
        os.environ.pop("DINGTALK_KEYWORD", None)
        outcome = dingtalk.send(WEBHOOK, "沪深300 ETF 简况 · 2026-11-04", "正文")
    return outcome, stub


class DelegationTests(unittest.TestCase):
    def test_success_delegates_and_reports_sent(self):
        outcome, stub = run_send(status="sent")
        self.assertEqual(outcome["status"], dingtalk.SENT)
        self.assertEqual(outcome["errcode"], 0)
        record = stub.recorded()
        self.assertEqual(record["webhook_env"], WEBHOOK)
        argv = record["argv"]
        self.assertEqual(argv[0], "send")
        self.assertIn("--title", argv)
        self.assertEqual(argv[argv.index("--title") + 1], "沪深300 ETF 简况 · 2026-11-04")
        self.assertEqual(argv[argv.index("--file") + 1], "-")
        self.assertEqual(record["stdin"], "正文")
        self.assertNotIn("secret-token", json.dumps(argv))

    def test_webhook_travels_by_env_not_argv(self):
        outcome, stub = run_send(status="sent")
        self.assertEqual(outcome["status"], dingtalk.SENT)
        self.assertNotIn(WEBHOOK, json.dumps(stub.recorded()["argv"]))
        self.assertEqual(stub.recorded()["webhook_env"], WEBHOOK)

    def test_duplicate_from_public_receipt_reports_sent_without_repost(self):
        outcome, _ = run_send(status="duplicate")
        self.assertEqual(outcome["status"], dingtalk.SENT)
        self.assertIn("重复", outcome["errmsg"])

    def test_keyword_rejection_maps_to_its_own_status(self):
        outcome, _ = run_send(status="failed", errcode=310000, error_code="keyword_rejected")
        self.assertEqual(outcome["status"], dingtalk.KEYWORD_MISSING)
        self.assertEqual(outcome["errcode"], 310000)

    def test_other_rejection_maps_to_rejected(self):
        outcome, _ = run_send(status="failed", errcode=300001, error_code="robot_rejected")
        self.assertEqual(outcome["status"], dingtalk.REJECTED)
        self.assertEqual(outcome["errcode"], 300001)

    def test_unknown_from_public_cli_stays_unknown(self):
        outcome, _ = run_send(status="unknown")
        self.assertEqual(outcome["status"], dingtalk.UNKNOWN)
        self.assertIn("先核对", outcome["errmsg"])

    def test_conflict_maps_to_rejected(self):
        outcome, _ = run_send(status="conflict", error_code="key_conflict")
        self.assertEqual(outcome["status"], dingtalk.REJECTED)

    def test_unparseable_cli_output_is_unknown(self):
        directory = tempfile.mkdtemp(prefix="dingtalk-delegate-")
        stub = StubPublicCli(directory)
        (Path(directory) / "scripts" / "dingtalk_send.py").write_text(
            "print('<html>gateway</html>')\n", encoding="utf-8")
        with patch.dict(os.environ, stub.env, clear=False):
            outcome = dingtalk.send(WEBHOOK, "沪深300 ETF 简况", "正文")
        self.assertEqual(outcome["status"], dingtalk.UNKNOWN)

    def test_dedupe_key_is_scoped_by_title_date(self):
        _, stub = run_send(status="sent")
        argv = stub.recorded()["argv"]
        self.assertEqual(argv[argv.index("--dedupe-key") + 1], "csi300:2026-11-04")

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
    def run_cli(self, argv, *, env_file=None, stdin="", env=None):
        from contextlib import redirect_stdout, redirect_stderr
        out, err = io.StringIO(), io.StringIO()
        env_context = patch.dict(dingtalk.os.environ, env or {}, clear=False)
        with env_context, redirect_stdout(out), redirect_stderr(err), \
                patch.object(dingtalk.sys, "stdin", io.StringIO(stdin)):
            code = dingtalk.main(["--env-file", str(env_file), *argv] if env_file else argv)
        return code, out.getvalue()

    def write_env(self, directory, webhook=WEBHOOK, keyword="ETF"):
        path = Path(directory) / ".env"
        path.write_text(f"DINGTALK_WEBHOOK={webhook}\nDINGTALK_KEYWORD={keyword}\n", encoding="utf-8")
        return path

    def test_keyword_missing_stops_before_any_subprocess(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(dingtalk, "subprocess") as sp:
            code, out = self.run_cli(["--title", "沪深300简况", "--text", "正文"],
                                     env_file=self.write_env(directory))
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["status"], dingtalk.KEYWORD_MISSING)
        sp.run.assert_not_called()

    def test_dry_run_sends_nothing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(dingtalk, "subprocess") as sp:
            code, out = self.run_cli(["--title", "沪深300 ETF", "--text", "正文", "--dry-run"],
                                     env_file=self.write_env(directory))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], dingtalk.DRY_RUN)
        sp.run.assert_not_called()

    def test_missing_env_reports_not_configured(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(dingtalk, "subprocess") as sp, \
                patch.dict(dingtalk.os.environ, {}, clear=True):
            code, out = self.run_cli(["--title", "沪深300 ETF", "--text", "正文"],
                                     env_file=Path(directory) / "missing.env")
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out)["status"], dingtalk.NOT_CONFIGURED)
        sp.run.assert_not_called()

    def test_stdin_text_is_supported(self):
        directory = tempfile.mkdtemp(prefix="dingtalk-cli-")
        stub = StubPublicCli(directory)
        with patch.dict(os.environ, stub.env, clear=False):
            code, out = self.run_cli(["--title", "沪深300 ETF", "--file", "-"],
                                     env_file=self.write_env(directory), stdin="来自 stdin 的 ETF 正文")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["status"], dingtalk.SENT)
        self.assertEqual(stub.recorded()["stdin"], "来自 stdin 的 ETF 正文")

    def test_unknown_exit_code_is_three(self):
        directory = tempfile.mkdtemp(prefix="dingtalk-cli-")
        stub = StubPublicCli(directory, status="unknown")
        with patch.dict(os.environ, stub.env, clear=False):
            code, out = self.run_cli(["--title", "沪深300 ETF", "--text", "正文"],
                                     env_file=self.write_env(directory))
        self.assertEqual(code, 3)
        self.assertEqual(json.loads(out)["status"], dingtalk.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
