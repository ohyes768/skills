import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_pm25 import NOW, SCRIPTS, snapshot


class CLITests(unittest.TestCase):
    def invoke(self, *args):
        self.assertTrue(
            (SCRIPTS / "hangzhou_pm25.py").is_file(), "CLI is not implemented"
        )
        return subprocess.run(
            [sys.executable, str(SCRIPTS / "hangzhou_pm25.py"), *map(str, args)],
            text=True,
            capture_output=True,
            encoding="utf-8",
            timeout=10,
            check=False,
        )

    def test_offline_json_and_output_files(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            root = Path(temp)
            source = root / "snapshot.json"
            source.write_text(json.dumps(snapshot()), encoding="utf-8")
            output = root / "result"
            result = self.invoke(
                "--input",
                source,
                "--now",
                NOW.isoformat(),
                "--format",
                "json",
                "--output-dir",
                output,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["current"]["kind"], "observation")
            self.assertEqual(
                json.loads((output / "report.json").read_text(encoding="utf-8")), data
            )
            markdown = (output / "report.md").read_text(encoding="utf-8")
            self.assertIn("非官方全市均值", markdown)
            self.assertIn("μg/m³", markdown)
            self.assertIn("包含已经过去", markdown)

    def test_all_network_data_absent_emits_unavailable_json_and_nonzero(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            source = Path(temp) / "snapshot.json"
            source.write_text(
                json.dumps({"errors": {"air": "timeout"}}), encoding="utf-8"
            )
            result = self.invoke(
                "--input", source, "--now", NOW.isoformat(), "--format", "json"
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["status"], "unavailable")

    def test_naive_or_live_now_override_is_rejected(self):
        for args in (
            ("--now", NOW.isoformat()),
            ("--input", "unused.json", "--now", "2026-10-24T12:30"),
        ):
            result = self.invoke(*args)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)

    def test_malformed_input_fails_cleanly(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            source = Path(temp) / "snapshot.json"
            source.write_text("[]", encoding="utf-8")
            result = self.invoke("--input", source)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)

    def test_earlier_snapshot_is_replayed_as_old_not_refreshed(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            source = Path(temp) / "snapshot.json"
            source.write_text(json.dumps(snapshot()), encoding="utf-8")
            result = self.invoke(
                "--input",
                source,
                "--now",
                "2026-10-27T12:30:00+08:00",
                "--format",
                "json",
            )
            data = json.loads(result.stdout)
            self.assertEqual(data["input_fetched_at"], NOW.isoformat())
            self.assertEqual(data["current"]["kind"], "model_estimate")
            self.assertTrue(any("旧批次" in warning for warning in data["warnings"]))


if __name__ == "__main__":
    unittest.main()
