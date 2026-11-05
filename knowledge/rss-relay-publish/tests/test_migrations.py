"""Business adapter contracts; HTTP transport is exercised in test_rss_publish."""
import contextlib
import concurrent.futures
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SENT = {'schema_version': 1, 'status': 'published', 'id': 'p1', 'detail_url': 'https://test/view/p1', 'verified': True}


def load(path):
    path = ROOT / path
    sys.path.insert(0, str(path.parent))
    try:
        spec = importlib.util.spec_from_file_location('adapter_' + str(abs(hash(str(path)))), path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


@unittest.skipUnless((ROOT / 'hk-ipo-research').exists(), 'Requires full source checkout')
class MigrationTests(unittest.TestCase):
    def test_waytoagi_concurrent_receipt_updates_preserve_all_tokens(self):
        m = load('waytoagi-update-log/scripts/publish_articles.py')
        original = m.read_receipts
        def slow_read(path):
            data = original(path)
            time.sleep(0.03)
            return data
        with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as tmp:
            receipt = Path(tmp) / 'pushed.json'
            with patch.object(m, 'read_receipts', side_effect=slow_read), concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(lambda token: m.record(receipt, token), ['t' + str(i) for i in range(6)]))
            self.assertEqual(len(json.loads(receipt.read_text(encoding='utf-8'))['articles']), 6)

    def test_waytoagi_records_each_success_before_next_failure(self):
        path = ROOT / 'waytoagi-update-log/scripts/publish_articles.py'
        self.assertTrue(path.exists(), 'WaytoAGI needs a shared-CLI publishing adapter')
        m = load('waytoagi-update-log/scripts/publish_articles.py')
        articles = [{'token': token, 'title': token, 'content': '说明', 'url': 'https://example.test/' + token}
                    for token in ('old', 'first', 'second')]
        with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as tmp:
            manifest = Path(tmp) / 'articles.json'
            manifest.write_text(json.dumps(articles), encoding='utf-8')
            receipt = Path(tmp) / 'pushed.json'
            receipt.write_text(json.dumps({'articles': {'old': 'previous'}}), encoding='utf-8')
            with patch.object(m, 'relay_publish', side_effect=[SENT, ValueError('unknown')]) as publish, \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(m.main(['--articles-json', str(manifest), '--receipts', str(receipt)]), 2)
            saved = json.loads(receipt.read_text(encoding='utf-8'))['articles']
            self.assertIn('first', saved)
            self.assertIn('old', saved)
            self.assertNotIn('second', saved)
            self.assertEqual(publish.call_count, 2)

    def test_macro_uses_public_cli_and_duplicate_retries_dashboard(self):
        for skill in ('a-share-macro-impact-skill', 'bond-market-macro-impact-skill'):
            m = load(f'finance-macro/{skill}/scripts/push_rss.py')
            self.assertTrue(hasattr(m, 'relay_publish'), 'macro adapter must invoke public CLI')
            with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as tmp:
                report = Path(tmp) / 'report.md'
                report.write_text('正文', encoding='utf-8')
                for status in ('published', 'duplicate'):
                    with patch.object(m, 'relay_publish', return_value=dict(SENT, status=status)) as publish, \
                         patch.object(m, 'is_duplicate', return_value=False), \
                         patch.object(m, 'push_report', return_value='ok') as dashboard, \
                         contextlib.redirect_stdout(io.StringIO()) as out:
                        code = m.main([str(report), '--title', '2026-11-05 T'])
                    self.assertEqual(code, 0 if status == 'published' else 3)
                    self.assertEqual(publish.call_args.args[0]['channel'], 'macro')
                    self.assertEqual(publish.call_args.args[0]['content'], '正文')
                    dashboard.assert_called_once()
                    self.assertEqual(json.loads(out.getvalue())['report_push'], 'ok')

    def test_bilibili_retains_business_receipt(self):
        m = load('bilibili-subtitle-rss/scripts/subtitle_rss.py')
        self.assertTrue(hasattr(m, 'relay_publish'), 'subtitle adapter must invoke public CLI')
        post = {'title': '视频', 'content': '字幕', 'url': 'https://www.bilibili.com/video/BV1dnbV6TEMy',
                'source': 'my-bot', 'channel': 'bilinote'}
        with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as tmp, \
             patch.object(m, 'request_json', return_value={'posts': []}), \
             patch.object(m, 'relay_publish', return_value=SENT) as publish:
            first = m.publish(post, m.DEFAULT_ENDPOINT, Path(tmp), insecure=True)
            again = m.publish(post, m.DEFAULT_ENDPOINT, Path(tmp))
        self.assertEqual((first['status'], again['status']), ('published', 'duplicate'))
        publish.assert_called_once()
        self.assertFalse(publish.call_args.kwargs['verify'])

    def test_hkipo_preserves_type_and_channel(self):
        m = load('hk-ipo-research/scripts/push_rss.py')
        self.assertTrue(hasattr(m, 'relay_publish'), 'IPO adapter must invoke public CLI')
        with tempfile.TemporaryDirectory(dir=ROOT / '.tmp') as tmp:
            report = Path(tmp) / 'report.md'
            report.write_text(m.REPORT_START_MARKER + '\n正文', encoding='utf-8')
            keys = []
            for kind, source in [('research', 'hk-ipo-research'), ('backtest', 'hk-ipo-backtest')]:
                argv = ['push_rss.py', str(report), '--title', '2026-11-05 T（00001.HK）',
                        '--report-type', kind, '--source', source, '--allow-duplicate']
                with patch.object(sys, 'argv', argv), patch.object(m, 'relay_publish', return_value=SENT) as publish, \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(m.main(), 0)
                    self.assertEqual(publish.call_args.args[0]['source'], source)
                    keys.append(publish.call_args.args[1])
            self.assertNotEqual(*keys)

    def test_ipo_precheck_separates_research_and_backtest(self):
        m = load('hk-ipo-research/scripts/push_rss.py')
        response = unittest.mock.Mock()
        response.json.return_value = {'posts': [{'title': '2026-11-05 港股IPO回测｜公司（00001.HK）',
                                                'content': '00001.HK', 'created_at': '2026-11-05',
                                                'source': 'hk-ipo-backtest', 'channel': 'hkipo'}]}
        with patch.object(m.httpx, 'get', return_value=response):
            self.assertFalse(m.is_duplicate(m.DEFAULT_POSTS_ENDPOINT, '2026-11-05 港股打新｜公司（00001.HK）', True))


if __name__ == '__main__':
    unittest.main()
