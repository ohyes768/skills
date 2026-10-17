"""报告校验：引用存在性、页码范围、计算值一致与证据完整性（机器可验证部分）。"""

from __future__ import annotations

import argparse
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from artifacts import emit_status, read_json, write_json

_CLAIM_TYPES = {"fact", "calculation", "inference", "company_explanation"}
_NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _value_variants(value: Decimal) -> set[str]:
    variants = {format(value, "f")}
    pct = value * 100
    for digits in (0, 1):
        quantized = pct.quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
        normalized = format(quantized, "f").rstrip("0").rstrip(".") or "0"
        variants.add(f"{normalized}%")
        variants.add(normalized)
    return variants


def _text_contains_value(text: str, value: Decimal) -> bool:
    variants = _value_variants(value)
    for match in _NUMBER_RE.finditer(text):
        candidate = match.group(0).replace(",", "")
        try:
            number = Decimal(candidate)
        except Exception:  # noqa: BLE001, S112 - 文本片段中混有非数字，跳过即可
            continue
        if format(number, "f") in variants:
            return True
        if number == value:
            return True
        pct_candidate = (number / 100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if pct_candidate == value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP):
            return True
    return False


def _empty_result() -> dict:
    return {
        "schema_version": 1,
        "unknown_fact_ids": [],
        "unknown_metric_ids": [],
        "unknown_evidence_ids": [],
        "out_of_range_pages": [],
        "value_mismatches": [],
        "missing_evidence_claims": [],
        "passed": False,
    }


def validate_report(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    document = read_json(run_dir / "document.json")
    financials = read_json(run_dir / "financials.json")
    metrics_doc = read_json(run_dir / "metrics.json")
    manifest = read_json(run_dir / "extraction_manifest.json")
    claims_doc = read_json(run_dir / "report_claims.json")
    page_count = int(document.get("page_count", 0))

    fact_ids = {f["fact_id"] for f in financials.get("facts", [])}
    metric_ids = {m["metric_id"] for m in metrics_doc.get("metrics", [])}
    metric_values = {
        m["metric_id"]: Decimal(m["value"])
        for m in metrics_doc.get("metrics", [])
        if m.get("value") is not None and m.get("status") == "computed"
    }
    evidence_ids = {e["evidence_id"] for e in manifest.get("evidences", [])}

    result = _empty_result()
    seen_claim_ids: set[str] = set()

    for claim in claims_doc.get("claims", []):
        claim_id = claim.get("claim_id", "<missing>")
        if claim_id in seen_claim_ids:
            result["missing_evidence_claims"].append(claim_id)
        seen_claim_ids.add(claim_id)

        for fid in claim.get("fact_ids", []):
            if fid not in fact_ids and fid not in result["unknown_fact_ids"]:
                result["unknown_fact_ids"].append(fid)
        for mid in claim.get("metric_ids", []):
            if mid not in metric_ids and mid not in result["unknown_metric_ids"]:
                result["unknown_metric_ids"].append(mid)
        for eid in claim.get("evidence_ids", []):
            if eid not in evidence_ids and eid not in result["unknown_evidence_ids"]:
                result["unknown_evidence_ids"].append(eid)

        for page in claim.get("source_pages", []):
            if not (1 <= int(page) <= page_count):
                result["out_of_range_pages"].append({"claim_id": claim_id, "page": page})

        claim_type = claim.get("claim_type")
        text = claim.get("text", "")
        if claim_type not in _CLAIM_TYPES:
            result["missing_evidence_claims"].append(claim_id)
            continue

        has_support = any(
            claim.get(key) for key in ("fact_ids", "metric_ids", "evidence_ids")
        )
        if not has_support:
            result["missing_evidence_claims"].append(claim_id)
            continue

        matched_metrics = [
            metric_values[mid]
            for mid in claim.get("metric_ids", [])
            if mid in metric_values
        ]
        if matched_metrics and not any(
            _text_contains_value(text, value) for value in matched_metrics
        ):
            result["value_mismatches"].append(
                {
                    "claim_id": claim_id,
                    "report_text_fragment": text[:80],
                    "metric_values": [format(v, "f") for v in matched_metrics],
                }
            )

    result["passed"] = not any(
        result[key]
        for key in (
            "unknown_fact_ids",
            "unknown_metric_ids",
            "unknown_evidence_ids",
            "out_of_range_pages",
            "value_mismatches",
            "missing_evidence_claims",
        )
    )
    write_json(run_dir / "report_validation.json", result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="校验 analysis.md 引用与台账一致性")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    required = ["document.json", "financials.json", "metrics.json",
                "extraction_manifest.json", "report_claims.json", "analysis.md"]
    missing = [name for name in required if not (run_dir / name).exists()]
    if missing:
        print(f"validate_report failed: missing artifacts: {missing}", file=sys.stderr)
        raise SystemExit(1)

    result = validate_report(run_dir)
    issues = []
    for key in ("unknown_fact_ids", "unknown_metric_ids", "unknown_evidence_ids",
                "out_of_range_pages", "value_mismatches", "missing_evidence_claims"):
        issues.extend(f"{key}: {item}" for item in result[key])
    emit_status(
        "ok" if result["passed"] else "partial",
        {"report_validation": str(run_dir / "report_validation.json")},
        issues,
    )
    if not result["passed"]:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
