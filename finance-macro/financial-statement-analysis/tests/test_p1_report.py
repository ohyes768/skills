"""P1 回归：交付正文、数字及来源必须与事实台账对应。"""

import json
from decimal import Decimal

import pytest
import validate_report
from test_validate_report import make_claim, prepare_run


def prepared(run_dir, **overrides):
    claim = make_claim(**overrides)
    prepare_run(run_dir, [claim], analysis_md="# 分析\n\n" + claim["text"] + "\n")
    return claim


def change_json(run_dir, name, update):
    path = run_dir / name
    value = json.loads(path.read_text(encoding="utf-8"))
    update(value)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_wrong_report_body_rejected_even_with_correct_ledger(run_dir):
    prepared(run_dir)
    (run_dir / "analysis.md").write_text("# Wrong\nRevenue declined 88%, no sources.\n", encoding="utf-8")
    assert not validate_report.validate_report(run_dir)["passed"]


def test_empty_ledger_cannot_validate_report(run_dir):
    prepare_run(run_dir, [], analysis_md="# 分析\n收入 999 元\n")
    assert not validate_report.validate_report(run_dir)["passed"]


def test_claim_must_occur_under_its_report_anchor(run_dir):
    prepared(run_dir, report_anchor="## 不存在的章节")
    assert not validate_report.validate_report(run_dir)["passed"]


def test_extra_unclaimed_numeric_statement_rejected(run_dir):
    prepared(run_dir)
    with open(run_dir / "analysis.md", "a", encoding="utf-8") as stream:
        stream.write("\n不存在的收入为 999 元。\n")
    assert not validate_report.validate_report(run_dir)["passed"]


@pytest.mark.parametrize(("text", "value"), [("Growth 2%", ".2"),
                                            ("FCF 10000 yuan", "100"),
                                            ("Growth 200%", ".2")])
def test_number_scale_errors_are_rejected(text, value):
    assert not validate_report._text_contains_value(text, Decimal(value))


@pytest.mark.parametrize(("text", "value"), [("Growth 20%", ".2"),
                                            ("Growth 20.0%", ".2"),
                                            ("现金 12 亿元", "1200000000"),
                                            ("现金 120,000 万元", "1200000000"),
                                            ("现金 1.23 亿元", "123456789"),
                                            ("现金比率 103.5%", "1.0350251")])
def test_explicit_units_and_display_precision_are_supported(text, value):
    assert validate_report._text_contains_value(text, Decimal(value))


def test_fact_value_is_checked_not_only_its_id(run_dir):
    prepared(run_dir, claim_type="fact", text="Revenue is 999 yuan", metric_ids=[])
    assert not validate_report.validate_report(run_dir)["passed"]


@pytest.mark.parametrize("status", ["insufficient_data", "conflict", "not_applicable"])
def test_uncomputed_metric_is_not_numeric_support(run_dir, status):
    prepared(run_dir)
    change_json(run_dir, "metrics.json", lambda data: data["metrics"][0].update(status=status, value=None))
    assert not validate_report.validate_report(run_dir)["passed"]


def test_in_range_but_wrong_page_rejected(run_dir):
    prepared(run_dir, source_pages=[1])
    assert not validate_report.validate_report(run_dir)["passed"]


def test_fact_source_must_resolve_to_manifest(run_dir):
    prepared(run_dir)
    change_json(run_dir, "financials.json", lambda data: data["facts"][0].update(evidence_ids=["ev-9999"]))
    assert not validate_report.validate_report(run_dir)["passed"]


def test_multiple_metrics_require_all_values_to_be_quoted(run_dir):
    prepared(run_dir, metric_ids=["revenue_yoy", "net_margin"])
    change_json(run_dir, "metrics.json", lambda data: data["metrics"].append({
        "metric_id": "net_margin", "value": "0.1", "status": "computed",
        "input_fact_ids": ["f-0001"], "source_pages": [9]}))
    assert not validate_report.validate_report(run_dir)["passed"]


def test_other_wrong_number_cannot_hide_behind_one_correct_value(run_dir):
    prepared(run_dir, text="营业收入同比增长 20%，营业收入为 999 元")
    assert not validate_report.validate_report(run_dir)["passed"]


def test_same_text_in_wrong_section_does_not_validate(run_dir):
    claim = prepared(run_dir, report_anchor="## 核心结论")
    (run_dir / "analysis.md").write_text(
        "# 分析\n## 核心结论\n暂缺。\n## 其他\n" + claim["text"], encoding="utf-8")
    assert not validate_report.validate_report(run_dir)["passed"]


def test_extra_number_on_same_body_line_is_not_covered_by_short_claim(run_dir):
    claim = prepared(run_dir)
    (run_dir / "analysis.md").write_text(
        "# 分析\n" + claim["text"] + "，不存在的收入为 999 元\n", encoding="utf-8")
    assert not validate_report.validate_report(run_dir)["passed"]


def test_actual_body_citation_must_match_ledger_pages(run_dir):
    claim = prepared(run_dir)
    (run_dir / "analysis.md").write_text(
        "# 分析\n" + claim["text"] + "（PDF 第 1 页）\n", encoding="utf-8")
    assert not validate_report.validate_report(run_dir)["passed"]


def test_actual_body_correct_citation_is_accepted(run_dir):
    claim = prepared(run_dir)
    (run_dir / "analysis.md").write_text(
        "# 分析\n" + claim["text"] + "（PDF 第 9 页）\n", encoding="utf-8")
    assert validate_report.validate_report(run_dir)["passed"]


def test_amount_cannot_be_written_as_a_percentage(run_dir):
    prepared(run_dir, claim_type="fact", metric_ids=[], text="收入为 120000000000%")
    assert not validate_report.validate_report(run_dir)["passed"]


def test_wrong_citation_inside_claim_is_rejected(run_dir):
    prepared(run_dir, text="营业收入同比增长 20%（PDF 第 1 页）")
    assert not validate_report.validate_report(run_dir)["passed"]


def test_correct_citation_inside_claim_is_accepted(run_dir):
    prepared(run_dir, text="营业收入同比增长 20%（PDF 第 9 页）")
    assert validate_report.validate_report(run_dir)["passed"]


@pytest.mark.parametrize("line", ["## 营业收入为 999 元", "- 来源：营业收入为 999 元"])
def test_numeric_heading_or_metadata_cannot_hide_uncovered_value(run_dir, line):
    claim = prepared(run_dir)
    (run_dir / "analysis.md").write_text("# 分析\n" + line + "\n" + claim["text"], encoding="utf-8")
    assert not validate_report.validate_report(run_dir)["passed"]


@pytest.mark.parametrize("kind", ["inference", "company_explanation"])
def test_numeric_inference_or_company_explanation_needs_numeric_support(run_dir, kind):
    prepared(run_dir, claim_type=kind, metric_ids=[], text="营业收入为 999 元，因销量变动")
    assert not validate_report.validate_report(run_dir)["passed"]


def test_year_number_cannot_hide_wrong_amount(run_dir):
    prepared(run_dir, text="营业收入同比增长 20%，营业收入为 2024 元")
    change_json(run_dir, "financials.json", lambda data: data["facts"][0].update(
        period={"start": "2024-01-01", "end": "2024-12-31"}))
    assert not validate_report.validate_report(run_dir)["passed"]
