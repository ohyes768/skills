"""紧凑事实输入 → 标准财务合同：别名映射、维度补全、证据定位核对。

模型只提交 metric/raw_label/raw_value/raw_unit/evidence 定位等需要判断的字段；
公共公司、币种、期间结构、归属维度、fact_id、missing_reason 均由程序从可信
元数据（document.json、source.json、extraction_manifest.json）推导。
任何映射或定位问题都阻塞 financials.json 写出，返回集中修复清单。
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from artifacts import emit_status, read_json, write_json
from fact_selection import prior_year
from financial_schema import (
    METRIC_CONTRACTS,
    STRUCTURED_FIELD_MAP,
    STRUCTURED_UNSUPPORTED,
    parse_amount,
    resolve_metric_label,
    validate_financials,
)

INPUT_SCHEMA_VERSION = 1
UNDISCLOSED_TOKENS = {"—", "–", "-", "--", ""}
_SCOPE_VALUES = {"consolidated", "parent"}
_BASIS_VALUES = {"as_reported", "restated"}
_AGGREGATIONS = {"cumulative", "single_period"}
_REVIEW_STATUSES = {"verified", "ambiguous", "missing", "conflict"}
_PERIOD_REFS = {"duration": {"current", "prior"}, "instant": {"closing", "opening"}}
_RAW_UNITS = {"元", "千元", "万元", "亿元"}
# inspect_pdf 把文档类型写入 period.frequency（如 semi_annual）；事实合同的
# frequency 值域是 annual/half_year/quarter，构造时归一化，不让 agent 改 document.json。
_FREQUENCY_ALIASES = {"semi_annual": "half_year", "q1": "quarter", "q3": "quarter"}

# 结构化模式建议抽查的科目：覆盖全部指标输入与风险信号引用。fact_inputs 未覆盖
# 本期值时给 warning 提示补充（不阻塞）——报告用到的每个数都应有 PDF 背书。
RECOMMENDED_SAMPLE_METRICS = (
    "revenue", "net_profit_owners", "net_profit_group", "cfo", "total_assets",
    "monetary_funds", "cost_of_sales", "total_equity", "total_liabilities",
    "cash_equivalents", "fx_effect_on_cash", "accounts_receivable", "inventory",
    "short_term_borrowings", "long_term_borrowings",
)


def _normalize_label(label: str) -> str:
    """去除序号前缀、括号注释与空白，统一全角括号，供精确定位比对。"""
    text = label.strip()
    text = re.sub(r"^[（(]?[一二三四五六七八九十\d]{1,3}[）)、.．]\s*", "", text)
    text = re.sub(r"[（(][^（）()]*[)）]\s*[:：]?$", "", text)
    text = text.rstrip(":=： ").strip()
    return re.sub(r"\s+", "", text).replace("(", "（").replace(")", "）")


def _normalize_cell(cell: str) -> str:
    text = str(cell).strip().replace(",", "").replace("，", "")
    text = text.replace("(", "(").replace(")", ")")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    return re.sub(r"\s+", "", text)


def _issue(index: int, error: str, **extra) -> dict:
    return {"input_index": index, "error": error, **extra}


def _resolve_period(document: dict, period_kind: str, period_ref: str,
                    aggregation: str | None) -> tuple[dict | None, str | None]:
    base = document.get("period")
    if not isinstance(base, dict) or not base.get("end"):
        return None, "document.json has no usable period; clarify before mapping"
    frequency = base.get("frequency") or "annual"
    frequency = _FREQUENCY_ALIASES.get(frequency, frequency)
    if period_kind == "duration":
        start, end = base.get("start"), base["end"]
        if period_ref == "prior":
            if not start:
                return None, "prior period needs document period start"
            start, end = prior_year(start), prior_year(end)
        return {
            "kind": "duration", "start": start, "end": end,
            "frequency": frequency, "aggregation": aggregation or "cumulative",
        }, None
    day = base["end"] if period_ref == "closing" else None
    if period_ref == "opening":
        if not base.get("start"):
            return None, "opening balance needs document period start"
        day = (date.fromisoformat(base["start"]) - timedelta(days=1)).isoformat()
    return {"kind": "instant", "start": None, "end": day,
            "frequency": frequency, "aggregation": "instant"}, None


def _check_evidence(run_dir: Path, index: int, raw_label: str, raw_value: str | None,
                    evidence: dict, review_status: str) -> tuple[list[dict], str]:
    """核对证据定位；返回 (issues, effective_review_status)。"""
    issues: list[dict] = []
    evidence_id = evidence.get("evidence_id")
    if not isinstance(evidence_id, str):
        return [_issue(index, "evidence.evidence_id is required", field="evidence")], review_status
    manifest_path = run_dir / "extraction_manifest.json"
    if not manifest_path.exists():
        return [_issue(index, "extraction_manifest.json missing; extract evidence first",
                       field="evidence")], review_status
    evidences = {e["evidence_id"]: e for e in read_json(manifest_path).get("evidences", [])}
    record = evidences.get(evidence_id)
    if record is None:
        return [_issue(index, f"unknown evidence_id: {evidence_id}",
                       field="evidence")], review_status

    status = review_status
    if record.get("kind") == "table" and record.get("complete", False):
        locator = evidence.get("locator") or {}
        row, col = locator.get("row"), locator.get("col")
        if not isinstance(row, int) or not isinstance(col, int):
            return [_issue(index, "table evidence requires locator row/col",
                           field="evidence", evidence_id=evidence_id)], status
        data = read_json(run_dir / record["file"])
        rows = data.get("rows", [])
        if not (0 <= row < len(rows) and isinstance(rows[row], list) and 0 <= col < len(rows[row])):
            return [_issue(index, f"locator out of range: row {row} col {col} "
                           f"(table has {len(rows)} rows)", field="evidence",
                           evidence_id=evidence_id)], status
        cell = _normalize_cell(rows[row][col] or "")
        if raw_value is not None and cell != _normalize_cell(raw_value):
            return [_issue(index, f"cell mismatch at row {row} col {col}: "
                           f"table {rows[row][col]!r} != raw_value {raw_value!r}",
                           field="evidence", evidence_id=evidence_id)], status
    elif record.get("kind") == "text" and record.get("complete", False):
        text_path = run_dir / record["file"]
        text = text_path.read_text(encoding="utf-8") if text_path.exists() else ""
        lines = text.splitlines()
        line_no = (evidence.get("locator") or {}).get("line")
        scope_lines = [lines[line_no - 1]] if (
            isinstance(line_no, int) and 1 <= line_no <= len(lines)) else lines
        label = _normalize_label(raw_label or "")
        if not label or not any(label in _normalize_label(line) for line in scope_lines):
            detail = f" at line {line_no}" if line_no else ""
            return [_issue(index, f"raw_label {raw_label!r} not found in text "
                           f"evidence {evidence_id}{detail}", field="evidence",
                           evidence_id=evidence_id)], status
    else:
        issues.append(_issue(index, f"evidence {evidence_id} is not verifiable "
                             f"(kind={record.get('kind')!r}, complete={record.get('complete')}); "
                             "review_status downgraded to ambiguous", field="evidence",
                             evidence_id=evidence_id, severity="warning"))
        status = "ambiguous" if status == "verified" else status
    return issues, status


def build_financials(run_dir: Path, inputs: dict) -> tuple[dict | None, dict]:
    """构造 financials.json 内容；返回 (financials | None, mapping_validation)。"""
    run_dir = Path(run_dir)
    document = read_json(run_dir / "document.json")
    source = read_json(run_dir / "source.json")
    facts_input = inputs.get("facts")
    validation: dict = {
        "schema_version": 1,
        "document_sha256": source.get("sha256"),
        "input_facts": 0,
        "mapped_facts": 0,
        "issues": [],
        "warnings": [],
    }
    if not isinstance(facts_input, list) or not facts_input:
        validation["issues"].append(_issue(-1, "facts must be a nonempty list"))
        return None, validation

    validation["input_facts"] = len(facts_input)
    built: list[dict] = []
    for index, item in enumerate(facts_input):
        if not isinstance(item, dict):
            validation["issues"].append(_issue(index, "fact entry must be an object"))
            continue
        problems = _build_one(run_dir, index, document, item, built, validation)
        validation["issues"].extend(p for p in problems if p.get("severity") != "warning")
        validation["warnings"].extend(p for p in problems if p.get("severity") == "warning")

    if validation["issues"]:
        return None, validation
    validation["mapped_facts"] = len(built)
    financials = {
        "schema_version": 1,
        "document_sha256": source.get("sha256"),
        "currency": document.get("currency"),
        "facts": built,
    }
    errors = validate_financials(financials)
    if errors:
        for error in errors:
            validation["issues"].append(_issue(-1, f"contract violation: "
                                               f"{error['fact_id']} {error['field']}: {error['error']}"))
        return None, validation
    return financials, validation


def _build_one(run_dir: Path, index: int, document: dict, item: dict,
               built: list[dict], validation: dict) -> list[dict]:
    raw_label = item.get("raw_label")
    raw_value_text = item.get("raw_value")
    raw_unit = item.get("raw_unit")
    metric_input = item.get("metric")
    period_ref = item.get("period_ref")

    problems: list[dict] = []
    metric = resolve_metric_label(metric_input, raw_label)
    if metric is None:
        return [_issue(index, f"unmapped metric label: metric={metric_input!r} "
                       f"raw_label={raw_label!r}; use a contracted metric",
                       field="metric")]
    contract = METRIC_CONTRACTS[metric]
    period_kind = contract["period_kind"]
    if period_ref not in _PERIOD_REFS[period_kind]:
        return [_issue(index, f"period_ref {period_ref!r} illegal for {metric} "
                       f"({period_kind}); expected one of {sorted(_PERIOD_REFS[period_kind])}",
                       field="period_ref")]
    scope = item.get("scope") or "consolidated"
    if scope not in _SCOPE_VALUES:
        problems.append(_issue(index, f"scope {scope!r} illegal", field="scope"))
        return problems
    basis = item.get("basis") or "as_reported"
    if basis not in _BASIS_VALUES:
        problems.append(_issue(index, f"basis {basis!r} illegal", field="basis"))
        return problems
    review_status = item.get("review_status") or "verified"
    if review_status not in _REVIEW_STATUSES:
        problems.append(_issue(index, f"review_status {review_status!r} illegal", field="review_status"))
        return problems

    if raw_unit not in _RAW_UNITS:
        problems.append(_issue(index, f"raw_unit {raw_unit!r} illegal; expected {_RAW_UNITS}",
                               field="raw_unit"))
        return problems

    undisclosed = (raw_value_text is None
                   or str(raw_value_text).strip() in UNDISCLOSED_TOKENS)
    if undisclosed:
        value = None
        missing_reason = item.get("note") or "not disclosed in source"
    else:
        value = parse_amount(str(raw_value_text), raw_unit)
        if value is None:
            problems.append(_issue(index, f"raw_value {raw_value_text!r} not parseable "
                                   f"with unit {raw_unit!r}", field="raw_value"))
            return problems
        missing_reason = None

    evidence_ids: list[str] = []
    evidence_entry = item.get("evidence")
    if value is not None:
        if not isinstance(evidence_entry, dict):
            problems.append(_issue(index, "non-null value requires evidence object", field="evidence"))
            return problems
        evidence_issues, review_status = _check_evidence(
            run_dir, index, raw_label, str(raw_value_text), evidence_entry, review_status)
        problems.extend(evidence_issues)
        if any(p.get("severity") != "warning" for p in evidence_issues):
            return problems
        evidence_ids = [evidence_entry["evidence_id"]]
    elif evidence_entry:
        evidence_ids = [evidence_entry.get("evidence_id")] if evidence_entry.get("evidence_id") else []

    aggregation = item.get("aggregation")
    if aggregation is not None and aggregation not in _AGGREGATIONS:
        problems.append(_issue(index, f"aggregation {aggregation!r} illegal", field="aggregation"))
        return problems
    period, period_error = _resolve_period(document, period_kind, period_ref, aggregation)
    if period_error:
        problems.append(_issue(index, period_error, field="period"))
        return problems

    built.append({
        "fact_id": f"f-{len(built) + 1:04d}",
        "metric": metric,
        "raw_label": raw_label,
        "raw_value": None if undisclosed else str(raw_value_text),
        "raw_unit": raw_unit,
        "value": None if value is None else format(value, "f"),
        "unit": "元",
        "currency": document.get("currency"),
        "scope": scope,
        "attribution": contract["attribution"],
        "period": period,
        "basis": basis,
        "evidence_ids": evidence_ids,
        "review_status": review_status,
        "missing_reason": missing_reason,
        "source": item.get("source") or "extracted",
    })
    return problems


def _date_for_ref(period: dict, period_ref: str) -> str | None:
    """把 period_ref 映射到结构化数据需要的报告期末日期。"""
    if period_ref in ("current", "closing"):
        return period.get("end")
    if period_ref == "prior" and period.get("end"):
        return prior_year(period["end"])
    if period_ref == "opening" and period.get("start"):
        return (date.fromisoformat(period["start"]) - timedelta(days=1)).isoformat()
    return None


def _structured_value(row: dict, field: str) -> tuple[Decimal | None, str | None]:
    """取结构化字段值；返回 (Decimal | None, None) 或 (None, 跳过原因)。"""
    if field not in row:
        return None, "field missing in structured response"
    raw = row[field]
    if raw is None:
        return None, None
    if isinstance(raw, Decimal):
        return raw, None
    if isinstance(raw, int) and not isinstance(raw, bool):
        return Decimal(raw), None
    if isinstance(raw, str):
        try:
            return Decimal(raw), None
        except InvalidOperation:
            return None, f"non-numeric structured value: {raw!r}"
    return None, f"unsupported structured value type: {type(raw).__name__}"


def _evidence_value_index(run_dir: Path) -> set[Decimal]:
    """收集 PDF 证据中出现的全部数值（含单位缩放），供全量存在性检查。"""
    from report_values import NUMBER_RE, SCALES

    manifest_path = run_dir / "extraction_manifest.json"
    if not manifest_path.exists():
        return set()
    values: set[Decimal] = set()
    for record in read_json(manifest_path).get("evidences", []):
        path = run_dir / record.get("file", "")
        if not path.exists():
            continue
        texts: list[str] = []
        if record.get("kind") == "table":
            try:
                data = read_json(path)
            except (OSError, ValueError):
                continue
            texts.extend(str(cell) for row in data.get("rows", []) for cell in row)
        else:
            try:
                texts.append(path.read_text(encoding="utf-8"))
            except OSError:
                continue
        for text in texts:
            for match in NUMBER_RE.finditer(text):
                try:
                    num = Decimal(match.group("number").replace(",", ""))
                except InvalidOperation:
                    continue
                scale = SCALES.get((match.group("unit") or "").lower(), Decimal(1))
                values.add(num * scale)
    return values


def build_financials_structured(run_dir: Path, structured: dict,
                                inputs: dict | None = None) -> tuple[dict | None, dict]:
    """从 structured_financials.json 生成 facts（source=structured，无 evidence 链）。

    为每个可映射指标生成本期与比较期事实（duration: current+prior，instant:
    closing+opening）。字段缺失生成 missing 事实；响应缺字段记 warning 跳过。
    inputs 为可选的抽查单（AI 从 PDF 抽取的关键数，过 evidence 核对）；与结构化
    事实双源并存，比对结果写入 validation.structured_check，不一致转 conflict。
    """
    run_dir = Path(run_dir)
    document = read_json(run_dir / "document.json")
    source = read_json(run_dir / "source.json")
    period = document.get("period") or {}
    validation: dict = {
        "schema_version": 1,
        "document_sha256": source.get("sha256"),
        "input_facts": 0,
        "mapped_facts": 0,
        "issues": [],
        "warnings": [],
        "data_source": "structured",
    }
    if not period.get("end"):
        validation["issues"].append(_issue(-1, "document.json has no usable period"))
        return None, validation
    reports = structured.get("reports") or {}

    built: list[dict] = []
    for metric, (kind, field) in STRUCTURED_FIELD_MAP.items():
        contract = METRIC_CONTRACTS[metric]
        for period_ref in sorted(_PERIOD_REFS[contract["period_kind"]]):
            day = _date_for_ref(period, period_ref)
            if not day or day not in reports or not (reports[day] or {}).get(kind):
                validation["issues"].append(_issue(
                    -1, f"structured data for {metric} {period_ref} ({day}) not fetched; "
                    "fetch dates must cover current, prior and opening periods",
                    field="structured"))
                continue
            row = reports[day][kind][0]
            value, skip = _structured_value(row, field)
            if skip:
                validation["warnings"].append(_issue(
                    -1, f"{metric} {period_ref}: {skip}", field="structured"))
                continue
            fact_period, period_error = _resolve_period(document, contract["period_kind"],
                                                        period_ref, None)
            if period_error:
                validation["issues"].append(_issue(-1, period_error, field="period"))
                continue
            built.append({
                "fact_id": f"f-{len(built) + 1:04d}",
                "metric": metric,
                "raw_label": field,
                "raw_value": None if value is None else format(value, "f"),
                "raw_unit": "元",
                "value": None if value is None else format(value, "f"),
                "unit": "元",
                "currency": document.get("currency"),
                "scope": "consolidated",
                "attribution": contract["attribution"],
                "period": fact_period,
                "basis": "as_reported",
                "evidence_ids": [],
                "review_status": "verified",
                "missing_reason": None if value is not None else "not disclosed in structured source",
                "source": "structured",
            })

    for metric in STRUCTURED_UNSUPPORTED:
        validation["warnings"].append(_issue(
            -1, f"{metric} has no structured field; supply via PDF evidence or derivation",
            field="structured"))

    if validation["issues"]:
        return None, validation

    # 抽样核对：fact_inputs（AI 从 PDF 抽查的关键数，过 evidence 核对）与结构化
    # 事实同台并存——值一致由 pick_usable 去重，不一致自动 conflict（既有语义）。
    check = {"schema_version": 1, "samples": [], "verified": 0, "conflicts": 0,
             "unchecked": 0}
    extracted_facts: list[dict] = []
    if inputs and isinstance(inputs.get("facts"), list) and inputs["facts"]:
        input_result = build_financials(run_dir, inputs)
        extracted_financials, extracted_validation = input_result
        if extracted_financials is None:
            validation["issues"].extend(extracted_validation["issues"])
            return None, validation
        validation["warnings"].extend(extracted_validation["warnings"])
        extracted_facts = extracted_financials["facts"]
        offset = len(built)
        for i, fact in enumerate(extracted_facts):
            fact["fact_id"] = f"f-{offset + i + 1:04d}"

    extracted_index = {(f["metric"], f["period"]["end"]): f for f in extracted_facts}
    for fact in built:
        if fact["value"] is None:
            continue
        twin = extracted_index.get((fact["metric"], fact["period"]["end"]))
        sample = {
            "metric": fact["metric"], "period_end": fact["period"]["end"],
            "structured_value": fact["value"],
            "extracted_value": twin["value"] if twin else None,
            "extracted_fact_id": twin["fact_id"] if twin else None,
            "evidence_ids": twin.get("evidence_ids", []) if twin else [],
            "pdf_pages": sorted({p for fid in (twin.get("evidence_ids", []) if twin else [])
                                 for p in _evidence_pages(run_dir, fid)}),
        }
        if twin is None:
            sample["status"] = "unchecked"
            check["unchecked"] += 1
        elif _same_amount(fact["value"], twin["value"]):
            sample["status"] = "verified"
            check["verified"] += 1
        else:
            sample["status"] = "conflict"
            fact["review_status"] = "conflict"
            check["conflicts"] += 1
            validation["issues"].append(_issue(
                -1, f"structured/extracted mismatch for {fact['metric']} "
                f"({fact['period']['end']}): structured {fact['value']} vs "
                f"extracted {twin['value']}", field="structured_check"))
        check["samples"].append(sample)

    # 全量数值存在性检查：structured 的每个非空值应在 PDF 证据文本中出现过
    # （弱背书——不配对科目，只验证数值真实出现在原文；找不到通常是证据未覆盖该页）。
    value_index = _evidence_value_index(run_dir)
    presence = {"found": 0, "not_found": 0, "no_value": 0, "not_found_metrics": []}
    for fact in built:
        if fact["value"] is None:
            presence["no_value"] += 1
            continue
        if Decimal(fact["value"]) in value_index:
            presence["found"] += 1
        else:
            presence["not_found"] += 1
            if len(presence["not_found_metrics"]) < 20:
                presence["not_found_metrics"].append(
                    {"metric": fact["metric"], "period_end": fact["period"]["end"]})
    check["presence"] = presence

    # 抽查覆盖建议：fact_inputs 未覆盖本期建议科目时提示补充（不阻塞）。
    covered = {f["metric"] for f in extracted_facts
               if f["period"]["end"] == period.get("end")}
    missing_reco = [m for m in RECOMMENDED_SAMPLE_METRICS
                    if m not in covered and m in STRUCTURED_FIELD_MAP]
    if missing_reco:
        validation["warnings"].append(_issue(
            -1, "sample sheet does not cover current-period metrics: "
            f"{', '.join(missing_reco)}; add PDF-verified samples for full conclusion backing",
            field="structured_check", severity="warning"))
    validation["structured_check"] = check

    all_facts = built + extracted_facts
    validation["input_facts"] = len(all_facts)
    validation["mapped_facts"] = len(all_facts)
    financials = {
        "schema_version": 1,
        "document_sha256": source.get("sha256"),
        "currency": document.get("currency"),
        "facts": all_facts,
    }
    errors = validate_financials(financials)
    if errors:
        for error in errors:
            validation["issues"].append(_issue(
                -1, f"contract violation: {error['fact_id']} {error['field']}: {error['error']}"))
        return None, validation
    return financials, validation


def _same_amount(left: str, right: str) -> bool:
    """双源一致：金额差不超过 1 分（两源的舍入级差异不视为冲突）。"""
    try:
        return abs(Decimal(left) - Decimal(right)) <= Decimal("0.01")
    except InvalidOperation:
        return False


def _evidence_pages(run_dir: Path, evidence_id: str) -> list[int]:
    manifest_path = run_dir / "extraction_manifest.json"
    if not manifest_path.exists():
        return []
    for record in read_json(manifest_path).get("evidences", []):
        if record.get("evidence_id") == evidence_id:
            return record.get("pdf_pages", [])
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从紧凑 fact_inputs.json 构造标准 financials.json")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--inputs", default="fact_inputs.json")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    inputs_path = run_dir / args.inputs
    try:
        inputs = read_json(inputs_path)
        if inputs.get("schema_version") != INPUT_SCHEMA_VERSION:
            print(f"build_financials failed: inputs schema_version must be {INPUT_SCHEMA_VERSION}",
                  file=sys.stderr)
            raise SystemExit(1)
        financials, validation = build_financials(run_dir, inputs)
    except (OSError, ValueError) as exc:
        print(f"build_financials failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    write_json(run_dir / "mapping_validation.json", validation)
    if financials is None:
        emit_status("repair_needed", {"mapping_validation": str(run_dir / "mapping_validation.json")},
                    [issue["error"] for issue in validation["issues"]])
        raise SystemExit(2)
    write_json(run_dir / "financials.json", financials)
    emit_status("ok", {
        "financials_json": str(run_dir / "financials.json"),
        "mapping_validation": str(run_dir / "mapping_validation.json"),
    }, [w["error"] for w in validation["warnings"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
