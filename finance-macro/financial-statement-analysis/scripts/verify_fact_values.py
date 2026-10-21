#!/usr/bin/env python3
"""fact_inputs.json 逐值复核：确认每个 raw_value 真的出现在其证据里。

skill 自带的 build_financials 只做"逐格核对"（table cell == raw_value）。
这个检查在"用错表"时依然会通过——同页双表场景下，母公司表的 cell 与你
抄进去的母公司数完全一致，程序无话可说，但整份资产负债结构结论全错。
本脚本补两层检查：

1. text 证据：定位 raw_label 所在行，往后扫连续金额行，确认 raw_value 在其中。
   能抓出"标签在页上但值不在"，以及把"流动负债合计"当成"负债合计"、
   或被 PDF 折行的长标签（"五、净利润（净亏损以“—”号填" / "列）"）误导。
2. table 证据：命中 multiple tables 告警时标 ATTRIBUTION_RISK，
   提示该页承载多张表，必须人工确认内容归属（合并 vs 母公司）。

用法：
    uv run python verify_fact_values.py --run-dir <run-dir> [--inputs fact_inputs.json]

退出码：0 全部通过；2 存在不一致（逐条打印原因）。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from financial_schema import parse_amount

AMOUNT_RE = re.compile(r"^(?:-?[\d,]+(?:\.\d+)?|\([\d,]+(?:\.\d+)?\))$")
PAGE_PREFIX_RE = re.compile(r"^\[p\.\d+\]\s*")


def norm_cell(text: str) -> str:
    return re.sub(r"\s+", "", str(text).replace(",", "").replace("，", ""))


def amounts_after(lines: list[str], index: int, depth: int = 10) -> list[str]:
    """标签行之后连续出现的金额行（PDF 会把长标签折行，故允许中间夹非金额行）。"""
    found: list[str] = []
    for line in lines[index + 1: index + 1 + depth]:
        text = line.strip()
        if AMOUNT_RE.match(text):
            found.append(text)
        elif found:
            break
    return found


def load_excerpt_lines(run_dir: Path, record: dict) -> list[str]:
    path = run_dir / record["file"]
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8").splitlines()
    return [PAGE_PREFIX_RE.sub("", line) for line in raw]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="fact_inputs 逐值复核")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--inputs", default="fact_inputs.json")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    facts = json.loads((run_dir / args.inputs).read_text(encoding="utf-8")).get("facts", [])
    manifest = json.loads((run_dir / "extraction_manifest.json").read_text(encoding="utf-8"))
    evidences = {e["evidence_id"]: e for e in manifest.get("evidences", [])}

    problems: list[str] = []
    risks: list[str] = []
    for index, item in enumerate(facts):
        metric = item.get("metric")
        label = item.get("raw_label") or ""
        raw_value = item.get("raw_value")
        unit = item.get("raw_unit") or "元"
        evidence = item.get("evidence") or {}
        evidence_id = evidence.get("evidence_id")
        record = evidences.get(evidence_id)
        if record is None:
            problems.append(f"[{index}] {metric}: unknown evidence_id {evidence_id!r}")
            continue
        if str(raw_value).strip() in {"—", "–", "-", "--", ""}:
            continue  # 未披露，程序会补 missing_reason

        target = parse_amount(str(raw_value), unit)
        if target is None:
            problems.append(f"[{index}] {metric}: raw_value {raw_value!r} unparseable with unit {unit!r}")
            continue

        if record.get("kind") == "table":
            data = json.loads((run_dir / record["file"]).read_text(encoding="utf-8"))
            rows = data.get("rows", [])
            locator = evidence.get("locator") or {}
            row, col = locator.get("row"), locator.get("col")
            if not isinstance(row, int) or not isinstance(col, int):
                problems.append(f"[{index}] {metric}: table evidence needs row/col locator")
                continue
            if not (0 <= row < len(rows) and 0 <= col < len(rows[row])):
                problems.append(f"[{index}] {metric}: locator out of range r{row}c{col}")
                continue
            cell = parse_amount(rows[row][col], unit)
            if cell is None or cell != target:
                problems.append(f"[{index}] {metric}: cell {rows[row][col]!r} != raw_value {raw_value!r}")
            if any("multiple tables" in issue for issue in record.get("issues", [])):
                risks.append(
                    f"[{index}] {metric}: {evidence_id} (p.{record['pdf_pages']}) 命中同页多表告警，"
                    f"确认内容归属（合并/母公司）")
            continue

        if record.get("kind") == "text":
            lines = load_excerpt_lines(run_dir, record)
            if not lines:
                problems.append(f"[{index}] {metric}: evidence file missing {record['file']}")
                continue
            locator = evidence.get("locator") or {}
            line_no = locator.get("line")
            if (not isinstance(line_no, int) or not 1 <= line_no <= len(lines)
                    or label.strip() != lines[line_no - 1].strip()):
                problems.append(f"[{index}] {metric}: exact label not at locator.line in {evidence_id}")
                continue
            window = amounts_after(lines, line_no - 1)
            numbers = [parse_amount(text, unit) for text in window]
            numbers = [n for n in numbers if n is not None]
            if not any(n == target for n in numbers):
                problems.append(
                    f"[{index}] {metric}: raw_value {raw_value!r} not in amount sequence "
                    f"after {label!r} in {evidence_id} (saw {window})")
            continue

        problems.append(
            f"[{index}] {metric}: evidence {evidence_id} kind={record.get('kind')!r} "
            f"不可核对，需人工确认")

    print(json.dumps({"passed": not problems, "checked": len(facts), "issues": problems,
                      "attribution_risks": risks}, ensure_ascii=False))
    return 2 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
