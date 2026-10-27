#!/usr/bin/env python3
"""Generate fact_inputs from a spec, migrated from financial-pitfall-recovery.

Each spec entry requires metric, label, cur, page and raw_unit; prior is optional.
Optional ref sets an explicit period (opening cash must use ref=opening).
Labels and values are checked against extracted text; duplicate labels are rejected.
Use ordinary fact_inputs for table evidence, missing values, or ambiguous text pages.
This does not determine consolidation scope or column-period meaning for the analyst.
CLI: --run-dir RUN --spec SPEC [--out fact_inputs.json].
退出码：0 成功；2 spec 与证据不一致（SpecError，消息走 stderr）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from artifacts import write_json
from financial_schema import METRIC_CONTRACTS, resolve_metric_label
from verify_fact_values import AMOUNT_RE, PAGE_PREFIX_RE


class SpecError(ValueError):
    """spec 与证据不一致：可修复的输入问题，经 run_pipeline 报 repair_needed。"""


class Run:
    """运行目录的只读视图：excerpt 行、证据清单、事实构造与逐值核对。"""

    def __init__(self, run_dir: Path):
        self.dir = run_dir
        manifest = json.loads(
            (run_dir / "extraction_manifest.json").read_text(encoding="utf-8"))
        self.text_ev: dict[int, str] = {}
        self.excerpt_lines: dict[int, list[str]] = {}
        self.excerpt_body: dict[int, list[str]] = {}
        for record in manifest.get("evidences", []):
            if record.get("kind") != "text" or len(record.get("pdf_pages", [])) != 1:
                continue
            page = record["pdf_pages"][0]
            if not record.get("complete", False):
                continue
            raw = (run_dir / record["file"]).read_text(encoding="utf-8").splitlines()
            if page in self.text_ev:
                if raw == self.excerpt_lines[page]:
                    continue
                raise ValueError(
                    f"ambiguous text evidence on p.{page}: {self.text_ev[page]} and "
                    f"{record['evidence_id']} differ; use fact_inputs.json with explicit evidence_id")
            self.text_ev[page] = record["evidence_id"]
            self.excerpt_lines[page] = raw
            self.excerpt_body[page] = [PAGE_PREFIX_RE.sub("", line).strip() for line in raw]

    def label_index(self, page: int, label: str) -> int | None:
        """精确定位标签行；精确优先，避免「负债合计」误命中「流动负债合计」。"""
        body = self.excerpt_body.get(page, [])
        hits = [i for i, line in enumerate(body) if line == label]
        if len(hits) > 1:
            raise ValueError(f"ambiguous 重复标签 {label!r} on p.{page}; split/select evidence")
        return hits[0] if hits else None

    def amounts_after(self, page: int, index: int, depth: int = 10) -> list[str]:
        """标签行之后的连续金额行（金额前允许夹非金额行，金额开始后遇非金额行才停）。"""
        found: list[str] = []
        for line in self.excerpt_body.get(page, [])[index + 1: index + 1 + depth]:
            if AMOUNT_RE.match(line):
                found.append(line)
            elif found:
                break
        return found

    def _ref(self, metric: str, which: int) -> str:
        if METRIC_CONTRACTS[metric]["period_kind"] == "instant":
            return "closing" if which == 0 else "opening"
        return "current" if which == 0 else "prior"

    def fact(self, entry: dict) -> list[dict]:
        metric, label, page = entry["metric"], entry["label"], entry["page"]
        metric = metric if metric in METRIC_CONTRACTS else resolve_metric_label(metric, label)
        if metric is None:
            raise ValueError(f"unknown metric: {entry['metric']}")
        unit = entry.get("raw_unit")
        if not unit:
            raise ValueError("raw_unit is required; copy the unit from the source table")
        index = self.label_index(page, label)
        if index is None:
            raise SpecError(f"LABEL NOT FOUND: {label!r} on p.{page}")
        evidence_id = self.text_ev.get(page)
        if not evidence_id:
            raise SpecError(
                f"p.{page} 没有 text 证据；先跑 extract_sections.py --pages {page}")
        line_no = index + 1  # locator.line 是 excerpt 文件的 1 起行号
        body = self.excerpt_body[page]
        if body[index] != label:
            raise SpecError(
                f"ALIGN ERROR p.{page} {evidence_id} line {line_no}: "
                f"期望标签行 {label!r}，实际 {body[index]!r}")
        candidates = self.amounts_after(page, index)
        if not candidates:
            raise SpecError(
                f"NO AMOUNTS p.{page}: 标签 {label!r} 之后没有连续金额行 "
                f"（行号基准或标签选择有问题）")

        explicit_ref = entry.get("ref")
        out: list[dict] = []
        for which, key in ((0, "cur"), (1, "prior")):
            if key not in entry:
                continue
            value = str(entry[key]).strip()
            if value not in candidates:
                raise SpecError(
                    f"VALUE NOT FOUND ({key}): {value!r} after {label!r} on p.{page}; "
                    f"candidates={candidates}")
            if explicit_ref:
                if which != 0:
                    raise SpecError("spec 条目带显式 ref 时不能同时有 prior")
                ref = explicit_ref
            else:
                ref = self._ref(metric, which)
            item = {
                "metric": metric,
                "raw_label": label,
                "raw_value": value,
                "raw_unit": unit,
                "period_ref": ref,
                "evidence": {"evidence_id": evidence_id, "locator": {"line": line_no}},
            }
            if entry.get("scope"):
                item["scope"] = entry["scope"]
            if entry.get("note"):
                item["note"] = entry["note"]
            out.append(item)
        return out


def build_inputs(run_dir: Path, spec: dict) -> dict:
    """Generate all facts before writing; a failed spec cannot replace valid inputs."""
    run = Run(run_dir)
    facts = [fact for entry in spec["facts"] for fact in run.fact(entry)]
    if not facts:
        raise ValueError("spec must contain at least one fact")
    return {"schema_version": 1, "facts": facts}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="fact_inputs 生成器（逐值核对）")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--spec", required=True, help="声明式规格 JSON 文件")
    parser.add_argument("--out", default="fact_inputs.json")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    try:
        out = build_inputs(run_dir, spec)
    except SpecError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    write_json(run_dir / args.out, out)
    print(json.dumps({"status": "ok", "fact_count": len(out["facts"]),
                      "path": str(run_dir / args.out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
