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


def test_persistent_failure_recorded_and_archived(run_dir):
    """接口故障（持续 5xx）不再整体致命：逐项记 fetch_failed，留档不写任何 rows。"""
    def always_500(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    doc = fetch_structured.fetch_structured("301313", DATES.split(","), run_dir,
                                            client=make_client(always_500), sleep=lambda s: None)
    expected_keys = {f"{d}/{k}" for d in DATES.split(",")
                     for k in ("balance", "cashflow", "income")}
    assert set(doc["fetch_failures"]) == expected_keys
    assert all(v["reason"] == "fetch_failed" for v in doc["fetch_failures"].values())
    assert all(not rows for per_date in doc["reports"].values() for rows in per_date.values())
    stored = json.loads((run_dir / "structured_financials.json").read_text(encoding="utf-8"))
    assert stored["fetch_failures"] == doc["fetch_failures"]


def test_empty_responses_recorded_as_no_data(run_dir):
    """接口正常但无数据（未披露/银行保险不在通用表）→ no_data，不是致命错误。"""
    payload = json.dumps({"result": None}).encode()

    def empty(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload)

    doc = fetch_structured.fetch_structured("301313", ["2026-06-30"], run_dir,
                                            client=make_client(empty), sleep=lambda s: None)
    assert set(doc["fetch_failures"]) == {f"2026-06-30/{k}"
                                          for k in ("balance", "cashflow", "income")}
    assert all(v["reason"] == "no_data" for v in doc["fetch_failures"].values())


def test_bad_json_retries_then_records_fetch_failed(run_dir):
    def bad(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    doc = fetch_structured.fetch_structured("301313", ["2026-06-30"], run_dir,
                                            client=make_client(bad), sleep=lambda s: None)
    assert {v["reason"] for v in doc["fetch_failures"].values()} == {"fetch_failed"}


def missing_income_handler(request: httpx.Request) -> httpx.Response:
    """income 表正常返回但无数据（如未披露），其余两表正常。"""
    if request.url.params.get("reportName") == "RPT_F10_FINANCE_GINCOME":
        return httpx.Response(200, content=json.dumps({"result": None}).encode(),
                              headers={"content-type": "application/json"})
    return ok_handler(request)


def test_partial_fetch_archived_and_completed_on_rerun(run_dir):
    """一次缺数（如未披露）不拖垮其余请求：缺项留档，重跑只补缺、补齐后视为完整。"""
    counter: list[tuple] = []

    doc = fetch_structured.fetch_structured("301313", ["2026-06-30"], run_dir,
                                            client=make_client(missing_income_handler, counter))
    assert set(doc["fetch_failures"]) == {"2026-06-30/income"}
    assert doc["fetch_failures"]["2026-06-30/income"]["reason"] == "no_data"
    assert sorted(doc["reports"]["2026-06-30"]) == ["balance", "cashflow"]
    assert len(counter) == 3, "all three reports are requested; the empty one becomes no_data"

    calls_first = len(counter)
    doc = fetch_structured.fetch_structured("301313", ["2026-06-30"], run_dir,
                                            client=make_client(ok_handler, counter))
    assert len(counter) - calls_first == 1, "rerun retries only the missing report"
    assert not doc["fetch_failures"]
    assert doc["reused"] is False
    assert sorted(doc["reports"]["2026-06-30"]) == ["balance", "cashflow", "income"]
    stored = json.loads((run_dir / "structured_financials.json").read_text(encoding="utf-8"))
    assert stored["fetch_failures"] == {}


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


def test_cli_partial_when_a_report_is_missing(run_dir, capsys, monkeypatch):
    """部分缺数：退出 0、status=partial、issues 携带缺项明细；重跑缺项仍在仍报 partial。"""
    monkeypatch.setattr(fetch_structured, "_cli_client", make_client(missing_income_handler))
    assert fetch_structured.main(["--code", "301313", "--dates", "2026-06-30",
                                  "--run-dir", str(run_dir)]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1
    out = json.loads(lines[0])
    assert out["status"] == "partial"
    assert any("2026-06-30/income" in issue for issue in out["issues"])

    assert fetch_structured.main(["--code", "301313", "--dates", "2026-06-30",
                                  "--run-dir", str(run_dir)]) == 0
    out = json.loads([line for line in capsys.readouterr().out.splitlines() if line.strip()][0])
    assert out["status"] == "partial", "still-missing parts must not be masked as reused"
