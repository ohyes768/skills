import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
CANONICAL = PACKAGE / 'scripts/rss_relay_client.py'
spec = importlib.util.spec_from_file_location('public_client', CANONICAL)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class ClientTests(unittest.TestCase):
    def test_generated_shims_match_canonical(self):
        consumers = [ROOT / name / 'scripts/rss_relay_client.py' for name in (
            'bilibili-subtitle-rss', 'hk-ipo-research', 'finance-macro/a-share-macro-impact-skill',
            'finance-macro/bond-market-macro-impact-skill', 'waytoagi-update-log')]
        consumers += [ROOT.parent / name / 'rss_relay_client.py' for name in ('daily-review', 'stock-info-dingding')]
        for path in consumers:
            if path.exists():
                with self.subTest(path=path):
                    self.assertEqual(path.read_bytes(), CANONICAL.read_bytes())

    def test_locate_and_stdin_preserve_text_without_shell_interpolation(self):
        temp_root = ROOT / '.cache/rss-client-tests'
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as tmp:
            package = Path(tmp) / 'installed skill'
            (package / 'scripts').mkdir(parents=True)
            (package / 'scripts/rss_publish.py').write_text(
                "import json,sys\nsys.stdin.reconfigure(encoding='utf-8',newline='')\n"
                "print(json.dumps({'schema_version':1,'status':'published','id':'p1','content':sys.stdin.read(),'argv':sys.argv[1:]}))\n",
                encoding='utf-8')
            payload = {'title': '标题 $(literal)', 'content': '正文\r\n\r\n完整\r\n', 'channel': 'macro', 'source': 'test', 'url': ''}
            with patch.dict(os.environ, {'RSS_RELAY_SKILL_DIR': str(package)}):
                response = client.publish(payload, 'daily:2026-11-05')
            self.assertEqual(response['content'], payload['content'])
            self.assertIn(payload['title'], response['argv'])

    def test_configured_missing_package_never_falls_back(self):
        with patch.dict(os.environ, {'RSS_RELAY_SKILL_DIR': str(PACKAGE / 'does-not-exist')}):
            with self.assertRaisesRegex(ValueError, 'RSS_RELAY_SKILL_DIR'):
                client.locate_script()


if __name__ == '__main__':
    unittest.main()
