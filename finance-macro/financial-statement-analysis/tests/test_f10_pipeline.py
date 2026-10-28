"""F10-only integration and report mutation regressions (offline)."""

import hashlib
import json
from copy import deepcopy

import pytest
import run_pipeline
from artifacts import read_json, write_json
from fetch_structured import REPORTS


def archive_fixture():
    reports = {}
    for day in ("2024-06-30", "2023-06-30", "2023-12-31"):
        current = day == "2024-06-30"
        identity = {"SECUCODE": "002093.SZ", "SECURITY_CODE": "002093",
                    "SECURITY_NAME_ABBR": "测试公司", "REPORT_DATE": day + " 00:00:00"}
        balance = {"TOTAL_ASSETS": "2000" if current else "1600",
                   "TOTAL_LIABILITIES": "800" if current else "600",
                   "TOTAL_EQUITY": "1200" if current else "1000",
                   "TOTAL_PARENT_EQUITY": "1200" if current else "1000",
                   "MONETARYFUNDS": "250" if current else "200",
                   "ACCOUNTS_RECE": "100", "INVENTORY": "50", "GOODWILL": "0",
                   "SHORT_LOAN": "0", "LONG_LOAN": "0"}
        income = {"TOTAL_OPERATE_INCOME": "1000" if current else "800",
                  "OPERATE_COST": "600" if current else "500",
                  "NETPROFIT": "100" if current else "80",
                  "PARENT_NETPROFIT": "100" if current else "80"}
        cash = {"NETCASH_OPERATE": "100", "NETCASH_INVEST": "-40",
                "NETCASH_FINANCE": "-10", "END_CCE": "250" if current else "200",
                "BEGIN_CCE": "200", "RATE_CHANGE_EFFECT": "0",
                "CONSTRUCT_LONG_ASSET": "40"}
        reports[day] = {kind: [{**identity, **fields}]
                        for kind, fields in (("balance", balance), ("income", income),
                                             ("cashflow", cash))}
    return {"schema_version": 1, "source": "structured_eastmoney",
            "security_code": "002093", "secucode": "002093.SZ",
            "report_dates": sorted(reports), "reports": reports, "fetch_failures": {},
            "fetched_at": "2026-10-28T00:00:00+00:00",
            "response_sha256": {f"{day}/{kind}": hashlib.sha256(
                json.dumps(rows, sort_keys=True).encode()).hexdigest()
                for day, kinds in reports.items() for kind, rows in kinds.items()},
            "requested": {"secucode": "002093.SZ", "report_dates": sorted(reports),
                          "report_names": sorted(REPORTS.values())}}


@pytest.fixture
def f10_run(run_dir, monkeypatch):
    archive = archive_fixture()

    def fetch(code, dates, path, **kwargs):
        assert code == "002093"
        assert set(dates) == set(archive["reports"])
        write_json(path / "structured_financials.json", archive)
        return {**deepcopy(archive), "reused": False}

    monkeypatch.setattr("fetch_structured.fetch_structured", fetch)
    result, code = run_pipeline.cmd_prepare("002093", "2024-06-30", run_dir)
    assert code == 0, result
    result, code = run_pipeline.cmd_compute(run_dir)
    assert code == 0, result
    return run_dir


def report_spec(run_dir):
    facts = read_json(run_dir / "financials.json")["facts"]
    ids = {f["metric"]: f["fact_id"] for f in facts
           if f["period"]["end"] == "2024-06-30"}
    sections = [{"anchor": "## 核心结论", "statements": [
        {"template": label + " {v:amount_yuan}。", "claim_type": "fact",
         "bindings": {"v": {"fact_id": ids[metric]}}}
        for label, metric in (("营业收入", "revenue"), ("合并净利润", "net_profit_group"),
                              ("经营现金流", "cfo"))]}]
    sections.append({"anchor": "## 三张报表", "table": {
        "columns": ["科目", "本期", "来源"], "rows": [
            {"label": "营业收入", "cells": [
                {"fact_id": ids["revenue"], "format": "amount_yuan"}, ""]}]}})
    for title in ("关键比率", "盈利质量", "风险信号", "数据质量"):
        sections.append({"anchor": "## " + title,
                         "paragraphs": ["本报告依据东财结构化财务数据，未取得的披露内容保留为资料不足。"]})
    return {"schema_version": 1, "sections": sections}


def deliver(run_dir):
    spec = run_dir / "report_spec.json"
    write_json(spec, report_spec(run_dir))
    return run_pipeline.cmd_report(run_dir, spec_path=spec, independent_review=True,
                                   include_report=True)


def test_f10_end_to_end_without_extraction_artifacts(f10_run):
    result, code = deliver(f10_run)
    assert code == 0, result
    assert result["quality_status"] == "verified"
    assert result["terminal"] is True
    assert "TOTAL_OPERATE_INCOME" in result["report_markdown"]
    assert "2024-06-30" in result["report_markdown"]
    assert not (f10_run / "source.pdf").exists()
    assert not (f10_run / "extraction_manifest.json").exists()


def test_archived_field_tampering_blocks_delivery(f10_run):
    archive = read_json(f10_run / "structured_financials.json")
    archive["reports"]["2024-06-30"]["income"][0]["TOTAL_OPERATE_INCOME"] = "9999"
    write_json(f10_run / "structured_financials.json", archive)
    result, code = deliver(f10_run)
    assert code != 0
    assert result["quality_status"] != "verified"
    assert "report_markdown" not in result


def test_old_source_cli_options_rejected(run_dir):
    with pytest.raises(SystemExit) as exc:
        run_pipeline.main(["compute", "--run-dir", str(run_dir), "--pdf-only"])
    assert exc.value.code == 2


def test_failed_source_recheck_revokes_previous_verified_state(f10_run):
    assert deliver(f10_run)[1] == 0
    fin = read_json(f10_run / "financials.json")
    fin["facts"][0]["value"] = "987654"
    write_json(f10_run / "financials.json", fin)
    assert deliver(f10_run)[1] != 0
    assert read_json(f10_run / "run_state.json")["quality_status"] != "verified"


def test_missing_comparison_remains_partial_with_no_fallback(f10_run):
    archive = read_json(f10_run / "structured_financials.json")
    archive["reports"]["2023-06-30"].pop("income")
    write_json(f10_run / "structured_financials.json", archive)
    result, code = run_pipeline.cmd_compute(f10_run)
    assert code == 2, result
    result, code = deliver(f10_run)
    assert code == 2, result
    assert result["quality_status"] == "partial"
    assert "report_markdown" not in result


@pytest.mark.parametrize("mutation", ["body", "claim", "metric", "citation"])
def test_report_mutations_rejected(f10_run, mutation):
    assert deliver(f10_run)[1] == 0
    if mutation == "body":
        body = f10_run / "analysis.md"
        body.write_text(body.read_text(encoding="utf-8") + "无依据增长 88%。\n", encoding="utf-8")
    elif mutation == "claim":
        doc = read_json(f10_run / "report_claims.json")
        doc["claims"] = []
        write_json(f10_run / "report_claims.json", doc)
    elif mutation == "citation":
        doc = read_json(f10_run / "report_claims.json")
        doc["claims"][0]["source_refs"][0]["field"] = "FAKE_FIELD"
        write_json(f10_run / "report_claims.json", doc)
    else:
        doc = read_json(f10_run / "metrics.json")
        doc["metrics"][0]["value"] = "9.99"
        write_json(f10_run / "metrics.json", doc)
        from verify_report_independent import verify_run
        assert not verify_run(f10_run)["passed"]
        return
    from validate_report import validate_report
    assert not validate_report(f10_run)["passed"]


def test_generated_risk_states_follow_current_screening(f10_run):
    from build_report_spec import build_spec
    skeleton = read_json(__import__("pathlib").Path(__file__).resolve().parents[1]
                         / "references/report-spec-skeleton.json")
    spec, _ = build_spec(f10_run, skeleton)
    risk = next(s for s in spec["sections"] if s["anchor"] == "## 风险信号")
    goodwill = next(r for r in risk["table"]["rows"] if r["label"] == "商誉占比过高")
    assert goodwill["cells"][0] == "已检查未发现"
    prepay = next(r for r in risk["table"]["rows"] if r["label"] == "预付款项突升")
    assert prepay["cells"][0] == "资料不足"
    inventory = next(r for r in risk["table"]["rows"] if r["label"] == "存货突升")
    assert inventory["cells"][0] == "已检查未发现"


def test_context_cursor_bound_to_actual_computed_data(f10_run):
    from pack_context import build_packet
    first = build_packet(f10_run, "analyze", "first", max_chars=1500)
    cursor = first["packet"]["next_cursor"]
    assert cursor
    assert len(json.dumps(first["packet"], ensure_ascii=False)) <= 1500
    second = build_packet(f10_run, "analyze", "second", max_chars=1500, cursor=cursor)
    assert first["packet"]["items"] != second["packet"]["items"]
    doc = read_json(f10_run / "metrics.json")
    doc["metrics"][0]["value"] = "1.9"
    write_json(f10_run / "metrics.json", doc)
    with pytest.raises(ValueError, match="stale"):
        build_packet(f10_run, "analyze", "stale", cursor=cursor)


def test_report_budget_persists_across_restart(f10_run):
    spec_path = f10_run / "report_spec.json"
    for attempt in range(4):
        spec = report_spec(f10_run)
        # A3 is checked after rendering; distinct inputs consume the formal budget.
        spec["sections"][0]["statements"] = spec["sections"][0]["statements"][:1]
        spec["sections"][0]["paragraphs"] = ["测试" + "补充" * attempt]
        write_json(spec_path, spec)
        result, code = run_pipeline.cmd_report(f10_run, spec_path=spec_path, independent_review=True)
        assert code != 0
    assert result["quality_status"] == "maintenance_required"


def test_f10_disclosed_risk_and_cash_adjustment_fields_are_mapped(f10_run):
    archive = read_json(f10_run / "structured_financials.json")
    archive["reports"]["2024-06-30"]["balance"][0].update(PREPAYMENT="12.5", CIP="25")
    write_json(f10_run / "structured_financials.json", archive)
    result, code = run_pipeline.cmd_compute(f10_run)
    assert code == 0, result
    facts = read_json(f10_run / "financials.json")["facts"]
    current = {f["metric"]: f for f in facts if f["period"]["end"] == "2024-06-30"}
    assert current["prepayments"]["value"] == "12.5"
    assert current["construction_in_progress"]["value"] == "25"
    assert current["fx_effect_on_cash"]["value"] == "0"
    assert current["fx_effect_on_cash"]["source_ref"]["field"] == "RATE_CHANGE_EFFECT"


def test_failed_compute_revokes_verified_state(f10_run):
    assert deliver(f10_run)[1] == 0
    archive = read_json(f10_run / "structured_financials.json")
    archive["reports"]["2024-06-30"]["income"][0]["TOTAL_OPERATE_INCOME"] = "oops"
    write_json(f10_run / "structured_financials.json", archive)
    assert run_pipeline.cmd_compute(f10_run)[1] != 0
    result, code = run_pipeline.cmd_review(f10_run)
    assert code != 0
    assert result["quality_status"] != "verified"


def test_missing_artifacts_cli_returns_single_failure_json(run_dir, capsys):
    assert run_pipeline.main(["compute", "--run-dir", str(run_dir)]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["stage"] == "compute"
    assert result["quality_status"] == "maintenance_required"


def test_independent_review_cannot_be_disabled(f10_run):
    spec = report_spec(f10_run)
    spec["sections"][0]["statements"] = spec["sections"][0]["statements"][:1]
    path = f10_run / "report_spec.json"
    write_json(path, spec)
    result, code = run_pipeline.cmd_report(f10_run, spec_path=path)
    assert code != 0
    assert result["quality_status"] != "verified"


def test_changing_metric_formula_and_value_together_cannot_pass(f10_run):
    metrics = read_json(f10_run / "metrics.json")
    revenue_yoy = next(m for m in metrics["metrics"] if m["metric_id"] == "revenue_yoy")
    revenue_yoy.update(value="1", formula="revenue_cur / revenue_cur")
    write_json(f10_run / "metrics.json", metrics)
    result, code = deliver(f10_run)
    assert code != 0
    assert result["quality_status"] != "verified"


def test_changing_risk_state_cannot_pass(f10_run):
    metrics = read_json(f10_run / "metrics.json")
    metrics["red_flags"][0]["status"] = "flagged"
    write_json(f10_run / "metrics.json", metrics)
    result, code = deliver(f10_run)
    assert code != 0
    assert result["quality_status"] != "verified"
