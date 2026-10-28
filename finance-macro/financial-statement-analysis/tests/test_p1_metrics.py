"""P1 回归：财务事实必须在同一报告期间和可用状态下配对。"""

from copy import deepcopy

import pytest
from calculate_metrics import calculate_metrics
from financial_schema import validate_financials
from test_metrics import build_core_document, metrics_by_id
from test_reconciliation import build_cash_document, cash_check


def test_prior_profit_cannot_substitute_for_missing_current_profit(make_fact):
    document = build_core_document(make_fact)
    document["facts"] = [f for f in document["facts"] if f["fact_id"] != "f-003"]
    metric = metrics_by_id(calculate_metrics(document))["net_margin_group"]
    assert metric["status"] == "insufficient_data"


@pytest.mark.parametrize(("field", "value"), [("currency", "USD"), ("unit", "万元"),
                                               ("basis", "restated")])
def test_ratio_rejects_measurement_mismatch(make_fact, field, value):
    document = build_core_document(make_fact)
    document["facts"][0][field] = value
    assert metrics_by_id(calculate_metrics(document))["net_margin_group"]["status"] != "computed"


def test_yoy_requires_prior_year_same_period(make_fact):
    document = build_core_document(make_fact)
    prior = document["facts"][1]
    prior["period"].update(start="2024-01-01", end="2024-06-30", frequency="half_year")
    assert metrics_by_id(calculate_metrics(document))["revenue_yoy"]["status"] == "insufficient_data"


def test_group_roe_rejects_parent_owner_equity(make_fact):
    document = build_core_document(make_fact)
    for fact in document["facts"]:
        if fact["metric"] == "total_equity":
            fact.update(scope="parent", attribution="owners")
    metrics = metrics_by_id(calculate_metrics(document))
    assert metrics["roe_group_simple"]["status"] == "insufficient_data"
    assert metrics["roe_dupont"]["status"] != "computed"


def test_parent_balances_do_not_create_false_group_conflict(make_fact):
    document = build_core_document(make_fact)
    document["facts"].append(make_fact("f-parent", "total_equity", "1", kind="instant",
                                       start=None, scope="parent", attribution="owners"))
    assert metrics_by_id(calculate_metrics(document))["roe_group_simple"]["status"] == "computed"


def test_average_balance_must_match_flow_opening_date(make_fact):
    document = build_core_document(make_fact)
    for fact in document["facts"]:
        if fact["fact_id"] == "f-013":
            fact["period"]["end"] = "2024-06-30"
    assert metrics_by_id(calculate_metrics(document))["roe_group_simple"]["status"] == "insufficient_data"


@pytest.mark.parametrize("metric", ["revenue", "net_profit_group", "cfo", "total_assets",
                                    "total_equity", "capex_purchase_fixed_assets"])
def test_legal_null_facts_produce_missing_status_without_crashing(make_fact, metric):
    document = build_core_document(make_fact)
    for fact in document["facts"]:
        if fact["metric"] == metric:
            fact.update(value=None, raw_value="-", review_status="missing",
                        missing_reason="not disclosed")
    assert validate_financials(document) == []
    result = calculate_metrics(document)
    assert any(m["status"] == "insufficient_data" for m in result["metrics"])


@pytest.mark.parametrize(("review_status", "expected"), [("conflict", "conflict"),
                                                        ("ambiguous", "insufficient_data")])
def test_unreviewed_facts_cannot_produce_computed_metrics(make_fact, review_status, expected):
    document = build_core_document(make_fact)
    document["facts"][0]["review_status"] = review_status
    metrics = metrics_by_id(calculate_metrics(document))
    assert metrics["revenue_yoy"]["status"] == expected
    assert metrics["net_margin_group"]["status"] == expected


def test_cash_reconciliation_uses_consolidated_balances(make_fact):
    document = build_cash_document(make_fact)
    for fact in document["facts"]:
        if fact["metric"] == "cash_equivalents":
            fact.update(scope="parent", attribution="owners")
    assert cash_check(calculate_metrics(document))["status"] != "passed"


def test_comparison_conflict_not_dependent_on_input_order(make_fact):
    document = build_core_document(make_fact)
    other = deepcopy(document["facts"][1])
    other.update(fact_id="prior-conflict", value="900")
    document["facts"].append(other)
    assert metrics_by_id(calculate_metrics(document))["revenue_yoy"]["status"] == "conflict"


def test_explicit_report_period_blocks_all_historical_fallback(make_fact):
    document = build_core_document(make_fact)
    document["period"] = {"kind": "duration", "start": "2025-01-01", "end": "2025-12-31",
                          "frequency": "annual", "aggregation": "cumulative"}
    assert metrics_by_id(calculate_metrics(document))["net_margin_group"]["status"] == "insufficient_data"


def test_dupont_preserves_component_conflict(make_fact):
    document = build_core_document(make_fact)
    document["facts"][0]["review_status"] = "conflict"
    assert metrics_by_id(calculate_metrics(document))["roe_dupont"]["status"] == "conflict"


def test_equity_multiplier_does_not_require_revenue(make_fact):
    document = build_core_document(make_fact)
    document["facts"] = [f for f in document["facts"] if f["metric"] != "revenue"]
    metric = metrics_by_id(calculate_metrics(document))["dupont_equity_multiplier"]
    assert metric["status"] == "computed"
    assert str(metric["value"]) == "2.5"
