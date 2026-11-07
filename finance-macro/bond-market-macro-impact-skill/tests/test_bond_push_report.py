import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('publish_report', Path(__file__).parents[1] / 'scripts/publish_report.py')
publish_report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publish_report)

TEST_TEMP = Path(__file__).resolve().parents[3] / '.cache/rss-tests'
TEST_TEMP.mkdir(parents=True, exist_ok=True)


class PushReportTests(unittest.TestCase):
    """push_report 纯逻辑：payload 组装与四种状态映射。"""

    def test_missing_token_skips_and_never_calls_http(self):
        with patch.object(publish_report, 'http_json') as mock_http:
            status = publish_report.push_report('https://x/report', '', 't', 'c', '', 'src', True)
        self.assertEqual(status, 'skipped_no_token')
        mock_http.assert_not_called()

    def test_payload_and_token_are_passed(self):
        with patch.object(publish_report, 'http_json', return_value={'success': True}) as mock_http:
            status = publish_report.push_report('https://x/report', 'tok', '标题', '正文', 'https://u', 'src', False)
        self.assertEqual(status, 'ok')
        args, kwargs = mock_http.call_args
        self.assertEqual(args[0], 'https://x/report')
        self.assertEqual(args[1], {'title': '标题', 'content': '正文', 'url': 'https://u', 'source': 'src'})
        self.assertFalse(args[2])
        self.assertEqual(kwargs.get('token'), 'tok')

    def test_exception_maps_to_failed(self):
        with patch.object(publish_report, 'http_json', side_effect=OSError('boom')):
            status = publish_report.push_report('https://x/report', 'tok', 't', 'c', '', 'src', True)
        self.assertTrue(status.startswith('failed:'), status)

    def test_duplicate_response_maps_to_duplicate(self):
        with patch.object(publish_report, 'http_json', return_value={'success': True, 'data': {'report_id': 'r1', 'duplicate': True}}):
            status = publish_report.push_report('https://x/report', 'tok', 't', 'c', '', 'src', True)
        self.assertEqual(status, 'duplicate')


class MainFlowTests(unittest.TestCase):
    def run_main(self, tmp, *, status='published', business_duplicate=False, token='', dashboard='ok', fail=False, extra=None):
        md = Path(tmp) / 'report.md'
        md.write_text('正文', encoding='utf-8')
        response = {'schema_version': 1, 'status': status, 'id': 'p1', 'detail_url': 'https://test/view/p1'}
        stdout = io.StringIO()
        with patch.object(publish_report, 'relay_publish', return_value=response, side_effect=ValueError('unknown') if fail else None) as relay, \
             patch.object(publish_report, 'is_duplicate', return_value=business_duplicate), \
             patch.object(publish_report, 'push_report', return_value=dashboard) as report, \
             contextlib.redirect_stdout(stdout):
            code = publish_report.main([str(md), '--title', 'T', '--report-token', token, *(extra or [])])
        return code, json.loads(stdout.getvalue()), relay, report

    def test_macro_relay_contract(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as tmp:
            code, result, relay, _ = self.run_main(tmp)
        self.assertEqual(code, 0)
        self.assertEqual(relay.call_args.args[0], {'title': 'T', 'content': '正文', 'channel': 'macro', 'source': 'my-bot', 'url': ''})
        self.assertEqual(relay.call_args.kwargs['endpoint'], publish_report.DEFAULT_ENDPOINT)
        self.assertTrue(result['pushed'])

    def test_rss_duplicate_still_retries_macro_push(self):
        for business in (False, True):
            with self.subTest(business=business), tempfile.TemporaryDirectory(dir=TEST_TEMP) as tmp:
                code, result, relay, report = self.run_main(tmp, status='duplicate', business_duplicate=business)
            self.assertEqual(code, 3)
            report.assert_called_once()
            self.assertFalse(result['pushed'])
            self.assertTrue(result['duplicate'])
            if business:
                relay.assert_not_called()

    def test_unconfirmed_rss_never_pushes_macro(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as tmp:
            code, result, _, report = self.run_main(tmp, fail=True)
        self.assertEqual(code, 2)
        self.assertFalse(result['pushed'])
        report.assert_not_called()

    def test_macro_failure_keeps_exit_code_zero(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as tmp:
            code, result, _, _ = self.run_main(tmp, dashboard='failed: connection refused')
        self.assertEqual(code, 0)
        self.assertTrue(result['report_push'].startswith('failed:'))

    def test_missing_token_reports_skipped_with_warning(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as tmp:
            code, result, _, _ = self.run_main(tmp, dashboard='skipped_no_token')
        self.assertEqual(code, 0)
        self.assertTrue(any('MACRO_SIGNAL_UPLOAD_TOKEN' in w for w in result['quality_warnings']))

    def test_strict_quality_failure_never_publishes(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as tmp:
            code, result, relay, report = self.run_main(tmp, extra=['--strict'])
        self.assertEqual(code, 2)
        relay.assert_not_called()
        report.assert_not_called()
        self.assertIn('quality_errors', result)


if __name__ == '__main__':
    unittest.main()
