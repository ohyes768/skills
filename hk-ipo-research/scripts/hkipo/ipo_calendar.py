"""TradeSmart-backed current IPO calendar summary."""

from .tradesmart import fetch_tracker_margin_records


def fetch_calendar() -> dict:
    records = fetch_tracker_margin_records()
    return {"ipos": [{
        "code": item["symbol"],
        "name": item["name"],
        "total_margin": item["margin_total_hkd_yi"],
        "oversubscription_forecast": item["oversubscription_ratio"],
        "observed_at": item["observed_at"],
    } for item in records]}
