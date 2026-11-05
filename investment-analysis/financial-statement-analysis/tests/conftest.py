import pytest


@pytest.fixture(autouse=True)
def no_structured_network(request, monkeypatch):
    """离线保证：除 mock HTTP 的单测文件外，fetch_structured 一律拒绝——默认
    compute 在测试中不得发起真实网络请求，只允许使用明确的离线夹具。"""
    if request.module.__name__ == "test_fetch_structured":
        return
    from fetch_structured import FetchStructuredError

    def _blocked(*args, **kwargs):
        raise FetchStructuredError("network disabled in tests")

    monkeypatch.setattr("fetch_structured.fetch_structured", _blocked)


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
            "source": "structured",
            "source_ref": {},
            "review_status": review_status,
            "missing_reason": None,
        }

    return _make
