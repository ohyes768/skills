import importlib.util
from pathlib import Path
import sys
import unittest


BUILD_SCRIPT = Path(__file__).parents[1] / "scripts" / "build_macro_signal.py"


def load_module():
    sys.path.insert(0, str(BUILD_SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("build_macro_signal", BUILD_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class BuildMacroSignalTests(unittest.TestCase):
    def test_build_signal_only_includes_mlf_and_lpr_with_equal_weights(self):
        module = load_module()
        signal = module.build_signal({
            "mlf": {"value": 6000, "published_at": "2026-09-03"},
            "lpr": {
                "lpr_1y": 3.0,
                "prev_lpr_1y": 3.0,
                "lpr_5y_plus": 3.5,
                "prev_lpr_5y_plus": 3.5,
                "published_at": "2026-09-20",
            },
        }, data_date_override="2026-09-15")
        self.assertEqual({"lpr_1y": 3.0, "lpr_5y": 3.5, "mlf_net_yi": 6000.0}, signal["details"])
        self.assertEqual(70.0, signal["total_score"])
        self.assertEqual(
            {"MLF净投放": 0.5, "LPR": 0.5},
            {entry["label"]: entry["weight"] for entry in signal["score_detail"]["dimensions"]},
        )


if __name__ == "__main__":
    unittest.main()