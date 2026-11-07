"""Rate expectations: source dates, probability validation and cache fallbacks."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json

import pytest
import requests

from gold.fed_expectations import normalize_record, build_report
from gold.fed_cache import get_fed_expectations

NOW = datetime(2026, 9, 29, 16, tzinfo=timezone(timedelta(hours=8)))


def record(day="2026-09-29", hold=29.1, hike=70.9, meeting="2026-10-28"):
    return {"category": "interestRateForecast", "time": day + " 06:00:00", "data": {
        "json": {"resData": [{"date": meeting, "target_rate": "375-400", "data": [
            {"name": "date", "value": [day, "2026-09-25"]},
            {"name": "350-375", "value": ["0.0%", "0.0%"]},
            {"name": "375-400 (Current)", "value": [f"{hold}%", "35.8%"]},
            {"name": "400-425", "value": [f"{hike}%", "64.2%"]},
        ]}]}}}


def test_normalizes_probabilities_and_weighted_midpoint():
    snap = normalize_record(record(), now=NOW)
    m = snap["meetings"][0]
    assert snap["published_at"] == "2026-09-29T06:00:00+08:00"
    assert m["meeting_date"] == "2026-10-28"
    assert (m["cut_pct"], m["hold_pct"], m["hike_pct"]) == (0, 29.1, 70.9)
    assert m["expected_rate_pct"] == pytest.approx(4.05225)


def test_compares_same_meeting_against_previous_publication_day():
    report = build_report([record(), record("2026-09-28", 35.2, 64.8)], now=NOW)
    m = report["meetings"][0]
    assert m["change"]["hike_pp"] == pytest.approx(6.1)
    assert m["change"]["expected_rate_bps"] == pytest.approx(1.525)
    assert m["change"]["baseline_published_at"].startswith("2026-09-28")
    assert m["direction"] == "hawkish"


def test_does_not_compare_two_updates_on_same_day():
    morning = record()
    afternoon = record(hold=25, hike=75)
    afternoon["time"] = "2026-09-29 15:00:00"
    result = build_report([morning, afternoon], now=NOW)
    assert result["meetings"][0]["change"] is None


def test_meeting_rollover_and_rate_regime_do_not_create_fake_changes():
    prior = record("2026-09-28", meeting="2026-09-30")
    assert build_report([record(), prior], now=NOW)["meetings"][0]["change"] is None
    prior = record("2026-09-28")
    prior["data"]["json"]["resData"][0]["target_rate"] = "350-375"
    prior["data"]["json"]["resData"][0]["data"][2]["name"] = "375-400"
    assert build_report([record(), prior], now=NOW)["meetings"][0]["change"] is None


def test_later_meeting_is_compared_by_identity_not_position():
    latest = record()
    later = deepcopy(latest["data"]["json"]["resData"][0])
    later["date"] = "2026-12-09"
    latest["data"]["json"]["resData"].append(later)
    earlier = record("2026-09-28", 35.2, 64.8, meeting="2026-12-09")
    ms = build_report([latest, earlier], now=NOW)["meetings"]
    assert ms[0]["change"] is None
    assert ms[1]["change"]["hike_pp"] == pytest.approx(6.1)


@pytest.mark.parametrize("value", ["NaN%", "inf%", "-1%", "101%", "", None, "no data"])
def test_rejects_invalid_probability(value):
    raw = record()
    raw["data"]["json"]["resData"][0]["data"][1]["value"][0] = value
    with pytest.raises(ValueError):
        normalize_record(raw, now=NOW)


def test_rejects_bad_total_future_date_and_duplicate_ranges():
    for raw in [record(hold=5, hike=5), record("2026-09-30")]:
        with pytest.raises(ValueError):
            normalize_record(raw, now=NOW)
    raw = record()
    rows = raw["data"]["json"]["resData"][0]["data"]
    rows.append(deepcopy(rows[1]))
    with pytest.raises(ValueError):
        normalize_record(raw, now=NOW)


def test_stale_and_meeting_day_snapshots_have_no_direction():
    r = build_report([record("2026-09-20")], now=NOW)
    assert r["status"] == "stale"
    assert r["meetings"][0]["direction"] == "unknown"
    r = build_report([record(meeting="2026-09-29")], now=NOW)
    assert r["status"] == "awaiting_update"
    assert r["meetings"] == []


class Response:
    def __init__(self, records):
        self.records = records

    def raise_for_status(self):
        pass

    def json(self):
        return {"status": 200, "data": self.records}


def test_cache_repeated_fetches_do_not_reset_comparison(tmp_path):
    cache = tmp_path / "fed.json"
    calls = []
    def fetch(*args, **kwargs):
        calls.append(kwargs)
        return Response([record(), record("2026-09-28", 35.2, 64.8)])
    first = get_fed_expectations(cache_path=cache, now=NOW, request_get=fetch)
    second = get_fed_expectations(cache_path=cache, now=NOW + timedelta(minutes=10), request_get=fetch)
    assert len(calls) == 1
    assert calls[0]["timeout"] == (5, 15)
    assert first["is_new_snapshot"] is True
    assert second["is_new_snapshot"] is False
    assert second["status"] == "cached"
    assert second["meetings"][0]["change"] == first["meetings"][0]["change"]
    assert len(json.loads(cache.read_text(encoding="utf8"))["records"]) == 2


def test_timeout_uses_cache_and_disables_direction(tmp_path):
    cache = tmp_path / "fed.json"
    get_fed_expectations(cache_path=cache, now=NOW, request_get=lambda *a, **kw: Response([record(), record("2026-09-28", 35.2, 64.8)]))
    def fail(*args, **kwargs):
        raise requests.Timeout("timeout")
    r = get_fed_expectations(cache_path=cache, now=NOW + timedelta(hours=2), request_get=fail)
    assert r["status"] == "fallback"
    assert r["published_at"].startswith("2026-09-29T06:")
    assert r["meetings"][0]["direction"] == "unknown"
    r = get_fed_expectations(cache_path=cache, now=NOW + timedelta(days=6), request_get=fail)
    assert r["status"] == "stale"


@pytest.mark.parametrize("content", ["{broken", "null", '{"version": 1, "records": "bad"}'])
def test_bad_cache_and_network_failure_degrade_to_unavailable(tmp_path, content):
    cache = tmp_path / "fed.json"
    cache.write_text(content, encoding="utf8")
    def fail(*args, **kwargs):
        raise requests.ConnectionError("offline")
    r = get_fed_expectations(cache_path=cache, now=NOW, request_get=fail)
    assert r["status"] == "unavailable"
    assert r["meetings"] == []


def test_invalid_network_data_does_not_overwrite_good_cache(tmp_path):
    cache = tmp_path / "fed.json"
    get_fed_expectations(cache_path=cache, now=NOW, request_get=lambda *a, **kw: Response([record()]))
    before = cache.read_text(encoding="utf8")
    r = get_fed_expectations(cache_path=cache, now=NOW + timedelta(hours=2), request_get=lambda *a, **kw: Response([record(hold=1, hike=2)]))
    assert r["status"] == "fallback"
    assert cache.read_text(encoding="utf8") == before


def test_cache_write_failure_does_not_discard_live_data(tmp_path):
    parent = tmp_path / "not_a_directory"
    parent.write_text("file", encoding="utf8")
    r = get_fed_expectations(cache_path=parent / "fed.json", now=NOW, request_get=lambda *a, **kw: Response([record()]))
    assert r["status"] == "fresh"
    assert "缓存写入失败" in r["warnings"]
