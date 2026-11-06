"""Offline tests for the shared DingTalk push CLI (stub server + temp state)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
CLI = SKILL_DIR / 'scripts' / 'dingtalk_send.py'
PYTHON = sys.executable
TOKEN = 'secret-token-abc'


class StubDingTalk:
    """Local robot/send stub; responses are served in request order."""

    def __init__(self, responses=None, delay=0.0):
        self.requests = []
        self.responses = list(responses or [{'errcode': 0, 'errmsg': 'ok'}])
        self.delay = delay
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get('Content-Length', 0) or 0)
                raw = self.rfile.read(length) if length else b'{}'
                try:
                    body = json.loads(raw.decode('utf-8'))
                except (ValueError, UnicodeDecodeError):
                    body = None
                with outer.lock:
                    outer.requests.append((self.path, body))
                    index = min(len(outer.requests) - 1, len(outer.responses) - 1)
                    response = outer.responses[index]
                if outer.delay:
                    time.sleep(outer.delay)
                payload = json.dumps(response).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        class QuietServer(ThreadingHTTPServer):
            # Timeout tests abort mid-response by design; silence client-side noise.
            def handle_error(self, request, client_address):
                pass

        self.server = QuietServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def webhook(self):
        return f'http://127.0.0.1:{self.server.server_address[1]}/robot/send?access_token={TOKEN}'

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class DingTalkSendTests(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp(prefix='dingtalk-state-')
        self.stub = StubDingTalk()
        self.stub.start()
        self.addCleanup(self.stub.stop)
        self.addCleanup(self.cleanup_state)

    def cleanup_state(self):
        import shutil
        shutil.rmtree(self.state, ignore_errors=True)

    def send(self, text, *, title='测试标题', extra=(), env=None):
        args = [PYTHON, str(CLI), 'send', '--title', title, '--text', text,
                '--state-dir', self.state, '--webhook', self.stub.webhook, *extra]
        proc = subprocess.run(args, capture_output=True, env=env)
        stdout = proc.stdout.decode('utf-8')
        try:
            data = json.loads(stdout)
        except ValueError:
            data = None
        return proc.returncode, data, stdout, proc.stderr.decode('utf-8')

    # -- success / dedupe -------------------------------------------------

    def test_send_success_then_duplicate_on_identical_rerun(self):
        rc, data, _, _ = self.send('第一条内容')
        self.assertEqual(rc, 0, data)
        self.assertEqual(data['status'], 'sent')
        self.assertEqual(data['errcode'], 0)
        self.assertEqual(len(self.stub.requests), 1)
        rc, data, _, _ = self.send('第一条内容')
        self.assertEqual(rc, 0, data)
        self.assertEqual(data['status'], 'duplicate')
        self.assertEqual(data['verification'], 'historical')
        self.assertEqual(len(self.stub.requests), 1)

    def test_conflict_when_same_key_has_different_payload(self):
        rc, data, _, _ = self.send('版本一', extra=('--dedupe-key', 'daily:2026-11-06'))
        self.assertEqual(rc, 0, data)
        rc, data, _, _ = self.send('版本二', title='另一标题',
                                   extra=('--dedupe-key', 'daily:2026-11-06'))
        self.assertEqual(rc, 4, data)
        self.assertEqual(data['status'], 'conflict')
        self.assertEqual(len(self.stub.requests), 1)

    def test_missing_key_dedupes_identical_content(self):
        rc, data, _, _ = self.send('无键内容', extra=('--keyword', '测试'))
        self.assertEqual(rc, 0, data)
        rc, data, _, _ = self.send('无键内容', extra=('--keyword', '测试'))
        self.assertEqual(rc, 0, data)
        self.assertEqual(data['status'], 'duplicate')
        self.assertEqual(len(self.stub.requests), 1)

    # -- keyword preflight / server rejection ------------------------------

    def test_keyword_preflight_blocks_send_without_network(self):
        rc, data, stdout, stderr = self.send('没有关键词的正文', extra=('--keyword', 'WaytoAGI'))
        self.assertEqual(rc, 2, data)
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(data['error']['code'], 'keyword_missing')
        self.assertEqual(self.stub.requests, [])
        rc, data, _, _ = self.send('包含 WaytoAGI 关键词的正文', extra=('--keyword', 'WaytoAGI'))
        self.assertEqual(rc, 0, data)
        self.assertEqual(data['status'], 'sent')

    def test_errcode_rejection_releases_claim_for_retry(self):
        self.stub.responses = [{'errcode': 310000, 'errmsg': '关键词不匹配'},
                               {'errcode': 0, 'errmsg': 'ok'}]
        rc, data, _, _ = self.send('正文')
        self.assertEqual(rc, 2, data)
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(data['errcode'], 310000)
        rc, data, _, _ = self.send('正文')
        self.assertEqual(rc, 0, data)
        self.assertEqual(data['status'], 'sent')
        self.assertEqual(len(self.stub.requests), 2)

    # -- transport failures -------------------------------------------------

    def test_connection_refused_fails_without_claim(self):
        dead = f'http://127.0.0.1:9/robot/send?access_token={TOKEN}'
        args = [PYTHON, str(CLI), 'send', '--title', 't', '--text', '正文',
                '--state-dir', self.state, '--webhook', dead,
                '--dedupe-key', 'k1', '--timeout', '3']
        proc = subprocess.run(args, capture_output=True)
        data = json.loads(proc.stdout.decode('utf-8'))
        self.assertEqual(proc.returncode, 2, data)
        self.assertEqual(data['status'], 'failed')
        rc, data, _, _ = self.send('正文', extra=('--dedupe-key', 'k1'))
        self.assertEqual(rc, 0, data)
        self.assertEqual(data['status'], 'sent')

    def test_timeout_is_unknown_and_never_blind_retries(self):
        self.stub.stop()
        slow = StubDingTalk(delay=2.0)
        slow.start()
        self.addCleanup(slow.stop)
        args = [PYTHON, str(CLI), 'send', '--title', 't', '--text', '正文',
                '--state-dir', self.state, '--webhook', slow.webhook,
                '--dedupe-key', 'k2', '--timeout', '0.5']
        first = subprocess.run(args, capture_output=True)
        data = json.loads(first.stdout.decode('utf-8'))
        self.assertEqual(first.returncode, 3, data)
        self.assertEqual(data['status'], 'unknown')
        second = subprocess.run(args, capture_output=True)
        data = json.loads(second.stdout.decode('utf-8'))
        self.assertEqual(second.returncode, 3, data)
        self.assertEqual(data['status'], 'unknown')
        self.assertEqual(len(slow.requests), 1)

    def test_malformed_success_is_unknown(self):
        self.stub.responses = [{}]
        rc, data, _, _ = self.send('正文')
        self.assertEqual(rc, 3, data)
        self.assertEqual(data['status'], 'unknown')

    # -- configuration -------------------------------------------------------

    def test_env_file_provides_webhook(self):
        env_file = Path(self.state) / '.env'
        env_file.write_text(f'DINGTALK_WEBHOOK={self.stub.webhook}\n', encoding='utf-8')
        env = dict(os.environ)
        env.pop('DINGTALK_WEBHOOK', None)
        args = [PYTHON, str(CLI), 'send', '--title', 't', '--text', '正文',
                '--state-dir', self.state, '--env-file', str(env_file),
                '--dedupe-key', 'envk']
        proc = subprocess.run(args, capture_output=True, env=env)
        data = json.loads(proc.stdout.decode('utf-8'))
        self.assertEqual(proc.returncode, 0, data)
        self.assertEqual(data['status'], 'sent')
        self.assertEqual(len(self.stub.requests), 1)

    def test_explicit_webhook_takes_precedence_over_missing_env_file(self):
        env = dict(os.environ)
        env.pop('DINGTALK_WEBHOOK', None)
        args = [PYTHON, str(CLI), 'send', '--title', 't', '--text', '正文',
                '--state-dir', self.state, '--webhook', self.stub.webhook,
                '--env-file', str(Path(self.state) / 'does-not-exist.env'),
                '--dedupe-key', 'prec']
        proc = subprocess.run(args, capture_output=True, env=env)
        data = json.loads(proc.stdout.decode('utf-8'))
        self.assertEqual(proc.returncode, 0, data)
        self.assertEqual(data['status'], 'sent')

    def test_dry_run_sends_nothing_and_writes_no_receipts(self):
        rc, data, _, _ = self.send('预览正文', extra=('--dry-run',))
        self.assertEqual(rc, 0, data)
        self.assertEqual(data['status'], 'preview')
        self.assertEqual(self.stub.requests, [])
        self.assertFalse((Path(self.state) / 'receipts.sqlite3').exists())

    def test_file_and_stdin_input(self):
        content_file = Path(self.state) / 'body.md'
        content_file.write_text('文件正文', encoding='utf-8')
        args = [PYTHON, str(CLI), 'send', '--title', '文件标题', '--file', str(content_file),
                '--state-dir', self.state, '--webhook', self.stub.webhook, '--dedupe-key', 'fk']
        proc = subprocess.run(args, capture_output=True)
        data = json.loads(proc.stdout.decode('utf-8'))
        self.assertEqual(proc.returncode, 0, data)
        self.assertEqual(data['status'], 'sent')
        self.assertEqual(self.stub.requests[0][1]['markdown']['text'], '文件正文')
        args = [PYTHON, str(CLI), 'send', '--title', 'stdin标题', '--file', '-',
                '--state-dir', self.state, '--webhook', self.stub.webhook, '--dedupe-key', 'sk']
        proc = subprocess.run(args, input='标准输入正文'.encode('utf-8'), capture_output=True)
        data = json.loads(proc.stdout.decode('utf-8'))
        self.assertEqual(proc.returncode, 0, data)
        self.assertEqual(data['status'], 'sent')
        self.assertEqual(self.stub.requests[1][1]['markdown']['text'], '标准输入正文')

    def test_keyword_errcode_is_flagged_distinctly(self):
        self.stub.responses = [{'errcode': 310000, 'errmsg': '关键词不匹配'}]
        rc, data, _, _ = self.send('正文', extra=('--keyword', 'WaytoAGI'))
        self.assertEqual(rc, 2, data)
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(data['errcode'], 310000)
        self.assertEqual(data['error']['code'], 'keyword_rejected')

    def test_missing_webhook_reports_not_configured(self):
        env = dict(os.environ)
        env.pop('DINGTALK_WEBHOOK', None)
        args = [PYTHON, str(CLI), 'send', '--title', 't', '--text', '正文',
                '--state-dir', self.state, '--dedupe-key', 'nowebhook']
        proc = subprocess.run(args, capture_output=True, env=env)
        data = json.loads(proc.stdout.decode('utf-8'))
        self.assertEqual(proc.returncode, 2, data)
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(data['error']['code'], 'not_configured')

    def test_invalid_input_fails_before_network(self):
        rc, data, _, _ = self.send('   ', title='  ')
        self.assertEqual(rc, 2, data)
        self.assertEqual(data['status'], 'failed')
        self.assertEqual(self.stub.requests, [])

    # -- secret hygiene --------------------------------------------------------

    def test_token_never_appears_in_output(self):
        self.stub.responses = [{'errcode': 310000, 'errmsg': '关键词不匹配'}]
        _, data, stdout, stderr = self.send('正文', extra=('--keyword', 'WaytoAGI'))
        combined = stdout + stderr + json.dumps(data, ensure_ascii=False)
        self.assertNotIn(TOKEN, combined)
        self.assertNotIn('access_token=', combined)
        rc, data, stdout, stderr = self.send('正文')
        combined = stdout + stderr + json.dumps(data, ensure_ascii=False)
        self.assertNotIn(TOKEN, combined)


if __name__ == '__main__':
    unittest.main()
