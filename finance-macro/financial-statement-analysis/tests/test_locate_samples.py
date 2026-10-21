"""locate_samples：抽查单候选定位回归。"""

import json

import locate_samples
from test_build_financials import prepare_build_run, structured_doc, write_json_file


def test_candidates_generated_with_line_and_values(run_dir):
    """标签命中即给出 evidence_id/line/数值候选；同名标签多行全列出。"""
    prepare_build_run(run_dir)
    result = locate_samples.locate_samples(run_dir, metrics=["net_profit_owners"])
    hits = result["candidates"]["net_profit_owners"]
    assert hits, "label present in ev-0002 text must be located"
    first = hits[0]
    assert first["evidence_id"] == "ev-0002"
    assert first["line"] == 1
    assert "123456789.00" in first["values"]
    assert first["suggested_period_ref"] == "current"


def test_match_structured_flagged_against_eastmoney(run_dir):
    """结构化数据存在时，候选值与之比对并标注 match_structured。"""
    prepare_build_run(run_dir)
    write_json_file(run_dir / "structured_financials.json", structured_doc())
    result = locate_samples.locate_samples(run_dir, metrics=["net_profit_owners"])
    hits = result["candidates"]["net_profit_owners"]
    assert all(hit["match_structured"] is False for hit in hits), (
        "fixture text value differs from structured value")


def test_unlocated_metric_reported(run_dir):
    prepare_build_run(run_dir)
    result = locate_samples.locate_samples(run_dir, metrics=["goodwill"])
    assert "goodwill" in result["not_located"]
    assert "goodwill" not in result["candidates"]


def test_cli_single_json_line(run_dir, capsys):
    prepare_build_run(run_dir)
    code = locate_samples.main(["--run-dir", str(run_dir), "--metrics", "net_profit_owners"])
    assert code == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["status"] == "ok"
    assert "net_profit_owners" in payload["artifacts"]["candidates"]


def test_all_recommended_metrics_located_on_real_layout(run_dir):
    """豪鹏式逐行布局上，建议清单的全部科目都能定位（除 fixture 缺失行）。"""
    prepare_build_run(run_dir)
    lines = [
        "[p.59] 一、营业总收入", "[p.59] 230,730,296.15", "[p.59] 319,200,000.00",
        "[p.59] 其中：营业成本", "[p.59] 158,078,681.91", "[p.59] 230,000,000.00",
        "[p.59] 净利润", "[p.59] -84,580,045.43", "[p.59] 0.00",
        "[p.59] 归属于母公司股东的净利润", "[p.59] -77,252,801.33", "[p.59] 0.00",
        "[p.59] 销售费用", "[p.59] 53,641,659.79", "[p.59] 82,952,174.94",
        "[p.59] 管理费用", "[p.59] 35,796,096.17", "[p.59] 39,774,641.80",
        "[p.59] 财务费用", "[p.59] 2,295,922.34", "[p.59] 0.00",
        "[p.59] 研发费用", "[p.59] 31,902,624.45", "[p.59] 84,084,350.93",
        "[p.59] 二、营业利润", "[p.59] -91,076,161.25", "[p.59] 95,332,000.00",
        "[p.59] 三、利润总额", "[p.59] -90,845,082.64", "[p.59] 94,716,000.00",
        "[p.59] 减：所得税费用", "[p.59] -6,265,037.21", "[p.59] 11,610,593.96",
    ]
    (run_dir / "excerpts" / "ev-0002.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    result = locate_samples.locate_samples(run_dir)
    located = set(result["candidates"])
    assert {"revenue", "cost_of_sales", "net_profit_group", "net_profit_owners"} <= located
    balance_items = {"total_assets", "monetary_funds", "cash_equivalents",
                     "cfo", "fx_effect_on_cash"}
    assert not (balance_items & located), "items absent from fixture lines must stay unlocated"
