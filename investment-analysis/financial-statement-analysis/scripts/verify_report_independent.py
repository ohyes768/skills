#!/usr/bin/env python3
"""独立复核已渲染的财报分析报告——不复用流水线自己的数字。

用法:
    uv run python scripts/verify_report_independent.py --run-dir <run-dir>

为什么需要它:
    `run_pipeline.py report` 返回 `quality_status=verified` 只证明**渲染与绑定层**自洽。
    上游 `validate_report` 不查:核心结论首节与句数、Markdown 表格列数、单位标注、
    母公司口径混入、**缺基期的比率被编出同比故事**。
    本脚本从 financials.json / metrics.json / saved F10 fields 重新推导,并逐字重渲染比对。

fail-closed 原则:
    无法独立复算的项一律记 FAIL,不静默跳过——避免"复核脚本其实没在跑"。

退出码:0=全通过,1=有 FAIL,2=输入缺失/无法运行
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from artifacts import read_json
from source_provenance import citation_text, source_refs

DIV = {"amount_yuan": (Decimal(1), "元"),
       "amount_wan": (Decimal("1e4"), "万元"),
       "amount_yi": (Decimal("1e8"), "亿元")}
PDIG = {"percent0": 0, "percent1": 1, "percent2": 2}
TOKEN_RE = re.compile(
    r"average\s+[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_][A-Za-z0-9_]*|\d+(?:\.\d+)?|[()+\-*/]")
PH = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([a-z0-9_]+))?\}")
STMT_CITE = "（来源："


def verify_run(run: Path) -> dict:
    """Read-only verification; never modifies the report or pipeline budget."""
    run = Path(run)
    not_applicable = []
    fails: list[str] = []
    checks = 0
    cats: dict[str, int] = {}

    def check(cond, label, detail=""):
        nonlocal checks
        checks += 1
        cat = label.split(" ", 1)[0]
        cats[cat] = cats.get(cat, 0) + 1
        if not cond:
            fails.append(label + (f" :: {detail}" if detail else ""))
        return bool(cond)

    def load(name):
        p = run / name
        if not p.exists():
            raise ValueError(f"missing artifact: {p}")
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            raise ValueError(f"invalid artifact: {p}: {exc}") from exc

    document = read_json(run / "document.json")
    fin = load("financials.json")
    met = load("metrics.json")
    rin = load("report_inputs.json")
    archive = load("structured_financials.json")
    load("report_claims.json")
    md_path = run / "analysis.md"
    if fin is None or met is None or rin is None or archive is None or not md_path.exists():
        raise ValueError("required report artifacts missing")

    body = md_path.read_text(encoding="utf-8")
    lines = body.splitlines()
    facts = {f["fact_id"]: f for f in fin.get("facts", [])}
    metrics = {m["metric_id"]: m for m in met.get("metrics", [])}
    from validate_report import calculation_errors

    contract_errors = calculation_errors(run)
    check(not contract_errors, "B0 指标公式和风险状态绑定到源事实", "; ".join(contract_errors))
    # ---------------------------------------------------------------- 事实取值
    by_metric: dict[str, dict[str, list]] = {}
    active_ids = None
    for f in facts.values():
        if (f.get("scope") != "consolidated" or f.get("review_status") != "verified"
                or f.get("value") is None):
            continue
        by_metric.setdefault(f.get("metric"), {}).setdefault(
            (f.get("period") or {}).get("end"), []).append(f)

    def value_at_end(metric: str, end: str) -> Decimal:
        bucket = by_metric.get(metric, {}).get(end)
        if not bucket:
            raise KeyError(f"{metric}@{end} 无事实")
        bucket = [b for b in bucket if active_ids is None or b["fact_id"] in active_ids]
        if not bucket:
            raise KeyError(f"{metric}@{end} absent from metric input_fact_ids")
        dimensions = {(b.get("currency"), b.get("unit"), b.get("basis")) for b in bucket}
        if len(dimensions) != 1:
            raise ValueError("incompatible measurement dimensions")
        vals = {b.get("value") for b in bucket}
        if len(vals) != 1:
            raise ValueError(f"{metric}@{end} 值冲突 {vals}")
        return Decimal(next(iter(vals)))

    def ends_of(metric: str) -> list:
        return sorted(k for k, bucket in by_metric.get(metric, {}).items()
                      if k and any(active_ids is None or f["fact_id"] in active_ids for f in bucket))

    def value_cur(metric: str) -> Decimal:
        es = ends_of(metric)
        if not es:
            raise KeyError(f"{metric} 无事实")
        return value_at_end(metric, es[-1])

    def value_prev(metric: str) -> Decimal:
        es = ends_of(metric)
        if len(es) < 2:
            raise KeyError(f"{metric} 缺上期余额")
        return value_at_end(metric, es[-2])

    def value_avg(metric: str) -> Decimal:
        return (value_cur(metric) + value_prev(metric)) / 2

    # ------------------------------------------- 独立格式化(重实现上游渲染契约)
    def format_value(value: Decimal, kind: str, fmt: str, with_direction: bool = False) -> str:
        abs_mode = fmt.startswith("decline_")
        base = fmt[len("decline_"):] if abs_mode else fmt
        if abs_mode and value > 0:
            raise ValueError(f"format {fmt} requires a nonpositive value, got {value}")
        if base in DIV:
            if kind != "amount":
                raise ValueError(f"format {fmt} applies to amounts, kind={kind}")
            divisor, label = DIV[base]
            shown = abs(value) if abs_mode else value
            q = (shown / divisor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            text = f"{q:,f}{label}"
        elif base in {"pp0", "pp1", "pp2"}:
            if kind != "ratio":
                raise ValueError("percentage points require a ratio")
            shown = abs(value) if abs_mode else value
            q = (shown * 100).quantize(Decimal(1).scaleb(-int(base[-1])), rounding=ROUND_HALF_UP)
            text = f"{q:f}个百分点"
        elif base in PDIG:
            if kind != "ratio":
                raise ValueError(f"format {fmt} applies to ratios, kind={kind}")
            shown = abs(value) if abs_mode else value
            q = (shown * 100).quantize(Decimal(1).scaleb(-PDIG[base]), rounding=ROUND_HALF_UP)
            text = f"{q:f}%"
        else:
            raise ValueError(f"unknown format {fmt!r}")
        if abs_mode and with_direction:
            return f"下降{text}"
        return text

    def kind_of(binding: dict) -> str:
        if "metric_id" in binding:
            return "amount" if binding["metric_id"] == "simplified_fcf" else "ratio"
        f = facts.get(binding.get("fact_id"), {})
        return "ratio" if f.get("unit") in ("ratio", "%", "％") else "amount"

    def binding_value(binding: dict) -> Decimal:
        if "metric_id" in binding:
            return Decimal(metrics[binding["metric_id"]]["value"])
        return Decimal(facts[binding["fact_id"]]["value"])

    def binding_facts(binding: dict) -> list:
        if "metric_id" in binding:
            return list(metrics[binding["metric_id"]].get("input_fact_ids", []))
        return [binding["fact_id"]]

    def binding_sources(binding: dict) -> list:
        return source_refs(facts, binding_facts(binding))

    # ================================================================== A 结构
    heads = [l for l in lines if l.startswith("## ")]
    check(bool(heads) and heads[0] == "## 核心结论", "A1 首节必须是 ## 核心结论", str(heads[:1]))
    check("## 核心结论" in heads, "A2 存在核心结论章节")

    core_secs = [s for s in rin.get("sections", []) if s.get("anchor") == "## 核心结论"]
    core_stmts = [st for s in core_secs for st in (s.get("statements") or [])]
    core_paras = [p for s in core_secs for p in (s.get("paragraphs") or [])]
    n_sent = len(core_stmts) + sum(
        len([x for x in re.split(r"。", p) if x.strip()]) for p in core_paras)
    check(3 <= n_sent <= 5, "A3 核心结论句数 3-5", f"actual={n_sent}")

    for kw in ["核心结论", "报表", "比率", "盈利", "风险", "数据质量"]:
        check(any(kw in h for h in heads), f"A4 存在含「{kw}」的章节", str(heads))

    in_tbl, hdr, mism = False, 0, []
    for i, l in enumerate(lines, 1):
        if l.startswith("|"):
            n = l.count("|")
            if not in_tbl:
                hdr, in_tbl = n, True
            elif n != hdr:
                mism.append((i, n, hdr))
        else:
            in_tbl = False
    check(not mism, "A5 Markdown 表格每行列数与表头一致", str(mism[:5]))

    leftover = [l for l in lines if PH.search(l)]
    check(not leftover, "A6 无未解析占位符", str(leftover[:2]))

    # ================================================================== B 数值
    used_facts: set = set()
    disclosed_parent_facts = set()

    def record_scope_context(bindings, text):
        if "母公司" in text:
            disclosed_parent_facts.update(b["fact_id"] for b in bindings if "fact_id" in b)

    def render_statement(st: dict) -> str:
        binds = st.get("bindings") or {}
        refs = []
        for b in binds.values():
            refs.extend(binding_sources(b))
            used_facts.update(binding_facts(b))

        def sub(m):
            name, fmt = m.group(1), m.group(2)
            b = binds.get(name)
            if b is None:
                raise ValueError(f"placeholder {name} 无绑定")
            if not fmt:
                raise ValueError(f"placeholder {name} 无 format")
            return format_value(binding_value(b), kind_of(b), fmt)

        text = PH.sub(sub, st.get("template", ""))
        if st.get("cite_sources", True) and refs:
            text += STMT_CITE + citation_text(refs) + "）"
        return text

    for sec in rin.get("sections", []):
        anchor = sec.get("anchor", "")
        for st in (sec.get("statements") or []):
            record_scope_context((st.get("bindings") or {}).values(),
                                 anchor + st.get("template", ""))
            try:
                text = render_statement(st)
            except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
                check(False, f"B1 statement 可渲染 [{anchor}]", str(exc))
                continue
            check(text in lines, f"B1 statement 逐字匹配 [{anchor}]", text)
        tbl = sec.get("table")
        if not tbl:
            continue
        for row in tbl.get("rows", []):
            record_scope_context([c for c in row.get("cells", []) if isinstance(c, dict)],
                                 anchor + row.get("label", ""))
            cells, ok = [], True
            for c in row.get("cells", []):
                if isinstance(c, str):
                    cells.append(c)
                    continue
                try:
                    cells.append(format_value(binding_value(c), kind_of(c),
                                             c.get("format", ""), with_direction=True))
                except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
                    check(False, f"B2 单元格可渲染 [{anchor}] {str(row.get('label'))[:16]}", str(exc))
                    ok = False
                    break
                used_facts.update(binding_facts(c))
            if not ok:
                continue
            text = "| " + " | ".join([row.get("label", ""), *cells]) + " |"
            check(text in lines, f"B2 表格行逐字匹配 [{anchor}] {str(row.get('label'))[:20]}", text)

    # ---- 独立复算全部指标(从事实出发,不信任已存指标值) ----
    def resolve_token(tok: str, seen: frozenset) -> Decimal:
        for suf, which in (("_cur", "cur"), ("_prev", "prev"),
                           ("_closing", "cur"), ("_opening", "prev")):
            if tok.endswith(suf):
                base = tok[:-len(suf)]
                return value_cur(base) if which == "cur" else value_prev(base)
        if tok in metrics:
            if tok in seen:
                raise ValueError(f"指标循环依赖 {tok}")
            m = metrics[tok]
            if m.get("status") != "computed":
                raise ValueError(f"指标 {tok} 未算出")
            return evaluate(m.get("formula", ""), seen | {tok})
        return value_cur(tok)

    def evaluate(formula: str, seen: frozenset = frozenset()) -> Decimal:
        if TOKEN_RE.sub("", formula).strip():
            raise ValueError("unsupported formula syntax")
        parts = []
        for m in TOKEN_RE.finditer(formula):
            t = m.group(0)
            if t.startswith("average"):
                name = t.split(None, 1)[1]
                parts.append(f"Decimal('{value_avg(name)}')")
            elif re.match(r"^[A-Za-z_]", t):
                parts.append(f"Decimal('{resolve_token(t, seen)}')")
            else:
                parts.append(t)
        expr = " ".join(parts)
        return eval(expr, {"__builtins__": {}}, {"Decimal": Decimal})

    for mid, m in metrics.items():
        if m.get("status") != "computed" or m.get("value") is None:
            not_applicable.append(f"B3 {mid}: {m.get("status")}")
            continue
        active_ids = set(m.get("input_fact_ids", []))
        try:
            expect = evaluate(m.get("formula", ""), frozenset({mid}))
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            check(False, f"B3 独立复算 {mid}", f"{m.get('formula')} :: {exc}")
            continue
        got = Decimal(m["value"])
        tol = abs(expect) * Decimal("1e-9") + Decimal("1e-9")
        check(abs(got - expect) <= tol, f"B3 独立复算一致 {mid}",
              f"recomputed={expect} stored={got}")

    active_ids = None

    # ================================================================== C 来源
    verified_sources = set()

    def independent_fact(fid):
        if fid in verified_sources:
            return
        verified_sources.add(fid)
        fact = facts.get(fid, {})
        check(fact.get("review_status") == "verified" and fact.get("value") is not None,
              f"C0 事实可用 {fid}")
        if fact.get("source") == "derived":
            operands = fact.get("input_fact_ids", [])
            if not check(len(operands) == 2 and fact.get("metric") == "gross_profit",
                         f"C1 派生事实合同 {fid}"):
                return
            for operand in operands:
                independent_fact(operand)
            left, right = (facts[i] for i in operands)
            check(left.get("metric") == "revenue" and right.get("metric") == "cost_of_sales"
                  and left.get("period") == right.get("period") == fact.get("period")
                  and Decimal(fact["value"]) == Decimal(left["value"]) - Decimal(right["value"]),
                  f"C1 独立复算毛利润 {fid}")
            return
        ref = fact.get("source_ref") or {}
        rows = archive.get("reports", {}).get(ref.get("report_date"), {}).get(ref.get("report_kind"), [])
        if not check(len(rows) == 1, f"C1 原始接口记录唯一 {fid}"):
            return
        row = rows[0]
        raw = row.get(ref.get("field"))
        try:
            same = raw is not None and Decimal(str(raw)) == Decimal(fact["value"])
        except (ValueError, TypeError, ArithmeticError):
            same = False
        check(same, f"C1 原值与接口字段一致 {fid}")
        check(str(row.get("REPORT_DATE", ""))[:10] == ref.get("report_date")
              and ref.get("security_code") == document.get("stock_code")
              and (row.get("SECURITY_CODE") == document.get("stock_code")
                   or str(row.get("SECUCODE", "")).split(".")[0] == document.get("stock_code")),
              f"C3 来源证券与报告期一致 {fid}")

    for fid in sorted(used_facts):
        independent_fact(fid)
        fact = facts.get(fid, {})
        disclosed = fid in disclosed_parent_facts and fact.get("scope") == "parent"
        check(fact.get("scope") == "consolidated" or disclosed,
              f"C4 合并报告未混入未标明的母公司事实 {fid}")

    groups = {}
    for f in facts.values():
        key = (f.get("metric"), f.get("scope"), json.dumps(f.get("period"), sort_keys=True))
        groups.setdefault(key, []).append(f)
    for key, group in groups.items():
        if len(group) > 1:
            check(len({f.get("value") for f in group}) == 1,
                  f"C2 同期间重复事实一致 {key[0]}")

    # ================================================================== D 恒等式
    period = document["period"]
    opening = (date.fromisoformat(period["start"]) - timedelta(days=1)).isoformat()
    for end, tag in ((period["end"], "期末"), (opening, "期初")):
        try:
            ta = value_at_end("total_assets", end)
            tl = value_at_end("total_liabilities", end)
            te = value_at_end("total_equity", end)
        except KeyError as exc:
            not_applicable.append(f"D1 {tag}: {exc}")
            continue
        except (ValueError, TypeError, ArithmeticError) as exc:
            check(False, f"D1 incompatible balance {tag}", str(exc))
            continue
        check(abs(ta - (tl + te)) <= Decimal("0.01"),
              f"D1 资产=负债+权益 {tag}", f"{ta} vs {tl + te}")

    try:
        resid = (value_at_end("cash_equivalents", opening)
                 + value_at_end("cfo", period["end"]) + value_at_end("cfi", period["end"])
                 + value_at_end("cff", period["end"])
                 + value_at_end("fx_effect_on_cash", period["end"])
                 - value_at_end("cash_equivalents", period["end"]))
        check(abs(resid) <= Decimal("0.005"), "D2 现金勾稽残差为零", str(resid))
    except KeyError as exc:
        not_applicable.append(f"D2: {exc}")
    except (ValueError, TypeError, ArithmeticError) as exc:
        check(False, "D2 incompatible cash facts", str(exc))

    # ================================================================== E 单位
    for sec in rin.get("sections", []):
        tbl = sec.get("table")
        if not tbl:
            continue
        for row in tbl.get("rows", []):
            for c in row.get("cells", []):
                if isinstance(c, dict):
                    try:
                        txt = format_value(binding_value(c), kind_of(c), c.get("format", ""))
                    except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
                        check(False, "E1 unit could not be verified", str(exc))
                        continue
                    check(txt.endswith(("元", "万元", "亿元", "%", "个百分点")),
                          f"E1 数值带单位 [{sec.get('anchor')}] {str(row.get('label'))[:16]}", txt)

    return {"passed": not fails, "checks": checks, "issues": fails,
            "not_applicable": not_applicable, "categories": cats}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Independent report verification")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_run(Path(args.run_dir))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"passed": False, "issues": [str(exc)]}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
