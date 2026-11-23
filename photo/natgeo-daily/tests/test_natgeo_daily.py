"""natgeo_daily 回归测试：摄影师提取 + 钉钉投递（走公共 CLI）。

重点覆盖三个历史缺陷：
  1. 重复推送：内联 POST 遇 errcode=-1「系统繁忙」会原样重发，而 -1 是受理后的
     繁忙回执（消息已进群）→ 群里两条相同消息。修复：改走公共 dingtalk-push CLI，
     回执去重（同内容 → duplicate 跳过）+ 结果未知不盲重（unknown）。
  2. 摄影师只从 og:description 正文匹配，"Photograph by" 之外的正文内嵌写法恒为 null。
  3. 署名在正文之外（独立图注 / 主图 JSON crdt）时提取不到 → 补兜底。
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


class StubDingTalkPush:
    """公共 dingtalk_push 模块替身：记录 send() 调用并返回预设状态。"""

    def __init__(self, status='sent', extra=None):
        self.status = status
        self.extra = extra or {}
        self.calls = []

    def send(self, title, text, *, webhook, keyword=None, **_kwargs):
        self.calls.append({'title': title, 'text': text,
                           'webhook': webhook, 'keyword': keyword})
        result = {'status': self.status}
        result.update(self.extra)
        return result


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

    def test_name_with_lowercase_particle(self):
        """回归点：姓名里的粒子词（de/van/von…）不能被截断。

        2026-11-20：'photographer Robin de Puy says' 只抽到 'Robin'，
        推送到群里的摄影师署名缺姓氏。
        """
        self.assertEqual(
            natgeo_daily.extract_photographer_from_description(
                '... who photographer Robin de Puy says was often perched on her shoulder'),
            'Robin de Puy')
        self.assertEqual(
            natgeo_daily.extract_photographer_from_description('photographer Vincent van Gogh says'),
            'Vincent van Gogh')
        self.assertEqual(
            natgeo_daily.normalize_credit('Robin de Puy'), 'Robin de Puy')

    def test_organization_name_still_rejected(self):
        """加了粒子词不能把机构名放进来：'National Geographic Pristine Seas' 仍不认。"""
        self.assertIsNone(natgeo_daily.normalize_credit('National Geographic Pristine Seas'))
        self.assertIsNone(natgeo_daily.normalize_credit('National Geographic'))

    def test_signature_ends_at_sentence_boundary(self):
        """回归点：署名后面的正文不能被吸进来。

        2026-11-20：'Photograph by Emre Çaylak. His work spans ...' 抽成
        'Emre Çaylak. His'，多了一个 ' His'。
        """
        self.assertEqual(
            natgeo_daily.extract_photographer_from_description(
                'Photograph by Emre Çaylak. His work spans four continents.'),
            'Emre Çaylak')

    def test_institution_after_comma_is_dropped(self):
        """回归点：'Steve Winter, National Geographic' 里的机构名不能进署名。"""
        self.assertEqual(
            natgeo_daily.extract_photographer_from_description(
                'Photograph by Steve Winter, National Geographic'),
            'Steve Winter')
        self.assertEqual(
            natgeo_daily.normalize_credit('Steve Winter, National Geographic'),
            'Steve Winter')

    def test_name_suffix_is_kept(self):
        self.assertEqual(
            natgeo_daily.extract_photographer_from_description(
                'Photograph by Carlton Ward Jr. He is based in Maine.'),
            'Carlton Ward Jr')

    def test_lowercase_phrase_is_not_a_name(self):
        self.assertIsNone(natgeo_daily.extract_photographer_from_description(
            'The photographer notes that the market was quiet that day.'))

    def test_empty_description(self):
        self.assertIsNone(natgeo_daily.extract_photographer_from_description(''))


class CreditFallbackTests(unittest.TestCase):
    """署名不在 og:description 正文时的兜底：图注 + 主图 JSON。"""

    CAPTION_HTML = (
        '<span aria-label="Manu San Félix, National Geographic Pristine Seas" '
        'class="RichText Caption__Credit">Manu San Félix, National Geographic Pristine Seas</span>'
    )
    JSON_HTML = (
        '{"rt":"https://i.natgeofe.com/x.jpg","src":"https://i.natgeofe.com/x.jpg",'
        '"altText":"Bright blue giant clams with wavy mantles.",'
        '"crdt":"Manu San Félix, National Geographic Pristine Seas",'
        '"dsc":"Giant clams (Tridacna maxima) ..."}'
    )

    def test_caption_credit_is_used(self):
        self.assertEqual(
            natgeo_daily.extract_photographer_from_html(self.CAPTION_HTML), 'Manu San Félix')

    def test_json_credit_is_used(self):
        self.assertEqual(
            natgeo_daily.extract_photographer_from_html(self.JSON_HTML), 'Manu San Félix')

    def test_organization_only_is_not_a_person(self):
        """机构名不是人名：超过 3 个词 → 不认。"""
        self.assertIsNone(natgeo_daily.normalize_credit('National Geographic Pristine Seas'))

    def test_normalize_credit_keeps_credential_only(self):
        self.assertEqual(natgeo_daily.normalize_credit('Endia Beal, MoCP'), 'Endia Beal, MoCP')
        self.assertEqual(
            natgeo_daily.normalize_credit('Manu San Félix, National Geographic Pristine Seas'),
            'Manu San Félix')
        self.assertEqual(natgeo_daily.normalize_credit('  Manu San Félix '), 'Manu San Félix')

    def test_extract_from_page_prefers_description(self):
        html = (
            '<meta property="og:title" content="Electric Reef">'
            '<meta property="og:description" content="A boy in dress. Photograph by Benjamin Pawlica">'
            '<meta property="og:image" content="https://i.natgeofe.com/x.jpg">'
            + self.CAPTION_HTML
        )
        photo = natgeo_daily.extract_from_page(html, 'https://www.nationalgeographic.com/photo-of-the-day/')
        self.assertIsNotNone(photo)
        self.assertEqual(photo.photographer, 'Benjamin Pawlica')

    def test_extract_from_page_falls_back_to_caption(self):
        html = (
            '<meta property="og:title" content="Electric Reef">'
            '<meta property="og:description" content="Giant clams spread their mantles.">'
            '<meta property="og:image" content="https://i.natgeofe.com/x.jpg">'
            + self.CAPTION_HTML
        )
        photo = natgeo_daily.extract_from_page(html, 'https://www.nationalgeographic.com/photo-of-the-day/')
        self.assertIsNotNone(photo)
        self.assertEqual(photo.photographer, 'Manu San Félix')


class PushTests(unittest.TestCase):
    """push_to_dingtalk：走公共 CLI，回执去重 + unknown 不盲重。"""

    def setUp(self):
        self.env = patch.dict(natgeo_daily.os.environ, {
            'NATGEO_DINGTALK_WEBHOOK': 'https://example.invalid/robot/send?access_token=x',
            'NATGEO_DINGTALK_SECRET': '',
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def _push(self, status='sent', extra=None):
        stub = StubDingTalkPush(status=status, extra=extra)
        with patch.object(natgeo_daily, '_load_dingtalk_push', return_value=stub):
            result = natgeo_daily.push_to_dingtalk('正文')
        return stub, result

    def test_sent_is_success(self):
        stub, status = self._push('sent')
        self.assertEqual(status, 'sent')
        self.assertEqual(len(stub.calls), 1)
        self.assertEqual(stub.calls[0]['keyword'], '国家地理')

    def test_duplicate_is_success_and_not_resent(self):
        """回归点：同内容再推 → duplicate 跳过，绝不产生第二条相同消息。"""
        stub, status = self._push('duplicate')
        self.assertEqual(status, 'duplicate')
        self.assertEqual(natgeo_daily._push_exit_code(status), 0)
        self.assertEqual(len(stub.calls), 1)

    def test_unknown_is_not_retried(self):
        """回归点：结果未知（可能已送达）→ 不自动重发，退出码 5。"""
        stub, status = self._push('unknown')
        self.assertEqual(status, 'unknown')
        self.assertEqual(natgeo_daily._push_exit_code(status), 5)
        self.assertEqual(len(stub.calls), 1)

    def test_failed_status_maps_to_exit_3(self):
        stub, status = self._push('failed')
        self.assertEqual(status, 'failed')
        self.assertEqual(natgeo_daily._push_exit_code(status), 3)
        self.assertEqual(len(stub.calls), 1)

    def test_missing_webhook_never_calls_cli(self):
        with patch.dict(natgeo_daily.os.environ, {'NATGEO_DINGTALK_WEBHOOK': ''}):
            stub = StubDingTalkPush()
            with patch.object(natgeo_daily, '_load_dingtalk_push', return_value=stub):
                status = natgeo_daily.push_to_dingtalk('正文')
        self.assertEqual(status, 'failed')
        self.assertEqual(stub.calls, [])

    def test_secret_mode_is_rejected_before_cli(self):
        """公共 CLI 不做加签；机器人是加签模式时必须显式失败，不能盲推。"""
        with patch.dict(natgeo_daily.os.environ, {'NATGEO_DINGTALK_SECRET': 'sec'}):
            stub = StubDingTalkPush()
            with patch.object(natgeo_daily, '_load_dingtalk_push', return_value=stub):
                status = natgeo_daily.push_to_dingtalk('正文')
        self.assertEqual(status, 'failed')
        self.assertEqual(stub.calls, [])

    def test_missing_cli_is_failure(self):
        with patch.object(natgeo_daily, '_load_dingtalk_push', side_effect=ImportError('not found')):
            status = natgeo_daily.push_to_dingtalk('正文')
        self.assertEqual(status, 'failed')


class ExitCodeTests(unittest.TestCase):
    """退出码语义：0 成功 / 3 被拒 / 5 结果未知。"""

    def test_mapping(self):
        self.assertEqual(natgeo_daily._push_exit_code('sent'), 0)
        self.assertEqual(natgeo_daily._push_exit_code('duplicate'), 0)
        self.assertEqual(natgeo_daily._push_exit_code('failed'), 3)
        self.assertEqual(natgeo_daily._push_exit_code('unknown'), 5)


if __name__ == '__main__':
    unittest.main()
