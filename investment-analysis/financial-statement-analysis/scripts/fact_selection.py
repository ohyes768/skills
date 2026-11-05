"""统一绑定报告期间、报表范围与事实可用性，禁止历史值静默回退。"""

from calendar import monthrange
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation


def period_key(period: dict) -> tuple:
    return (period.get("start"), period.get("end"),
            period.get("frequency"), period.get("aggregation"))


def prior_year(value: str) -> str:
    current = date.fromisoformat(value)
    year = current.year - 1
    return current.replace(year=year, day=min(current.day, monthrange(year, current.month)[1])).isoformat()


def pick_usable(candidates: list[dict]) -> tuple[dict | None, str | None, str | None]:
    if not candidates:
        return None, "insufficient_data", "fact not available for scope/period/aggregation"
    if any(f.get("review_status") == "conflict" for f in candidates):
        return None, "conflict", "source fact has unresolved conflict"
    if any(f.get("review_status") != "verified" or f.get("value") is None for f in candidates):
        return None, "insufficient_data", "source fact missing or requires verification"
    try:
        values = [Decimal(f["value"]) for f in candidates]
    except (InvalidOperation, TypeError, ValueError):
        return None, "conflict", "source fact is not a finite decimal"
    if not all(value.is_finite() for value in values):
        return None, "conflict", "source fact is not a finite decimal"
    dimensions = {(f.get("currency"), f.get("unit"), f.get("basis")) for f in candidates}
    if len(set(values)) > 1 or len(dimensions) > 1:
        return None, "conflict", "multiple conflicting values or measurement dimensions"
    return min(candidates, key=lambda f: f["fact_id"]), None, None


class FactSelection:
    def __init__(self, document: dict):
        self.facts = document.get("facts", [])
        self.by_id = {f["fact_id"]: f for f in self.facts}
        self.period = document.get("period")
        if not self.period:
            durations = [f["period"] for f in self.facts
                         if f.get("scope") == "consolidated" and f["period"]["kind"] == "duration"]
            if durations:
                latest = max(p["end"] for p in durations)
                current = [p for p in durations if p["end"] == latest]
                self.period = min(current, key=lambda p: (
                    p.get("aggregation") != "cumulative", p.get("start") or ""
                ))

    def flows(self, metric: str, *, scope="consolidated", attribution="group",
              aggregation="cumulative", prior=False) -> list[dict]:
        if not self.period:
            return []
        target = dict(self.period)
        if prior:
            target.update(start=prior_year(target["start"]), end=prior_year(target["end"]))
        return [f for f in self.facts
                if f["metric"] == metric and f["scope"] == scope
                and f["attribution"] == attribution and f["period"]["kind"] == "duration"
                and f["period"]["aggregation"] == aggregation
                and period_key(f["period"]) == period_key(target)]

    def balance(self, metric: str, *, opening=False):
        if not self.period:
            return None, "insufficient_data", f"average {metric} needs a report period"
        day = ((date.fromisoformat(self.period["start"]) - timedelta(days=1)).isoformat()
               if opening else self.period["end"])
        candidates = [f for f in self.facts
                      if f["metric"] == metric and f["scope"] == "consolidated"
                      and f["attribution"] in ("group", "not_applicable")
                      and f["period"]["kind"] == "instant" and f["period"]["end"] == day]
        return pick_usable(candidates)

    def measurement_error(self, fact_ids: list[str]) -> str | None:
        facts = [self.by_id[fid] for fid in fact_ids]
        for key in ("currency", "unit", "basis"):
            values = {f.get(key) for f in facts}
            if len(values) != 1 or None in values:
                return f"input {key} mismatch"
        return None
