from decimal import Decimal

from calculate_metrics import calculate_metrics


def build_cash_document(make_fact, closing="107") -> dict:
    facts = [
        make_fact("f-c01", "cash_equivalents", "100", kind="instant", start=None,
                  end="2023-12-31"),
        make_fact("f-c02", "cash_equivalents", closing, kind="instant", start=None),
        make_fact("f-c03", "cfo", "20"),
        make_fact("f-c04", "cfi", "-10"),
        make_fact("f-c05", "cff", "-5"),
        make_fact("f-c06", "fx_effect_on_cash", "2"),
    ]
    return {"schema_version": 1, "document_sha256": "x", "facts": facts}


def cash_check(result: dict) -> dict:
    return {c["check_id"]: c for c in result["validation"]}["cash_reconciliation"]


def test_cash_reconciliation_passes(make_fact):
    result = calculate_metrics(build_cash_document(make_fact))
    check = cash_check(result)
    assert check["status"] == "passed"
    assert Decimal(check["residual"]) == Decimal(0)


def test_monetary_funds_not_substituted_for_cash_equivalents(make_fact):
    doc = build_cash_document(make_fact)
    doc["facts"].append(
        make_fact("f-c07", "monetary_funds", "130", kind="instant", start=None)
    )
    check = cash_check(calculate_metrics(doc))
    assert check["status"] == "passed"
    assert "f-c07" not in check["input_fact_ids"]


def test_cash_reconciliation_fails_beyond_tolerance(make_fact):
    result = calculate_metrics(build_cash_document(make_fact, closing="110"))
    check = cash_check(result)
    assert check["status"] == "failed"
    assert Decimal(check["residual"]) == Decimal(3)
    assert Decimal(check["tolerance"]) == Decimal("0.5")


def test_tolerance_follows_input_precision(make_fact):
    doc = build_cash_document(make_fact)
    for f in doc["facts"]:
        if f["value"] is not None:
            f["value"] = f["value"] + ".00"
    result = calculate_metrics(doc)
    check = cash_check(result)
    assert check["status"] == "passed"
    assert Decimal(check["tolerance"]) == Decimal("0.005")
