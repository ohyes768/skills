"""核验实际交付正文、财务显示值与 claim→metric→fact→F10 字段 来源链。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from artifacts import _json_default, emit_status, read_json, write_json
from report_values import (
    NUMBER_RE,
    decline_context,
    matches_number,
    percentage_point_suffix,
    period_year_suffix,
    plain_text,
)
from source_provenance import citation_text, source_errors, source_refs

_CLAIM_TYPES = {"fact", "calculation", "inference", "company_explanation"}
_ISSUE_KEYS = (
    "unknown_fact_ids", "unknown_metric_ids",
    "value_mismatches", "missing_source_claims", "body_mismatches", "unclaimed_numeric_lines",
    "invalid_support", "source_mismatches",
)


def calculation_errors(run_dir: Path) -> list[str]:
    """Bind persisted formulas, operands, statuses and risk flags to the source facts."""
    from calculate_metrics import calculate_metrics

    try:
        expected = json.loads(json.dumps(
            calculate_metrics(read_json(Path(run_dir) / "financials.json")), default=_json_default))
        actual = read_json(Path(run_dir) / "metrics.json")
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        return [f"calculation validation unavailable: {exc}"]
    errors = [] if actual == expected else [
        "metrics, formulas or risk flags differ from source calculations"]
    from analysis_pack import analysis_pack_errors
    errors.extend(analysis_pack_errors(run_dir))
    return errors


def _number_explained(text: str, number, value: Decimal, display_unit: str | None,
                      kind: str) -> bool:
    pp = percentage_point_suffix(text, number)
    adjusted = value * 100 if pp and kind == "ratio" else value
    direction = "decline" if decline_context(text, number) else None
    return matches_number(number, adjusted, display_unit, kind, direction=direction)


def _section(body: str, anchor: str) -> str | None:
    """Resolve a Markdown heading to its section, respecting nested headings."""
    lines = body.splitlines()
    for index, line in enumerate(lines):
        if plain_text(line) != plain_text(anchor):
            continue
        heading = re.match(r"^(#{1,6})\s+", line)
        if heading:
            depth = len(heading[1])
            for end in range(index + 1, len(lines)):
                other = re.match(r"^(#{1,6})\s+", lines[end])
                if other and len(other[1]) <= depth:
                    return "\n".join(lines[index:end])
        return "\n".join(lines[index:])
    return None


def _decimal(record: dict) -> Decimal | None:
    try:
        value = Decimal(record["value"])
        return value if value.is_finite() else None
    except (KeyError, InvalidOperation, TypeError, ValueError):
        return None


def _body_coverage(body: str, claims: list[dict], document: dict) -> list[str]:
    covered = [plain_text(c["text"]) for c in claims if c.get("text")]
    company, code = document.get("company_name"), document.get("stock_code")
    end = (document.get("period") or {}).get("end", "")
    title = f"# {company}（{code}）{end[:4]}分析"
    issues = []
    for line in body.splitlines():
        if line == title:
            continue
        remaining = plain_text(line)
        for text in covered:
            if text in remaining:
                remaining = remaining.replace(text, "")
        if NUMBER_RE.search(remaining):
            issues.append(line[:200])
    return issues


def validate_report(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    document = read_json(run_dir / "document.json")
    financials = read_json(run_dir / "financials.json")
    metrics_doc = read_json(run_dir / "metrics.json")
    claims = read_json(run_dir / "report_claims.json").get("claims", [])
    body = (run_dir / "analysis.md").read_text(encoding="utf-8")
    facts = {f["fact_id"]: f for f in financials.get("facts", [])}
    metrics = {m["metric_id"]: m for m in metrics_doc.get("metrics", [])}
    result = {"schema_version": 1, **{key: [] for key in _ISSUE_KEYS}, "passed": False}
    if not claims or not body.strip():
        result["body_mismatches"].append("nonempty report and claims are required")
    result["invalid_support"].extend(source_errors(run_dir, financials))
    result["invalid_support"].extend(calculation_errors(run_dir))
    from analysis_pack import build_analysis_pack, qualitative_claim_errors
    try:
        inputs = read_json(run_dir / "report_inputs.json")
        paragraphs = [
            paragraph for section in inputs.get("sections") or []
            for paragraph in section.get("paragraphs") or []
        ]
        result["invalid_support"].extend(dict.fromkeys(
            qualitative_claim_errors(build_analysis_pack(run_dir), [*paragraphs, body])))
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        result["invalid_support"].append(f"qualitative support unavailable: {exc}")
    # Delivered body and claims must be exactly the deterministic rendering of inputs.
    from render_report import render_report
    expected_body, expected_claims, render_issues = render_report(
        run_dir, read_json(run_dir / "report_inputs.json"))
    if render_issues or expected_body != body or expected_claims != claims:
        result["body_mismatches"].append("report body or claim ledger differs from bound inputs")

    seen = set()
    for claim in claims:
        cid = claim.get("claim_id", "<missing>")
        if cid in seen:
            result["missing_source_claims"].append(cid)
        seen.add(cid)
        text = claim.get("text", "")
        section = _section(body, claim.get("report_anchor", ""))
        if not text.strip() or section is None or plain_text(text) not in plain_text(section):
            result["body_mismatches"].append(cid)
        claim_type = claim.get("claim_type")
        if claim_type not in _CLAIM_TYPES:
            result["missing_source_claims"].append(cid)
            continue

        fids = set(claim.get("fact_ids", []))
        mids = set(claim.get("metric_ids", []))
        required_values = []
        all_values = []
        for mid in mids:
            if mid not in metrics:
                result["unknown_metric_ids"].append(mid)
                continue
            metric = metrics[mid]
            value = _decimal(metric)
            if metric.get("status") != "computed" or value is None:
                result["invalid_support"].append(f"{cid}: unusable metric {mid}")
            else:
                kind = "amount" if mid == "simplified_fcf" else "ratio"
                required_values.append((value, kind))
                all_values.append((value, kind))
            fids.update(metric.get("input_fact_ids", []))

        allowed_years = set()
        for fid in fids:
            if fid not in facts:
                result["unknown_fact_ids"].append(fid)
                continue
            fact = facts[fid]
            value = _decimal(fact)
            if fact.get("review_status", "verified") != "verified" or value is None:
                result["invalid_support"].append(f"{cid}: unusable fact {fid}")
            else:
                kind = "ratio" if fact.get("unit") in ("ratio", "%", "％") else "amount"
                all_values.append((value, kind))
                if claim_type == "fact":
                    required_values.append((value, kind))
            for field in ("start", "end"):
                day = fact.get("period", {}).get(field)
                if day:
                    allowed_years.add(day[:4])

        expected_refs = source_refs(facts, sorted(fids & facts.keys()))
        if claim.get("source_refs") != expected_refs:
            # Canonical ordering may differ, but content and complete closure must agree.
            canonical = lambda refs: sorted(json.dumps(r, sort_keys=True) for r in refs)
            if canonical(claim.get("source_refs", [])) != canonical(expected_refs):
                result["source_mismatches"].append(cid)
        if not expected_refs or (claim_type == "calculation" and not mids):
            result["missing_source_claims"].append(cid)
        if claim_type == "fact" and NUMBER_RE.search(text) and not fids:
            result["missing_source_claims"].append(cid)
        # Only exact generated source metadata is exempt from financial number matching.
        numeric_text = text.replace(citation_text(expected_refs), "") if expected_refs else text

        display_unit = claim.get("display_unit")
        if any(not any(_number_explained(numeric_text, number, value, display_unit, kind)
                       for number in NUMBER_RE.finditer(numeric_text))
               for value, kind in required_values):
            result["value_mismatches"].append({"claim_id": cid, "report_text_fragment": text[:100]})
        if claim_type in _CLAIM_TYPES:
            for number in NUMBER_RE.finditer(numeric_text):
                literal = number.group("number").replace(",", "")
                is_year = (literal in allowed_years and not number.group("unit")
                           and period_year_suffix(numeric_text, number))
                if is_year:
                    continue
                if any(_number_explained(numeric_text, number, value, display_unit, kind)
                       for value, kind in all_values):
                    continue
                result["value_mismatches"].append({"claim_id": cid, "unbound_number": literal})

    result["unclaimed_numeric_lines"] = _body_coverage(body, claims, document)
    result["passed"] = not any(result[key] for key in _ISSUE_KEYS)
    write_json(run_dir / "report_validation.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 analysis.md 正文、数值与来源")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    required = ["document.json", "financials.json", "metrics.json",
                "structured_financials.json", "report_inputs.json", "report_claims.json", "analysis.md"]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        print(f"validate_report failed: missing artifacts: {missing}", file=sys.stderr)
        raise SystemExit(1)
    result = validate_report(run_dir)
    issues = [f"{key}: {item}" for key in _ISSUE_KEYS for item in result[key]]
    emit_status("ok" if result["passed"] else "partial",
                {"report_validation": str(run_dir / "report_validation.json")}, issues)
    if not result["passed"]:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
