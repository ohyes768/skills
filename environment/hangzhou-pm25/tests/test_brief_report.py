import importlib
import re
import unittest

from test_pm25 import NOW, snapshot


class BriefReportTests(unittest.TestCase):
    def render(self, data):
        module = importlib.import_module("report")
        report = module.build_report(data, now=NOW)
        text = module.render_markdown(report)
        visible = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        self.assertLessEqual(len(re.sub(r"[\s#*|\-]", "", visible)), 300)
        return text

    def test_brief_report_keeps_current_and_five_dates_without_technical_dump(self):
        text = self.render(snapshot())
        self.assertIn("10", text)
        self.assertIn("12:00", text)
        self.assertIn("实测", text)
        self.assertIn("非官方全市均值", text)
        self.assertIn("μg/m³", text)
        self.assertIn("今天剩余", text)
        for day in ("10/25", "10/26", "10/27", "10/28"):
            self.assertIn(day, text)
        for detail in ("站点明细", "边界层", "生成时间", "风速低于", "使用边界"):
            self.assertNotIn(detail, text)

    def test_incomplete_forecast_is_marked_and_model_fallback_is_explicit(self):
        data = snapshot([20] * 117 + [None] * 3)
        data["observations"] = []
        text = self.render(data)
        self.assertIn("模型估计，非实测", text)
        self.assertIn("不完整", text)
        self.assertRegex(text, r"10/28.*\*")

    def test_outage_is_short_and_does_not_dump_network_exception(self):
        text = self.render({"errors": {"air": "URLError stack and internal detail"}})
        self.assertIn("暂无", text)
        self.assertNotIn("URLError", text)

    def test_few_hour_forecast_is_not_presented_as_daily_mean(self):
        data = snapshot([10] * 24 + [500] * 2 + [None] * 22 + [10] * 72)
        text = self.render(data)
        self.assertRegex(text, r"10/25.*不足")

    def test_old_replay_remains_identifiable(self):
        data = snapshot()
        data["fetched_at"] = "2026-10-23T12:00:00+08:00"
        self.assertIn("旧数据", self.render(data))


if __name__ == "__main__":
    unittest.main()
