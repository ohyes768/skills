"""指标计算与三表勾稽：只用同口径事实，退化输出状态与原因而非默认值。"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from artifacts import emit_status, read_json, write_json
from financial_schema import validate_financials

ZERO = Decimal(0)


def _f(
    facts: list[dict],
    metric: str,
    *,
    scope: str = "consolidated",
    attribution: str = "group",
    aggregation: str = "cumulative",
) -> list[dict]:
    return [
        f
        for f in facts
        if f["metric"] == metric
        and f["scope"] == scope
        and f["attribution"] == attribution
        and (f["period"]["kind"] == "instant" or f["period"]["aggregation"] == aggregation)
    ]


def _entry(
    metric_id: str,
    value: Decimal | None,
    status: str,
    formula: str,
    input_ids: list[str],
    reason: str | None = None,
) -> dict:
    return {
        "metric_id": metric_id,
        "value": value,
        "status": status,
        "formula": formula,
        "input_fact_ids": input_ids,
        "source_pages": [],
        "reason": reason,
    }


def _insufficient(metric_id: str, formula: str, metric: str, aggregation: str) -> dict:
    return _entry(
        metric_id,
        None,
        "insufficient_data",
        formula,
        [],
        f"{metric} not available with scope/attribution/aggregation "
        f"(aggregation={aggregation})",
    )


def _pick_single(candidates: list[dict]) -> tuple[dict | None, str | None, str | None]:
    """取唯一本期值；同期间多条不同值即冲突，不默认取第一项。"""
    if not candidates:
        return None, "insufficient_data", "fact not available"
    by_end: dict[str, list[dict]] = {}
    for fact in candidates:
        by_end.setdefault(fact["period"]["end"], []).append(fact)
    latest = by_end[max(by_end)]
    if len({f["value"] for f in latest}) > 1:
        return None, "conflict", f"multiple conflicting values for period {latest[0]['period']['end']}"
    return latest[0], None, None


def _current_and_prior(
    candidates: list[dict],
) -> tuple[dict | None, dict | None, str | None, str | None]:
    if not candidates:
        return None, None, "insufficient_data", "fact not available"
    by_end: dict[str, list[dict]] = {}
    for fact in candidates:
        by_end.setdefault(fact["period"]["end"], []).append(fact)
    ends = sorted(by_end, reverse=True)
    if len(ends) < 2:
        return None, None, "insufficient_data", "no prior period for comparison"
    current_list = by_end[ends[0]]
    if len({f["value"] for f in current_list}) > 1:
        return None, None, "conflict", f"multiple conflicting values for period {ends[0]}"
    current = current_list[0]
    prior_list = [f for f in by_end[ends[1]] if f["basis"] == current["basis"]]
    if not prior_list:
        return None, None, "insufficient_data", (
            f"no same-basis prior period (basis={current['basis']})"
        )
    return current, prior_list[0], None, None


def _avg_balance(
    facts: list[dict], metric: str
) -> tuple[Decimal | None, list[str], str | None, str | None]:
    instants = [
        f for f in facts if f["metric"] == metric and f["period"]["kind"] == "instant"
    ]
    if len(instants) < 2:
        return None, [], "insufficient_data", f"insufficient data for average {metric}"
    by_end: dict[str, list[dict]] = {}
    for fact in instants:
        by_end.setdefault(fact["period"]["end"], []).append(fact)
    ends = sorted(by_end, reverse=True)
    current_list = by_end[ends[0]]
    if len({f["value"] for f in current_list}) > 1:
        return None, [], "conflict", f"multiple conflicting {metric} values for {ends[0]}"
    current = current_list[0]
    prior_list = [f for f in by_end[ends[1]] if f["basis"] == current["basis"]]
    if not prior_list:
        return None, [], "insufficient_data", f"no same-basis prior {metric}"
    prior = prior_list[0]
    avg = (Decimal(current["value"]) + Decimal(prior["value"])) / 2
    return avg, [current["fact_id"], prior["fact_id"]], None, None


def _divide(num: Decimal, den: Decimal, zero_label: str = "zero denominator") -> tuple:
    if den == 0:
        return None, "not_applicable", zero_label
    if den < 0:
        return None, "not_applicable", "negative denominator"
    return num / den, None, None


def _yoy(facts: list[dict], metric: str, metric_id: str) -> dict:
    formula = f"({metric}_cur - {metric}_prev) / {metric}_prev"
    attribution = "owners" if metric.endswith("_owners") else "group"
    cur, prior, status, reason = _current_and_prior(
        _f(facts, metric, attribution=attribution)
    )
    if status is not None:
        return _entry(metric_id, None, status, formula, [], reason)
    cur_v, prior_v = Decimal(cur["value"]), Decimal(prior["value"])
    if prior_v < 0:
        return _entry(
            metric_id, None, "not_applicable", formula,
            [cur["fact_id"], prior["fact_id"]], "negative base period",
        )
    value, status, reason = _divide(cur_v - prior_v, prior_v, zero_label="zero base period")
    return _entry(metric_id, value, status or "computed", formula,
                  [cur["fact_id"], prior["fact_id"]], reason)


def _simple_ratio(
    facts: list[dict],
    metric_id: str,
    num_spec: tuple[str, str],
    den_spec: tuple[str, str],
    formula: str,
) -> dict:
    num_f = _f(facts, num_spec[0], attribution=num_spec[1])
    den_f = _f(facts, den_spec[0], attribution=den_spec[1])
    if not num_f:
        return _insufficient(metric_id, formula, num_spec[0], "cumulative")
    if not den_f:
        return _insufficient(metric_id, formula, den_spec[0], "cumulative")
    num, status, reason = _pick_single(num_f)
    if status is not None:
        return _entry(metric_id, None, status, formula, [], reason)
    den, status, reason = _pick_single(den_f)
    if status is not None:
        return _entry(metric_id, None, status, formula, [], reason)
    value, status, reason = _divide(Decimal(num["value"]), Decimal(den["value"]))
    return _entry(metric_id, value, status or "computed", formula,
                  [num["fact_id"], den["fact_id"]], reason)


def _dupont(facts: list[dict]) -> list[dict]:
    entries: list[dict] = []
    margin = _simple_ratio(
        facts, "dupont_net_margin", ("net_profit_group", "group"), ("revenue", "group"),
        "net_profit_group / revenue",
    )
    turnover_inputs = _f(facts, "revenue")
    avg_assets, asset_ids, status, reason = _avg_balance(facts, "total_assets")
    revenue_pick, rev_status, rev_reason = _pick_single(turnover_inputs)
    if rev_status is not None or status is not None:
        turnover = _entry("dupont_asset_turnover", None, rev_status or status or "insufficient_data",
                          "revenue / average total_assets", [], rev_reason or reason)
    else:
        value, status2, reason2 = _divide(Decimal(revenue_pick["value"]), avg_assets)
        turnover = _entry("dupont_asset_turnover", value, status2 or "computed",
                          "revenue / average total_assets",
                          [revenue_pick["fact_id"]] + asset_ids, reason2)
    entries.append(margin)
    entries.append(turnover)

    avg_equity, equity_ids, eq_status, eq_reason = _avg_balance(facts, "total_equity")
    if status is not None or eq_status is not None:
        multiplier = _entry("dupont_equity_multiplier", None,
                            status or eq_status or "insufficient_data",
                            "average total_assets / average total_equity", [], reason or eq_reason)
    elif turnover["value"] is None:
        multiplier = _entry("dupont_equity_multiplier", None, "insufficient_data",
                            "average total_assets / average total_equity", [])
    else:
        value, status2, reason2 = _divide(avg_assets, avg_equity)
        multiplier = _entry("dupont_equity_multiplier", value, status2 or "computed",
                            "average total_assets / average total_equity",
                            asset_ids + equity_ids, reason2)
    entries.append(multiplier)

    if (
        margin["status"] == "computed"
        and turnover["status"] == "computed"
        and multiplier["status"] == "computed"
    ):
        roe = margin["value"] * turnover["value"] * multiplier["value"]
        entries.append(
            _entry(
                "roe_dupont", roe, "computed",
                "dupont_net_margin * dupont_asset_turnover * dupont_equity_multiplier",
                margin["input_fact_ids"] + turnover["input_fact_ids"]
                + multiplier["input_fact_ids"],
            )
        )
    else:
        parts = [margin, turnover, multiplier]
        reason = next((p["reason"] for p in parts if p["reason"]), None)
        entries.append(
            _entry("roe_dupont", None, "insufficient_data",
                   "dupont_net_margin * dupont_asset_turnover * dupont_equity_multiplier", [], reason)
        )
    return entries


def _simplified_fcf(facts: list[dict]) -> dict:
    formula = "cfo - capex_purchase_fixed_assets"
    cfo, status, reason = _pick_single(_f(facts, "cfo"))
    if status is not None:
        return _entry("simplified_fcf", None, status, formula, [], reason)
    capex, status, reason = _pick_single(_f(facts, "capex_purchase_fixed_assets"))
    if status is not None:
        return _entry("simplified_fcf", None, status, formula, [], reason)
    value = Decimal(cfo["value"]) - Decimal(capex["value"])
    return _entry("simplified_fcf", value, "computed", formula,
                  [cfo["fact_id"], capex["fact_id"]])


def _roe_simple(facts: list[dict]) -> dict:
    formula = "net_profit_group / average total_equity"
    profit, status, reason = _pick_single(_f(facts, "net_profit_group"))
    if status is not None:
        return _entry("roe_group_simple", None, status, formula, [], reason)
    avg_equity, ids, status, reason = _avg_balance(facts, "total_equity")
    if status is not None:
        return _entry("roe_group_simple", None, status, formula, [profit["fact_id"]], reason)
    value, status, reason = _divide(Decimal(profit["value"]), avg_equity)
    return _entry("roe_group_simple", value, status or "computed", formula,
                  [profit["fact_id"]] + ids, reason)


def _accrual_ratio(facts: list[dict]) -> dict:
    formula = "(net_profit_group - cfo) / average total_assets"
    profit, status, reason = _pick_single(_f(facts, "net_profit_group"))
    if status is not None:
        return _entry("accrual_ratio", None, status, formula, [], reason)
    cfo, status, reason = _pick_single(_f(facts, "cfo"))
    if status is not None:
        return _entry("accrual_ratio", None, status, formula, [], reason)
    avg_assets, ids, status, reason = _avg_balance(facts, "total_assets")
    if status is not None:
        return _entry("accrual_ratio", None, status, formula, [], reason)
    numerator = Decimal(profit["value"]) - Decimal(cfo["value"])
    value, status, reason = _divide(numerator, avg_assets)
    return _entry("accrual_ratio", value, status or "computed", formula,
                  [profit["fact_id"], cfo["fact_id"]] + ids, reason)


def _turnover(
    facts: list[dict], metric_id: str, flow: str, balance: str
) -> dict:
    formula = f"{flow} / average {balance}"
    flow_pick, status, reason = _pick_single(_f(facts, flow))
    if status is not None:
        return _entry(metric_id, None, status, formula, [], reason)
    avg, ids, status, reason = _avg_balance(facts, balance)
    if status is not None:
        return _entry(metric_id, None, status, formula, [flow_pick["fact_id"]], reason)
    value, status, reason = _divide(Decimal(flow_pick["value"]), avg)
    return _entry(metric_id, value, status or "computed", formula,
                  [flow_pick["fact_id"]] + ids, reason)


def _tolerance(values: list[Decimal]) -> Decimal:
    coarsest = max(v.as_tuple().exponent for v in values)
    return Decimal(1).scaleb(coarsest) / 2


def _cash_reconciliation(facts: list[dict]) -> dict:
    entry = {
        "check_id": "cash_reconciliation",
        "status": "not_applicable",
        "input_fact_ids": [],
        "residual": None,
        "tolerance": None,
        "issues": [],
    }
    instants = [
        f for f in facts
        if f["metric"] == "cash_equivalents" and f["period"]["kind"] == "instant"
    ]
    if len(instants) < 2:
        entry["issues"] = ["cash_reconciliation needs opening and closing cash_equivalents"]
        return entry
    by_end: dict[str, list[dict]] = {}
    for fact in instants:
        by_end.setdefault(fact["period"]["end"], []).append(fact)
    ends = sorted(by_end, reverse=True)
    closing_list = by_end[ends[0]]
    if len({f["value"] for f in closing_list}) > 1:
        entry["status"] = "conflict"
        entry["issues"] = [f"multiple closing cash_equivalents values for {ends[0]}"]
        return entry
    closing = closing_list[0]
    opening_list = [f for f in by_end[ends[1]] if f["basis"] == closing["basis"]]
    if not opening_list:
        entry["status"] = "not_applicable"
        entry["issues"] = ["no same-basis opening cash_equivalents"]
        return entry
    opening = opening_list[0]

    input_ids = [opening["fact_id"], closing["fact_id"]]
    flows: dict[str, Decimal] = {}
    for metric in ("cfo", "cfi", "cff"):
        candidates = [
            f
            for f in _f(facts, metric)
            if f["period"]["end"] == closing["period"]["end"]
        ]
        pick, status, reason = _pick_single(candidates)
        if status is not None:
            entry["status"] = status
            entry["input_fact_ids"] = input_ids
            entry["issues"] = [f"{metric}: {reason}"]
            return entry
        flows[metric] = Decimal(pick["value"])
        input_ids.append(pick["fact_id"])

    issues: list[str] = []
    fx_candidates = [
        f
        for f in _f(facts, "fx_effect_on_cash")
        if f["period"]["end"] == closing["period"]["end"]
    ]
    if fx_candidates:
        fx_pick, status, reason = _pick_single(fx_candidates)
        if status is not None:
            entry["status"] = status
            entry["input_fact_ids"] = input_ids
            entry["issues"] = [f"fx_effect_on_cash: {reason}"]
            return entry
        fx = Decimal(fx_pick["value"])
        input_ids.append(fx_pick["fact_id"])
    else:
        fx = ZERO
        issues.append("fx_effect_on_cash not disclosed; treated as 0")

    expected = Decimal(opening["value"]) + flows["cfo"] + flows["cfi"] + flows["cff"] + fx
    closing_v = Decimal(closing["value"])
    residual = closing_v - expected
    tolerance = _tolerance(
        [Decimal(opening["value"]), closing_v, flows["cfo"], flows["cfi"], flows["cff"], fx]
    )
    entry.update(
        {
            "status": "passed" if abs(residual) <= tolerance else "failed",
            "input_fact_ids": input_ids,
            "residual": residual,
            "tolerance": tolerance,
            "issues": issues,
        }
    )
    return entry


def calculate_metrics(document: dict) -> dict:
    facts = document.get("facts", [])
    metrics: list[dict] = [
        _yoy(facts, "revenue", "revenue_yoy"),
        _yoy(facts, "net_profit_group", "net_profit_group_yoy"),
        _yoy(facts, "net_profit_owners", "net_profit_owners_yoy"),
        _simple_ratio(
            facts, "net_margin_group",
            ("net_profit_group", "group"), ("revenue", "group"),
            "net_profit_group / revenue",
        ),
        _simple_ratio(
            facts, "cfo_to_net_profit_group",
            ("cfo", "group"), ("net_profit_group", "group"),
            "cfo / net_profit_group",
        ),
        _simplified_fcf(facts),
        _roe_simple(facts),
    ]
    metrics.extend(_dupont(facts))
    metrics.append(_turnover(facts, "receivable_turnover", "revenue", "accounts_receivable"))
    metrics.append(_turnover(facts, "inventory_turnover", "cost_of_sales", "inventory"))
    metrics.append(_accrual_ratio(facts))
    validation = [_cash_reconciliation(facts)]
    return {"schema_version": 1, "metrics": metrics, "validation": validation}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="基于 financials.json 计算指标并做三表勾稽")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    financials_path = run_dir / "financials.json"
    if not financials_path.exists():
        print(f"calculate_metrics failed: missing {financials_path}", file=sys.stderr)
        raise SystemExit(1)

    document = read_json(financials_path)
    errors = validate_financials(document)
    if errors:
        for error in errors:
            print(
                f"contract violation: {error['fact_id']} {error['field']}: {error['error']}",
                file=sys.stderr,
            )
        raise SystemExit(1)

    result = calculate_metrics(document)

    manifest_path = run_dir / "extraction_manifest.json"
    if manifest_path.exists():
        evidences = {
            e["evidence_id"]: e["pdf_pages"]
            for e in read_json(manifest_path).get("evidences", [])
        }
        fact_evidence = {
            f["fact_id"]: f.get("evidence_ids", []) for f in document.get("facts", [])
        }
        for metric in result["metrics"]:
            pages: set[int] = set()
            for fact_id in metric["input_fact_ids"]:
                for ev in fact_evidence.get(fact_id, []):
                    pages.update(evidences.get(ev, []))
            metric["source_pages"] = sorted(pages)

    write_json(run_dir / "metrics.json", result)
    write_json(run_dir / "validation.json", {"schema_version": 1, "checks": result["validation"]})

    problems = [
        f"{c['check_id']}: {c['status']}"
        + (f" residual={c['residual']}" if c.get("residual") is not None else "")
        for c in result["validation"]
        if c["status"] not in ("passed", "not_applicable")
    ]
    emit_status(
        "ok" if not problems else "partial",
        {
            "metrics_json": str(run_dir / "metrics.json"),
            "validation_json": str(run_dir / "validation.json"),
        },
        problems,
    )
    if problems:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
