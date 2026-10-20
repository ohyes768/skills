"""Hermes MiniMax-M3 实际运行中出现的表达误报负例回归。

证据来源：.trellis/tasks/10-19-financial-analysis-hermes-runtime/research/runtime-evidence.md
场景：AI 3D 产品名、范围页码 56-57、下降正幅度、2026上半年、百分点幅度。
每个修复必须保留错误金额/符号/页码的拦截能力。
"""

import json
from pathlib import Path

import validate_report


def prepare_run(run_dir: Path, claims: list[dict], facts: list[dict],
                metrics: list[dict], analysis_md: str | None = None) -> None:
    (run_dir / "document.json").write_text(
        json.dumps({"schema_version": 1, "page_count": 149}, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "financials.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_sha256": "abc",
                "facts": [
                    {
                        **fact,
                        "raw_label": fact["metric"],
                        "raw_value": fact["value"],
                        "raw_unit": "元",
                        "unit": "元",
                        "currency": "CNY",
                        "scope": "consolidated",
                        "attribution": "group",
                        "period": fact.get(
                            "period",
                            {"kind": "duration", "start": "2026-01-01",
                             "end": "2026-06-30", "frequency": "half_year",
                             "aggregation": "cumulative"},
                        ),
                        "basis": "as_reported",
                        "review_status": "verified",
                        "missing_reason": None,
                    }
                    for fact in facts
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metrics": [
                    {
                        "metric_id": metric["metric_id"],
                        "value": metric["value"],
                        "status": "computed",
                        "formula": "(cur-prev)/prev",
                        "input_fact_ids": [f["fact_id"] for f in facts],
                        "source_pages": [9],
                        "reason": None,
                    }
                    for metric in metrics
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "extraction_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "page_count": 149,
                "evidences": [
                    {
                        "evidence_id": "ev-0001",
                        "section_id": "s-1",
                        "pdf_pages": [9, 56, 57],
                        "kind": "text",
                        "file": "excerpts/ev-0001.txt",
                        "method": "pymupdf_text",
                        "complete": True,
                        "issues": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "report_claims.json").write_text(
        json.dumps({"schema_version": 1, "claims": claims}, ensure_ascii=False), encoding="utf-8"
    )
    if analysis_md is None:
        analysis_md = "# 分析\n\n" + "\n\n".join(claim["text"] for claim in claims) + "\n"
    (run_dir / "analysis.md").write_text(analysis_md, encoding="utf-8")


def revenue_fact(value: str = "1200000000.00") -> dict:
    return {"fact_id": "f-0001", "metric": "revenue", "value": value}


def make_claim(**overrides) -> dict:
    claim = {
        "claim_id": "c-001",
        "report_anchor": "# 分析",
        "text": "营业收入 12 亿元（PDF第9页）",
        "fact_ids": ["f-0001"],
        "metric_ids": [],
        "evidence_ids": ["ev-0001"],
        "source_pages": [9],
        "claim_type": "fact",
        "display_unit": "亿元",
    }
    claim.update(overrides)
    return claim


def load_result(run_dir: Path) -> dict:
    return json.loads((run_dir / "report_validation.json").read_text(encoding="utf-8"))


def unbound_literals(result: dict) -> list[str]:
    return [
        item.get("unbound_number")
        for item in result["value_mismatches"]
        if isinstance(item, dict) and item.get("unbound_number")
    ]


def test_ai_3d_product_name_not_treated_as_number(run_dir):
    """msg 复核：NUMBER_RE 将 AI 3D 识别出 3，导致 unbound_number=3 误报。"""
    claim = make_claim(text="公司 AI 3D 可视化业务收入 12 亿元（PDF第9页）")
    prepare_run(run_dir, [claim], [revenue_fact()], [])
    validate_report.validate_report(run_dir)
    assert unbound_literals(load_result(run_dir)) == []


def test_range_pages_56_57_not_unbound_numbers(run_dir):
    """msg 复核：PDF第56-57页 中的 56、57 被当作两个未绑定数字。"""
    claim = make_claim(text="营业收入详见 PDF第56-57页 的 12 亿元披露（PDF第9页）",
                       source_pages=[9, 56, 57])
    prepare_run(run_dir, [claim], [revenue_fact()], [])
    validate_report.validate_report(run_dir)
    result = load_result(run_dir)
    assert unbound_literals(result) == []
    assert result["page_mismatches"] == []


def test_decline_with_positive_magnitude_matches_negative_ratio(run_dir):
    """msg 复核：下降 27.80% 不匹配负 ratio（-0.2780）。"""
    claim = make_claim(
        text="营业收入同比下降 27.80%（PDF第9页）",
        fact_ids=[],
        metric_ids=["revenue_yoy"],
        claim_type="calculation",
    )
    prepare_run(run_dir, [claim], [revenue_fact()],
                [{"metric_id": "revenue_yoy", "value": "-0.2780"}])
    validate_report.validate_report(run_dir)
    assert load_result(run_dir)["value_mismatches"] == []


def test_2026_half_year_suffix_exempt(run_dir):
    """msg 复核：2026上半年 不符合仅「YYYY年」的日期豁免。"""
    claim = make_claim(text="2026上半年公司实现营业收入 12 亿元（PDF第9页）")
    prepare_run(run_dir, [claim], [revenue_fact()], [])
    validate_report.validate_report(run_dir)
    assert unbound_literals(load_result(run_dir)) == []


def test_percentage_point_decline_matches_ratio(run_dir):
    """msg 复核：毛利率下降 2.3 个百分点不匹配 -0.023 的 ratio。"""
    claim = make_claim(
        text="净利率同比下降 2.3 个百分点（PDF第9页）",
        fact_ids=[],
        metric_ids=["net_margin_yoy"],
        claim_type="calculation",
        display_unit=None,
    )
    prepare_run(run_dir, [claim], [revenue_fact()],
                [{"metric_id": "net_margin_yoy", "value": "-0.023"}])
    validate_report.validate_report(run_dir)
    assert load_result(run_dir)["value_mismatches"] == []


def test_decline_text_with_positive_ratio_still_rejected(run_dir):
    """负例：文本说下降但绑定值为正（符号矛盾），必须拦截。"""
    claim = make_claim(
        text="营业收入同比下降 27.80%（PDF第9页）",
        fact_ids=[],
        metric_ids=["revenue_yoy"],
        claim_type="calculation",
    )
    prepare_run(run_dir, [claim], [revenue_fact()],
                [{"metric_id": "revenue_yoy", "value": "0.2780"}])
    validate_report.validate_report(run_dir)
    result = load_result(run_dir)
    assert result["value_mismatches"], "decline text with positive ratio must fail"


def test_wrong_amount_still_rejected(run_dir):
    claim = make_claim(text="营业收入 34 亿元（PDF第9页）")
    prepare_run(run_dir, [claim], [revenue_fact()], [])
    validate_report.validate_report(run_dir)
    result = load_result(run_dir)
    assert result["value_mismatches"], "wrong amount must fail"


def test_wrong_cited_page_still_rejected(run_dir):
    claim = make_claim(text="营业收入 12 亿元（PDF第40页）")
    prepare_run(run_dir, [claim], [revenue_fact()], [])
    validate_report.validate_report(run_dir)
    result = load_result(run_dir)
    assert result["page_mismatches"], "wrong cited page must fail"


def test_plain_signed_ratio_still_matches(run_dir):
    """复核确认：普通带符号 31.49% 与 -0.3149 已可匹配，修复不得破坏。"""
    claim = make_claim(
        text="净利润率为 -31.49%（PDF第9页）",
        fact_ids=[],
        metric_ids=["net_margin"],
        claim_type="calculation",
    )
    prepare_run(run_dir, [claim], [revenue_fact()],
                [{"metric_id": "net_margin", "value": "-0.3149"}])
    validate_report.validate_report(run_dir)
    assert load_result(run_dir)["value_mismatches"] == []


def test_body_coverage_ignores_range_citations(run_dir):
    """claim 覆盖的行内范围页码引用不应被判为未覆盖数字。"""
    claim = make_claim(
        text="营业收入 12 亿元（PDF第9页），详细表格见 PDF第56-57页",
        source_pages=[9, 56, 57],
    )
    body = (
        "# 分析\n\n"
        "营业收入 12 亿元（PDF第9页），详细表格见 PDF第56-57页\n"
    )
    prepare_run(run_dir, [claim], [revenue_fact()], [], analysis_md=body)
    validate_report.validate_report(run_dir)
    result = load_result(run_dir)
    assert result["unclaimed_numeric_lines"] == []
    assert result["page_mismatches"] == []
