import importlib
import json
import math
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 24, 12, 30, tzinfo=TZ)


def station(code="a", value="10", hour=12, lat="30.2741", lon="120.1551"):
    return {
        "Area": "杭州市",
        "CityCode": 330100,
        "StationCode": code,
        "PositionName": code,
        "PM2_5": value,
        "Latitude": lat,
        "Longitude": lon,
        "TimePointStr": f"2026年10月24日 {hour}时",
    }


def snapshot(values=None):
    times = [
        (datetime(2026, 10, 24, tzinfo=TZ) + timedelta(hours=i))
        .replace(tzinfo=None)
        .isoformat(timespec="minutes")
        for i in range(120)
    ]
    return {
        "fetched_at": NOW.isoformat(),
        "observations": [station()],
        "errors": {},
        "air": {
            "timezone": "Asia/Shanghai",
            "hourly_units": {"pm2_5": "μg/m³"},
            "hourly": {
                "time": times,
                "pm2_5": values if values is not None else [10] * 120,
            },
        },
        "weather": {
            "timezone": "Asia/Shanghai",
            "hourly_units": {
                "wind_speed_10m": "m/s",
                "wind_direction_10m": "°",
                "precipitation": "mm",
                "relative_humidity_2m": "%",
                "temperature_2m": "°C",
                "boundary_layer_height": "m",
            },
            "hourly": {
                "time": times,
                "wind_speed_10m": [1] * 120,
                "wind_direction_10m": [359, 1] * 60,
                "precipitation": [0] * 120,
                "relative_humidity_2m": [85] * 120,
                "temperature_2m": [20] * 120,
                "boundary_layer_height": [200] * 120,
            },
        },
    }


class PM25Tests(unittest.TestCase):
    def provider(self):
        self.assertTrue(
            (SCRIPTS / "providers.py").is_file(),
            "provider normalization is not implemented",
        )
        return importlib.import_module("providers")

    def report(self, data=None, **kwargs):
        self.assertTrue(
            (SCRIPTS / "report.py").is_file(), "report aggregation is not implemented"
        )
        return importlib.import_module("report").build_report(
            data or snapshot(), now=NOW, **kwargs
        )

    def test_zero_is_a_real_observation_and_invalid_values_are_absent(self):
        p = self.provider()
        for invalid in (None, "NA", "", "-1", math.nan, math.inf, True):
            self.assertIsNone(p.number(invalid))
        self.assertEqual(p.number("0"), 0)
        result = p.select_observations([station(value="0"), station("b", "NA")], NOW)
        self.assertEqual(result["mean_pm25"], 0)
        self.assertEqual(len(result["stations"]), 1)

    def test_only_latest_valid_hour_near_reference_point_is_averaged(self):
        rows = [
            station("old", "100", 11),
            station("new", "10"),
            station("new2", "20"),
            station("future", "200", 13),
            station("far", "300", lat="29.6"),
            dict(station("other", "999"), CityCode=310100, Area="上海市"),
        ]
        result = self.provider().select_observations(rows, NOW)
        self.assertEqual(result["mean_pm25"], 15)
        self.assertEqual({v["code"] for v in result["stations"]}, {"new", "new2"})

    def test_duplicate_station_does_not_skew_mean(self):
        rows = [station("a", "10"), station("a", "10"), station("b", "20")]
        self.assertEqual(
            self.provider().select_observations(rows, NOW)["mean_pm25"], 15
        )

    def test_stale_observations_are_not_current(self):
        data = snapshot()
        data["observations"] = [station(hour=8)]
        result = self.report(data)
        self.assertEqual(result["observations"]["status"], "stale")
        self.assertEqual(result["current"]["kind"], "model_estimate")
        self.assertEqual(result["status"], "partial")

    def test_current_observation_wins_over_model(self):
        data = snapshot([99] * 120)
        self.assertEqual(self.report(data)["current"]["pm25"], 10)
        self.assertEqual(self.report(data)["current"]["kind"], "observation")

    def test_model_does_not_pull_future_hour_for_current(self):
        data = snapshot()
        data["observations"] = []
        data["air"]["hourly"]["pm2_5"][12] = None
        data["air"]["hourly"]["pm2_5"][11] = 7
        data["air"]["hourly"]["pm2_5"][13] = 999
        self.assertEqual(self.report(data)["current"]["pm25"], 7)

    def test_calendar_days_missing_tail_and_zero(self):
        result = self.report(snapshot([0] * 117 + [None] * 3))
        self.assertEqual(len(result["daily"]), 5)
        last = result["daily"][-1]
        self.assertEqual(last["valid_hours"], 21)
        self.assertEqual(last["mean_pm25"], 0)
        self.assertFalse(last["complete"])
        self.assertEqual(last["date"], "2026-10-28")
        self.assertEqual(result["daily"][0]["remaining_hours"], 11)

    def test_all_missing_day_is_present_and_not_zero(self):
        result = self.report(snapshot([10] * 24 + [None] * 24 + [20] * 72))
        self.assertIsNone(result["daily"][1]["mean_pm25"])
        self.assertEqual(result["daily"][1]["valid_hours"], 0)

    def test_bad_units_or_duplicate_hours_reject_air_provider(self):
        for mutate in (
            lambda d: d["air"]["hourly_units"].update(pm2_5="AQI"),
            lambda d: d["air"]["hourly"]["time"].__setitem__(
                1, d["air"]["hourly"]["time"][0]
            ),
        ):
            data = snapshot()
            mutate(data)
            result = self.report(data)
            self.assertEqual(result["daily"][0]["valid_hours"], 0)
            self.assertEqual(result["current"]["kind"], "observation")
            self.assertTrue(result["warnings"])

    def test_inconsistent_arrays_reject_provider(self):
        data = snapshot()
        data["air"]["hourly"]["pm2_5"].pop()
        self.assertEqual(self.report(data)["daily"][0]["valid_hours"], 0)

    def test_wrong_timezone_is_not_silently_relabelled(self):
        data = snapshot()
        data["air"]["timezone"] = "UTC"
        self.assertEqual(self.report(data)["daily"][0]["valid_hours"], 0)

    def test_wind_direction_wraps_around_north(self):
        weather = self.report()["daily"][0]["weather"]
        self.assertLess(
            min(weather["wind_direction_deg"], 360 - weather["wind_direction_deg"]), 2
        )
        self.assertEqual(weather["humid_calm_hours"], 24)
        self.assertEqual(weather["low_mixing_calm_hours"], 24)

    def test_missing_weather_does_not_imply_dry_or_good_dispersion(self):
        data = snapshot()
        data["weather"] = None
        day = self.report(data)["daily"][0]
        self.assertIsNone(day["weather"]["precipitation_sum_mm"])
        self.assertEqual(day["weather"]["counts"]["precipitation"], 0)
        self.assertEqual(day["factors"], [])

    def test_weather_explanation_has_joint_hour_evidence(self):
        data = snapshot()
        data["weather"]["hourly"]["relative_humidity_2m"] = [90] * 12 + [30] * 108
        data["weather"]["hourly"]["wind_speed_10m"] = [4] * 12 + [1] * 108
        self.assertEqual(
            self.report(data)["daily"][0]["weather"]["humid_calm_hours"], 0
        )

    def test_total_failure_has_structured_unavailable_report(self):
        result = self.report(
            {
                "fetched_at": NOW.isoformat(),
                "air": None,
                "observations": None,
                "weather": None,
                "errors": {"air": "network unavailable"},
            }
        )
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["current"])
        self.assertEqual(len(result["daily"]), 5)
        json.dumps(result, allow_nan=False)

    def test_replay_at_next_day_does_not_show_old_day_as_forecast(self):
        self.assertTrue(
            (SCRIPTS / "report.py").is_file(), "report aggregation is not implemented"
        )
        result = importlib.import_module("report").build_report(
            snapshot(), now=NOW + timedelta(days=1)
        )
        self.assertEqual(result["daily"][0]["date"], "2026-10-25")
        self.assertEqual(result["daily"][-1]["date"], "2026-10-29")
        self.assertEqual(result["daily"][-1]["valid_hours"], 0)


if __name__ == "__main__":
    unittest.main()
