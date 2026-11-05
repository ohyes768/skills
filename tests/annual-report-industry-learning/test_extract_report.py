import importlib.util
import io
from unittest.mock import patch
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / 'investment-analysis/annual-report-industry-learning/scripts/extract_report.py'
spec = importlib.util.spec_from_file_location('extract_report', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExtractionTests(unittest.TestCase):
    def test_boundaries_and_children(self):
        pages = [{'page': 1, 'text': '第三节 管理层讨论与分析......15'},
                 {'page': 15, 'text': '第三节 管理层讨论与分析\n一、报告期内公司所处行业情况\n行业原文\n二、报告期内公司从事的主要业务\n（一）主要业务\n产品原文\n三、核心竞争力分析\n优势原文'},
                 {'page': 16, 'text': '四、公司未来发展的展望\n趋势原文\n（一）风险因素\n风险原文\n第五节之外不是边界\n第四节 公司治理\n不应出现'}]
        candidates, warnings = module.locate(pages)
        self.assertEqual(candidates[0]['start_page'], 15)
        business = next(c for c in candidates if 'business' in c['topics'])
        self.assertIn('产品原文', [l['text'] for l in business['lines']])
        self.assertNotIn('优势原文', [l['text'] for l in business['lines']])
        self.assertNotIn('不应出现', str(candidates))
        self.assertEqual(warnings, [])
        self.assertEqual(sum('business' in c['topics'] for c in candidates), 1)

    def test_numeric_risk_children_are_preserved(self):
        for prefix in ['6、', '（六）', '六、']:
            text = ('第三节 管理层讨论与分析\n一、公司未来发展的展望\n'
                    + prefix + '可能面临的风险\n（1）政策风险\n风险甲\n（2）汇率风险\n风险乙\n二、其他情况\n不能收录\n第四节 公司治理')
            candidates, _ = module.locate([{'page': 1, 'text': text}])
            risk = next(c for c in candidates if 'risks' in c['topics'])
            self.assertIn('风险乙', [l['text'] for l in risk['lines']])
            self.assertNotIn('不能收录', str(risk))

    def test_tables_only_visit_candidate_pages(self):
        import types
        from unittest.mock import MagicMock
        fake_pages = [MagicMock(), MagicMock(), MagicMock()]
        texts = ['封面', '第三节 管理层讨论与分析\n一、主要业务\n业务原文', '第四节 公司治理']
        for page, text in zip(fake_pages, texts):
            page.extract_text.return_value = text
            page.extract_tables.return_value = []
        pdf = MagicMock(); pdf.__enter__.return_value.pages = fake_pages
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); pdf_path = root/'source.pdf'; pdf_path.write_bytes(b'%PDF-1.4')
            with patch.dict('sys.modules', {'pdfplumber': types.SimpleNamespace(open=lambda _: pdf)}):
                result = module.extract(pdf_path, root)
            self.assertEqual(result['table_pages'], [2])
            fake_pages[0].extract_tables.assert_not_called()
            fake_pages[1].extract_tables.assert_called_once()
            fake_pages[2].extract_tables.assert_not_called()

    def test_absent_chapter_is_not_success(self):
        candidates, warnings = module.locate([{'page': 1, 'text': '年度报告摘要'}])
        self.assertFalse(candidates)
        self.assertTrue(warnings)

    def test_missing_section_warns(self):
        _, warnings = module.locate([{'page': 1, 'text': '第三节 管理层讨论与分析\n一、核心竞争力分析\n内容\n第四节 公司治理'}])
        self.assertTrue(any('industry' in warning for warning in warnings))

    def test_invalid_download_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'input.html', Path(folder)/'source.pdf'
            source.write_bytes(b'<html>error</html>')
            target.write_bytes(b'previous')
            with self.assertRaises(ValueError):
                module.obtain_pdf(str(source), target)
            self.assertEqual(target.read_bytes(), b'previous')
            self.assertEqual(len(list(Path(folder).iterdir())), 2)

    def test_http_download(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'source.pdf'
            with patch.object(module, 'urlopen', return_value=io.BytesIO(b'%PDF-1.4\nremote')):
                module.obtain_pdf('https://example.test/report.pdf', target)
            self.assertEqual(target.read_bytes(), b'%PDF-1.4\nremote')

    def test_http_html_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'source.pdf'
            with patch.object(module, 'urlopen', return_value=io.BytesIO(b'<html>blocked</html>')):
                with self.assertRaises(ValueError):
                    module.obtain_pdf('https://example.test/report.pdf', target)
            self.assertFalse(target.exists())

    def test_local_pdf_copy(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'input.pdf', Path(folder)/'source.pdf'
            source.write_bytes(b'%PDF-1.4\nfixture')
            module.obtain_pdf(str(source), target)
            self.assertEqual(source.read_bytes(), target.read_bytes())


if __name__ == '__main__':
    unittest.main()
