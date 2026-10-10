import importlib.util
import copy
import ssl
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'subtitle_rss.py'
spec = importlib.util.spec_from_file_location('subtitle_rss', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
BV = 'BV1dnbV6TEMy'
TEST_TEMP = Path(__file__).parents[2] / '.cache' / 'subtitle-tests'
TEST_TEMP.mkdir(parents=True, exist_ok=True)


def fixture():
    return {'ok': True, 'schema_version': '1', 'data': {
        'video': {'bvid': BV, 'title': '测试视频', 'owner': {'name': 'UP主'}, 'duration': '15:31'},
        'subtitle': {'available': True, 'items': [
            {'from': 0.12, 'to': 2.34, 'content': '完整第一句'},
            {'from': 3601, 'to': 3602.9, 'content': '<script>alert(1)</script> **原话**'},
        ]}, 'warnings': []}}


class SubtitleTests(unittest.TestCase):
    def test_tls_verified_by_default_and_disabled_only_on_request(self):
        with patch.object(m, 'urlopen') as open_url, patch.object(m.json, 'load', return_value={}):
            m.request_json('https://example.test/posts')
            secure = open_url.call_args.kwargs['context']
            self.assertTrue(secure.check_hostname)
            self.assertEqual(secure.verify_mode, ssl.CERT_REQUIRED)
            m.request_json('https://example.test/posts', insecure=True)
            insecure = open_url.call_args.kwargs['context']
            self.assertFalse(insecure.check_hostname)
            self.assertEqual(insecure.verify_mode, ssl.CERT_NONE)

    def test_insecure_applies_to_duplicate_check_and_post(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder, patch.object(m, 'request_json', side_effect=[
            {'posts': []}, {'id': 'tls-test'}
        ]) as request:
            m.publish(m.build_post(fixture(), BV), m.DEFAULT_ENDPOINT, Path(folder), insecure=True)
            self.assertEqual(request.call_count, 2)
            self.assertTrue(all(call.kwargs['insecure'] for call in request.call_args_list))

    def test_cli_passes_insecure_to_publish(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder, patch.object(m, 'extract', return_value=fixture()), \
                patch.object(m, 'publish', return_value={'status': 'published', 'id': 'cli-test'}) as publish, \
                patch('builtins.print'):
            self.assertEqual(m.main([BV, '--push', '--insecure', '--output-dir', folder]), 0)
            self.assertTrue(publish.call_args.kwargs['insecure'])

    def test_normalizes_links_and_drops_tracking(self):
        for value in (BV, f'https://www.bilibili.com/video/{BV}/?p=1&spm_id_from=foo'):
            self.assertEqual(m.resolve_video(value), (BV, f'https://www.bilibili.com/video/{BV}'))

    def test_rejects_wrong_host_or_nonfirst_page(self):
        for value in (f'https://evil.test/{BV}', f'https://www.bilibili.com/video/{BV}?p=2',
                      f'https://www.bilibili.com/video/{BV}?p=oops', 'BV123'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                m.resolve_video(value)

    def test_short_link_checks_final_destination(self):
        with patch.object(m, 'resolve_short_link', return_value=f'https://www.bilibili.com/video/{BV}?p=1'):
            self.assertEqual(m.resolve_video('https://b23.tv/example')[0], BV)
        with patch.object(m, 'resolve_short_link', return_value=f'https://evil.test/{BV}'):
            with self.assertRaises(ValueError):
                m.resolve_video('https://b23.tv/example')

    def test_renders_every_segment_and_escapes_markup(self):
        post = m.build_post(fixture(), BV)
        self.assertEqual(post['source'], 'my-bot')
        self.assertEqual(post['channel'], 'bilinote')
        self.assertEqual(set(post), {'title', 'content', 'channel', 'source', 'url'})
        self.assertIn('完整第一句', post['content'])
        self.assertNotIn('01:00:01.000', post['content'])
        self.assertNotIn(' → ', post['content'])
        self.assertIn('&lt;script&gt;', post['content'])
        self.assertNotIn('<script>', post['content'])
        self.assertIn('\\*\\*原话\\*\\*', post['content'])

    def test_continuous_subtitles_merge_without_changing_source(self):
        data = fixture()
        data['data']['subtitle']['items'] = [
            {'from': 0, 'to': 1, 'content': '第一句'},
            {'from': 2.5, 'to': 3, 'content': '第二句'},
            {'from': 4.51, 'to': 5, 'content': '第三句'},
        ]
        original = copy.deepcopy(data)
        post = m.build_post(data, BV)
        body = post['content'].split('## 完整文字稿\n\n')[1]
        self.assertEqual(body, '第一句 第二句\n\n第三句\n')
        self.assertEqual(data, original)

    def test_length_threshold_splits_before_next_segment(self):
        for length, expected in ((119, ['甲' * 119 + ' 乙', '丙']),
                                 (120, ['甲' * 120, '乙 丙'])):
            data = fixture()
            data['data']['subtitle']['items'] = [
                {'from': 0, 'to': 1, 'content': '甲' * length},
                {'from': 1, 'to': 2, 'content': '乙'},
                {'from': 2, 'to': 3, 'content': '丙'},
            ]
            with self.subTest(length=length):
                body = m.build_post(data, BV)['content'].split('## 完整文字稿\n\n')[1]
                self.assertEqual(body.rstrip('\n').split('\n\n'), expected)

    def test_no_subtitles_never_becomes_article(self):
        data = fixture()
        data['data']['subtitle'] = {'available': False, 'items': [], 'text': ''}
        with self.assertRaisesRegex(ValueError, '字幕'):
            m.build_post(data, BV)

    def test_wrong_video_or_failed_envelope_rejected(self):
        data = fixture()
        data['data']['video']['bvid'] = 'BV1xxxxxxxxx'
        with self.assertRaises(ValueError):
            m.build_post(data, BV)
        with self.assertRaises(ValueError):
            m.build_post({'ok': False, 'error': {'message': 'failed'}}, BV)

    def test_invalid_timestamps_rejected(self):
        for start, end in ((float('nan'), 2), (2, 1), (-1, 1), (0, float('inf'))):
            data = fixture()
            data['data']['subtitle']['items'][0].update({'from': start, 'to': end})
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                m.build_post(data, BV)

    def test_duplicate_skips_post(self):
        post = m.build_post(fixture(), BV)
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder, patch.object(m, 'request_json', return_value={
            'posts': [{'id': 'existing', 'url': post['url'] + '/?spm_id_from=abc'}]
        }) as request:
            result = m.publish(post, m.DEFAULT_ENDPOINT, Path(folder))
            self.assertEqual(result['status'], 'duplicate')
            self.assertEqual(request.call_count, 1)

    def test_failed_duplicate_check_prevents_post(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder, patch.object(m, 'request_json', side_effect=OSError('offline')) as request:
            with self.assertRaises(OSError):
                m.publish(m.build_post(fixture(), BV), m.DEFAULT_ENDPOINT, Path(folder))
            self.assertEqual(request.call_count, 1)

    def test_success_has_receipt_and_second_run_skips_network(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder, patch.object(m, 'request_json', side_effect=[
            {'posts': []}, {'id': 'post-123'}
        ]) as request:
            result = m.publish(m.build_post(fixture(), BV), m.DEFAULT_ENDPOINT, Path(folder))
            self.assertEqual(result['status'], 'published')
            again = m.publish(m.build_post(fixture(), BV), m.DEFAULT_ENDPOINT, Path(folder))
            self.assertEqual(again['status'], 'duplicate')
            self.assertEqual(request.call_count, 2)
            self.assertEqual(request.call_args_list[1].kwargs['method'], 'POST')
            payload = request.call_args_list[1].kwargs['payload']
            self.assertEqual(payload['channel'], 'bilinote')
            self.assertEqual(payload['source'], 'my-bot')

    def test_ambiguous_post_failure_not_retried_or_recorded(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as folder, patch.object(m, 'request_json', side_effect=[
            {'posts': []}, TimeoutError('timeout')
        ]) as request:
            with self.assertRaises(TimeoutError):
                m.publish(m.build_post(fixture(), BV), m.DEFAULT_ENDPOINT, Path(folder))
            self.assertEqual(request.call_count, 2)
            self.assertFalse(list(Path(folder).glob('*.receipt.json')))


if __name__ == '__main__':
    unittest.main()
