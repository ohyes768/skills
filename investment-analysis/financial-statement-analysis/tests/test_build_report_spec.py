"""build_report_spec 的映射规则测试。

核心不变量：骨架里的每个 FACT_* 占位都必须能解析到本次 compute 的真实 fact_id，
或者被明确丢弃（本次确实没有该科目）——绝不生成悬空绑定。
"""

import json
from pathlib import Path

import pytest
from build_report_spec import (
    PLACEHOLDER_TO_METRIC,
    _fix_decline_formats,
    build_spec,
)

ROOT = Path(__file__).resolve().parents[1]
SKELETON = ROOT / "references" / "report-spec-skeleton.json"


def _fact(fact_id, metric, period, scope="consolidated", attribution="not_applicable",
          kind="duration", end=None, start=None):
    return {
        "fact_id": fact_id,
        "metric": metric,
        "raw_label": metric,
        "raw_value": "1",
        "raw_unit": "元",
        "value": "1",
        "unit": "元",
        "currency": "CNY",
        "scope": scope,
        "attribution": attribution,
        "period": {"kind": kind, "start": start, "end": end, "frequency": "half_year",
                   "aggregation": "cumulative"},
        "basis": "as_reported",
        "source_ref": {},
        "review_status": "verified",
        "missing_reason": None,
        "source": "structured",
    }


@pytest.fixture
def run_dir(tmp_path):
    """构造一个最小可用的 run 目录：facts + metrics + document。"""
    facts = [
        _fact("f-cur-rev", "revenue", None, end="2026-06-30", start="2026-01-01"),
        _fact("f-prev-rev", "revenue", None, end="2025-06-30", start="2025-01-01"),
        _fact("f-cur-np", "net_profit_group", None, end="2026-06-30", start="2026-01-01",
              attribution="group"),
        _fact("f-prev-np", "net_profit_group", None, end="2025-06-30", start="2025-01-01",
              attribution="group"),
        _fact("f-cur-ta", "total_assets", None, end="2026-06-30", kind="instant"),
        _fact("f-prev-ta", "total_assets", None, end="2025-12-31", kind="instant"),
    ]
    (tmp_path / "financials.json").write_text(
        json.dumps({"schema_version": 1, "currency": "CNY", "facts": facts}), encoding="utf-8")
    (tmp_path / "metrics.json").write_text(
        json.dumps({"schema_version": 1, "metrics": [
            {"metric_id": "revenue_yoy", "value": "0.1", "status": "computed",
             "formula": "", "input_fact_ids": ["f-cur-rev"], "reason": None},
        ]}), encoding="utf-8")
    (tmp_path / "document.json").write_text(
        json.dumps({"company_name": "测试公司", "stock_code": "600000",
                    "period": {"kind": "duration", "start": "2026-01-01", "end": "2026-06-30",
                               "frequency": "half_year", "aggregation": "cumulative"}}),
        encoding="utf-8")
    return tmp_path


def _all_bindings(node, out=None):
    out = [] if out is None else out
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("fact_id", "metric_id") and isinstance(value, str):
                out.append(value)
            else:
                _all_bindings(value, out)
    elif isinstance(node, list):
        for item in node:
            _all_bindings(item, out)
    return out


def test_generated_spec_has_no_placeholder_bindings(run_dir):
    """生成结果里不能再出现 FACT_* 占位。"""
    skeleton = json.loads(SKELETON.read_text(encoding="utf-8"))
    spec, _ = build_spec(run_dir, skeleton)
    bindings = _all_bindings(spec)
    stale = [b for b in bindings if b.startswith("FACT_")]
    assert not stale, f"未解析的占位: {stale}"


def test_bindings_reference_known_facts_and_metrics(run_dir):
    """所有绑定必须指向 financials / metrics 里真实存在的条目。"""
    skeleton = json.loads(SKELETON.read_text(encoding="utf-8"))
    spec, _ = build_spec(run_dir, skeleton)
    facts = {f["fact_id"] for f in
             json.loads((run_dir / "financials.json").read_text(encoding="utf-8"))["facts"]}
    metrics = {m["metric_id"] for m in
               json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))["metrics"]}
    for binding in _all_bindings(spec):
        if binding.startswith("FACT_"):
            continue
        if binding in metrics:
            continue
        assert binding in facts, f"绑定指向不存在的条目: {binding}"


def test_missing_facts_drop_rows_instead_of_zero_filling(run_dir):
    """本次没有的科目整行删除，不得填零占位。"""
    skeleton = json.loads(SKELETON.read_text(encoding="utf-8"))
    spec, notes = build_spec(run_dir, skeleton)
    labels = []
    for section in spec["sections"]:
        for row in section.get("table", {}).get("rows", []):
            labels.append(row.get("label"))
    # 商誉 / 借款在本次 facts 中不存在，行必须消失
    assert "商誉" not in labels
    assert "短期借款" not in labels
    assert any("丢弃行" in note for note in notes)


def test_duration_prev_is_prior_year_same_period(run_dir):
    """duration 科目的比较期是上年同期，不是上年末。"""
    skeleton = json.loads(SKELETON.read_text(encoding="utf-8"))
    spec, _ = build_spec(run_dir, skeleton)
    facts = {f["fact_id"]: f for f in
             json.loads((run_dir / "financials.json").read_text(encoding="utf-8"))["facts"]}
    revenue_bindings = set()
    for section in spec["sections"]:
        for row in section.get("table", {}).get("rows", []):
            if row.get("label") == "营业收入":
                revenue_bindings = {c["fact_id"] for c in row["cells"] if isinstance(c, dict)}
    assert "f-prev-rev" in revenue_bindings
    assert facts["f-prev-rev"]["period"]["end"] == "2025-06-30"


def test_instant_prev_is_prior_year_end(run_dir):
    """instant 科目的比较期是上年末。"""
    skeleton = json.loads(SKELETON.read_text(encoding="utf-8"))
    spec, _ = build_spec(run_dir, skeleton)
    facts = {f["fact_id"]: f for f in
             json.loads((run_dir / "financials.json").read_text(encoding="utf-8"))["facts"]}
    asset_bindings = set()
    for section in spec["sections"]:
        for row in section.get("table", {}).get("rows", []):
            if row.get("label") == "资产总计":
                asset_bindings = {c["fact_id"] for c in row["cells"] if isinstance(c, dict)}
    assert "f-prev-ta" in asset_bindings
    assert facts["f-prev-ta"]["period"]["end"] == "2025-12-31"


def test_placeholder_metric_map_covers_skeleton_placeholders():
    """骨架里出现的每个占位名都必须在映射表里，否则会被静默丢弃。"""
    skeleton = json.loads(SKELETON.read_text(encoding="utf-8"))
    import re
    text = json.dumps(skeleton, ensure_ascii=False)
    placeholders = set(re.findall(r"FACT_([A-Z0-9_]+?)_(?:CUR|PREV|OPEN|CLOSE)", text))
    unknown = {p for p in placeholders if p not in PLACEHOLDER_TO_METRIC}
    assert not unknown, f"映射表缺少: {sorted(unknown)}"


def test_decline_format_switches_to_percent_when_metric_positive():
    """decline_* 遇到正值必须改用 percent*，否则渲染阻塞。"""
    metrics = {"revenue_yoy": {"metric_id": "revenue_yoy", "value": "0.25", "status": "computed"}}
    node = [{"metric_id": "revenue_yoy", "format": "decline_percent2"}]
    _fix_decline_formats(node, metrics)
    assert node[0]["format"] == "percent2"


def test_decline_format_kept_when_metric_nonpositive():
    """指标为负时保留 decline_*。"""
    metrics = {"revenue_yoy": {"metric_id": "revenue_yoy", "value": "-0.25", "status": "computed"}}
    node = [{"metric_id": "revenue_yoy", "format": "decline_percent2"}]
    _fix_decline_formats(node, metrics)
    assert node[0]["format"] == "decline_percent2"


def test_table_row_cells_length_matches_columns(run_dir):
    """表格契约：len(cells) == len(columns) - 1。"""
    skeleton = json.loads(SKELETON.read_text(encoding="utf-8"))
    spec, _ = build_spec(run_dir, skeleton)
    for section in spec["sections"]:
        table = section.get("table")
        if not table:
            continue
        for row in table.get("rows", []):
            assert len(row["cells"]) == len(table["columns"]) - 1, row.get("label")


def test_placeholder_paragraphs_are_flagged_for_agent(run_dir):
    """骨架提示语必须被标记为待改写，否则报告里会留下「这里写……」这类占位。"""
    skeleton = json.loads(SKELETON.read_text(encoding="utf-8"))
    spec, _ = build_spec(run_dir, skeleton)
    todo = spec.get("_paragraphs_todo")
    assert todo, "待改写段落清单缺失"
    anchors = {item["anchor"] for item in todo}
    assert "## 核心结论" in anchors
    for item in todo:
        assert item["index"] >= 1
        assert item["hint"]


def test_todo_list_is_top_level_not_inside_sections(run_dir):
    """待办清单放顶层——塞进 section 可能被渲染/校验契约拒绝。"""
    skeleton = json.loads(SKELETON.read_text(encoding="utf-8"))
    spec, _ = build_spec(run_dir, skeleton)
    for section in spec["sections"]:
        assert "_paragraphs_todo" not in section
