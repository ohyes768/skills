"""Declarative report-input constructor: spec JSON → report_inputs.json.

Spec sections mirror the report_inputs.json contract, with one construction-time
expansion: a trailing "" cell in a table row is replaced by the united source-page
citation of that row's bound cells. Every statement, row and paragraph is validated
against the ledger while building, and the full input preflight runs before writing;
a failed spec writes nothing and spends no report budget.
CLI: --run-dir RUN --spec SPEC [--out report_inputs.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from artifacts import read_json, write_json
from render_report import (
    RenderIssue,
    _check_static_text,
    _Ledger,
    _render_statement,
    _render_table_row,
)

ReportInputError = RenderIssue


def _expand_row_cells(ledger: _Ledger, anchor: str, row: dict) -> dict:
    cells = list(row.get("cells", []))
    pages: set[int] = set()
    for cell in cells:
        if isinstance(cell, dict):
            pages.update(ledger.resolve(cell)[-1])
    if cells and cells[-1] == "":
        if not pages:
            raise ReportInputError("cannot generate source citation without evidence pages",
                                   anchor=anchor, row_label=row.get("label"))
        cells[-1] = "、".join(f"PDF 第 {p} 页" for p in sorted(pages))
    item = {"label": row.get("label"), "cells": cells}
    if row.get("claim_type"):
        item["claim_type"] = row["claim_type"]
    return item


def build_report_inputs(run_dir: Path | str, spec: dict) -> dict:
    """Validate against the ledger, expand auto citations, preflight, return inputs."""
    run_dir = Path(run_dir)
    ledger = _Ledger(run_dir)
    sections_out: list[dict] = []
    for s_index, section in enumerate(spec.get("sections", []), 1):
        anchor = section.get("anchor")
        if not isinstance(anchor, str) or not anchor.strip():
            raise ReportInputError(f"section #{s_index} anchor is required")
        out: dict = {"anchor": anchor}
        statements = []
        for index, item in enumerate(section.get("statements", []), 1):
            _render_statement(ledger, anchor, item, index, index)
            statements.append(item)
        if statements:
            out["statements"] = statements
        paragraphs = []
        for index, text in enumerate(section.get("paragraphs", []), 1):
            _check_static_text(text, {"anchor": anchor, "paragraph_index": index}, strict=True)
            paragraphs.append(text)
        if paragraphs:
            out["paragraphs"] = paragraphs
        table = section.get("table")
        if table:
            rows = []
            for index, row in enumerate(table.get("rows", []), 1):
                item = _expand_row_cells(ledger, anchor, row)
                _render_table_row(ledger, anchor, table.get("display_unit"), item, index, index)
                rows.append(item)
            table_out = {key: value for key, value in table.items() if key != "rows"}
            table_out["rows"] = rows
            out["table"] = table_out
        sections_out.append(out)
    inputs: dict = {"schema_version": 1, "sections": sections_out}
    if spec.get("report_title"):
        inputs["report_title"] = spec["report_title"]

    from verify_report_inputs import verify_inputs

    issues = verify_inputs(run_dir, inputs)
    if issues:
        raise ReportInputError(str(issues))
    return inputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="report_inputs 构造器（声明式 spec，逐项校验）")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--spec", required=True, help="声明式报告规格 JSON 文件")
    parser.add_argument("--out", default="report_inputs.json")
    args = parser.parse_args(argv)

    try:
        spec = read_json(Path(args.spec))
        inputs = build_report_inputs(args.run_dir, spec)
    except (OSError, ValueError, KeyError, TypeError, RenderIssue) as exc:
        print(json.dumps({"status": "repair_needed", "issues": [str(exc)]}, ensure_ascii=False))
        return 2
    write_json(Path(args.run_dir) / args.out, inputs)
    print(json.dumps({"status": "ok", "path": str(Path(args.run_dir) / args.out),
                      "sections": len(inputs["sections"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
