"""结构化数据源端到端：默认 compute 模式、--pdf-only 逃生门、structured fact 的报告支撑。"""

import json
from pathlib import Path

import pytest
import run_pipeline
import validate_report
from test_build_financials import fact_input, prepare_build_run, structured_doc, write_json_file


def run_compute(run_dir: Path, **kwargs) -> tuple[dict, int]:
    return run_pipeline.cmd_compute(run_dir, **kwargs)


def test_compute_structured_mode_without_fact_inputs(run_dir):
    """默认模式下 fact_inputs 可选：全量结构化 facts + metrics + check 落盘。"""
    prepare_build_run(run_dir)
    write_json_file(run_dir / "structured_financials.json", structured_doc())
    result, _code = run_compute(run_dir)
    assert (run_dir / "financials.json").exists()
    assert (run_dir / "metrics.json").exists()
    check = json.loads((run_dir / "structured_check.json").read_text(encoding="utf-8"))
    assert check["samples"] and check["conflicts"] == 0
    facts = json.loads((run_dir / "financials.json").read_text(encoding="utf-8"))["facts"]
    assert all(f.get("source") == "structured" for f in facts)
    assert result["metric_counts"]["computed"] >= 1


def test_compute_structured_with_sample_inputs(run_dir):
    """抽查单存在时与结构化事实双源并存并写入 check。"""
    prepare_build_run(run_dir)
    write_json_file(run_dir / "structured_financials.json", structured_doc())
    write_json_file(run_dir / "fact_inputs.json", {"schema_version": 1, "facts": [
        fact_input(),
    ]})
    _result, code = run_compute(run_dir)
    assert code in (0, 2)
    check = json.loads((run_dir / "structured_check.json").read_text(encoding="utf-8"))
    revenue = next(s for s in check["samples"] if s["metric"] == "revenue"
                   and s["period_end"] == "2026-06-30")
    assert revenue["status"] in ("verified", "conflict", "unchecked")
    assert revenue["status"] != "unchecked"


def test_compute_structured_fetch_failure_falls_back(run_dir, monkeypatch):
    """结构化拉取失败：自动回退纯 PDF 模式并在 warnings 标注。"""
    from fetch_structured import FetchStructuredError

    prepare_build_run(run_dir)
    document = json.loads((run_dir / "document.json").read_text(encoding="utf-8"))
    document["stock_code"] = "300000"
    write_json_file(run_dir / "document.json", document)
    write_json_file(run_dir / "fact_inputs.json", {"schema_version": 1, "facts": [
        fact_input(),
    ]})

    def boom(code, dates, run_dir_arg, **kwargs):
        raise FetchStructuredError("network unreachable")

    monkeypatch.setattr("fetch_structured.fetch_structured", boom)
    _result, code = run_compute(run_dir)
    assert code in (0, 2)
    assert (run_dir / "financials.json").exists(), "fallback must still produce financials"
    mapping = json.loads((run_dir / "mapping_validation.json").read_text(encoding="utf-8"))
    assert any("fell back to PDF-only" in w["error"] for w in mapping.get("warnings", []))
    facts = json.loads((run_dir / "financials.json").read_text(encoding="utf-8"))["facts"]
    assert all(f.get("source", "extracted") == "extracted" for f in facts)


def test_pdf_only_forbids_structured_fetch(run_dir, monkeypatch):
    """--pdf-only 逃生门：即使有 stock_code 也绝不发起结构化拉取。"""
    prepare_build_run(run_dir)
    document = json.loads((run_dir / "document.json").read_text(encoding="utf-8"))
    document["stock_code"] = "300000"
    write_json_file(run_dir / "document.json", document)
    write_json_file(run_dir / "fact_inputs.json", {"schema_version": 1, "facts": [
        fact_input(),
    ]})
    monkeypatch.setattr(
        "fetch_structured.fetch_structured",
        lambda *a, **k: pytest.fail("pdf_only must not fetch structured data"))
    _result, code = run_compute(run_dir, pdf_only=True)
    assert code in (0, 2)
    mapping = json.loads((run_dir / "mapping_validation.json").read_text(encoding="utf-8"))
    assert not any(w.get("field") == "structured" for w in mapping.get("warnings", []))
    facts = json.loads((run_dir / "financials.json").read_text(encoding="utf-8"))["facts"]
    assert all(f.get("source", "extracted") == "extracted" for f in facts)


def test_default_compute_without_inputs_or_structured_is_fatal(run_dir):
    """默认模式：无抽查单且结构化源不可用 → 致命错误并说明两条出路。"""
    prepare_build_run(run_dir)
    document = json.loads((run_dir / "document.json").read_text(encoding="utf-8"))
    document["stock_code"] = "300000"
    write_json_file(run_dir / "document.json", document)
    result, code = run_compute(run_dir)
    assert code == 1
    assert ("fact_inputs.json missing and structured source unavailable"
            in result["issues"][0])


def test_validate_structured_metric_needs_clean_check(run_dir):
    """calculation claim 引用 structured facts：无 clean check 拒绝，有则通过。"""
    import render_report
    from test_render_report import prepare_render_run, revenue_inputs

    prepare_render_run(run_dir)
    facts = json.loads((run_dir / "financials.json").read_text(encoding="utf-8"))
    for fact in facts["facts"]:
        fact["source"] = "structured"
        fact["evidence_ids"] = []
    write_json_file(run_dir / "financials.json", facts)

    inputs = revenue_inputs()
    markdown, claims, issues = render_report.render_report(run_dir, inputs)
    assert issues == []
    write_json_file(run_dir / "report_claims.json", {"schema_version": 1, "claims": claims})
    (run_dir / "analysis.md").write_text(markdown, encoding="utf-8")

    result = validate_report.validate_report(run_dir)
    assert result["passed"] is False
    assert any("lacks a clean sample check" in item for item in result["invalid_support"])

    write_json_file(run_dir / "structured_check.json",
                    {"schema_version": 1, "samples": [{"metric": "revenue",
                                                       "status": "unchecked"}],
                     "verified": 0, "conflicts": 0, "unchecked": 1})
    result = validate_report.validate_report(run_dir)
    assert result["passed"] is True, result
