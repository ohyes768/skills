import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RETIRED_SKILLS = {
    "macro-overview-skill",
    "bond-market-overview-skill",
    "risk-appetite-skill",
    "exchange-rate-skill",
}
RETAINED_MACRO_SKILLS = {
    "bond-market-macro-impact-skill",
    "a-share-macro-impact-skill",
    "monetary-policy-skill",
    "money-supply-skill",
    "entity-economy-skill",
    "inflation-skill",
}


class MacroSkillCatalogTest(unittest.TestCase):
    def test_registry_contains_only_retained_macro_skills(self):
        registry = json.loads((ROOT / "registry.json").read_text(encoding="utf-8"))
        macro_skills = {
            item["name"]
            for item in registry["skills"]
            if "finance-macro" in item.get("tags", [])
        }

        self.assertEqual(macro_skills, RETAINED_MACRO_SKILLS)
        self.assertTrue(RETIRED_SKILLS.isdisjoint(macro_skills))

    def test_retired_skill_directories_are_absent(self):
        for skill_name in RETIRED_SKILLS:
            directory = {
                "macro-overview-skill": "a-share-macro-skill",
                "bond-market-overview-skill": "bond-market-overview-skill",
                "risk-appetite-skill": "risk-appetite-skill",
                "exchange-rate-skill": "exchange-rate-skill",
            }[skill_name]
            self.assertFalse((ROOT / "finance-macro" / directory).exists())


if __name__ == "__main__":
    unittest.main()
