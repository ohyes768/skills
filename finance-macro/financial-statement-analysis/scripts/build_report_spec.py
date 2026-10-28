"""从 compute 产物机械生成 report spec（施工图）。

把 references/report-spec-skeleton.json 里的 FACT_* 占位替换成本次 compute 的真实
fact_id，并按本次实际可用的 fact / metric 裁剪结构；生成的 spec 只含结构与绑定，
定性段落留给 agent 填写。

映射规则（纯查表，无语义判断）：
  - 占位名后缀 _CUR → 本期/期末；_PREV → 比较期
  - 比较期语义随科目而异：duration 科目（利润表、现金流量表）取上年同期；
    instant 科目（资产负债表）取上年末
  - scope：consolidated 优先，parent 只在骨架明确要求母公司口径时使用
  - 本次没有的事实（如无商誉、无在建工程）：整行删除，不填零
  - metric 绑定：status 必须为 computed 且 value 非空，否则该绑定删除
  - *_yoy 在基期为负时为 not_applicable，改写为「由上年同期转为本期」双事实句式

CLI: --run-dir RUN [--skeleton PATH] [--out spec.json] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from artifacts import read_json, write_json

PLACEHOLDER_RE = re.compile(r"^FACT_([A-Z0-9_]+?)_(CUR|PREV|OPEN|CLOSE)$")

# 骨架占位名 → financials.json 的 metric 名。骨架用的是可读简称。
PLACEHOLDER_TO_METRIC = {
    "REVENUE": "revenue",
    "COST_OF_SALES": "cost_of_sales",
    "SELLING_EXPENSES": "selling_expenses",
    "ADMIN_EXPENSES": "admin_expenses",
    "RD_EXPENSE": "r_and_d_expense",
    "FINANCE_COSTS": "finance_costs",
    "OPERATING_PROFIT": "operating_profit",
    "PROFIT_BEFORE_TAX": "net_profit_before_tax",
    "NET_PROFIT_GROUP": "net_profit_group",
    "NET_PROFIT_OWNERS": "net_profit_owners",
    "CFO": "cfo",
    "CFI": "cfi",
    "CFF": "cff",
    "CAPEX": "capex_purchase_fixed_assets",
    "MONETARY_FUNDS": "monetary_funds",
    "AR": "accounts_receivable",
    "PREPAYMENTS": "prepayments",
    "INVENTORY": "inventory",
    "FIXED_ASSETS": "fixed_assets",
    "CIP": "construction_in_progress",
    "GOODWILL": "goodwill",
    "ST_BORROWINGS": "short_term_borrowings",
    "LT_BORROWINGS": "long_term_borrowings",
    "CONTRACT_LIABILITIES": "contract_liabilities",
    "TOTAL_LIABILITIES": "total_liabilities",
    "EQUITY_OWNERS": "total_equity_owners",
    "TOTAL_EQUITY": "total_equity",
    "TOTAL_ASSETS": "total_assets",
    "TOTAL_CURRENT_ASSETS": "total_current_assets",
    "TOTAL_CURRENT_LIABILITIES": "total_current_liabilities",
    "CASH_EQUIVALENTS": "cash_equivalents",
    "NOTES_RECEIVABLE": "notes_receivable",
    "GROSS_PROFIT": "gross_profit",
    "FX_EFFECT_ON_CASH": "fx_effect_on_cash",
}


class SpecBuildError(ValueError):
    """生成不了 spec：数据结构与骨架假设不符。"""


class _FactIndex:
    """按 (metric, scope, period 角色) 索引 financials.json 的事实。"""

    def __init__(self, financials: dict):
        self.facts = [f for f in financials.get("facts", []) if f.get("review_status") == "verified" and f.get("value") is not None]
        self._by_metric: dict[str, list[dict]] = {}
        for f in self.facts:
            self._by_metric.setdefault(f["metric"], []).append(f)

    def find(self, metric: str, role: str, target_end: str,
             scope_preference: tuple[str, ...] = ("consolidated",)) -> dict | None:
        from fact_selection import prior_year
        from financial_schema import METRIC_CONTRACTS
        instant = METRIC_CONTRACTS[metric]["period_kind"] == "instant"
        expected_end = (target_end if role == "cur" else
                        f"{int(target_end[:4])-1}-12-31" if instant else prior_year(target_end))
        candidates = self._by_metric.get(metric) or []
        for scope in scope_preference:
            matched = [f for f in candidates if f.get("scope") == scope
                       and f.get("period", {}).get("end") == expected_end
                       and f.get("period", {}).get("kind") == ("instant" if instant else "duration")]
            if matched:
                if len({f["value"] for f in matched}) > 1:
                    raise SpecBuildError(f"conflicting report facts for {metric}@{expected_end}")
                return matched[0]
        return None


def _target_end(run_dir: Path, facts: list[dict]) -> str:
    """本次报告期的期末日：取 duration 类事实里最晚的 end。"""
    period = read_json(run_dir / "document.json").get("period", {})
    if period.get("end"):
        return period["end"]
    ends = set()
    for f in facts:
        period = f.get("period") or {}
        if period.get("kind") == "duration" and period.get("end"):
            ends.add(period["end"])
    if not ends:
        raise SpecBuildError("no duration facts found; cannot determine report period end")
    return max(ends)


def _resolve_placeholder(name: str, index: _FactIndex, target_end: str) -> dict | None:
    """FACT_* 占位 → 真实 fact。返回 None 表示本次没有该事实。"""
    m = PLACEHOLDER_RE.match(name)
    if not m:
        return None
    metric_key, role = m.group(1), m.group(2)
    metric = PLACEHOLDER_TO_METRIC.get(metric_key)
    if metric is None:
        return None
    if role == "CUR":
        return index.find(metric, "cur", target_end)
    # PREV / OPEN / CLOSE：duration 科目取上年同期，instant 科目取上年末
    for scope in ("consolidated",):
        found = index.find(metric, "prev", target_end, (scope,))
        if found:
            return found
    return None


def _cell_bindings(spec: dict) -> list[str]:
    """收集 spec 里出现的所有 fact_id 占位。"""
    found: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "fact_id" and isinstance(value, str):
                    found.append(value)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(spec)
    return found


def _rewrite_binding(node, index: _FactIndex, target_end: str) -> bool:
    """就地替换 node 内的 fact_id 占位。

    返回 False 表示**必需的事实缺失**（调用方应整行/整条删除）；
    只含 metric 绑定或已替换完的节点返回 True（metric 可用性另行检查）。
    """
    ok = True
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key == "fact_id" and isinstance(value, str) and value.startswith("FACT_"):
                fact = _resolve_placeholder(value, index, target_end)
                if fact is None:
                    return False  # 缺失 → 调用方整行删除
                node[key] = fact["fact_id"]
            else:
                ok = _rewrite_binding(value, index, target_end) and ok
    elif isinstance(node, list):
        for item in node:
            ok = _rewrite_binding(item, index, target_end) and ok
    return ok


def _metric_ok(metrics: dict, metric_id: str) -> bool:
    metric = metrics.get(metric_id)
    return bool(metric and metric.get("status") == "computed" and metric.get("value") is not None)


def _metric_value(metrics: dict, metric_id: str) -> Decimal | None:
    metric = metrics.get(metric_id)
    if not metric or metric.get("value") is None:
        return None
    try:
        return Decimal(str(metric["value"]))
    except (ValueError, TypeError, InvalidOperation):
        return None


def _fix_decline_formats(node, metrics: dict) -> None:
    """decline_* 只接受非正值；指标实际为正（增长）时改用 percent*。

    表格单元格用 decline_* 时会自动输出「下降X%」前缀，与正号矛盾时必须换格式符，
    否则渲染直接阻塞。statement 模板的方向词由模板文字决定，这里只换格式符。
    """
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if key == "format" and isinstance(value, str) and value.startswith("decline_"):
                metric_id = node.get("metric_id")
                if metric_id:
                    number = _metric_value(metrics, metric_id)
                    if number is not None and number > 0:
                        node[key] = value[len("decline_"):]
            else:
                _fix_decline_formats(value, metrics)
    elif isinstance(node, list):
        for item in node:
            _fix_decline_formats(item, metrics)


_PLACEHOLDER_PARAGRAPH_MARKERS = (
    "这里写", "写清", "各写一句", "逐条写明", "写明", "各覆盖一层",
)


def _is_placeholder_paragraph(text: str) -> bool:
    """骨架提示语特征：包含「写…」类祈使表述，不是真正的分析结论。"""
    if not text:
        return False
    return any(marker in text for marker in _PLACEHOLDER_PARAGRAPH_MARKERS)


def _report_title(run_dir: Path) -> str | None:
    """按 document.json 生成标题。

    上游契约（report-template.md + validate_report.py）：标题固定为
    `{公司}（{代码}）{结束年份}分析`，校验器按 document 元数据强制匹配，
    因此这里生成的值只作 document 元数据缺失时的兜底。
    """
    document = read_json(run_dir / "document.json")
    company = document.get("company_name")
    code = document.get("stock_code")
    period = document.get("period") or {}
    end = period.get("end") or ""
    if not (company and code and end):
        return None
    return f"{company}（{code}）{end[:4]}分析"


def build_spec(run_dir: Path, skeleton: dict) -> tuple[dict, list[str]]:
    """返回 (spec, notes)。notes 记录每个占位的解析结果，便于审计。"""
    financials = read_json(run_dir / "financials.json")
    metrics_doc = read_json(run_dir / "metrics.json")
    metrics = {m["metric_id"]: m for m in metrics_doc.get("metrics", [])}

    facts = [f for f in financials.get("facts", []) if f.get("review_status") == "verified" and f.get("value") is not None]
    if not facts:
        raise SpecBuildError("financials.json has no verified facts")
    target_end = _target_end(run_dir, facts)
    index = _FactIndex(financials)

    risk_flags = {f["flag_id"]: f for f in metrics_doc.get("red_flags", [])}
    risk_ids = dict(zip(
        ["存贷双高", "应收账款增速超过营业收入", "存货突升", "经营现金流为负而净利润为正",
         "少数股东损益异常", "商誉占比过高", "预付款项突升", "在建工程长期不转固"],
        ["dual_high_cash_debt", "receivable_outpacing_revenue", "inventory_sudden_rise",
         "negative_cfo_positive_profit", "minority_interest_anomaly", "goodwill_heavy",
         "prepayment_surge", "construction_not_converting"], strict=True))
    status_text = {"flagged": "触发", "clear": "已检查未发现", "insufficient_data": "资料不足",
                   "not_applicable": "行业不适用"}
    notes: list[str] = []
    out_sections: list[dict] = []

    for section in skeleton.get("sections", []):
        out_section = dict(section)
        anchor = section.get("anchor", "")

        # ---- statements ----
        kept_statements = []
        for stmt in section.get("statements", []):
            binding = stmt.get("bindings") or {}
            missing_metric = [
                name for name, b in binding.items()
                if "metric_id" in b and not _metric_ok(metrics, b["metric_id"])
            ]
            if missing_metric:
                notes.append(f"{anchor}: 丢弃 statement（metric 不可用: {missing_metric}）")
                continue
            stmt = json.loads(json.dumps(stmt))
            if not _rewrite_binding(stmt, index, target_end):
                notes.append(f"{anchor}: 丢弃 statement（事实缺失）")
                continue
            kept_statements.append(stmt)

        if "statements" in out_section:
            out_section["statements"] = kept_statements

        # ---- table ----
        table = section.get("table")
        if table:
            table = json.loads(json.dumps(table))
            kept_rows = []
            for row in table.get("rows", []):
                if anchor == "## 风险信号":
                    status = risk_flags.get(risk_ids.get(row.get("label")), {}).get("status", "insufficient_data")
                    row["cells"][0] = status_text.get(status, "资料不足")
                    row["cells"][-1] = ("结构化筛查发现异常信号，具体原因仍需进一步披露支持。" if status == "flagged"
                                        else "当前数据未触发本项筛查阈值。" if status == "clear"
                                        else "接口信息不足，不能据此排除本项风险。")
                    if status not in {"flagged", "clear"}:
                        row["cells"][1] = "不可用"
                cells = row.get("cells", [])
                metric_cells = [c for c in cells if isinstance(c, dict) and "metric_id" in c]
                if metric_cells and not all(_metric_ok(metrics, c["metric_id"]) for c in metric_cells):
                    notes.append(f"{anchor}/{row.get('label')}: 丢弃行（metric 不可用）")
                    continue
                if not _rewrite_binding(row, index, target_end):
                    notes.append(f"{anchor}/{row.get('label')}: 丢弃行（事实缺失）")
                    continue
                kept_rows.append(row)
            table["rows"] = kept_rows
            out_section["table"] = table

        # ---- paragraphs：保留骨架原文，语义内容由 agent 按本次实际情况改写 ----
        if section.get("paragraphs"):
            out_section["paragraphs"] = list(section["paragraphs"])

        out_sections.append(out_section)

    limitations = [f"{f['metric']}（{f['period']['end']}）：{f.get('missing_reason') or '不可用'}"
                   for f in financials.get("facts", []) if f.get("value") is None]
    quality = next((sec for sec in out_sections if sec.get("anchor") == "## 数据质量评估"), None)
    if quality is not None:
        unavailable = sorted({f["metric"] for f in financials.get("facts", []) if f.get("value") is None})
        # Human prose avoids raw field names containing numeric tokens; detailed items remain in spec metadata.
        if unavailable:
            quality.setdefault("paragraphs", []).append("接口部分科目或期间不可用，相关比率及风险判断已保留为资料不足。")
    spec = {"schema_version": 1, "sections": out_sections, "_data_limitations": limitations}

    # decline_* 格式符按指标实际方向自适应
    _fix_decline_formats(spec["sections"], metrics)

    # 标题：渲染器默认只取年份，半年报会丢期间，这里补全
    title = _report_title(run_dir)
    if title:
        spec["report_title"] = title

    # 定性段落待办清单：骨架的提示语必须由 agent 改写成本次实际情况，
    # 否则报告里会留下「这里写……」这类提示语。清单放顶层，不塞进 section
    # （section 的额外键可能被渲染/校验契约拒绝）。
    todo = [
        {"anchor": s.get("anchor", ""), "index": i + 1, "hint": text[:60]}
        for s in out_sections
        for i, text in enumerate(s.get("paragraphs") or [])
        if _is_placeholder_paragraph(text)
    ]
    if todo:
        spec["_paragraphs_todo"] = todo

    return spec, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="report spec 构造器（骨架 + compute 产物 → spec）")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--skeleton", default="", help="骨架 JSON（默认取 references/report-spec-skeleton.json）")
    parser.add_argument("--out", default="report_spec.json")
    parser.add_argument("--dry-run", action="store_true", help="只打印解析说明，不写文件")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    skeleton_path = Path(args.skeleton) if args.skeleton else (
        Path(__file__).resolve().parent.parent / "references" / "report-spec-skeleton.json"
    )

    try:
        skeleton = read_json(skeleton_path)
        spec, notes = build_spec(run_dir, skeleton)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2

    for note in notes:
        print(f"[note] {note}", file=__import__("sys").stderr)
    print(json.dumps({
        "status": "ok",
        "sections": len(spec["sections"]),
        "notes": len(notes),
        "dry_run": bool(args.dry_run),
    }, ensure_ascii=False))
    if not args.dry_run:
        write_json(run_dir / args.out, spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
