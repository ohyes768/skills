"""Reusable sibling tools must work across companies, dates and supported formats."""

import importlib
import json
from decimal import Decimal

import pytest
import run_pipeline
from test_build_financials import prepare_build_run, write_json_file


def text_run(run_dir):
    prepare_build_run(run_dir, {
        "kind": "duration", "start": "2024-01-01", "end": "2024-12-31",
        "frequency": "annual", "aggregation": "cumulative",
    })
    (run_dir / "excerpts/ev-0002.txt").write_text(
        "[p.6] 合并利润表\n[p.6] 单位：万元\n[p.6] 营业收入\n"
        "[p.6] 120.00\n[p.6] 100.00\n[p.6] 负债合计\n[p.6] 30.00\n",
        encoding="utf-8",
    )
    return {"facts": [{"metric": "revenue", "label": "营业收入", "cur": "120.00",
                        "prior": "100.00", "page": 6, "raw_unit": "万元"}]}


def complete_inputs():
    return {"schema_version": 1, "sections": [
        {"anchor": "## 核心结论", "statements": [{
            "template": "本期收入 {rev:amount_wan}。",
            "bindings": {"rev": {"fact_id": "f-0001"}}, "claim_type": "fact"}],
         "paragraphs": ["收入有所增长。", "仍需关注现金回收风险。"]},
        *[{"anchor": "## " + name, "paragraphs": ["详见来源与计算说明。"]}
          for name in ["主要报表数据", "关键比率", "盈利质量", "风险信号", "数据质量评估"]],
    ]}


def computed(run_dir):
    write_json_file(run_dir / "spec.json", text_run(run_dir))
    result, _ = run_pipeline.cmd_compute(run_dir, spec_path=run_dir / "spec.json",
                                         pdf_only=True)
    assert result.get("metric_counts"), result
    write_json_file(run_dir / "report_inputs.json", complete_inputs())


def test_spec_compute_preserves_unit_and_excerpt_line(run_dir):
    computed(run_dir)
    inputs = json.loads((run_dir / "fact_inputs.json").read_text(encoding="utf-8"))
    assert inputs["facts"][0]["raw_unit"] == "万元"
    assert inputs["facts"][0]["evidence"]["locator"]["line"] == 3
    facts = json.loads((run_dir / "financials.json").read_text(encoding="utf-8"))["facts"]
    assert Decimal(facts[0]["value"]) == Decimal(1200000)


def test_generator_reads_authoritative_metric_contract(run_dir, monkeypatch):
    from financial_schema import METRIC_CONTRACTS
    module = importlib.import_module("build_fact_inputs_verified")
    monkeypatch.setitem(METRIC_CONTRACTS, "new_balance", {"period_kind": "instant"})
    text_run(run_dir)
    facts = module.Run(run_dir).fact({"metric": "new_balance", "label": "负债合计",
                                      "cur": "30.00", "page": 6, "raw_unit": "万元"})
    assert facts[0]["period_ref"] == "closing"


def test_bad_spec_is_rejected_before_compute_budget(run_dir):
    spec = text_run(run_dir)
    spec["facts"][0]["cur"] = "999.00"
    write_json_file(run_dir / "spec.json", spec)
    result, code = run_pipeline.cmd_compute(run_dir, spec_path=run_dir / "spec.json",
                                            pdf_only=True)
    assert code == 2
    assert "VALUE" in str(result["issues"])
    assert not (run_dir / "financials.json").exists()
    assert not (run_dir / "run_state.json").exists()


def test_repeated_label_requires_explicit_evidence_selection(run_dir):
    module = importlib.import_module("build_fact_inputs_verified")
    spec = text_run(run_dir)
    path = run_dir / "excerpts/ev-0002.txt"
    path.write_text(path.read_text(encoding="utf-8") +
                    "[p.6] 母公司利润表\n[p.6] 营业收入\n[p.6] 80.00\n", encoding="utf-8")
    with pytest.raises(ValueError, match="(?i)ambiguous|重复"):
        module.Run(run_dir).fact(spec["facts"][0])


def test_builder_rejects_numbers_in_qualitative_paragraphs(run_dir):
    computed(run_dir)
    builder = importlib.import_module("report_inputs_builder")
    spec = complete_inputs()
    spec["sections"][0]["paragraphs"] = ["详见 PDF 第 6 页。"]
    with pytest.raises(builder.ReportInputError):
        builder.build_report_inputs(run_dir, spec)


def test_report_spec_expands_source_pages_and_validates_bindings(run_dir):
    computed(run_dir)
    builder = importlib.import_module("report_inputs_builder")
    spec = {"sections": [{
        "anchor": "## 关键比率",
        "table": {"columns": ["指标", "同比", "来源"],
                  "rows": [{"label": "收入变化",
                            "cells": [{"metric_id": "revenue_yoy", "format": "percent2"}, ""]}]},
    }]}
    inputs = builder.build_report_inputs(run_dir, spec)
    row = inputs["sections"][0]["table"]["rows"][0]
    assert row["cells"][-1] == "PDF 第 6 页"
    bad = {"sections": [{"anchor": "## 核心结论", "statements": [
        {"template": "收入 {rev:amount_wan}。", "bindings": {},
         "claim_type": "fact"}]}]}
    with pytest.raises(builder.ReportInputError):
        builder.build_report_inputs(run_dir, bad)


def test_report_spec_failure_writes_nothing_and_spends_no_budget(run_dir):
    computed(run_dir)
    before = (run_dir / "report_inputs.json").read_text(encoding="utf-8")
    spec = {"sections": [{"anchor": "## 核心结论", "statements": [
        {"template": "收入 {rev:amount_wan}。", "bindings": {"rev": {"fact_id": "f-9999"}},
         "claim_type": "fact"}]}]}
    write_json_file(run_dir / "report_spec.json", spec)
    result, code = run_pipeline.cmd_report(run_dir, spec_path=run_dir / "report_spec.json")
    assert code == 2
    assert "construction failed" in str(result["issues"])
    assert (run_dir / "report_inputs.json").read_text(encoding="utf-8") == before


def test_report_spec_runs_to_verified_terminal(run_dir):
    computed(run_dir)
    write_json_file(run_dir / "report_spec.json", complete_inputs())
    result, code = run_pipeline.cmd_report(
        run_dir, spec_path=run_dir / "report_spec.json", independent_review=True)
    assert code == 0, result
    assert result["terminal"] is True
    inputs = json.loads((run_dir / "report_inputs.json").read_text(encoding="utf-8"))
    assert inputs["sections"][0]["statements"][0]["claim_type"] == "fact"


def test_combined_report_checks_before_terminal_and_returns_exact_body(run_dir):
    computed(run_dir)
    result, code = run_pipeline.cmd_report(run_dir, include_report=True, independent_review=True)
    assert code == 0, result
    assert result["terminal"] is True
    assert result["independent_review"]["passed"] is True
    assert result["report_markdown"] == (run_dir / "analysis.md").read_text(encoding="utf-8")


def test_independent_failure_blocks_delivery_and_uses_existing_budget(run_dir):
    computed(run_dir)
    inputs = complete_inputs()
    inputs["sections"][0]["paragraphs"] = []
    write_json_file(run_dir / "report_inputs.json", inputs)
    result, code = run_pipeline.cmd_report(run_dir, include_report=True, independent_review=True)
    assert code == 2
    assert result.get("terminal") is not True
    assert "report_markdown" not in result
    assert result["quality_status"] == "partial"
    assert any("A3" in issue for issue in result["issues"])
    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["repairs"]["report"]["count"] == 1
    assert state["quality_status"] == "partial"


def test_independent_review_detects_metric_tampering(run_dir):
    computed(run_dir)
    path = run_dir / "metrics.json"
    metrics = json.loads(path.read_text(encoding="utf-8"))
    next(m for m in metrics["metrics"] if m["metric_id"] == "revenue_yoy")["value"] = "0.9"
    write_json_file(path, metrics)
    result, code = run_pipeline.cmd_report(run_dir, independent_review=True)
    assert code == 2
    assert any("B3" in issue for issue in result["issues"])


def test_independent_review_accepts_missing_metrics_without_inventing_values(run_dir):
    computed(run_dir)
    result, code = run_pipeline.cmd_report(run_dir, independent_review=True)
    assert code == 0, result
    assert result["independent_review"]["not_applicable"]


@pytest.mark.parametrize("mutation,expected", [
    ("number", "B1"), ("columns", "A5"), ("placeholder", "A6"),
    ("parent", "C4"), ("metric", "B3"), ("core", "A3"),
])
def test_verifier_mutations_are_company_independent(run_dir, mutation, expected):
    """Maintenance checks use generated IDs/values, never a particular company's report."""
    computed(run_dir)
    inputs = complete_inputs()
    inputs["sections"][1]["table"] = {
        "columns": ["项目", "本期（万元）", "来源"], "rows": [
            {"label": "营业收入", "cells": [
                {"fact_id": "f-0001", "format": "amount_wan"}, "PDF 第 6 页"]}]}
    write_json_file(run_dir / "report_inputs.json", inputs)
    assert run_pipeline.cmd_report(run_dir, independent_review=True)[1] == 0
    from verify_report_independent import verify_run
    if mutation in {"number", "parent"}:
        path = run_dir / "financials.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["facts"][0]["value" if mutation == "number" else "scope"] = (
            "9999" if mutation == "number" else "parent")
        write_json_file(path, data)
    elif mutation == "metric":
        path = run_dir / "metrics.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        next(m for m in data["metrics"] if m["metric_id"] == "revenue_yoy")["value"] = "999"
        write_json_file(path, data)
    elif mutation == "core":
        inputs["sections"][0]["paragraphs"] = ["额外判断。"] * 6
        write_json_file(run_dir / "report_inputs.json", inputs)
    else:
        path = run_dir / "analysis.md"
        body = path.read_text(encoding="utf-8")
        body = (body.replace("| 营业收入 | 120.00万元 | PDF 第 6 页 |",
                             "| 营业收入 | 120.00万元 |") if mutation == "columns"
                else body + "\n{unresolved:percent2}\n")
        path.write_text(body, encoding="utf-8")
    review = verify_run(run_dir)
    assert review["passed"] is False
    assert any(issue.startswith(expected) for issue in review["issues"]), review


def test_balance_review_uses_document_dates_and_allows_minority_profit(run_dir):
    spec = text_run(run_dir)
    path = run_dir / "excerpts/ev-0002.txt"
    path.write_text(path.read_text(encoding="utf-8") +
                    "[p.6] 资产总计\n[p.6] 100.00\n"
                    "[p.6] 所有者权益合计\n[p.6] 70.00\n"
                    "[p.6] 净利润\n[p.6] 20.00\n"
                    "[p.6] 归母净利润\n[p.6] 18.00\n", encoding="utf-8")
    spec["facts"] += [{"metric": metric, "label": label, "cur": amount,
                       "page": 6, "raw_unit": "万元"} for metric, label, amount in [
        ("total_assets", "资产总计", "100.00"), ("total_liabilities", "负债合计", "30.00"),
        ("total_equity", "所有者权益合计", "70.00"), ("net_profit_group", "净利润", "20.00"),
        ("net_profit_owners", "归母净利润", "18.00")]]
    write_json_file(run_dir / "spec.json", spec)
    run_pipeline.cmd_compute(run_dir, spec_path=run_dir / "spec.json", pdf_only=True)
    write_json_file(run_dir / "report_inputs.json", complete_inputs())
    result, code = run_pipeline.cmd_report(run_dir, independent_review=True)
    assert code == 0, result
    from verify_report_independent import verify_run
    path = run_dir / "financials.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    next(f for f in data["facts"] if f["metric"] == "total_assets")["value"] = "9000000"
    write_json_file(path, data)
    assert any(i.startswith("D1") for i in verify_run(run_dir)["issues"])


def test_cli_combines_build_and_delivery_with_single_json(run_dir, capsys):
    write_json_file(run_dir / "spec.json", text_run(run_dir))
    run_pipeline.main(["compute", "--run-dir", str(run_dir), "--spec", str(run_dir / "spec.json")])
    assert json.loads(capsys.readouterr().out)["stage"] == "compute"
    write_json_file(run_dir / "report_inputs.json", complete_inputs())
    assert run_pipeline.main(["report", "--run-dir", str(run_dir),
                              "--independent-review", "--include-report"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["terminal"] is True
    assert result["independent_review"]["passed"] is True


def test_explicit_parent_comparison_is_separate_from_consolidated_metrics(run_dir):
    computed(run_dir)
    path = run_dir / "financials.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    parent = dict(data["facts"][0], fact_id="f-parent", scope="parent")
    data["facts"].append(parent)
    write_json_file(path, data)
    inputs = complete_inputs()
    inputs["sections"].append({"anchor": "## 母公司对照", "statements": [{
        "template": "母公司收入 {parent:amount_wan}。",
        "bindings": {"parent": {"fact_id": "f-parent"}}, "claim_type": "fact"}]})
    write_json_file(run_dir / "report_inputs.json", inputs)
    result, code = run_pipeline.cmd_report(run_dir, independent_review=True)
    assert code == 0, result


def test_preflight_failure_invalidates_old_verified_state(run_dir):
    computed(run_dir)
    assert run_pipeline.cmd_report(run_dir, independent_review=True)[1] == 0
    inputs = complete_inputs()
    inputs["sections"][0]["paragraphs"] = ["错误的裸数字 88。"]
    write_json_file(run_dir / "report_inputs.json", inputs)
    result, code = run_pipeline.cmd_report(run_dir, independent_review=True, include_report=True)
    assert code == 2
    assert result.get("terminal") is not True
    assert "report_markdown" not in result
    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["quality_status"] == "partial"
    assert state["repairs"]["report"]["count"] == 1
