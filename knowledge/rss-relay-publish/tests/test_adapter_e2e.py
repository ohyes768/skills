"""Exercise business entry -> subprocess CLI -> fake HTTP relay, never production."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import unittest
from unittest.mock import patch

import test_rss_publish as relay_fixture
from test_rss_publish import SCRIPT
from test_migrations import load, ROOT
from test_external_migrations import load as load_external


@unittest.skipUnless((ROOT / 'hk-ipo-research').exists() and importlib.util.find_spec('httpx'),
                     'Business end-to-end tests require source checkout and its dependencies')
class AdapterEndToEndTests(unittest.TestCase):
    def setUp(self):
        relay_fixture.RelayTests.setUp(self)
        self.environment = patch.dict(os.environ, {'RSS_RELAY_SKILL_DIR': str(SCRIPT.parents[1]),
                                                   'RSS_RELAY_STATE_DIR': str(self.root / 'state')})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        relay_fixture.RelayTests.tearDown(self)

    def test_both_macro_reports_and_retry(self):
        for kind in ('a-share', 'bond-market'):
            m = load(f'finance-macro/{kind}-macro-impact-skill/scripts/push_rss.py')
            args = [str(self.file), '--title', '2026-11-05 ' + kind, '--allow-duplicate',
                    '--endpoint', self.base + '/post', '--report-token', '']
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(m.main(args), 0)
                self.assertEqual(m.main(args), 3)
        self.assertEqual(self.writes, 2)
        self.assertTrue(all(p['channel'] == 'macro' for p in self.posts))

    def test_both_ipo_report_types(self):
        m = load('hk-ipo-research/scripts/push_rss.py')
        for kind in ('research', 'backtest'):
            args = ['push_rss.py', str(self.file), '--title', '2026-11-05 ' + kind + ' 00001.HK',
                    '--report-type', kind, '--source', 'hk-ipo-' + kind, '--allow-duplicate', '--endpoint', self.base + '/post']
            with patch.object(sys, 'argv', args), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(m.main(), 0)
                self.assertEqual(m.main(), 3)
        self.assertEqual(self.writes, 2)
        self.assertEqual({p['source'] for p in self.posts}, {'hk-ipo-research', 'hk-ipo-backtest'})

    def test_bilibili_business_receipt_and_cli(self):
        m = load('bilibili-subtitle-rss/scripts/subtitle_rss.py')
        post = {'title': '视频', 'content': '完整字幕', 'url': 'https://www.bilibili.com/video/BV1dnbV6TEMy',
                'channel': 'bilinote', 'source': 'my-bot'}
        args = (post, self.base + '/post', self.root / 'subtitles')
        self.assertEqual(m.publish(*args)['status'], 'published')
        self.assertEqual(m.publish(*args)['status'], 'duplicate')
        self.assertEqual(self.writes, 1)

    def test_waytoagi_business_receipt_and_cli(self):
        m = load('waytoagi-update-log/scripts/publish_articles.py')
        manifest = self.root / 'articles.json'
        manifest.write_text(json.dumps([{'token': 'wiki1', 'title': '文章', 'content': '说明', 'url': 'https://example.test/wiki1'}]), encoding='utf-8')
        args = ['--articles-json', str(manifest), '--receipts', str(self.root / 'tokens.json'), '--endpoint', self.base + '/post']
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(m.main(args), 0)
            self.assertEqual(m.main(args), 0)
        self.assertEqual(self.writes, 1)
        self.assertEqual(self.posts[0]['channel'], 'waytoagi')

    def test_external_news_and_daily_review(self):
        projects = ROOT.parent
        if not (projects / 'daily-review/daily_review.py').exists():
            self.skipTest('External checkouts unavailable')
        daily = load_external(projects / 'daily-review/daily_review.py')
        news = load_external(projects / 'stock-info-dingding/xwlb_to_rss.py')
        with patch.object(daily, 'RSS_POST_URL', self.base + '/post'), contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(daily.rss_push('2026-11-05 日报', '完整日报'))
            self.assertTrue(daily.rss_push('2026-11-05 日报', '完整日报'))
            payload = {'title': '新闻联播 2026-11-05', 'content': '新闻摘要', 'url': news.CHANNEL_URL, 'source': 'xwlb', 'channel': 'xinwen'}
            self.assertTrue(news.post_to_rss_relay(self.base + '/post', payload))
            self.assertTrue(news.post_to_rss_relay(self.base + '/post', payload))
        self.assertEqual(self.writes, 2)
        self.assertEqual({p['channel'] for p in self.posts}, {'workreport', 'xinwen'})


if __name__ == '__main__':
    unittest.main()
