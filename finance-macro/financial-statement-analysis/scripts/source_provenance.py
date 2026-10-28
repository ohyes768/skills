"""Archived-field provenance and deterministic report citations for F10 facts."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from artifacts import read_json


def decimal_value(raw):
    """Accept exact finite API numerics; missing is distinct from malformed."""
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (str, int, Decimal)):
        raise ValueError(f"unsupported numeric value: {raw!r}")  # noqa: TRY004
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise ValueError(f"malformed numeric value: {raw!r}") from exc
    if not value.is_finite():
        raise ValueError(f"nonfinite numeric value: {raw!r}")
    return value


def source_errors(run_dir: Path, financials: dict | None = None) -> list[str]:
    """Rebuild from the exact saved archive and compare the entire normalized contract."""
    run_dir = Path(run_dir)
    try:
        financials = (
            financials if financials is not None else read_json(run_dir / "financials.json")
        )
        archive_path = run_dir / "structured_financials.json"
        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        errors = []
        if financials.get("source_sha256") != digest:
            errors.append("structured source archive hash mismatch")
        from build_financials import build_financials_structured

        expected, mapping = build_financials_structured(run_dir, read_json(archive_path))
        if expected is None:
            return errors + [
                f"structured source invalid: {item['error']}" for item in mapping["issues"]
            ]
        for field in ("source", "stock_code", "company_name", "currency", "period"):
            if financials.get(field) != expected.get(field):
                errors.append(f"structured source {field} mismatch")
        actual_facts = financials.get("facts")
        if not isinstance(actual_facts, list):
            return errors + ["structured source facts missing"]
        # Canonical IDs bind every fact to an exact metric, period and derivation.
        expected_by_id = {fact["fact_id"]: fact for fact in expected["facts"]}
        actual_by_id = {
            fact.get("fact_id"): fact for fact in actual_facts if isinstance(fact, dict)
        }
        if len(actual_by_id) != len(actual_facts) or set(actual_by_id) != set(expected_by_id):
            errors.append("structured source fact identity set mismatch")
        for fact_id, actual in actual_by_id.items():
            reference = expected_by_id.get(fact_id)
            if reference is None:
                continue
            if set(actual) != set(reference):
                errors.append(f"{fact_id}: source-bound field set mismatch")
            for field, value in reference.items():
                if actual.get(field) != value:
                    errors.append(f"{fact_id}: source-bound {field} mismatch")
        return errors
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"structured source validation failed: {exc}"]


def source_refs(facts, fact_ids) -> list[dict]:
    """Resolve derived operands to stable, unique saved-field references."""
    by_id = facts if isinstance(facts, dict) else {fact["fact_id"]: fact for fact in facts}
    result, seen, visiting = [], set(), set()

    def visit(fact_id):
        if fact_id in visiting:
            raise ValueError("cyclic fact derivation")
        fact = by_id.get(fact_id)
        if fact is None:
            raise ValueError(f"unknown fact: {fact_id}")
        visiting.add(fact_id)
        if fact.get("source") == "derived":
            for operand in fact.get("input_fact_ids", []):
                visit(operand)
        elif fact.get("source_ref") and fact.get("value") is not None:
            ref = fact["source_ref"]
            key = json.dumps(ref, sort_keys=True, ensure_ascii=False)
            if key not in seen:
                seen.add(key)
                result.append(dict(ref))
        visiting.remove(fact_id)

    for fact_id in fact_ids:
        visit(fact_id)
    return sorted(result, key=lambda ref: json.dumps(ref, sort_keys=True, ensure_ascii=False))


def citation_text(refs) -> str:
    refs = [
        json.loads(key)
        for key in sorted({json.dumps(ref, sort_keys=True, ensure_ascii=False) for ref in refs})
    ]
    names = {"balance": "合并资产负债表", "income": "合并利润表", "cashflow": "合并现金流量表"}
    return "；".join(
        f"东财接口（{names.get(ref.get('report_kind'), ref.get('report_name', ''))}；{ref.get('field', '')}；{ref.get('report_date', '')}）"
        for ref in refs
    )
