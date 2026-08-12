import json
import tempfile
import unittest
from pathlib import Path

from scripts import generate_macro_signals as signals


class GenerateMacroSignalsTests(unittest.TestCase):
    def test_generates_standard_signal_files_from_existing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_json(root / "monetary-policy-skill" / "data" / "2026-05" / "dr007.json", {"value": 1.6, "published_at": "2026-05-20"})
            self._write_json(root / "monetary-policy-skill" / "data" / "2026-05" / "lpr.json", {"lpr_1y": 3.0, "prev_lpr_1y": 3.1, "month": "2026-05"})
            self._write_json(root / "money-supply-skill" / "data" / "money_supply_latest.json", {
                "as_of_date": "2026-05-20",
                "m1_m2": {"latest": {"m2_yoy": 8.8, "m1_yoy": 5.8, "m1_m2_spread": -3.0}},
                "social_financing": {"monthly_new_yoy_pct": 5.0, "balance_yoy_pct": 8.2},
            })
            self._write_json(root / "entity-economy-skill" / "data" / "2026-05" / "electricity.json", {"month": "2026-05", "yoy_percent": 5.0})
            self._write_json(root / "entity-economy-skill" / "data" / "2026-05" / "railway_freight.json", {"month": "2026-05", "yoy_percent": 3.0})
            self._write_json(root / "inflation-skill" / "data" / "2026-05" / "inflation.json", {
                "month": "2026-05",
                "cpi": {"cpi_national_yoy": 1.0},
                "ppi": {"ppi_yoy": 0.5},
                "core_cpi": {"core_cpi_yoy": 1.1},
            })
            self._write_json(root / "exchange-rate-skill" / "exchange_rate_data.json", {
                "fetched_at": "2026-05-20T00:00:00Z",
                "data": {
                    "exchange_rates": {"dollar_index": {"value": 99.0, "date": "2026-05-20"}, "usd_cny": {"value": 7.1, "date": "2026-05-20"}},
                    "fund_flow": {"north_cumulative": {"turnover_7d_change_pct": 2.0}},
                    "ted_spread": {"ted_spread": 0.1},
                },
                "errors": [],
            })

            result = signals.generate_all(root)

            self.assertEqual(result["failed"], [])
            for name in signals.DIMENSIONS:
                payload = json.loads((root / signals.FOLDERS[name] / "macro_signal.json").read_text(encoding="utf-8"))
                self.assertEqual(payload["dimension"], name)
                self.assertIsInstance(payload["score"], (int, float))
                self.assertTrue(0 <= payload["score"] <= 100)
                self.assertTrue(payload["data_date"])

    def _write_json(self, path: Path, payload: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
