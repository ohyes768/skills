"""国内黄金日线口径及独立手算RSI回归。"""
from datetime import date, timedelta

import pytest

from gold.rsi_calculator import calculate_rsi, calculate_simple_rsi


def candles(count=21):
    days = []
    day = date(2026, 9, 1)
    while len(days) < count:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return [{"D": str(day), "C": 100 + i, "H": 102 + i, "L": 98 + i}
            for i, day in enumerate(days)]


def summary(rows, quote=121, today="2026-09-30"):
    from gold.technicals import build_price_summary
    return build_price_summary(rows, quote, today=today)


def test_price_windows_and_comparison_dates():
    result = summary(candles()[::-1])
    assert result["ma5"] == 118
    assert result["ma20"] == 110.5
    assert result["five_day_change_pct"] == pytest.approx((120 / 115 - 1) * 100)
    assert result["quote_change_pct"] == pytest.approx((121 / 120 - 1) * 100)
    assert result["day_change_pct"] == pytest.approx((120 / 119 - 1) * 100)
    assert result["last_close_date"] == "2026-09-29"
    assert result["range_low"] == 99
    assert result["range_high"] == 122
    assert result["range_kind"] == "高低区间"


def test_invalid_duplicate_conflicting_and_current_rows():
    rows = candles(6)
    rows += [dict(rows[0]), {**rows[1], "C": 999},
             {"D": "2026-09-10", "C": float("nan")},
             {"D": "2026-09-30", "C": 999}, {"D": "bad", "C": 100}]
    result = summary(rows)
    assert result["sample_count"] == 5
    assert result["five_day_change_pct"] is None
    assert result["ma20"] is None
    assert result["warnings"]


def test_missing_high_low_uses_close_range_and_stale_label():
    rows = [{"D": r["D"], "C": r["C"]} for r in candles()]
    result = summary(rows, today="2026-10-14")
    assert result["status"] == "stale"
    assert result["range_kind"] == "收盘区间"
    assert result["range_low"] == 101
    assert result["range_high"] == 120
    assert summary([])["status"] == "unavailable"


def test_wilder_seed_does_not_double_count_next_change():
    # 前14次变化：7次+1，7次-1；随后+2。均值更新后up=8.5/14，down=6.5/14。
    prices = [100]
    for delta in [1, -1] * 7 + [2]:
        prices.append(prices[-1] + delta)
    assert calculate_rsi(prices) == 56.67


@pytest.mark.parametrize("prices, expected", [
    (list(range(100, 115)), 100), (list(range(115, 100, -1)), 0),
    ([100] * 15, 50), ([100] * 14, None),
])
def test_rsi_boundaries(prices, expected):
    assert calculate_rsi(prices) == expected
    assert calculate_simple_rsi(prices) == expected


def test_holdings_compare_valid_records_across_gaps():
    from gold.technicals import build_holdings_summary
    result = build_holdings_summary([
        {"Date": "2026-09-25", "gold_tonnes": 1000},
        {"Date": "2026-09-28", "gold_tonnes": None},
        {"Date": "2026-09-29", "gold_tonnes": 998},
        {"Date": "2026-09-30", "gold_tonnes": 999},
    ], today="2026-09-30")
    assert result["baseline_date"] == "2026-09-25"
    assert result["date"] == "2026-09-29"
    assert result["change_tonnes"] == -2


def test_nonfinite_quote_does_not_produce_percentage():
    assert summary(candles(), quote=float("inf"))["quote_change_pct"] is None
