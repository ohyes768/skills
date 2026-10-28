"""Map archived F10 consolidated statements into exact, traceable facts."""

from __future__ import annotations

import argparse
import hashlib
import re
from datetime import date, timedelta
from pathlib import Path

from artifacts import emit_status, read_json, write_json
from fact_selection import prior_year
from fetch_structured import REPORTS, FetchStructuredError, secucode, validate_rows
from financial_schema import METRIC_CONTRACTS, STRUCTURED_FIELD_MAP, validate_financials
from source_provenance import decimal_value


def build_financials_structured(run_dir: Path, structured: dict) -> tuple[dict | None, dict]:
    run_dir = Path(run_dir)
    document = read_json(run_dir / "document.json")
    period = document.get("period") or {}
    validation = {
        "schema_version": 1,
        "issues": [],
        "warnings": [],
        "data_source": "structured",
        "mapped_facts": 0,
    }

    def issue(message):
        validation["issues"].append({"error": message})

    try:
        start, end = period["start"], period["end"]
        if (
            period.get("kind") != "duration"
            or start != f"{end[:4]}-01-01"
            or period.get("aggregation") != "cumulative"
            or period.get("frequency") not in {"annual", "half_year", "quarter"}
        ):
            raise ValueError("invalid target cumulative reporting period")
        date.fromisoformat(end)
        if document.get("currency") != "CNY":
            raise ValueError("F10 source requires CNY currency")
        if structured.get("source") != "structured_eastmoney":
            raise ValueError("unsupported structured source")
        opening = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
        code = document["stock_code"].split(".")[0]
        if structured.get("security_code", "").split(".")[0] != code:
            raise ValueError("archive security identity mismatch")
        reports = structured.get("reports") or {}
        for day, kinds in reports.items():
            for kind, rows in kinds.items():
                if kind not in REPORTS:
                    raise ValueError("unknown report kind")
                validate_rows(rows, secucode(code), day)
                digest = structured.get("response_sha256", {}).get(f"{day}/{kind}", "")
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError("missing or invalid response digest")
        archive = read_json(run_dir / "structured_financials.json")
        if archive.get("reports") != structured.get("reports"):
            # Decimal values and serialized decimal strings compare through normalization below.
            import json

            from artifacts import _json_default

            if json.loads(
                json.dumps(structured.get("reports"), default=_json_default)
            ) != archive.get("reports"):
                raise ValueError("provided rows differ from saved archive")
    except (KeyError, TypeError, ValueError, FetchStructuredError) as exc:
        issue(str(exc))
        return None, validation
    facts = []

    def fact(metric, ref, kind, field):
        contract = METRIC_CONTRACTS[metric]
        instant = contract["period_kind"] == "instant"
        day = {"current": end, "prior": prior_year(end), "closing": end, "opening": opening}[ref]
        row_date = day
        rows = reports.get(day, {}).get(kind, [])
        if (
            metric == "cash_equivalents"
            and ref == "opening"
            and (not rows or rows[0].get(field) is None)
        ):
            rows = reports.get(end, {}).get(kind, [])
            row_date, field = end, "BEGIN_CCE"
        row = rows[0] if rows else {}
        try:
            value = decimal_value(row.get(field))
        except ValueError as exc:
            issue(f"{metric} {ref}: {exc}")
            value = None
        fact_period = {
            "kind": "instant" if instant else "duration",
            "start": None if instant else (prior_year(start) if ref == "prior" else start),
            "end": day,
            "frequency": period["frequency"],
            "aggregation": "instant" if instant else period["aggregation"],
        }
        source_ref = {
            "security_code": code,
            "report_kind": kind,
            "report_name": REPORTS[kind],
            "report_date": row_date,
            "field": field,
            "response_sha256": structured.get("response_sha256", {}).get(f"{row_date}/{kind}"),
        }
        result = {
            "fact_id": f"fact-{metric}-{ref}",
            "metric": metric,
            "raw_label": field,
            "raw_value": None if value is None else str(value),
            "raw_unit": "元",
            "value": None if value is None else str(value),
            "unit": "元",
            "currency": document["currency"],
            "scope": "consolidated",
            "attribution": contract["attribution"],
            "period": fact_period,
            "basis": "as_reported",
            "review_status": "missing" if value is None else "verified",
            "missing_reason": "not disclosed in structured source" if value is None else None,
            "source": "structured",
            "source_ref": source_ref,
        }
        if value is None:
            validation["warnings"].append({"error": f"{metric} {ref}: not disclosed"})
        facts.append(result)
        return result

    for metric in METRIC_CONTRACTS:
        if metric == "gross_profit":
            continue
        kind, field = STRUCTURED_FIELD_MAP.get(
            metric, ("cashflow" if metric == "fx_effect_on_cash" else "balance", "__UNMAPPED__")
        )
        refs = (
            ("closing", "opening")
            if METRIC_CONTRACTS[metric]["period_kind"] == "instant"
            else ("current", "prior")
        )
        for ref in refs:
            fact(metric, ref, kind, field)
    for ref in ("current", "prior"):
        revenue = next(f for f in facts if f["fact_id"] == f"fact-revenue-{ref}")
        cost = next(f for f in facts if f["fact_id"] == f"fact-cost_of_sales-{ref}")
        value = (
            None
            if revenue["value"] is None or cost["value"] is None
            else str(decimal_value(revenue["value"]) - decimal_value(cost["value"]))
        )
        derived = {
            **revenue,
            "fact_id": f"fact-gross_profit-{ref}",
            "metric": "gross_profit",
            "raw_label": "gross_profit",
            "raw_value": value,
            "value": value,
            "source": "derived",
            "input_fact_ids": [revenue["fact_id"], cost["fact_id"]],
            "formula": "revenue - cost_of_sales",
            "review_status": "verified" if value is not None else "missing",
            "missing_reason": None if value is not None else "missing derivation operand",
        }
        derived.pop("source_ref")
        facts.append(derived)
    result = {
        "schema_version": 1,
        "stock_code": code,
        "company_name": document.get("company_name"),
        "currency": document["currency"],
        "period": period,
        "source": "structured_eastmoney",
        "source_sha256": hashlib.sha256(
            (run_dir / "structured_financials.json").read_bytes()
        ).hexdigest(),
        "facts": facts,
    }
    validation["issues"].extend(validate_financials(result))
    validation["mapped_facts"] = len(facts)
    return (None if validation["issues"] else result), validation


def main(argv=None):
    parser = argparse.ArgumentParser(description="Map saved F10 statements")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    result, mapping = build_financials_structured(
        run_dir, read_json(run_dir / "structured_financials.json")
    )
    write_json(run_dir / "mapping_validation.json", mapping)
    if result is None:
        emit_status("failed", {}, mapping["issues"])
        return 2
    write_json(run_dir / "financials.json", result)
    emit_status("ok", {"financials_json": str(run_dir / "financials.json")}, mapping["warnings"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
