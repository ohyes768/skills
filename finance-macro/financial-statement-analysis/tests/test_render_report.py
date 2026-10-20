"""render_report：同源渲染、结构化绑定与篡改防护回归。"""

import json
from pathlib import Path

import render_report
import validate_report


def write_json_file(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_render_run(run_dir: Path) -> None:
    write_json_file(run_dir / "document.json", {
        "schema_version": 1, "company_name": "测试公司", "stock_code": "300000",
        "currency": "CNY", "page_count": 20,
        "period": {"kind": "duration", "start": "2026-01-01", "end": "2026-06-30",
                   "frequency": "half_year", "aggregation": "cumulative"},
    })
    write_json_file(run_dir / "financials.json", {
        "schema_version": 1, "document_sha256": "abc",
        "facts": [
            {"fact_id": "f-0001", "metric": "revenue", "raw_label": "营业收入",
             "raw_value": "1,234,567,890.12", "raw_unit": "元", "value": "1234567890.12",
             "unit": "元", "currency": "CNY", "scope": "consolidated",
             "attribution": "group", "basis": "as_reported", "review_status": "verified",
             "missing_reason": None, "evidence_ids": ["ev-0001"],
             "period": {"kind": "duration", "start": "2026-01-01", "end": "2026-06-30",
                        "frequency": "half_year", "aggregation": "cumulative"}},
        ],
    })
    write_json_file(run_dir / "metrics.json", {
        "schema_version": 1,
        "metrics": [
            {"metric_id": "revenue_yoy", "value": "-0.2780", "status": "computed",
             "formula": "(cur-prev)/prev", "input_fact_ids": ["f-0001"],
             "source_pages": [5], "reason": None},
            {"metric_id": "net_margin_yoy", "value": "-0.023", "status": "computed",
             "formula": "x", "input_fact_ids": ["f-0001"], "source_pages": [5], "reason": None},
        ],
    })
    write_json_file(run_dir / "extraction_manifest.json", {
        "schema_version": 1, "document_sha256": "abc", "page_count": 20,
        "evidences": [
            {"evidence_id": "ev-0001", "section_id": "s-1", "pdf_pages": [5],
             "kind": "table", "file": "excerpts/ev-0001.table.json",
             "method": "pdfplumber_table", "complete": True, "issues": []},
        ],
    })
    (run_dir / "excerpts").mkdir(exist_ok=True)
    (run_dir / "excerpts" / "ev-0001.table.json").write_text("{}", encoding="utf-8")


def revenue_statement(**overrides) -> dict:
    statement = {
        "template": "2026上半年公司实现营业收入 {rev:amount_yi}，同比下降 {yoy:decline_percent2}。",
        "bindings": {
            "rev": {"fact_id": "f-0001"},
            "yoy": {"metric_id": "revenue_yoy"},
        },
        "claim_type": "calculation",
    }
    statement.update(overrides)
    return statement


def revenue_inputs(**statement_overrides) -> dict:
    return {"schema_version": 1, "sections": [
        {"anchor": "## 经营分析", "statements": [revenue_statement(**statement_overrides)]},
    ]}


def load_claims(run_dir: Path) -> list[dict]:
    return json.loads((run_dir / "report_claims.json").read_text(encoding="utf-8"))["claims"]


def test_rendered_report_passes_validation(run_dir):
    """同源闭环：渲染产物不经任何修改直接通过固定校验器。"""
    prepare_render_run(run_dir)
    markdown, claims, issues = render_report.render_report(run_dir, revenue_inputs())
    assert issues == []
    (run_dir / "analysis.md").write_text(markdown, encoding="utf-8")
    write_json_file(run_dir / "report_claims.json", {"schema_version": 1, "claims": claims})
    result = validate_report.validate_report(run_dir)
    assert result["passed"] is True, result


def test_claim_carries_resolved_sources(run_dir):
    prepare_render_run(run_dir)
    _, claims, _ = render_report.render_report(run_dir, revenue_inputs())
    claim = claims[0]
    assert claim["claim_id"] == "c-0001"
    assert claim["report_anchor"] == "## 经营分析"
    assert claim["fact_ids"] == ["f-0001"]
    assert claim["metric_ids"] == ["revenue_yoy"]
    assert claim["evidence_ids"] == ["ev-0001"]
    assert claim["source_pages"] == [5]
    assert "下降 27.80%" in claim["text"].replace("下降 ", "下降") or "下降" in claim["text"]
    assert "（PDF第5页）" in claim["text"]


def test_tampered_body_fails_validation(run_dir):
    """渲染后篡改正文：固定校验器必须拒绝（同源不代替验证）。"""
    prepare_render_run(run_dir)
    markdown, claims, _ = render_report.render_report(run_dir, revenue_inputs())
    tampered = markdown.replace("12.35", "99.99")
    assert tampered != markdown
    (run_dir / "analysis.md").write_text(tampered, encoding="utf-8")
    write_json_file(run_dir / "report_claims.json", {"schema_version": 1, "claims": claims})
    assert validate_report.validate_report(run_dir)["passed"] is False


def test_unknown_binding_rejected(run_dir):
    prepare_render_run(run_dir)
    inputs = revenue_inputs(
        bindings={"rev": {"fact_id": "f-9999"}, "yoy": {"metric_id": "revenue_yoy"}})
    _, _, issues = render_report.render_report(run_dir, inputs)
    assert any("unknown fact_id" in issue["error"] for issue in issues)


def test_uncomputed_metric_rejected(run_dir):
    prepare_render_run(run_dir)
    write_json_file(run_dir / "metrics.json", {
        "schema_version": 1,
        "metrics": [
            {"metric_id": "revenue_yoy", "value": None, "status": "insufficient_data",
             "formula": "x", "input_fact_ids": [], "source_pages": [], "reason": "missing"},
        ],
    })
    _, _, issues = render_report.render_report(run_dir, revenue_inputs())
    assert any("not computed" in issue["error"] for issue in issues)


def test_format_kind_mismatch_rejected(run_dir):
    prepare_render_run(run_dir)
    inputs = revenue_statement(overrides=None) and revenue_inputs(
        template="毛利率 {yoy:amount_yi}",
        bindings={"yoy": {"metric_id": "revenue_yoy"}},
    )
    _, _, issues = render_report.render_report(run_dir, inputs)
    assert any("applies to" in issue["error"] for issue in issues)


def test_decline_format_with_positive_value_rejected(run_dir):
    prepare_render_run(run_dir)
    write_json_file(run_dir / "metrics.json", {
        "schema_version": 1,
        "metrics": [
            {"metric_id": "revenue_yoy", "value": "0.2780", "status": "computed",
             "formula": "x", "input_fact_ids": ["f-0001"], "source_pages": [5], "reason": None},
        ],
    })
    _, _, issues = render_report.render_report(run_dir, revenue_inputs())
    assert any("requires a nonpositive value" in issue["error"] for issue in issues)


def test_static_numbers_in_free_text_rejected(run_dir):
    prepare_render_run(run_dir)
    inputs = {"schema_version": 1, "sections": [
        {"anchor": "## 经营分析",
         "statements": [],
         "paragraphs": ["公司第3大客户贡献突出。"]},
    ]}
    _, _, issues = render_report.render_report(run_dir, inputs)
    assert any("must not contain numbers" in issue["error"] for issue in issues)
    assert issues[0]["paragraph_index"] == 1


def test_year_in_template_allowed(run_dir):
    prepare_render_run(run_dir)
    inputs = revenue_inputs(
        template="2026上半年营业收入 {rev:amount_yi}，同比下降 {yoy:decline_percent2}。")
    markdown, _, issues = render_report.render_report(run_dir, inputs)
    assert issues == []
    assert "2026上半年" in markdown


def test_table_rows_rendered_with_claims(run_dir):
    prepare_render_run(run_dir)
    inputs = {"schema_version": 1, "sections": [
        {"anchor": "## 关键指标", "statements": [], "paragraphs": [],
         "table": {
             "display_unit": "亿元",
             "columns": ["指标", "数值"],
             "rows": [
                 {"label": "营业收入", "cells": [{"fact_id": "f-0001", "format": "amount_yi"}]},
                 {"label": "收入同比", "cells": [{"metric_id": "revenue_yoy",
                                                  "format": "decline_percent1"}],
                  "claim_type": "calculation"},
             ],
         }},
    ]}
    markdown, claims, issues = render_report.render_report(run_dir, inputs)
    assert issues == []
    assert "| 营业收入 | 12.35亿元 |" in markdown
    assert "| 收入同比 | 27.8% |" in markdown
    assert len(claims) == 2
    assert claims[1]["claim_type"] == "calculation"


def test_placeholder_without_binding_rejected(run_dir):
    prepare_render_run(run_dir)
    inputs = revenue_inputs(template="收入 {rev:amount_yi} 同比 {yoy:decline_percent2}",
                            bindings={"rev": {"fact_id": "f-0001"}})
    _, _, issues = render_report.render_report(run_dir, inputs)
    assert any("has no binding" in issue["error"] for issue in issues)


def test_failed_render_writes_no_deliverables(run_dir):
    prepare_render_run(run_dir)
    inputs = revenue_inputs(bindings={})
    markdown, claims, issues = render_report.render_report(run_dir, inputs)
    assert markdown is None and claims is None and issues
    assert not (run_dir / "analysis.md").exists()
    assert not (run_dir / "report_claims.json").exists()


def test_render_issues_carry_positions(run_dir):
    """渲染错误必须指明在哪个 statement / 表格行 / 段落，模型不用猜。"""
    prepare_render_run(run_dir)
    inputs = {"schema_version": 1, "sections": [
        {"anchor": "## 经营分析",
         "statements": [
             revenue_statement(),
             {"template": "客户 {miss:amount_yi} 家。", "bindings": {}},
         ],
         "paragraphs": ["第3大客户贡献突出。"],
         "table": {"columns": ["指标", "数值"], "rows": [
             {"label": "不存在的事实", "cells": [{"fact_id": "f-9999", "format": "amount_yi"}]},
         ]},
        },
    ]}
    _, _, issues = render_report.render_report(run_dir, inputs)
    assert any(i.get("statement_index") == 2 for i in issues)
    assert any(i.get("paragraph_index") == 1 for i in issues)
    assert any(i.get("row_label") == "不存在的事实" for i in issues)


def test_paragraph_year_and_citation_rejected_strictly(run_dir):
    """定性段落禁止一切数字：年份与页码引用都不放行，与验收器规则一致。"""
    prepare_render_run(run_dir)
    inputs = {"schema_version": 1, "sections": [
        {"anchor": "## 经营分析", "statements": [], "paragraphs": [],
         },
    ]}
    for text in ("2026上半年需求收缩明显。", "成因详见 PDF第23页。"):
        inputs["sections"][0]["paragraphs"] = [text]
        _, _, issues = render_report.render_report(run_dir, inputs)
        assert issues, f"paragraph with number must be rejected: {text}"
        assert "statements/tables" in issues[0]["error"]
        assert issues[0]["paragraph_index"] == 1


def test_plain_qualitative_paragraph_passes(run_dir):
    prepare_render_run(run_dir)
    inputs = {"schema_version": 1, "sections": [
        {"anchor": "## 经营分析", "statements": [], "paragraphs": [
            "收入下滑主要受行业需求收缩影响，公司未给出量化归因，需后续跟踪。",
        ]},
    ]}
    markdown, _, issues = render_report.render_report(run_dir, inputs)
    assert issues == []
    assert "需求收缩" in markdown
