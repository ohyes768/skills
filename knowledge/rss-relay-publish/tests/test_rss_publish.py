import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/rss_publish.py'


class RelayTests(unittest.TestCase):
    def setUp(self):
        temp_root = SCRIPT.parents[3] / '.tmp'
        temp_root.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=temp_root)
        self.root = Path(self.tmp.name)
        self.file = self.root / '中文 report.md'
        self.file.write_bytes(b'\xef\xbb\xbf' + '# 标题\n\n正文\n'.encode('utf-8'))
        self.posts = []
        self.writes = 0
        self.mode = ''
        test = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send_json(self, code, data):
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                try:
                    self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
                except (BrokenPipeError, ConnectionResetError):
                    pass  # The crash-recovery test intentionally kills its client.

            def do_GET(self):
                if self.path.startswith('/api/posts'):
                    if test.mode == 'list-error':
                        return self.send_json(503, {})
                    return self.send_json(200, {'posts': test.posts})
                if test.mode == 'readback-404':
                    return self.send_json(404, {})
                post = dict(next((p for p in test.posts if self.path == '/api/post/' + p['id']), {}))
                if test.mode == 'mismatch':
                    post['content'] = 'wrong'
                if test.mode == 'normalized-readback' and post:
                    post['content'] = post['content'].replace('\r\n', '\n')
                return self.send_json(200 if post else 404, post)

            def do_POST(self):
                test.writes += 1
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if test.mode == 'reject':
                    return self.send_json(422, {'detail': 'Unknown channel'})
                if test.mode == 'server-error':
                    return self.send_json(503, {})
                if test.mode == 'empty-id':
                    return self.send_json(201, {'id': ''})
                if test.mode == 'slow':
                    time.sleep(0.3)
                post = dict(payload, id=str(len(test.posts) + 1))
                test.posts.append(post)
                if test.mode == 'disconnect':
                    self.close_connection = True
                    return
                if test.mode == 'bad-json':
                    self.send_response(201)
                    self.end_headers()
                    self.wfile.write(b'not json')
                    return
                if test.mode == 'truncated':
                    self.send_response(201)
                    self.send_header('Content-Length', '9999')
                    self.end_headers()
                    self.wfile.write(b'{')
                    self.close_connection = True
                    return
                return self.send_json(201, {'id': post['id'], 'detail_url': test.base + '/view/' + post['id']})

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.base = f'http://127.0.0.1:{self.server.server_port}/api'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.tmp.cleanup()

    def run_cli(self, *extra, script=SCRIPT):
        env = dict(os.environ, RSS_RELAY_STATE_DIR=str(self.root / 'state'))
        proc = subprocess.run([sys.executable, str(script), 'publish', '--file', str(self.file),
                               '--title', '标题', '--channel', 'macro', '--source', 'test',
                               '--dedupe-key', 'daily:2026-11-05', '--base-url', self.base,
                               *extra], cwd=self.root, env=env, capture_output=True, encoding='utf-8')
        self.assertTrue(proc.stdout.strip(), proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def test_publish_verifies_exact_content(self):
        code, result = self.run_cli()
        self.assertEqual((code, result['status'], result['verified']), (0, 'published', True))
        self.assertEqual(self.posts[0]['content'], '# 标题\n\n正文\n')
        self.assertEqual(set(self.posts[0]) - {'id'}, {'title', 'content', 'channel', 'source', 'url'})

    def test_file_newlines_are_not_rewritten_in_post(self):
        self.file.write_bytes('# 标题\r\n\r\n正文\r\n'.encode('utf-8'))
        self.assertEqual(self.run_cli()[1]['status'], 'published')
        self.assertEqual(self.posts[0]['content'], '# 标题\r\n\r\n正文\r\n')

    def test_server_line_ending_normalization_is_verifiable(self):
        self.mode = 'normalized-readback'
        self.file.write_bytes('# 标题\r\n正文\r\n'.encode('utf-8'))
        self.assertEqual(self.run_cli()[1]['status'], 'published')

    def test_truncated_post_response_is_recovered(self):
        self.mode = 'truncated'
        code, response = self.run_cli()
        self.assertEqual((code, response['status']), (0, 'published'))
        self.run_cli()
        self.assertEqual(self.writes, 1)

    def test_dry_run_has_no_state_or_network_writes(self):
        code, result = self.run_cli('--dry-run')
        self.assertEqual((code, result['status']), (0, 'preview'))
        self.assertFalse((self.root / 'state').exists())
        self.assertEqual(self.writes, 0)

    def test_duplicate_and_content_conflict(self):
        self.run_cli()
        code, result = self.run_cli()
        self.assertEqual((code, result['status'], result['verification']), (0, 'duplicate', 'historical'))
        self.file.write_text('changed', encoding='utf-8')
        code, result = self.run_cli()
        self.assertEqual((code, result['status']), (4, 'conflict'))
        self.assertEqual(self.writes, 1)

    def test_namespace_does_not_dedupe_on_title(self):
        self.run_cli()
        self.run_cli('--source', 'other')
        self.run_cli('--channel', 'other')
        self.assertEqual(self.writes, 3)

    def test_disconnect_is_recovered_without_second_post(self):
        self.mode = 'disconnect'
        code, result = self.run_cli()
        self.assertEqual((code, result['verified']), (0, True))
        self.run_cli()
        self.assertEqual(self.writes, 1)

    def test_server_error_stays_unknown_across_retries(self):
        self.mode = 'server-error'
        for _ in range(2):
            code, result = self.run_cli()
            self.assertEqual((code, result['status']), (3, 'unknown'))
        self.assertEqual(self.writes, 1)

    def test_empty_id_without_remote_evidence_is_unknown(self):
        self.mode = 'empty-id'
        for _ in range(2):
            self.assertEqual(self.run_cli()[1]['status'], 'unknown')
        self.assertEqual(self.writes, 1)

    def test_package_upgrade_keeps_external_receipt(self):
        self.run_cli()
        installed = self.root / 'installed package/rss_publish.py'
        installed.parent.mkdir()
        installed.write_bytes(SCRIPT.read_bytes())
        self.assertEqual(self.run_cli(script=installed)[1]['status'], 'duplicate')
        self.assertEqual(self.writes, 1)

    def test_killed_process_recovers_pending_without_new_post(self):
        self.mode = 'slow'
        env = dict(os.environ, RSS_RELAY_STATE_DIR=str(self.root / 'state'))
        args = [sys.executable, str(SCRIPT), 'publish', '--file', str(self.file), '--title', '标题',
                '--channel', 'macro', '--source', 'test', '--dedupe-key', 'daily:2026-11-05', '--base-url', self.base]
        proc = subprocess.Popen(args, cwd=self.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 10
            while not self.writes and time.monotonic() < deadline and proc.poll() is None:
                time.sleep(0.01)
            self.assertEqual(self.writes, 1)
            proc.kill()
            proc.communicate(timeout=5)
            time.sleep(0.4)
            code, response = self.run_cli()
            self.assertEqual((code, response['status'], response['verified']), (0, 'duplicate', True))
            self.assertEqual(self.writes, 1)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.communicate(timeout=5)

    def test_mismatch_never_reports_success_or_reposts(self):
        self.mode = 'mismatch'
        for _ in range(2):
            code, result = self.run_cli()
            self.assertEqual((code, result['status']), (3, 'unknown'))
        self.assertEqual(self.writes, 1)

    def test_readback_404_does_not_release_accepted_write(self):
        self.mode = 'readback-404'
        for _ in range(2):
            self.assertEqual(self.run_cli()[1]['status'], 'unknown')
        self.assertEqual(self.writes, 1)

    def test_list_failure_is_safe_to_retry(self):
        self.mode = 'list-error'
        code, result = self.run_cli()
        self.assertEqual((code, result['status'], self.writes), (2, 'failed', 0))
        self.mode = ''
        self.assertEqual(self.run_cli()[1]['status'], 'published')

    def test_explicit_rejection_can_be_retried(self):
        self.mode = 'reject'
        self.assertEqual(self.run_cli()[1]['status'], 'failed')
        self.mode = ''
        self.assertEqual(self.run_cli()[1]['status'], 'published')

    def test_remote_adoption_requires_full_match(self):
        self.posts.append({'id': 'old', 'title': '标题', 'content': '# 标题\n\n正文\n',
                           'channel': 'macro', 'source': 'test', 'url': ''})
        code, result = self.run_cli()
        self.assertEqual((code, result['status'], result['verified']), (0, 'duplicate', True))
        self.assertEqual(self.writes, 0)

    def test_multiple_remote_matches_are_ambiguous(self):
        self.posts.extend([{'id': str(i), 'title': '标题', 'content': '# 标题\n\n正文\n',
                            'channel': 'macro', 'source': 'test', 'url': ''} for i in range(2)])
        self.assertEqual(self.run_cli()[1]['status'], 'unknown')
        self.assertEqual(self.writes, 0)

    def test_same_key_concurrency_posts_once(self):
        self.mode = 'slow'
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.run_cli(), range(2)))
        self.assertEqual(self.writes, 1)
        self.assertTrue(any(r['status'] == 'published' for _, r in results))

    def test_bad_arguments_and_missing_file_emit_json(self):
        code, result = self.run_cli('--file', 'missing.md')
        self.assertEqual((code, result['status']), (2, 'failed'))
        code, result = self.run_cli('--timeout', 'invalid')
        self.assertEqual((code, result['status']), (2, 'failed'))

    def test_unwritable_state_prevents_post(self):
        code, result = self.run_cli('--state-dir', str(self.file))
        self.assertEqual((code, result['status'], self.writes), (2, 'failed', 0))

    def test_bad_json_after_accepted_write_can_be_recovered(self):
        self.mode = 'bad-json'
        code, result = self.run_cli()
        self.assertEqual((code, result['verified']), (0, True))
        self.run_cli()
        self.assertEqual(self.writes, 1)


if __name__ == '__main__':
    unittest.main()
