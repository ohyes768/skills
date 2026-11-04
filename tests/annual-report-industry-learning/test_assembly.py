import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'finance-macro/annual-report-industry-learning/scripts/assemble_report.py'
spec = importlib.util.spec_from_file_location('assembly', SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

class AssemblyTests(unittest.TestCase):
    def test_visible_count_includes_table_but_not_url(self):
        self.assertEqual(m.visible_text('## 摘要\n[风电](https://a.test/long)\n| 指标 | 值 |\n|---|---|\n| 容量 | 10GW |'), '摘要风电指标值容量10GW')

    def test_hard_limit_boundary_and_source_preservation(self):
        source = '## 第二部分：年报所选原文\n\n原文 **格式**\n| A | B |\n'
        doc, stats = m.assemble('标题', '字'*1800, source)
        self.assertEqual(stats['summary_characters'], 1800)
        self.assertTrue(doc.endswith(source))
        with self.assertRaises(ValueError):m.assemble('标题', '字'*1801, source)

    def test_budget_warning_is_not_failure(self):
        _, stats = m.assemble('标题','### 行业全貌\n很短','原文')
        self.assertTrue(any('行业全貌' in w for w in stats['warnings']))

    def test_empty_or_inline_page_marker_rejected(self):
        for source in ['', '【PDF 第 14 页】\n原文']:
            with self.assertRaises(ValueError):m.assemble('标题','摘要',source)
