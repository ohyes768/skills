from pathlib import Path
import subprocess
import sys
import unittest


SKILL_DIR = Path(__file__).parents[1]
RUN_ALL = SKILL_DIR / "scripts" / "run_all.py"


class CliOptionsTests(unittest.TestCase):
    def test_help_does_not_offer_upload(self):
        completed = subprocess.run(
            [sys.executable, str(RUN_ALL), "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        self.assertNotIn(b"--upload", completed.stdout)


if __name__ == "__main__":
    unittest.main()