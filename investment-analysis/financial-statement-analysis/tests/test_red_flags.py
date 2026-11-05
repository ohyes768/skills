"""程序化红旗检测：metrics.json.red_flags 的判定、恒定输出与分层隔离。"""

from calculate_metrics import calculate_metrics
from financial_schema import resolve_metric_label


def flags_by_id(result: dict) -> dict:
    return {f["flag_id"]: f for f in result["red_flags"]}


def build(make_fact, overrides: dict | None = None) -> dict:
    facts = [
        make_fact("f-r01", "revenue", "1100"),
        make_fact("f-r02", "revenue", "1000", end="2023-12-31", start="2023-01-01"),
        make_fact("f-r03", "net_profit_group", "100"),
        make_fact("f-r04", "net_profit_group", "120", end="2023-12-31", start="2023-01-01"),
        make_fact("f-r05", "net_profit_owners", "92", attribution="owners"),
        make_fact("f-r06", "net_profit_owners", "110", attribution="owners",
                  end="2023-12-31", start="2023-01-01"),
        make_fact("f-r07", "cfo", "150"),
        make_fact("f-r08", "monetary_funds", "100", kind="instant", start=None),
        make_fact("f-r09", "short_term_borrowings", "50", kind="instant", start=None),
        make_fact("f-r10", "long_term_borrowings", "50", kind="instant", start=None),
        make_fact("f-r11", "accounts_receivable", "110", kind="instant", start=None),
        make_fact("f-r12", "accounts_receivable", "100", kind="instant", start=None,
                  end="2023-12-31"),
        make_fact("f-r13", "inventory", "88", kind="instant", start=None),
        make_fact("f-r14", "inventory", "80", kind="instant", start=None, end="2023-12-31"),
        make_fact("f-r15", "goodwill", "100", kind="instant", start=None),
        make_fact("f-r16", "total_equity_owners", "800", kind="instant", start=None,
                  attribution="owners"),
        make_fact("f-r17", "prepayments", "11", kind="instant", start=None),
        make_fact("f-r18", "prepayments", "10", kind="instant", start=None, end="2023-12-31"),
        make_fact("f-r19", "construction_in_progress", "100", kind="instant", start=None),
        make_fact("f-r20", "fixed_assets", "400", kind="instant", start=None),
    ]
    if overrides:
        for fact in facts:
            if fact["fact_id"] in overrides:
                fact["value"] = overrides[fact["fact_id"]]
    return {"schema_version": 1, "source_sha256": "x", "facts": facts}


EXPECTED_FLAGS = {
    "dual_high_cash_debt", "receivable_outpacing_revenue", "inventory_sudden_rise",
    "negative_cfo_positive_profit", "minority_interest_anomaly", "goodwill_heavy",
    "prepayment_surge", "construction_not_converting",
}


def test_red_flags_constant_ids_and_clear_baseline(make_fact):
    """基线健康数据：8 个红旗恒定输出且全部 clear。"""
    result = calculate_metrics(build(make_fact))
    flags = flags_by_id(result)
    assert set(flags) == EXPECTED_FLAGS
    assert all(f["status"] == "clear" for f in flags.values()), flags


def test_dual_high_cash_debt_flagged(make_fact):
    result = calculate_metrics(build(make_fact, {
        "f-r08": "400", "f-r09": "350", "f-r10": "100"}))
    flag = flags_by_id(result)["dual_high_cash_debt"]
    assert flag["status"] == "flagged"
    assert "0.30" in flag["threshold"]


def test_receivable_outpacing_revenue_flagged(make_fact):
    result = calculate_metrics(build(make_fact, {
        "f-r11": "200", "f-r12": "100"}))
    assert flags_by_id(result)["receivable_outpacing_revenue"]["status"] == "flagged"


def test_inventory_sudden_rise_flagged(make_fact):
    result = calculate_metrics(build(make_fact, {"f-r13": "240"}))
    assert flags_by_id(result)["inventory_sudden_rise"]["status"] == "flagged"


def test_negative_cfo_positive_profit_flagged(make_fact):
    result = calculate_metrics(build(make_fact, {"f-r07": "-50"}))
    assert flags_by_id(result)["negative_cfo_positive_profit"]["status"] == "flagged"


def test_minority_interest_anomaly_flagged(make_fact):
    result = calculate_metrics(build(make_fact, {"f-r05": "50"}))
    assert flags_by_id(result)["minority_interest_anomaly"]["status"] == "flagged"


def test_goodwill_heavy_flagged(make_fact):
    result = calculate_metrics(build(make_fact, {"f-r15": "300"}))
    assert flags_by_id(result)["goodwill_heavy"]["status"] == "flagged"


def test_prepayment_surge_flagged(make_fact):
    result = calculate_metrics(build(make_fact, {"f-r17": "100"}))
    assert flags_by_id(result)["prepayment_surge"]["status"] == "flagged"


def test_construction_not_converting_flagged(make_fact):
    result = calculate_metrics(build(make_fact, {"f-r19": "300"}))
    assert flags_by_id(result)["construction_not_converting"]["status"] == "flagged"


def test_missing_facts_yield_insufficient_not_absent(make_fact):
    """事实不足的红旗输出 insufficient_data，而不是从列表消失——模型逐项标注依赖恒定清单。"""
    doc = build(make_fact)
    keep = {"f-r01", "f-r02"}
    doc["facts"] = [f for f in doc["facts"] if f["fact_id"] in keep]
    result = calculate_metrics(doc)
    flags = flags_by_id(result)
    assert set(flags) == EXPECTED_FLAGS
    assert all(f["status"] == "insufficient_data" for f in flags.values())


def test_red_flags_are_separate_from_validation(make_fact):
    """红旗是风险发现层：触发不进入 validation 检查，勾稽结果不受影响。"""
    result = calculate_metrics(build(make_fact, {
        "f-r08": "400", "f-r09": "350", "f-r10": "100"}))
    assert any(f["status"] == "flagged" for f in result["red_flags"])
    check_ids = {c["check_id"] for c in result["validation"]}
    assert not any("flag" in cid for cid in check_ids)
    assert result["validation"][0]["status"] in ("passed", "not_applicable", "failed")


def test_new_metric_contracts_resolved():
    assert resolve_metric_label("prepayments", None) == "prepayments"
    assert resolve_metric_label("预付款项", None) == "prepayments"
    assert resolve_metric_label("construction_in_progress", None) == "construction_in_progress"
    assert resolve_metric_label("在建工程", None) == "construction_in_progress"
