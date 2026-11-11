"""natgeo_daily 回归测试：摄影师提取 + 钉钉推送判定。

重点覆盖两个历史缺陷：
  1. 推送只看 HTTP 200，钉钉业务失败(errcode=-1 系统繁忙)被误判成功 → 必须看 errcode
  2. 摄影师正则只匹配 "Photograph by"，NatGeo 描述多为正文内嵌 "photographer X says" → 恒为 null
"""
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

_SCRIPT = Path(__file__).parents[1] / 'scripts/natgeo_daily.py'
_spec = importlib.util.spec_from_file_location('natgeo_daily', _SCRIPT)
assert _spec is not None and _spec.loader is not None
natgeo_daily = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(natgeo_daily)


class StubResponse:
    """模拟钉钉响应：HTTP 200 既可能是成功也可能是业务失败。"""

    def __init__(self, status_code=200, body=None, text=None):
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else repr(body)

    def json(self):
        if self._body is None:
            raise ValueError('not json')
        return self._body


class StubPost:
    """按顺序返回桩响应；前 errors 次抛网络异常。记录调用次数。"""

    def __init__(self, responses, errors=0):
        self.responses = responses
        self.errors = errors
        self.calls = 0

    def __call__(self, *_args, **_kwargs):
        i = self.calls
        self.calls += 1
        if i < self.errors:
            raise natgeo_daily.requests.RequestException('boom')
        return self.responses[min(i - self.errors, len(self.responses) - 1)]


class PhotographerTests(unittest.TestCase):
    """extract_photographer_from_description：两种署名写法 + 负例。"""

    def test_credit_appended_to_description(self):
        desc = ('Nine-year-old Kerim Efe Umut sits on a ceremonial throne ... '
                'but photographer Emre Çaylak says rising gold prices ...')
        self.assertEqual(natgeo_daily.extract_photographer_from_description(desc), 'Emre Çaylak')

    def test_photograph_by_signature(self):
        self.assertEqual(
            natgeo_daily.extract_photographer_from_description('A boy in dress. Photograph by Benjamin Pawlica'),
            'Benjamin Pawlica')

    def test_photographed_by_signature(self):
        self.assertEqual(
            natgeo_daily.extract_photographer_from_description('A boy in dress. Photographed by Sasha Arutyunova'),
            'Sasha Arutyunova')

    def test_credit_suffix_is_kept(self):
        self.assertEqual(
            natgeo_daily.extract_photographer_from_description('Photograph by Endia Beal, MoCP'),
            'Endia Beal, MoCP')

    def test_lowercase_phrase_is_not_a_name(self):
        self.assertIsNone(natgeo_daily.extract_photographer_from_description(
            'The photographer notes that the market was quiet that day.'))

    def test_empty_description(self):
        self.assertIsNone(natgeo_daily.extract_photographer_from_description(''))


class PushTests(unittest.TestCase):
    """push_to_dingtalk：HTTP 200 不等于送达，必须校验 errcode。"""

    def setUp(self):
        self.env = patch.dict(natgeo_daily.os.environ, {
            'NATGEO_DINGTALK_WEBHOOK': 'https://example.invalid/robot/send?access_token=x',
            'NATGEO_DINGTALK_SECRET': '',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        no_sleep = patch.object(natgeo_daily.time, 'sleep')
        no_sleep.start()
        self.addCleanup(no_sleep.stop)

    def test_busy_errcode_is_failure_not_success(self):
        """回归点：HTTP 200 + errcode=-1 旧代码会误报成功。"""
        post = StubPost([StubResponse(200, {'errcode': -1, 'errmsg': '系统繁忙'})])
        with patch.object(natgeo_daily.requests, 'post', post):
            self.assertFalse(natgeo_daily.push_to_dingtalk('m', attempts=1))
        self.assertEqual(post.calls, 1)

    def test_busy_errcode_retries_until_success(self):
        post = StubPost([StubResponse(200, {'errcode': -1}),
                          StubResponse(200, {'errcode': 0, 'errmsg': 'ok'})])
        with patch.object(natgeo_daily.requests, 'post', post):
            self.assertTrue(natgeo_daily.push_to_dingtalk('m'))
        self.assertEqual(post.calls, 2)

    def test_retries_exhausted_returns_false(self):
        post = StubPost([StubResponse(200, {'errcode': -1})])
        with patch.object(natgeo_daily.requests, 'post', post):
            self.assertFalse(natgeo_daily.push_to_dingtalk('m', attempts=3))
        self.assertEqual(post.calls, 3)

    def test_client_error_is_not_retried(self):
        """4xx 是配置/签名问题，重试无意义，应立即失败。"""
        post = StubPost([StubResponse(400, {'errcode': 310000})])
        with patch.object(natgeo_daily.requests, 'post', post):
            self.assertFalse(natgeo_daily.push_to_dingtalk('m', attempts=3))
        self.assertEqual(post.calls, 1)

    def test_network_error_then_success(self):
        post = StubPost([StubResponse(200, {'errcode': 0})], errors=1)
        with patch.object(natgeo_daily.requests, 'post', post):
            self.assertTrue(natgeo_daily.push_to_dingtalk('m'))
        self.assertEqual(post.calls, 2)

    def test_non_json_200_body_is_failure(self):
        post = StubPost([StubResponse(200, None, text='<html>oops</html>')])
        with patch.object(natgeo_daily.requests, 'post', post):
            self.assertFalse(natgeo_daily.push_to_dingtalk('m', attempts=1))

    def test_missing_webhook_never_calls_http(self):
        with patch.dict(natgeo_daily.os.environ, {'NATGEO_DINGTALK_WEBHOOK': ''}):
            post = StubPost([StubResponse(200, {'errcode': 0})])
            with patch.object(natgeo_daily.requests, 'post', post):
                self.assertFalse(natgeo_daily.push_to_dingtalk('m'))
            self.assertEqual(post.calls, 0)

    def test_success_sends_once(self):
        post = StubPost([StubResponse(200, {'errcode': 0, 'errmsg': 'ok'})])
        with patch.object(natgeo_daily.requests, 'post', post):
            self.assertTrue(natgeo_daily.push_to_dingtalk('m'))
        self.assertEqual(post.calls, 1)


if __name__ == '__main__':
    unittest.main()
