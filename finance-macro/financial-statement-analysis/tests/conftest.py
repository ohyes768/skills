import pytest


@pytest.fixture()
def run_dir(tmp_path):
    d = tmp_path / "run"
    d.mkdir()
    return d


@pytest.fixture()
def make_fact():
    def _make(
        fact_id: str,
        metric: str,
        value: str | None,
        *,
        end: str = "2024-12-31",
        start: str | None = "2024-01-01",
        kind: str = "duration",
        scope: str = "consolidated",
        attribution: str = "group",
        aggregation: str = "cumulative",
        basis: str = "as_reported",
        frequency: str = "annual",
        evidence_ids: list[str] | None = None,
        review_status: str = "verified",
    ) -> dict:
        return {
            "fact_id": fact_id,
            "metric": metric,
            "raw_label": metric,
            "raw_value": value,
            "raw_unit": "元",
            "value": value,
            "unit": "元",
            "currency": "CNY",
            "scope": scope,
            "attribution": attribution,
            "period": {
                "kind": kind,
                "start": start,
                "end": end,
                "frequency": frequency,
                "aggregation": aggregation,
            },
            "basis": basis,
            "evidence_ids": evidence_ids or ["ev-0001"],
            "review_status": review_status,
            "missing_reason": None,
        }

    return _make
