import copy

from artifacts import write_json
from build_financials import build_financials_structured


def archive(run_dir):
    write_json(
        run_dir / "document.json",
        {
            "stock_code": "600519",
            "company_name": "测试",
            "currency": "CNY",
            "period": {
                "kind": "duration",
                "start": "2024-01-01",
                "end": "2024-12-31",
                "frequency": "annual",
                "aggregation": "cumulative",
            },
        },
    )
    reports = {}
    for day in ("2024-12-31", "2023-12-31"):
        reports[day] = {
            kind: [
                {
                    "SECUCODE": "600519.SH",
                    "SECURITY_CODE": "600519",
                    "REPORT_DATE": day + " 00:00:00",
                    "TOTAL_OPERATE_INCOME": "100.01",
                    "OPERATE_COST": "40",
                    "END_CCE": "20",
                }
            ]
            for kind in ("income", "balance", "cashflow")
        }
    data = {
        "security_code": "600519",
        "secucode": "600519.SH",
        "source": "structured_eastmoney",
        "reports": reports,
        "response_sha256": {f"{day}/{kind}": "a" * 64 for day in reports for kind in reports[day]},
    }
    write_json(run_dir / "structured_financials.json", data)
    return data


def test_build_and_provenance_without_document_evidence(run_dir):
    from source_provenance import citation_text, source_errors, source_refs

    data = archive(run_dir)
    financials, mapping = build_financials_structured(run_dir, data)
    assert not mapping["issues"]
    assert source_errors(run_dir, financials) == []
    gross = next(
        f
        for f in financials["facts"]
        if f["metric"] == "gross_profit" and f["period"]["end"] == "2024-12-31"
    )
    assert gross["value"] == "60.01"
    refs = source_refs(financials["facts"], [gross["fact_id"]])
    assert len(refs) == 2
    assert "2024-12-31" in citation_text(refs)
    mutated = copy.deepcopy(financials)
    next(f for f in mutated["facts"] if f["value"] is not None)["value"] = "999"
    assert source_errors(run_dir, mutated)


def test_wrong_identity_and_nonfinite_fail_closed(run_dir):
    data = archive(run_dir)
    data["reports"]["2024-12-31"]["income"][0]["SECUCODE"] = "000001.SZ"
    result, mapping = build_financials_structured(run_dir, data)
    assert result is None and mapping["issues"]
    data = archive(run_dir)
    data["reports"]["2024-12-31"]["income"][0]["OPERATE_COST"] = "NaN"
    write_json(run_dir / "structured_financials.json", data)
    result, mapping = build_financials_structured(run_dir, data)
    assert result is None and mapping["issues"]


def test_missing_values_and_comparison_are_nullable(run_dir):
    from source_provenance import source_errors

    data = archive(run_dir)
    data["reports"].pop("2023-12-31")
    data["reports"]["2024-12-31"]["income"][0]["OPERATE_COST"] = None
    write_json(run_dir / "structured_financials.json", data)
    result, mapping = build_financials_structured(run_dir, data)
    assert not mapping["issues"] and mapping["warnings"]
    assert source_errors(run_dir, result) == []
    assert (
        next(f for f in result["facts"] if f["fact_id"] == "fact-cost_of_sales-current")["value"]
        is None
    )
    assert next(f for f in result["facts"] if f["fact_id"] == "fact-revenue-prior")["value"] is None
    assert all(f["value"] is None for f in result["facts"] if f["metric"] == "fx_effect_on_cash")


def test_opening_cash_uses_current_begin_only_when_prior_end_unavailable(run_dir):
    from source_provenance import source_errors

    data = archive(run_dir)
    data["reports"]["2024-12-31"]["cashflow"][0]["BEGIN_CCE"] = "12.50"
    data["reports"]["2023-12-31"]["cashflow"][0]["END_CCE"] = None
    write_json(run_dir / "structured_financials.json", data)
    result, _ = build_financials_structured(run_dir, data)
    opening = next(f for f in result["facts"] if f["fact_id"] == "fact-cash_equivalents-opening")
    assert opening["value"] == "12.50"
    assert opening["source_ref"]["field"] == "BEGIN_CCE"
    assert opening["period"]["end"] == "2023-12-31"
    assert source_errors(run_dir, result) == []


def test_provenance_rejects_ref_dimensions_derived_and_archive_tampering(run_dir):
    from source_provenance import source_errors

    data = archive(run_dir)
    result, _ = build_financials_structured(run_dir, data)
    for field, value in [("scope", "parent"), ("unit", "万元"), ("period", {}), ("source_ref", {})]:
        mutated = copy.deepcopy(result)
        mutated["facts"][0][field] = value
        assert source_errors(run_dir, mutated)
    mutated = copy.deepcopy(result)
    gross = next(f for f in mutated["facts"] if f["metric"] == "gross_profit")
    gross["input_fact_ids"] = [gross["fact_id"]]
    assert source_errors(run_dir, mutated)
    data["reports"]["2024-12-31"]["income"][0]["TOTAL_OPERATE_INCOME"] = "900"
    write_json(run_dir / "structured_financials.json", data)
    assert source_errors(run_dir, result)
