"""Regression tests for publish_articles.py.

The relay host serves a self-signed certificate. The public RSS CLI verifies
TLS against the system trust store, so publishing without a CA bundle fails
with "preflight_failed: Could not read remote posts; nothing published" -- a
failure that publishes zero articles while looking like a relay outage.

These tests stand up a local HTTPS server with a self-signed certificate and
drive the real script end to end.
"""
import importlib.util
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'publish_articles.py'
CLI_DIR = '/home/ohyes768/skills/knowledge/rss-relay-publish'
PREFIX = '/api/rss-relay'          # the CLI appends paths to base + PREFIX
CANONICAL_PEM = Path(os.path.expanduser(
    '~/.local/state/rss-relay-publish/relay_ca.pem'))


def load_module():
    spec = importlib.util.spec_from_file_location('publish_articles', SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRelay:
    """Minimal relay: GET /posts, GET /post/{id}, POST /post."""

    def __init__(self):
        self.posts = []
        self.post_count = 0
        self.dir = Path(tempfile.mkdtemp(prefix='hermes-verify-relay-'))
        self.key, self.cert = self.dir / 'key.pem', self.dir / 'cert.pem'
        subprocess.run(
            ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
             '-keyout', str(self.key), '-out', str(self.cert), '-days', '2',
             '-subj', '/CN=127.0.0.1',
             '-addext', 'subjectAltName=IP:127.0.0.1'],
            check=True, capture_output=True)
        relay = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, format, *args):
                pass

            def _send(self, code, body):
                raw = json.dumps(body, ensure_ascii=False).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                path = self.path.split('?')[0]
                if path == PREFIX + '/posts':
                    self._send(200, {'total': len(relay.posts), 'posts': relay.posts})
                elif path.startswith(PREFIX + '/post/'):
                    pid = path.rsplit('/', 1)[-1]
                    hit = [p for p in relay.posts if p.get('id') == pid]
                    self._send(200, hit[0] if hit else {})
                else:
                    self._send(404, {})

            def do_POST(self):
                length = int(self.headers.get('Content-Length') or 0)
                payload = json.loads(self.rfile.read(length).decode('utf-8'))
                relay.post_count += 1
                payload['id'] = 'test-%04d' % relay.post_count
                payload['detail_url'] = 'https://%s/view/%s' % (
                    self.headers.get('Host'), payload['id'])
                relay.posts.append(payload)
                self._send(201, {'id': payload['id'],
                                 'detail_url': payload['detail_url']})

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(self.cert), keyfile=str(self.key))
        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        self.port = self.server.socket.getsockname()[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self):
        return 'https://127.0.0.1:%d%s' % (self.port, PREFIX)

    def reset(self):
        self.posts.clear()
        self.post_count = 0

    def close(self):
        self.server.shutdown()
        shutil.rmtree(self.dir, ignore_errors=True)


class PublishArticlesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.relay = FakeRelay()
        cls.module = load_module()

    @classmethod
    def tearDownClass(cls):
        cls.relay.close()

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix='hermes-verify-publish-'))
        self.state = self.work / 'state'
        self.receipt = self.work / 'receipt.json'
        self.articles = self.work / 'articles.json'
        self.articles.write_text(json.dumps([{
            'token': 'VERIFYTOKEN001', 'title': '《验证条目》',
            'content': '📝 验证内容',
            'url': 'https://waytoagi.feishu.cn/wiki/VERIFYTOKEN001',
        }], ensure_ascii=False), encoding='utf-8')
        self.relay.reset()

    def tearDown(self):
        shutil.rmtree(self.work, ignore_errors=True)

    def publish(self, **env_extra):
        env = dict(os.environ)
        env.pop('RSS_RELAY_CA_FILE', None)
        env['RSS_RELAY_SKILL_DIR'] = CLI_DIR
        env['RSS_RELAY_STATE_DIR'] = str(self.state)
        env['RSS_RELAY_BASE_URL'] = self.relay.base
        env.update(env_extra)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), '--articles-json', str(self.articles),
             '--receipts', str(self.receipt)],
            capture_output=True, env=env, text=True, timeout=120)
        try:
            result = json.loads(proc.stdout)
        except ValueError:
            self.fail('unparseable stdout=%r stderr=%r'
                      % (proc.stdout[:200], proc.stderr[:200]))
        return result

    # ---- resolve_ca_file ----

    def test_env_var_wins(self):
        with tempfile.NamedTemporaryFile(suffix='.pem') as pem:
            os.environ['RSS_RELAY_CA_FILE'] = pem.name
            self.assertEqual(self.module.resolve_ca_file(), pem.name)
            del os.environ['RSS_RELAY_CA_FILE']

    def test_falls_back_to_state_dir_pem(self):
        if not CANONICAL_PEM.is_file():
            self.skipTest('canonical relay CA not present')
        self.assertEqual(self.module.resolve_ca_file(), str(CANONICAL_PEM))

    def test_returns_none_when_nothing_exists(self):
        """No candidate on disk -> None, so the CLI reports the real error."""
        home = tempfile.mkdtemp(prefix='hermes-verify-home-')
        saved = {k: os.environ.get(k) for k in ('HOME', 'RSS_RELAY_CA_FILE')}
        os.environ['HOME'] = home
        os.environ.pop('RSS_RELAY_CA_FILE', None)
        try:
            self.assertIsNone(self.module.resolve_ca_file())
        finally:
            for key, value in saved.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            shutil.rmtree(home, ignore_errors=True)

    def test_env_var_is_read_at_call_time(self):
        """A late export must still apply -- not frozen at import."""
        with tempfile.NamedTemporaryFile(suffix='.pem') as pem:
            saved = os.environ.pop('RSS_RELAY_CA_FILE', None)
            try:
                os.environ['RSS_RELAY_CA_FILE'] = pem.name
                self.assertEqual(self.module.resolve_ca_file(), pem.name)
            finally:
                os.environ.pop('RSS_RELAY_CA_FILE', None)
                if saved is not None:
                    os.environ['RSS_RELAY_CA_FILE'] = saved

    # ---- publishing ----

    def test_without_ca_publishes_nothing(self):
        result = self.publish()
        self.assertFalse(result['ok'])
        self.assertIn('preflight_failed', result['error'])
        self.assertEqual(self.relay.post_count, 0)
        self.assertFalse(self.receipt.exists())

    def test_with_ca_publishes_once_and_records_receipt(self):
        result = self.publish(RSS_RELAY_CA_FILE=str(self.relay.cert))
        self.assertTrue(result['ok'], result.get('error'))
        self.assertEqual(result['results'][0]['status'], 'published')
        self.assertEqual(self.relay.post_count, 1)
        stored = self.relay.posts[0]
        self.assertEqual(stored['channel'], 'waytoagi')
        self.assertEqual(stored['source'], 'waytoagi-daily')
        receipt = json.loads(self.receipt.read_text(encoding='utf-8'))['articles']
        self.assertIn('VERIFYTOKEN001', receipt)
        self.assertTrue(receipt['VERIFYTOKEN001'].endswith('+08:00'))

    def test_rerun_skips_and_never_double_posts(self):
        self.publish(RSS_RELAY_CA_FILE=str(self.relay.cert))
        again = self.publish(RSS_RELAY_CA_FILE=str(self.relay.cert))
        self.assertTrue(again['ok'])
        self.assertEqual(again['results'][0]['status'], 'skipped')
        self.assertEqual(self.relay.post_count, 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
