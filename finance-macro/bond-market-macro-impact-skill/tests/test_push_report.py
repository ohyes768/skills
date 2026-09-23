import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('push_rss', Path(__file__).parents[1] / 'scripts/push_rss.py')
push_rss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(push_rss)


class PushReportTests(unittest.TestCase):
    """push_report 纯逻辑：payload 组装与四种状态映射。"""

    def test_missing_token_skips_and_never_calls_http(self):
        with patch.object(push_rss, 'http_json') as mock_http:
            status = push_rss.push_report('https://x/report', '', 't', 'c', '', 'src', True)
        self.assertEqual(status, 'skipped_no_token')
        mock_http.assert_not_called()

    def test_payload_and_token_are_passed(self):
        with patch.object(push_rss, 'http_json', return_value={'success': True}) as mock_http:
            status = push_rss.push_report('https://x/report', 'tok', '标题', '正文', 'https://u', 'src', False)
        self.assertEqual(status, 'ok')
        args, kwargs = mock_http.call_args
        self.assertEqual(args[0], 'https://x/report')
        self.assertEqual(args[1], {'title': '标题', 'content': '正文', 'url': 'https://u', 'source': 'src'})
        self.assertFalse(args[2])
        self.assertEqual(kwargs.get('token'), 'tok')

    def test_exception_maps_to_failed(self):
        with patch.object(push_rss, 'http_json', side_effect=OSError('boom')):
            status = push_rss.push_report('https://x/report', 'tok', 't', 'c', '', 'src', True)
        self.assertTrue(status.startswith('failed:'), status)

    def test_duplicate_response_maps_to_duplicate(self):
        with patch.object(push_rss, 'http_json', return_value={'success': True, 'data': {'report_id': 'r1', 'duplicate': True}}):
            status = push_rss.push_report('https://x/report', 'tok', 't', 'c', '', 'src', True)
        self.assertEqual(status, 'duplicate')


class MainFlowTests(unittest.TestCase):
    """main 流程：RSS 已成功才推 macro；RSS 失败绝不触发 macro 推送；整体返回码不受 macro 结果影响。"""

    def write_report(self, tmp):
        md = Path(tmp) / 'report.md'
        md.write_text('正文', encoding='utf-8')
        return str(md)

    def test_rss_duplicate_blocks_macro_push(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(push_rss, 'http_json', return_value={'posts': [{'title': 'T'}]}), \
                 patch.object(push_rss, 'push_report') as mock_push:
                code = push_rss.main([self.write_report(tmp), '--title', 'T'])
        self.assertEqual(code, 3)
        mock_push.assert_not_called()

    def test_rss_success_pushes_report_ok(self):
        def fake_http(url, payload, verify, timeout=20, token=None):
            if token is None:
                return {'posts': []}
            return {'success': True, 'data': {'report_id': 'r1', 'duplicate': False}}
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with patch.object(push_rss, 'http_json', side_effect=fake_http), contextlib.redirect_stdout(stdout):
                code = push_rss.main([self.write_report(tmp), '--title', 'T', '--report-token', 'tok'])
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertTrue(result['pushed'])
        self.assertEqual(result['report_push'], 'ok')

    def test_macro_failure_keeps_exit_code_zero(self):
        rss_calls = []

        def fake_http(url, payload, verify, timeout=20, token=None):
            if token is None:
                rss_calls.append(payload is not None)  # True=POST 推送，False=GET 查重
                return {'posts': []}
            raise OSError('connection refused')
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with patch.object(push_rss, 'http_json', side_effect=fake_http), contextlib.redirect_stdout(stdout):
                code = push_rss.main([self.write_report(tmp), '--title', 'T', '--report-token', 'tok'])
        self.assertEqual(code, 0)
        self.assertTrue(any(rss_calls))  # RSS POST 推送已发生且成功
        result = json.loads(stdout.getvalue())
        self.assertTrue(result['pushed'])
        self.assertTrue(result['report_push'].startswith('failed:'), result['report_push'])

    def test_missing_token_reports_skipped_with_warning(self):
        def fake_http(url, payload, verify, timeout=20, token=None):
            return {'posts': []}
        with tempfile.TemporaryDirectory() as tmp:
            stdout = io.StringIO()
            with patch.object(push_rss, 'http_json', side_effect=fake_http), contextlib.redirect_stdout(stdout):
                code = push_rss.main([self.write_report(tmp), '--title', 'T', '--report-token', ''])
        self.assertEqual(code, 0)
        result = json.loads(stdout.getvalue())
        self.assertTrue(result['pushed'])
        self.assertEqual(result['report_push'], 'skipped_no_token')
        self.assertTrue(any('MACRO_SIGNAL_UPLOAD_TOKEN' in w for w in result.get('quality_warnings', [])))


if __name__ == '__main__':
    unittest.main()
