from copy import deepcopy
from decimal import Decimal

import pytest
from financial_schema import parse_amount, select_facts, validate_financials


@pytest.mark.parametrize(
    ("raw", "unit", "expected"),
    [
        ("1,234.50", "万元", Decimal("12345000.00")),
        ("(25.00)", "万元", Decimal("-250000.00")),
        ("0", "元", Decimal(0)),
        ("—", "元", None),
        ("", "元", None),
    ],
)
def test_parse_amount_preserves_value_and_missing(raw, unit, expected):
    assert parse_amount(raw, unit) == expected


def test_parse_amount_other_units():
    assert parse_amount("2", "亿元") == Decimal(200000000)
    assert parse_amount("3", "千元") == Decimal(3000)
    assert parse_amount("12.5", "元") == Decimal("12.5")
    assert parse_amount("12.5", "unknown_unit") is None


def make_fact(**overrides) -> dict:
    fact = {
        "fact_id": "f-0001",
        "metric": "revenue",
        "raw_label": "营业收入",
        "raw_value": "1,200,000,000.00",
        "raw_unit": "元",
        "value": "1200000000.00",
        "unit": "元",
        "currency": "CNY",
        "scope": "consolidated",
        "attribution": "group",
        "period": {
            "kind": "duration",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "frequency": "annual",
            "aggregation": "cumulative",
        },
        "basis": "as_reported",
        "evidence_ids": ["ev-0001"],
        "review_status": "verified",
        "missing_reason": None,
    }
    fact.update(overrides)
    return fact


def make_document(facts: list[dict]) -> dict:
    return {"schema_version": 1, "document_sha256": "abc", "facts": facts}


def test_valid_document_passes():
    assert validate_financials(make_document([make_fact()])) == []


def test_null_value_requires_missing_reason():
    fact = make_fact(value=None, raw_value="—", evidence_ids=[], missing_reason=None)
    errors = validate_financials(make_document([fact]))
    assert any(e["field"] == "missing_reason" for e in errors)


def test_missing_reason_for_missing_fact():
    fact = make_fact(value=None, raw_value="—", evidence_ids=[], missing_reason="not disclosed")
    assert validate_financials(make_document([fact])) == []


def test_value_fact_must_not_have_missing_reason():
    fact = make_fact(missing_reason="unused")
    errors = validate_financials(make_document([fact]))
    assert any(e["field"] == "missing_reason" for e in errors)


def test_value_requires_evidence_ids():
    fact = make_fact(evidence_ids=[])
    errors = validate_financials(make_document([fact]))
    assert any(e["field"] == "evidence_ids" for e in errors)


def test_float_value_rejected():
    fact = make_fact(value=1234.5)
    errors = validate_financials(make_document([fact]))
    assert any(e["field"] == "value" for e in errors)


def test_illegal_scope_rejected():
    fact = make_fact(scope="group_total")
    errors = validate_financials(make_document([fact]))
    assert any(e["field"] == "scope" for e in errors)


def test_illegal_attribution_rejected():
    fact = make_fact(attribution="minority")
    errors = validate_financials(make_document([fact]))
    assert any(e["field"] == "attribution" for e in errors)


def test_illegal_period_kind_rejected():
    fact = make_fact(period={"kind": "range", "start": None, "end": "2024-12-31",
                             "frequency": "annual", "aggregation": "cumulative"})
    errors = validate_financials(make_document([fact]))
    assert any(e["field"] == "period.kind" for e in errors)


def test_illegal_basis_rejected():
    fact = make_fact(basis="adjusted")
    errors = validate_financials(make_document([fact]))
    assert any(e["field"] == "basis" for e in errors)


def test_illegal_review_status_rejected():
    fact = make_fact(review_status="ok")
    errors = validate_financials(make_document([fact]))
    assert any(e["field"] == "review_status" for e in errors)


def test_bad_evidence_id_format_rejected():
    fact = make_fact(evidence_ids=["page nine"])
    errors = validate_financials(make_document([fact]))
    assert any(e["field"] == "evidence_ids" for e in errors)


def test_duplicate_fact_id_rejected():
    errors = validate_financials(make_document([make_fact(), make_fact()]))
    assert any("fact_id" in e["field"] for e in errors)


def build_doc() -> dict:
    period_2024 = {
        "kind": "duration",
        "start": "2024-01-01",
        "end": "2024-12-31",
        "frequency": "annual",
        "aggregation": "cumulative",
    }
    period_2023 = deepcopy(period_2024)
    period_2023.update({"start": "2023-01-01", "end": "2023-12-31"})
    return make_document(
        [
            make_fact(fact_id="f-0001", metric="revenue", value="1200000000.00", period=period_2024),
            make_fact(
                fact_id="f-0002",
                metric="revenue",
                scope="parent",
                value="1100000000.00",
                period=period_2024,
            ),
            make_fact(
                fact_id="f-0003",
                metric="net_profit_group",
                attribution="owners",
                value="110000000.00",
                period=period_2024,
            ),
            make_fact(fact_id="f-0004", metric="revenue", value="1000000000.00", period=period_2023),
        ]
    )


def test_select_facts_filters_all_dimensions():
    result = select_facts(build_doc(), "revenue", "consolidated", "group", "cumulative")
    assert [f["fact_id"] for f in result] == ["f-0001", "f-0004"]


def test_select_facts_returns_conflicting_candidates_not_first():
    doc = build_doc()
    restated = make_fact(
        fact_id="f-0005",
        metric="revenue",
        value="1190000000.00",
        basis="restated",
        period={
            "kind": "duration",
            "start": "2024-01-01",
            "end": "2024-12-31",
            "frequency": "annual",
            "aggregation": "cumulative",
        },
    )
    doc["facts"].append(restated)
    result = select_facts(doc, "revenue", "consolidated", "group", "cumulative")
    assert len(result) == 3
    assert {f["basis"] for f in result} == {"as_reported", "restated"}
