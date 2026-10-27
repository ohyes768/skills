import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = (
    Path(__file__).resolve().parents[2] / "finance-macro/basic-quality-rating/scripts"
)
spec = importlib.util.spec_from_file_location(
    "retire_runbook", SCRIPTS / "retire_legacy_runbook.py"
)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


class RunbookMigrationTests(unittest.TestCase):
    def fixture(self, root):
        path = root / "quality-rating-pipeline-runbook"
        (path / "scripts").mkdir(parents=True)
        (path / "SKILL.md").write_text(
            "---\nname: quality-rating-pipeline-runbook\n---\n旧整数与反算规则",
            encoding="utf-8",
        )
        (path / "scripts/validate_rating_json.py").write_text(
            "raise RuntimeError('old validator')", encoding="utf-8"
        )
        return path

    def test_preview_is_read_only_and_apply_backs_up_then_forwards(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            root = Path(work)
            runbook = self.fixture(root)
            before = {
                p.relative_to(runbook): p.read_bytes()
                for p in runbook.rglob("*")
                if p.is_file()
            }
            result = migration.retire_runbook(runbook, SCRIPTS.parent)
            self.assertEqual(result["status"], "preview")
            self.assertEqual(
                before,
                {
                    p.relative_to(runbook): p.read_bytes()
                    for p in runbook.rglob("*")
                    if p.is_file()
                },
            )
            result = migration.retire_runbook(runbook, SCRIPTS.parent, apply=True)
            self.assertEqual(result["status"], "updated")
            self.assertEqual(
                (runbook / "SKILL.md.pre-unification.bak").read_bytes(),
                before[Path("SKILL.md")],
            )
            self.assertEqual(
                (
                    runbook / "scripts/validate_rating_json.py.pre-unification.bak"
                ).read_bytes(),
                before[Path("scripts/validate_rating_json.py")],
            )
            rating = root / "bad.json"
            rating.write_text("{}", encoding="utf-8")
            run = subprocess.run(
                [
                    sys.executable,
                    str(runbook / "scripts/validate_rating_json.py"),
                    str(rating),
                ],
                capture_output=True,
                check=False,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(run.returncode, 2, run.stderr)
            self.assertEqual(json.loads(run.stdout)["status"], "failed")
            self.assertEqual(
                migration.retire_runbook(runbook, SCRIPTS.parent, apply=True)["status"],
                "unchanged",
            )

    def test_refuses_wrong_target_and_preserves_existing_backups(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            runbook = self.fixture(Path(work))
            (runbook / "SKILL.md.pre-unification.bak").write_text(
                "different old backup", encoding="utf-8"
            )
            with self.assertRaises(ValueError):
                migration.retire_runbook(runbook, SCRIPTS.parent, apply=True)
            self.assertIn("旧整数", (runbook / "SKILL.md").read_text(encoding="utf-8"))
            (runbook / "SKILL.md").write_text("name: unrelated-skill", encoding="utf-8")
            with self.assertRaises(ValueError):
                migration.retire_runbook(runbook, SCRIPTS.parent, apply=True)

    def test_retargeting_owned_forwarder_preserves_original_backups(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as work:
            root = Path(work)
            runbook = self.fixture(root)
            migration.retire_runbook(runbook, SCRIPTS.parent, apply=True)
            backup = runbook / "scripts/validate_rating_json.py.pre-unification.bak"
            original = backup.read_bytes()
            new_skill = root / "moved-skill"
            shutil.copytree(SCRIPTS, new_skill / "scripts")
            result = migration.retire_runbook(runbook, new_skill, apply=True)
            self.assertEqual(result["status"], "updated")
            self.assertEqual(backup.read_bytes(), original)
            self.assertIn(
                repr(str(new_skill.resolve())),
                (runbook / "scripts/validate_rating_json.py").read_text(
                    encoding="utf-8"
                ),
            )


if __name__ == "__main__":
    unittest.main()
