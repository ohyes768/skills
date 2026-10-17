from decimal import Decimal

from calculate_metrics import calculate_metrics


def build_core_document(make_fact) -> dict:
    facts = [
        make_fact("f-001", "revenue", "1200"),
        make_fact("f-002", "revenue", "1000", end="2023-12-31", start="2023-01-01"),
        make_fact("f-003", "net_profit_group", "120"),
        make_fact("f-004", "net_profit_group", "80", end="2023-12-31", start="2023-01-01"),
        make_fact("f-005", "net_profit_owners", "110", attribution="owners"),
        make_fact("f-006", "net_profit_owners", "70", attribution="owners",
                  end="2023-12-31", start="2023-01-01"),
        make_fact("f-007", "net_profit_deducted_owners", "90", attribution="owners"),
        make_fact("f-008", "cfo", "150"),
        make_fact("f-009", "capex_purchase_fixed_assets", "50"),
        make_fact("f-010", "total_assets", "2100", kind="instant", start=None),
        make_fact("f-011", "total_assets", "1900", kind="instant", start=None,
                  end="2023-12-31"),
        make_fact("f-012", "total_equity", "850", kind="instant", start=None),
        make_fact("f-013", "total_equity", "750", kind="instant", start=None,
                  end="2023-12-31"),
    ]
    return {"schema_version": 1, "document_sha256": "x", "facts": facts}


def metrics_by_id(result: dict) -> dict:
    return {m["metric_id"]: m for m in result["metrics"]}


def test_core_metrics_from_full_facts(make_fact):
    result = calculate_metrics(build_core_document(make_fact))
    metrics = metrics_by_id(result)
    assert metrics["revenue_yoy"]["value"] == Decimal("0.2")
    assert metrics["revenue_yoy"]["status"] == "computed"
    assert metrics["net_margin_group"]["value"] == Decimal("0.1")
    assert metrics["cfo_to_net_profit_group"]["value"] == Decimal("1.25")
    assert metrics["simplified_fcf"]["value"] == Decimal(100)
    assert metrics["roe_group_simple"]["value"] == Decimal("0.15")


def test_dupont_decomposition_consistent(make_fact):
    result = calculate_metrics(build_core_document(make_fact))
    metrics = metrics_by_id(result)
    roe = metrics["roe_dupont"]["value"]
    assert roe == Decimal("0.15")
    product = (
        metrics["dupont_net_margin"]["value"]
        * metrics["dupont_asset_turnover"]["value"]
        * metrics["dupont_equity_multiplier"]["value"]
    )
    assert product == roe


def test_zero_base_period_not_computed(make_fact):
    doc = build_core_document(make_fact)
    doc["facts"] = [f for f in doc["facts"] if f["fact_id"] != "f-002"]
    doc["facts"].append(make_fact("f-002", "revenue", "0", end="2023-12-31", start="2023-01-01"))
    result = calculate_metrics(doc)
    metric = metrics_by_id(result)["revenue_yoy"]
    assert metric["status"] == "not_applicable"
    assert "base" in metric["reason"].lower()


def test_negative_base_period_not_computed(make_fact):
    doc = build_core_document(make_fact)
    doc["facts"] = [f for f in doc["facts"] if f["fact_id"] != "f-002"]
    doc["facts"].append(
        make_fact("f-002", "revenue", "-100", end="2023-12-31", start="2023-01-01")
    )
    result = calculate_metrics(doc)
    metric = metrics_by_id(result)["revenue_yoy"]
    assert metric["status"] == "not_applicable"
    assert "negative" in metric["reason"].lower()


def test_missing_average_balance_blocks_roe(make_fact):
    doc = build_core_document(make_fact)
    doc["facts"] = [f for f in doc["facts"] if f["fact_id"] != "f-013"]
    result = calculate_metrics(doc)
    metric = metrics_by_id(result)["roe_group_simple"]
    assert metric["status"] == "insufficient_data"
    assert "average" in metric["reason"].lower()


def test_aggregation_mismatch_blocks_margin(make_fact):
    doc = build_core_document(make_fact)
    for f in doc["facts"]:
        if f["metric"] == "net_profit_group":
            f["period"]["aggregation"] = "single_period"
            f["period"]["start"] = "2024-10-01"
            f["period"]["frequency"] = "quarter"
    result = calculate_metrics(doc)
    metric = metrics_by_id(result)["net_margin_group"]
    assert metric["status"] == "insufficient_data"
    assert "aggregation" in metric["reason"].lower()


def test_parent_scope_does_not_leak_into_consolidated(make_fact):
    doc = build_core_document(make_fact)
    doc["facts"].append(make_fact("f-014", "revenue", "999", scope="parent"))
    result = calculate_metrics(doc)
    assert metrics_by_id(result)["revenue_yoy"]["value"] == Decimal("0.2")


def test_restated_conflict_reported_not_picked(make_fact):
    doc = build_core_document(make_fact)
    doc["facts"].append(make_fact("f-015", "revenue", "1190", basis="restated"))
    result = calculate_metrics(doc)
    metric = metrics_by_id(result)["revenue_yoy"]
    assert metric["status"] == "conflict"


def test_owner_attribution_not_substituted_for_group(make_fact):
    doc = build_core_document(make_fact)
    doc["facts"] = [f for f in doc["facts"] if f["metric"] != "net_profit_group"]
    result = calculate_metrics(doc)
    metric = metrics_by_id(result)["cfo_to_net_profit_group"]
    assert metric["status"] == "insufficient_data"


def test_receivable_turnover(make_fact):
    doc = build_core_document(make_fact)
    doc["facts"].extend(
        [
            make_fact("f-016", "accounts_receivable", "190", kind="instant", start=None),
            make_fact("f-017", "accounts_receivable", "150", kind="instant", start=None,
                      end="2023-12-31"),
        ]
    )
    result = calculate_metrics(doc)
    metric = metrics_by_id(result)["receivable_turnover"]
    assert metric["status"] == "computed"
    assert metric["value"] == (Decimal(1200) / Decimal(170))
