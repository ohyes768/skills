"""report_inputs.json → analysis.md 与 report_claims.json 同源渲染。

正文由结构化绑定（fact_id/metric_id）确定性渲染，claim 随片段同时生成，
证据页码由台账自动解析——禁止根据正文数值反查碰巧相等的支持事实。
定量陈述必须绑定；自由段落中的静态数字仅允许年份与页码引用。
渲染失败（绑定缺失、值不可用、格式与数量类型不符、方向词与符号矛盾）
时不写任何交付文件，返回集中修复清单。
"""

from __future__ import annotations

import argparse
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from artifacts import emit_status, read_json, write_json
from report_values import NUMBER_RE, period_year_suffix

INPUT_SCHEMA_VERSION = 1
_CLAIM_TYPES = {"fact", "calculation", "inference", "company_explanation"}
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([a-z0-9_]+))?\}")
_AMOUNT_SPECS = {
    "amount_yuan": (Decimal(1), "元"), "amount_wan": (Decimal("1e4"), "万元"),
    "amount_yi": (Decimal("1e8"), "亿元"),
}
_PERCENT_SPECS = {"percent0": 0, "percent1": 1, "percent2": 2}
_PP_SPECS = {"pp0": 0, "pp1": 1, "pp2": 2}


class RenderIssue(Exception):
    def __init__(self, error: str, **context):
        super().__init__(error)
        self.issue = {"error": error, **context}


def _format_amount(value: Decimal, spec: str, abs_mode: bool) -> str:
    divisor, label = _AMOUNT_SPECS[spec]
    shown = abs(value) if abs_mode else value
    return f"{(shown / divisor).quantize(Decimal(1).scaleb(-2), rounding=ROUND_HALF_UP):,f}{label}"


def _format_percent(value: Decimal, digits: int, abs_mode: bool) -> str:
    shown = abs(value) if abs_mode else value
    scaled = (shown * 100).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return f"{scaled:f}%"


def _format_pp(value: Decimal, digits: int, abs_mode: bool) -> str:
    shown = abs(value) if abs_mode else value
    scaled = (shown * 100).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    return f"{scaled:f}个百分点"


def format_value(value: Decimal, kind: str, fmt: str) -> str:
    abs_mode = fmt.startswith("decline_")
    base = fmt[len("decline_"):] if abs_mode else fmt
    if abs_mode and value > 0:
        raise RenderIssue(f"format {fmt} requires a nonpositive value, got {value}")
    if base in _AMOUNT_SPECS:
        if kind != "amount":
            raise RenderIssue(f"format {fmt} applies to amounts, value kind is {kind}")
        return _format_amount(value, base, abs_mode)
    if base in _PERCENT_SPECS:
        if kind != "ratio":
            raise RenderIssue(f"format {fmt} applies to ratios, value kind is {kind}")
        return _format_percent(value, _PERCENT_SPECS[base], abs_mode)
    if base in _PP_SPECS:
        if kind != "ratio":
            raise RenderIssue(f"format {fmt} applies to ratios, value kind is {kind}")
        return _format_pp(value, _PP_SPECS[base], abs_mode)
    raise RenderIssue(f"unknown format {fmt!r}")


def _value_kind(metric_id: str, metric: dict, fact: dict | None) -> str:
    if metric is not None:
        return "amount" if metric_id == "simplified_fcf" else "ratio"
    return "ratio" if fact and fact.get("unit") in ("ratio", "%", "％") else "amount"


class _Ledger:
    def __init__(self, run_dir: Path):
        self.facts = {f["fact_id"]: f for f in read_json(run_dir / "financials.json").get("facts", [])}
        self.metrics = {m["metric_id"]: m for m in read_json(run_dir / "metrics.json").get("metrics", [])}
        manifest = read_json(run_dir / "extraction_manifest.json")
        self.evidence_pages = {e["evidence_id"]: e.get("pdf_pages", [])
                               for e in manifest.get("evidences", [])}
        self.document = read_json(run_dir / "document.json")

    def resolve(self, binding: dict) -> tuple[Decimal, str, list[str], set[str], set[int]]:
        """返回 (value, kind, fact_ids, metric_ids, evidence_pages)。"""
        fact_ids: set[str] = set()
        metric_ids: set[str] = set()
        if "metric_id" in binding:
            metric_id = binding["metric_id"]
            metric = self.metrics.get(metric_id)
            if metric is None:
                raise RenderIssue(f"unknown metric_id: {metric_id}", binding=binding)
            if metric.get("status") != "computed" or metric.get("value") is None:
                raise RenderIssue(f"metric {metric_id} is not computed "
                                  f"(status={metric.get('status')!r})", binding=binding)
            metric_ids.add(metric_id)
            fact_ids.update(metric.get("input_fact_ids", []))
            value = Decimal(metric["value"])
            kind = _value_kind(metric_id, metric, None)
        elif "fact_id" in binding:
            fact_id = binding["fact_id"]
            fact = self.facts.get(fact_id)
            if fact is None:
                raise RenderIssue(f"unknown fact_id: {fact_id}", binding=binding)
            if fact.get("review_status") != "verified" or fact.get("value") is None:
                raise RenderIssue(f"fact {fact_id} is not verified usable "
                                  f"(review_status={fact.get('review_status')!r})", binding=binding)
            fact_ids.add(fact_id)
            value = Decimal(fact["value"])
            kind = _value_kind(None, None, fact)
        else:
            raise RenderIssue("binding needs fact_id or metric_id", binding=binding)
        pages: set[int] = set()
        for fact_id in fact_ids:
            fact = self.facts[fact_id]
            for evidence_id in fact.get("evidence_ids", []):
                pages.update(self.evidence_pages.get(evidence_id, []))
        return value, kind, sorted(fact_ids), sorted(metric_ids), pages


def _check_static_text(text: str, context: dict) -> None:
    """自由文字中的静态数字只允许年份与页码引用。"""
    for number in NUMBER_RE.finditer(text):
        literal = number.group("number").replace(",", "")
        prefix = text[max(0, number.start() - 8):number.start()]
        if literal.isdigit() and re.search(r"(?:PDF\s*第|p\.)\s*$", prefix):
            continue
        if literal.isdigit() and len(literal) == 4 and period_year_suffix(text, number):
            continue
        raise RenderIssue(f"static number {literal!r} in free text must be a year or page citation",
                          **context)


def _render_statement(ledger: _Ledger, anchor: str, statement: dict,
                      claim_no: int) -> tuple[str, dict]:
    template = statement.get("template")
    if not isinstance(template, str) or not template.strip():
        raise RenderIssue("statement.template is required", anchor=anchor)
    claim_type = statement.get("claim_type") or "inference"
    if claim_type not in _CLAIM_TYPES:
        raise RenderIssue(f"illegal claim_type {claim_type!r}", anchor=anchor)
    bindings = statement.get("bindings") or {}
    _check_static_text(_PLACEHOLDER_RE.sub("X", template), {"anchor": anchor})

    fact_ids: set[str] = set()
    metric_ids: set[str] = set()
    pages: set[int] = set()

    def replace(match) -> str:
        name, fmt = match.group(1), match.group(2)
        binding = bindings.get(name)
        if binding is None:
            raise RenderIssue(f"template placeholder {{{name}}} has no binding", anchor=anchor)
        if fmt is None:
            raise RenderIssue(f"placeholder {{{name}}} needs an explicit format", anchor=anchor)
        value, kind, fids, mids, pgs = ledger.resolve(binding)
        fact_ids.update(fids)
        metric_ids.update(mids)
        pages.update(pgs)
        return format_value(value, kind, fmt)

    text = _PLACEHOLDER_RE.sub(replace, template)
    if claim_type == "calculation" and not metric_ids:
        raise RenderIssue("calculation statement needs a metric binding", anchor=anchor)
    if claim_type == "fact" and not fact_ids:
        raise RenderIssue("fact statement needs a fact binding", anchor=anchor)

    if statement.get("cite_pages", True) and pages:
        citation = "、".join(str(page) for page in sorted(pages))
        text = f"{text}（PDF第{citation}页）"

    claim = {
        "claim_id": f"c-{claim_no:04d}",
        "report_anchor": anchor,
        "text": text,
        "fact_ids": sorted(fact_ids),
        "metric_ids": sorted(metric_ids),
        "evidence_ids": sorted({
            evidence_id
            for fact_id in fact_ids
            for evidence_id in ledger.facts[fact_id].get("evidence_ids", [])
        }),
        "source_pages": sorted(pages),
        "claim_type": claim_type,
        "display_unit": statement.get("display_unit"),
    }
    return text, claim


def _render_table_row(ledger: _Ledger, anchor: str, display_unit: str | None,
                      row: dict, claim_no: int) -> tuple[str, dict]:
    label = row.get("label")
    if not isinstance(label, str) or not label.strip():
        raise RenderIssue("table row label is required", anchor=anchor)
    cells_spec = row.get("cells")
    if not isinstance(cells_spec, list):
        raise RenderIssue("table row cells must be a list", anchor=anchor)

    fact_ids: set[str] = set()
    metric_ids: set[str] = set()
    pages: set[int] = set()
    cells: list[str] = []
    for cell in cells_spec:
        if isinstance(cell, str):
            _check_static_text(cell, {"anchor": anchor, "row": label})
            cells.append(cell)
            continue
        if not isinstance(cell, dict):
            raise RenderIssue("table cell must be a string or a binding", anchor=anchor)
        fmt = cell.get("format")
        if not fmt:
            raise RenderIssue("bound table cell needs a format", anchor=anchor)
        value, kind, fids, mids, pgs = ledger.resolve(cell)
        fact_ids.update(fids)
        metric_ids.update(mids)
        pages.update(pgs)
        cells.append(format_value(value, kind, fmt))

    text = "| " + " | ".join([label, *cells]) + " |"
    claim_type = row.get("claim_type") or ("calculation" if metric_ids else "fact")
    if claim_type not in _CLAIM_TYPES:
        raise RenderIssue(f"illegal claim_type {claim_type!r}", anchor=anchor)
    claim = {
        "claim_id": f"c-{claim_no:04d}",
        "report_anchor": anchor,
        "text": text,
        "fact_ids": sorted(fact_ids),
        "metric_ids": sorted(metric_ids),
        "evidence_ids": sorted({
            evidence_id
            for fact_id in fact_ids
            for evidence_id in ledger.facts[fact_id].get("evidence_ids", [])
        }),
        "source_pages": sorted(pages),
        "claim_type": claim_type,
        "display_unit": display_unit,
    }
    return text, claim


def render_report(run_dir: Path, inputs: dict) -> tuple[str | None, list[dict] | None, list[dict]]:
    """渲染正文与 claims；返回 (markdown | None, claims | None, issues)。"""
    run_dir = Path(run_dir)
    ledger = _Ledger(run_dir)
    sections = inputs.get("sections")
    if not isinstance(sections, list) or not sections:
        return None, None, [{"error": "sections must be a nonempty list"}]

    issues: list[dict] = []
    body_parts: list[str] = []
    claims: list[dict] = []
    claim_no = 0

    title = _report_title(ledger.document, inputs.get("report_title"))
    if title:
        body_parts.append(f"# {title}")

    for section in sections:
        anchor = section.get("anchor")
        if not isinstance(anchor, str) or not anchor.strip():
            issues.append({"error": "section.anchor is required"})
            continue
        body_parts.append(anchor)
        for statement in section.get("statements") or []:
            try:
                text, claim = _render_statement(ledger, anchor, statement, claim_no + 1)
            except RenderIssue as exc:
                issues.append(exc.issue)
                continue
            claim_no += 1
            body_parts.append(text)
            claims.append(claim)
        table = section.get("table")
        if table:
            try:
                rows_spec = table.get("rows")
                if not isinstance(rows_spec, list):
                    raise RenderIssue("table.rows must be a list", anchor=anchor)
                columns = table.get("columns") or []
                lines = ["| " + " | ".join(str(c) for c in columns) + " |",
                         "| " + " | ".join("---" for _ in columns) + " |"]
                for row in rows_spec:
                    text, claim = _render_table_row(
                        ledger, anchor, table.get("display_unit"), row, claim_no + 1)
                    claim_no += 1
                    lines.append(text)
                    claims.append(claim)
                body_parts.append("\n".join(lines))
            except RenderIssue as exc:
                issues.append(exc.issue)
        for paragraph in section.get("paragraphs") or []:
            try:
                _check_static_text(paragraph, {"anchor": anchor})
            except RenderIssue as exc:
                issues.append(exc.issue)
                continue
            body_parts.append(paragraph)

    if issues:
        return None, None, issues
    return "\n\n".join(body_parts) + "\n", claims, []


def _report_title(document: dict, provided: str | None) -> str | None:
    company, code = document.get("company_name"), document.get("stock_code")
    period = document.get("period") or {}
    end = period.get("end") or ""
    if company and code and end:
        return f"{company}（{code}）{end[:4]}分析"
    return provided


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="同源渲染 analysis.md 与 report_claims.json")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--inputs", default="report_inputs.json")
    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    try:
        inputs = read_json(run_dir / args.inputs)
        markdown, claims, issues = render_report(run_dir, inputs)
    except (OSError, ValueError) as exc:
        print(f"render_report failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if issues:
        write_json(run_dir / "render_issues.json",
                   {"schema_version": 1, "issues": issues})
        emit_status("repair_needed", {"render_issues": str(run_dir / "render_issues.json")},
                    [issue["error"] for issue in issues])
        raise SystemExit(2)
    write_json(run_dir / "report_claims.json",
               {"schema_version": 1, "claims": claims})
    (run_dir / "analysis.md").write_text(markdown, encoding="utf-8", newline="\n")
    emit_status("ok", {
        "analysis_md": str(run_dir / "analysis.md"),
        "report_claims_json": str(run_dir / "report_claims.json"),
    }, [])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
