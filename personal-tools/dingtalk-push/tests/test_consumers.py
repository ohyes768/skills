"""消费方一致性锁:已迁移入口不得再内联钉钉 POST,同源 shim 副本保持一致,
公共 CLI 的 stdin 委托入口保持可用。路径缺失时跳过对应断言,不误报。"""
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
REPO = PACKAGE.parents[1]  # skills 仓库根

CSI300_SHIM_COPIES = [
    REPO / 'investment-analysis/csi300-brief/scripts/dingtalk_push.py',
    REPO.parent / 'stock-info-dingding/csi300_brief/dingtalk_push.py',
]
NO_INLINE_POST_FILES = [
    REPO / 'personal-tools/waytoagi-update-log/scripts/cron_runner.js',
    REPO.parent / 'daily-review/daily_review.py',
]
WAYTOAGI_SHIM = REPO / 'personal-tools/waytoagi-update-log/scripts/send_dingtalk.js'


class ConsumerTests(unittest.TestCase):
    def test_csi300_shim_copies_stay_identical(self):
        paths = [p for p in CSI300_SHIM_COPIES if p.is_file()]
        if len(paths) < 2:
            self.skipTest('less than two csi300 shim copies present')
        first = paths[0].read_bytes()
        for path in paths[1:]:
            self.assertEqual(path.read_bytes(), first, f'drifted copy: {path}')

    def test_migrated_consumers_never_post_inline(self):
        for path in NO_INLINE_POST_FILES:
            with self.subTest(path=str(path)):
                self.assertTrue(path.is_file(), f'missing migrated consumer: {path}')
                text = path.read_text(encoding='utf-8')
                self.assertNotIn('oapi.dingtalk.com', text, path)
                self.assertNotIn('robot/send', text, path)

    def test_waytoagi_shim_keeps_stdin_entry(self):
        self.assertTrue(WAYTOAGI_SHIM.is_file(), 'send_dingtalk.js missing')
        text = WAYTOAGI_SHIM.read_text(encoding='utf-8')
        self.assertIn('sendViaStdin', text)
        self.assertIn('never sends HTTP itself', text)


if __name__ == '__main__':
    unittest.main()
