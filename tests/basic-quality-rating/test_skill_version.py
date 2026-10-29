import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "finance-macro/basic-quality-rating"
sys.path.insert(0, str(ROOT / "scripts"))
import rating_math
from validate_rating_json import validate


class SkillVersionTests(unittest.TestCase):
    def draft(self):
        return {
            "code": "000001",
            "name": "样本",
            "dimensions": dict.fromkeys(rating_math.WEIGHTS, 3),
            "summary": "摘要",
            "risks": [],
            "watch_points": [],
            "report_md": "# 报告",
        }

    def test_finalize_stamps_own_metadata_version(self):
        result = rating_math.finalize(self.draft())
        self.assertEqual(result["skill_version"], "4.3.0")
        self.assertEqual(len(result), 11)
        self.assertEqual(validate(result)["status"], "passed")

    def test_validator_rejects_forged_or_missing_version(self):
        result = rating_math.finalize(self.draft())
        result["skill_version"] = "0.0.0"
        self.assertEqual(validate(result)["status"], "failed")
        result.pop("skill_version")
        self.assertEqual(validate(result)["status"], "failed")

    def test_finalize_rejects_a_foreign_skill_version(self):
        with self.assertRaisesRegex(ValueError, "skill_version"):
            rating_math.finalize(dict(self.draft(), skill_version="0.0.0"))


if __name__ == "__main__":
    unittest.main()
