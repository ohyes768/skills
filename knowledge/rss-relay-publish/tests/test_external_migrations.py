import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

PROJECTS = Path(__file__).resolve().parents[4]
SENT = {'schema_version': 1, 'status': 'published', 'id': 'p1', 'detail_url': 'https://test/view/p1', 'verified': True}


def load(path):
    spec = importlib.util.spec_from_file_location('external_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@unittest.skipUnless((PROJECTS / 'daily-review/daily_review.py').exists() and
                     (PROJECTS / 'stock-info-dingding/xwlb_to_rss.py').exists(), 'Requires external source checkouts')
class ExternalMigrationTests(unittest.TestCase):
    def test_daily_review_boolean_contract_and_namespace(self):
        m = load(PROJECTS / 'daily-review/daily_review.py')
        self.assertTrue(hasattr(m, 'relay_publish'), 'daily-review must delegate RSS writes')
        with patch.object(m, 'relay_publish', return_value=SENT) as publish, contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(m.rss_push('2026-11-05 日报', '完整日报'))
        self.assertEqual(publish.call_args.args[0]['channel'], 'workreport')
        self.assertEqual(publish.call_args.args[0]['source'], 'daily-review')
        with patch.object(m, 'relay_publish', side_effect=ValueError('unknown')), contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(m.rss_push('2026-11-05 日报', '完整日报'))

    def test_news_no_blind_retry_after_unknown(self):
        m = load(PROJECTS / 'stock-info-dingding/xwlb_to_rss.py')
        self.assertTrue(hasattr(m, 'relay_publish'), 'news must delegate RSS writes')
        payload = {'title': '新闻联播 2026-11-05', 'content': '新闻摘要', 'url': '', 'source': 'xwlb', 'channel': 'xinwen'}
        with patch.object(m, 'relay_publish', return_value=SENT) as publish, contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(m.post_to_rss_relay('https://test/api/post', payload))
        self.assertEqual(publish.call_args.args[0], payload)
        with patch.object(m, 'relay_publish', side_effect=ValueError('unknown')) as publish, contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(m.post_to_rss_relay('https://test/api/post', payload))
            publish.assert_called_once()


if __name__ == '__main__':
    unittest.main()
