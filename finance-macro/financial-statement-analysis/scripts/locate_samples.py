"""抽查单候选定位器：按建议清单在 PDF 证据中定位标签与数值行。

输出每个 metric 的候选（evidence_id / line / 数值候选），供 agent 复核挑选后
组装 fact_inputs 抽查单——agent 不应再为抽查编写定位脚本。与结构化数据同存时
自动标注候选值是否与东财一致，辅助挑选。
"""

from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from artifacts import emit_status, read_json
from financial_schema import METRIC_CONTRACTS, STRUCTURED_FIELD_MAP
from report_values import NUMBER_RE, SCALES

RECOMMENDED = (
    "revenue", "net_profit_owners", "net_profit_group", "cfo", "total_assets",
    "monetary_funds", "cost_of_sales", "total_equity", "total_liabilities",
    "cash_equivalents", "fx_effect_on_cash", "accounts_receivable", "inventory",
    "short_term_borrowings", "long_term_borrowings",
)
_VALUE_LINES_AFTER = 3


def _normalize_label(label: str) -> str:
    text = label.strip()
    text = re.sub(r"^[（(]?[一二三四五六七八九十\d]{1,3}[）)、.．]\s*", "", text)
    text = re.sub(r"[（(][^（）()]*[)）]\s*[:：]?$", "", text)
    text = text.rstrip(":=： ").strip()
    return re.sub(r"\s+", "", text)


def _extract_values(text: str) -> list[str]:
    """提取行内全部数值（含单位缩放），返回精确十进制字符串。"""
    found: list[str] = []
    for match in NUMBER_RE.finditer(text):
        try:
            num = Decimal(match.group("number").replace(",", ""))
        except InvalidOperation:
            continue
        scale = SCALES.get((match.group("unit") or "").lower(), Decimal(1))
        found.append(format(num * scale, "f"))
    return found


def _evidence_texts(run_dir: Path) -> list[tuple[str, int, str]]:
    """返回 [(evidence_id, line_no, line_text)]，仅 text 证据。"""
    manifest_path = run_dir / "extraction_manifest.json"
    if not manifest_path.exists():
        return []
    out: list[tuple[str, int, str]] = []
    for record in read_json(manifest_path).get("evidences", []):
        if record.get("kind") != "text" or not record.get("complete", False):
            continue
        path = run_dir / record.get("file", "")
        if not path.exists():
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            out.append((record["evidence_id"], line_no, line))
    return out


def _structured_current(run_dir: Path, metric: str) -> str | None:
    """结构化模式下该指标本期值（用于标注候选一致性），不可得返回 None。"""
    path = run_dir / "structured_financials.json"
    mapping = STRUCTURED_FIELD_MAP.get(metric)
    if not path.exists() or mapping is None:
        return None
    kind, field = mapping
    try:
        doc = read_json(path)
        document = read_json(run_dir / "document.json")
    except (OSError, ValueError):
        return None
    day = (document.get("period") or {}).get("end")
    rows = ((doc.get("reports") or {}).get(day) or {}).get(kind) or []
    if not rows:
        return None
    value = rows[0].get(field)
    return None if value is None else (value if isinstance(value, str) else format(value, "f"))


def locate_samples(run_dir: Path, metrics: list[str] | None = None) -> dict:
    run_dir = Path(run_dir)
    wanted = list(metrics or RECOMMENDED)
    lines = _evidence_texts(run_dir)
    normalized = [(eid, no, _normalize_label(text), text) for eid, no, text in lines]

    candidates: dict[str, list[dict]] = {}
    missing: list[str] = []
    for metric in wanted:
        contract = METRIC_CONTRACTS.get(metric)
        if contract is None:
            missing.append(metric)
            continue
        aliases = [_normalize_label(a) for a in (metric, *contract["aliases"])]
        hits: list[dict] = []
        for eid, no, norm, raw in normalized:
            label = next((a for a in aliases if a and a in norm), None)
            if label is None:
                continue
            window = [raw]
            for eid2, no2, _n, raw2 in normalized:
                if eid2 == eid and no <= no2 <= no + _VALUE_LINES_AFTER:
                    window.append(raw2)
            values: list[str] = []
            for line in window:
                for value in _extract_values(line):
                    if value not in values:
                        values.append(value)
            hits.append({
                "evidence_id": eid, "line": no, "label": label,
                "values": values[:6],
                "suggested_period_ref": ("current" if contract["period_kind"] == "duration"
                                         else "closing"),
                "match_structured": None,
            })
        expected = _structured_current(run_dir, metric)
        if expected is not None:
            for hit in hits:
                hit["match_structured"] = expected in hit["values"]
        if hits:
            candidates[metric] = hits
        else:
            missing.append(metric)
    return {"status": "ok", "candidates": candidates, "not_located": missing,
            "hint": ("review candidates, pick one per metric, then write fact_inputs.json "
                     "(values must equal the PDF; match_structured=true helps choose)")}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="按建议清单生成抽查单候选定位")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--metrics", default="", help="逗号分隔 metric；缺省为建议清单")
    args = parser.parse_args(argv)
    metrics = [m.strip() for m in args.metrics.split(",") if m.strip()] or None
    try:
        result = locate_samples(Path(args.run_dir), metrics)
    except (OSError, ValueError) as exc:
        print(f"locate_samples failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    emit_status(result["status"],
                {"candidates": result["candidates"], "not_located": result["not_located"],
                 "hint": result["hint"]},
                [f"not located: {m}" for m in result["not_located"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
