import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "finance-macro/basic-quality-rating"
sys.path.insert(0, str(ROOT / "scripts"))
import rating_math
from validate_rating_json import validate


class NoStarsTests(unittest.TestCase):
    def draft(self):
        return {
            "code": "000001",
            "name": "样本",
            "dimensions": dict.fromkeys(rating_math.WEIGHTS, 3),
            "summary": "业务模式清晰，存在周期风险",
            "risks": ["原料价格波动"],
            "watch_points": ["关注盈利变化"],
            "report_md": "# 基本面评级：样本\n\n## 业务核实\n主营业务已核实。\n## 五维评分表\n业务模式、护城河、行业前景、管理层、财务质量\n## 结论与风险\n周期风险。\n## 证据来源\n[年报](https://example.com/annual)",
        }

    def test_starless_report_preserves_compatibility_fields(self):
        result = rating_math.finalize(self.draft())
        self.assertEqual(result["stars"], 3)
        self.assertEqual(result["weighted_score"], 3)
        self.assertEqual(result["skill_version"], "4.4.0")
        checked = validate(result)
        self.assertEqual(checked["status"], "passed")
        self.assertFalse(any("边界" in warning for warning in checked["warnings"]))

    def test_finalize_rejects_aggregate_rating_prose(self):
        for field, value in [
            ("summary", "综合评级为3星"),
            ("summary", "综合评级：三星，经营稳定"),
            ("report_md", "## 星级与边界\n非边界档位"),
            ("report_md", "⭐⭐⭐ (3/5)"),
            ("risks", ["任一维度降1分即降至2星"]),
            ("watch_points", ["踩线 3 星，单维升1分不足以升星"]),
        ]:
            with self.subTest(field=field, value=value):
                draft = self.draft()
                draft[field] = value
                with self.assertRaisesRegex(ValueError, "星级|踩线"):
                    rating_math.finalize(draft)

    def test_readonly_validator_rejects_star_prose_without_mutation(self):
        result = rating_math.finalize(self.draft())
        result["report_md"] += "\n评级结果：3星"
        original = result["report_md"]
        self.assertEqual(validate(result)["status"], "failed")
        self.assertEqual(result["report_md"], original)

    def test_real_business_stars_and_risk_boundaries_are_allowed(self):
        draft = self.draft()
        draft["report_md"] += (
            "\n主营五星酒店及3星级酒店，综合采购三星电子产品，明确业务风险边界。"
        )
        self.assertEqual(validate(rating_math.finalize(draft))["status"], "passed")


if __name__ == "__main__":
    unittest.main()
