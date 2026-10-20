"""核验实际交付正文、财务显示值与 claim→metric→fact→evidence 来源链。"""

from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from artifacts import emit_status, read_json, write_json
from report_values import (
    NUMBER_RE,
    decline_context,
    extract_cited_pages,
    in_range_citation,
    matches_number,
    percentage_point_suffix,
    period_year_suffix,
    plain_text,
)

_CLAIM_TYPES = {"fact", "calculation", "inference", "company_explanation"}
_ISSUE_KEYS = (
    "unknown_fact_ids", "unknown_metric_ids", "unknown_evidence_ids", "out_of_range_pages",
    "value_mismatches", "missing_evidence_claims", "body_mismatches", "unclaimed_numeric_lines",
    "invalid_support", "page_mismatches",
)


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
    """Numeric statements require ledger coverage; document metadata is exempt."""
    covered = [(plain_text(c["text"]), set(c.get("source_pages", [])))
               for c in claims if c.get("text")]
    issues = []
    for line in body.splitlines():
        # Only a whole, syntactically constrained source line is metadata.
        if re.fullmatch(r"[-*]\s*来源[:：]\s*https?://[^\s<>（）]+"
                        r"(?:（SHA-256 前 8 位：[0-9a-fA-F]{8}）)?", line):
            continue
        if not NUMBER_RE.search(plain_text(line)):
            continue
        normalized = re.sub(r"^#{1,6}", "", plain_text(line))
        normalized = re.sub(r"^\d+[.)、]", "", normalized)
        if line.startswith("# "):
            # The document title may contain its verified stock code and period.
            company, code = document.get("company_name"), document.get("stock_code")
            end = (document.get("period") or {}).get("end", "")
            if company and code and end:
                expected = f"{company}（{code}）{end[:4]}分析"
                if normalized == plain_text(expected):
                    continue
        remaining = normalized
        allowed_pages = set()
        for text, pages in covered:
            if text in normalized:
                remaining = remaining.replace(text, "")
                allowed_pages.update(pages)
            elif normalized in text:
                remaining = ""
                allowed_pages.update(pages)
        def remove_citation(match, allowed=allowed_pages):
            nums = [int(n) for n in re.findall(r"\d+", match.group(1))]
            return "" if all(page in allowed for page in nums) else match.group(0)
        remaining = re.sub(
            r"(?:PDF\s*第\s*|p\.\s*)(\d+(?:\s*[-–—、,，]\s*\d+)*)\s*页?",
            remove_citation, remaining, flags=re.IGNORECASE,
        )
        if remaining and NUMBER_RE.search(remaining):
            issues.append(line[:200])
    return issues


def validate_report(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    document = read_json(run_dir / "document.json")
    financials = read_json(run_dir / "financials.json")
    metrics_doc = read_json(run_dir / "metrics.json")
    manifest = read_json(run_dir / "extraction_manifest.json")
    claims = read_json(run_dir / "report_claims.json").get("claims", [])
    body = (run_dir / "analysis.md").read_text(encoding="utf-8")
    page_count = int(document.get("page_count", 0))
    facts = {f["fact_id"]: f for f in financials.get("facts", [])}
    metrics = {m["metric_id"]: m for m in metrics_doc.get("metrics", [])}
    evidences = {e["evidence_id"]: e for e in manifest.get("evidences", [])}
    result = {"schema_version": 1, **{key: [] for key in _ISSUE_KEYS}, "passed": False}
    if not claims or not body.strip():
        result["body_mismatches"].append("nonempty report and claims are required")
    source_path = run_dir / "source.json"
    source_sha = read_json(source_path).get("sha256") if source_path.exists() else None
    bound_sha = manifest.get("document_sha256")
    if ((source_sha and financials.get("document_sha256") != source_sha)
            or (bound_sha and financials.get("document_sha256") != bound_sha)):
        result["invalid_support"].append("financials and source document versions differ")

    seen = set()
    for claim in claims:
        cid = claim.get("claim_id", "<missing>")
        if cid in seen:
            result["missing_evidence_claims"].append(cid)
        seen.add(cid)
        text = claim.get("text", "")
        section = _section(body, claim.get("report_anchor", ""))
        if not text.strip() or section is None or plain_text(text) not in plain_text(section):
            result["body_mismatches"].append(cid)
        claim_type = claim.get("claim_type")
        if claim_type not in _CLAIM_TYPES:
            result["missing_evidence_claims"].append(cid)
            continue

        fids = set(claim.get("fact_ids", []))
        mids = set(claim.get("metric_ids", []))
        eids = set(claim.get("evidence_ids", []))
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
            source_ids = fact.get("evidence_ids", [])
            if not source_ids:
                result["invalid_support"].append(f"{cid}: fact {fid} has no evidence")
            eids.update(source_ids)
            for field in ("start", "end"):
                day = fact.get("period", {}).get(field)
                if day:
                    allowed_years.add(day[:4])

        expected_pages = set()
        for eid in eids:
            if eid not in evidences:
                result["unknown_evidence_ids"].append(eid)
            else:
                expected_pages.update(evidences[eid].get("pdf_pages", []))
        for page in claim.get("source_pages", []):
            if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= page_count:
                result["out_of_range_pages"].append({"claim_id": cid, "page": page})
        if set(claim.get("source_pages", [])) != expected_pages:
            result["page_mismatches"].append(cid)
        cited_pages = extract_cited_pages(text)
        if not cited_pages <= expected_pages:
            result["page_mismatches"].append(cid)
        if not eids or (claim_type == "calculation" and not mids):
            result["missing_evidence_claims"].append(cid)
        if claim_type == "fact" and NUMBER_RE.search(text) and not fids:
            result["missing_evidence_claims"].append(cid)

        display_unit = claim.get("display_unit")
        if any(not any(_number_explained(text, number, value, display_unit, kind)
                       for number in NUMBER_RE.finditer(text))
               for value, kind in required_values):
            result["value_mismatches"].append({"claim_id": cid, "report_text_fragment": text[:100]})
        if claim_type in _CLAIM_TYPES:
            for number in NUMBER_RE.finditer(text):
                literal = number.group("number").replace(",", "")
                prefix = text[max(0, number.start() - 8):number.start()]
                is_year = (literal in allowed_years and not number.group("unit")
                           and period_year_suffix(text, number))
                if is_year or re.search(r"(?:PDF\s*第|p\.)\s*$", prefix):
                    continue
                if in_range_citation(text, number):
                    continue
                if any(_number_explained(text, number, value, display_unit, kind)
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
                "extraction_manifest.json", "report_claims.json", "analysis.md"]
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
