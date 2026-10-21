"""fetch_structured：东财 F10 多期三表拉取、增量缓存与失败路径（离线 mock）。"""

import json

import fetch_structured
import httpx
import pytest

DATES = "2026-06-30,2025-06-30,2025-12-31"


def make_client(handler, counter=None) -> httpx.Client:
    def counting(request: httpx.Request) -> httpx.Response:
        if counter is not None:
            counter.append((request.url.params.get("reportName"),
                            str(request.url.params.get("filter"))))
        return handler(request)

    return httpx.Client(transport=httpx.MockTransport(counting), headers=fetch_structured._HEADERS)


def report_payload(**fields) -> bytes:
    return json.dumps({"version": "v", "result": {"pages": 1, "data": [dict(fields)]}},
                      ensure_ascii=False).encode("utf-8")


def ok_handler(request: httpx.Request) -> httpx.Response:
    by_name = {
        "RPT_F10_FINANCE_GBALANCE": {"TOTAL_ASSETS": 1366525227.25, "MONETARYFUNDS": 123625294.67},
        "RPT_F10_FINANCE_GINCOME": {"TOTAL_OPERATE_INCOME": 230730296.15,
                                     "PARENT_NETPROFIT": -77252801.33},
        "RPT_F10_FINANCE_GCASHFLOW": {"NETCASH_OPERATE": -57969741.72, "END_CCE": 105663595.93},
    }
    name = request.url.params.get("reportName")
    return httpx.Response(200, content=report_payload(**by_name[name]),
                          headers={"content-type": "application/json"})


def test_fetch_writes_archive_for_all_dates_and_reports(run_dir):
    counter: list[tuple] = []
    doc = fetch_structured.fetch_structured(
        "301313", DATES.split(","), run_dir, client=make_client(ok_handler, counter))
    assert doc["reused"] is False
    assert doc["source"] == "structured_eastmoney"
    assert doc["secucode"] == "301313.SZ"
    assert sorted(doc["reports"]) == ["2025-06-30", "2025-12-31", "2026-06-30"]
    for date in doc["reports"]:
        assert sorted(doc["reports"][date]) == ["balance", "cashflow", "income"]
    from decimal import Decimal

    assert (doc["reports"]["2026-06-30"]["income"][0]["TOTAL_OPERATE_INCOME"]
            == Decimal("230730296.15")), "values must survive as exact decimals"
    assert len(counter) == 9
    assert set(doc["response_sha256"]) == {f"{d}/{k}" for d in doc["reports"]
                                            for k in ("balance", "cashflow", "income")}
    stored = json.loads((run_dir / "structured_financials.json").read_text(encoding="utf-8"))
    assert (stored["reports"]["2025-12-31"]["balance"][0]["MONETARYFUNDS"]
            == "123625294.67"), "archived decimals are serialized as exact strings"


def test_cache_reused_without_new_requests(run_dir):
    counter: list[tuple] = []
    fetch_structured.fetch_structured("301313", DATES.split(","), run_dir,
                                      client=make_client(ok_handler, counter))
    calls_after_first = len(counter)
    doc = fetch_structured.fetch_structured("301313", DATES.split(","), run_dir,
                                            client=make_client(ok_handler, counter))
    assert doc["reused"] is True
    assert len(counter) == calls_after_first


def test_incremental_fetch_only_missing_dates(run_dir):
    counter: list[tuple] = []
    fetch_structured.fetch_structured("301313", ["2026-06-30"], run_dir,
                                      client=make_client(ok_handler, counter))
    calls_after_first = len(counter)
    doc = fetch_structured.fetch_structured("301313", ["2026-06-30", "2025-06-30"], run_dir,
                                            client=make_client(ok_handler, counter))
    assert doc["reused"] is False
    assert len(counter) - calls_after_first == 3, "only the new date's three reports are fetched"
    assert sorted(doc["reports"]) == ["2025-06-30", "2026-06-30"]


def test_refresh_forces_refetch(run_dir):
    counter: list[tuple] = []
    fetch_structured.fetch_structured("301313", DATES.split(","), run_dir,
                                      client=make_client(ok_handler, counter))
    calls_after_first = len(counter)
    doc = fetch_structured.fetch_structured("301313", DATES.split(","), run_dir,
                                            client=make_client(ok_handler, counter),
                                            refresh=True)
    assert doc["reused"] is False
    assert len(counter) == calls_after_first + 9


def test_transient_error_retried(run_dir):
    attempts = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("reportName") == "RPT_F10_FINANCE_GINCOME":
            attempts["n"] += 1
            if attempts["n"] < 2:
                return httpx.Response(502)
        return ok_handler(request)

    doc = fetch_structured.fetch_structured("301313", DATES.split(","), run_dir,
                                            client=make_client(flaky), sleep=lambda s: None)
    assert doc["reused"] is False
    assert attempts["n"] == 4, "first date retries once (2), later dates succeed once each"


def test_persistent_failure_raises(run_dir):
    def always_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(fetch_structured.FetchStructuredError):
        fetch_structured.fetch_structured("301313", DATES.split(","), run_dir,
                                          client=make_client(always_500), sleep=lambda s: None)
    assert not (run_dir / "structured_financials.json").exists()


@pytest.mark.parametrize("payload", [
    b"not json",
    json.dumps({"result": None}).encode(),
    json.dumps({"result": {"data": []}}).encode(),
])
def test_bad_responses_rejected(run_dir, payload):
    def bad(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    with pytest.raises(fetch_structured.FetchStructuredError):
        fetch_structured.fetch_structured("301313", DATES.split(","), run_dir,
                                          client=make_client(bad), sleep=lambda s: None)


def test_invalid_code_rejected(run_dir):
    with pytest.raises(fetch_structured.FetchStructuredError):
        fetch_structured.fetch_structured("abc", DATES.split(","), run_dir,
                                          client=make_client(ok_handler))


def test_cli_exit_codes(run_dir, capsys, monkeypatch):
    monkeypatch.setattr(fetch_structured, "_cli_client", make_client(ok_handler))
    assert fetch_structured.main(["--code", "301313", "--dates", DATES,
                                  "--run-dir", str(run_dir)]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["status"] == "ok"

    monkeypatch.setattr(fetch_structured, "_cli_client",
                        make_client(lambda r: httpx.Response(404)))
    with pytest.raises(SystemExit) as exc:
        fetch_structured.main(["--code", "301313", "--dates", DATES,
                               "--run-dir", str(run_dir), "--refresh"])
    assert exc.value.code == 1
