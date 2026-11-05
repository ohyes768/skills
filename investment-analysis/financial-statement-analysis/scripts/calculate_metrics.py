"""指标计算与三表勾稽：只用同口径事实，退化输出状态与原因而非默认值。"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from pathlib import Path

from artifacts import emit_status, read_json, write_json
from fact_selection import FactSelection, pick_usable
from financial_schema import validate_financials

ZERO = Decimal(0)


def _f(
    facts: FactSelection,
    metric: str,
    *,
    scope: str = "consolidated",
    attribution: str = "group",
    aggregation: str = "cumulative",
) -> list[dict]:
    return facts.flows(metric, scope=scope, attribution=attribution, aggregation=aggregation)


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
    return pick_usable(candidates)


def _avg_balance(
    facts: FactSelection, metric: str
) -> tuple[Decimal | None, list[str], str | None, str | None]:
    current, status, reason = facts.balance(metric)
    if status:
        return None, [], status, f"average {metric}: {reason}"
    prior, status, reason = facts.balance(metric, opening=True)
    if status:
        return None, [], status, f"average {metric}: {reason}"
    mismatch = facts.measurement_error([current["fact_id"], prior["fact_id"]])
    if mismatch:
        return None, [], "conflict", mismatch
    avg = (Decimal(current["value"]) + Decimal(prior["value"])) / 2
    return avg, [current["fact_id"], prior["fact_id"]], None, None


def _divide(num: Decimal, den: Decimal, zero_label: str = "zero denominator") -> tuple:
    if den == 0:
        return None, "not_applicable", zero_label
    if den < 0:
        return None, "not_applicable", "negative denominator"
    return num / den, None, None


def _yoy(facts: FactSelection, metric: str, metric_id: str) -> dict:
    formula = f"({metric}_cur - {metric}_prev) / {metric}_prev"
    attribution = "owners" if metric.endswith("_owners") else "group"
    cur, status, reason = _pick_single(_f(facts, metric, attribution=attribution))
    if status is not None:
        return _entry(metric_id, None, status, formula, [], reason)
    prior, status, reason = _pick_single(facts.flows(metric, attribution=attribution, prior=True))
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
    facts: FactSelection,
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


def _dupont(facts: FactSelection) -> list[dict]:
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
            _entry("roe_dupont", None,
                   "conflict" if any(p["status"] == "conflict" for p in parts) else "insufficient_data",
                   "dupont_net_margin * dupont_asset_turnover * dupont_equity_multiplier", [], reason)
        )
    return entries


def _simplified_fcf(facts: FactSelection) -> dict:
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


def _roe_simple(facts: FactSelection) -> dict:
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


def _accrual_ratio(facts: FactSelection) -> dict:
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
    facts: FactSelection, metric_id: str, flow: str, balance: str
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


def _cash_reconciliation(facts: FactSelection) -> dict:
    entry = {
        "check_id": "cash_reconciliation",
        "status": "not_applicable",
        "input_fact_ids": [],
        "residual": None,
        "tolerance": None,
        "issues": [],
    }
    closing, status, reason = facts.balance("cash_equivalents")
    opening, open_status, open_reason = facts.balance("cash_equivalents", opening=True)
    if status or open_status:
        entry["status"] = "conflict" if "conflict" in (status, open_status) else "not_applicable"
        entry["issues"] = [
            "cash_reconciliation needs opening and closing cash_equivalents",
            reason or open_reason,
        ]
        return entry

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
        entry["status"] = "insufficient_data"
        entry["issues"] = ["fx_effect_on_cash not disclosed; cannot reconcile cash"]
        return entry

    expected = Decimal(opening["value"]) + flows["cfo"] + flows["cfi"] + flows["cff"] + fx
    mismatch = facts.measurement_error(input_ids)
    if mismatch:
        entry.update(status="conflict", input_fact_ids=input_ids, issues=[mismatch])
        return entry
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


_RED_FLAG_THRESHOLDS = {
    "dual_high_ratio": Decimal("0.30"),
    "outpacing_factor": Decimal("1.5"),
    "inventory_surge_factor": Decimal("1.5"),
    "prepayment_surge_factor": Decimal("1.5"),
    "minority_shift": Decimal("0.20"),
    "goodwill_ratio": Decimal("0.30"),
    "construction_ratio": Decimal("0.50"),
}


def _flag(flag_id: str, status: str, *, value=None, threshold=None,
          detail: str = "") -> dict:
    return {"flag_id": flag_id, "status": status, "value": value, "threshold": threshold,
            "detail": detail}


def _flow_value(facts: FactSelection, metric: str, *, attribution: str = "group",
                prior: bool = False) -> Decimal | None:
    pick, status, _reason = _pick_single(
        facts.flows(metric, attribution=attribution, prior=prior))
    return None if status is not None or pick is None else Decimal(pick["value"])


def _balance_value(facts: FactSelection, metric: str, *, opening: bool = False) -> Decimal | None:
    pick, status, _reason = facts.balance(metric, opening=opening)
    return None if status is not None or pick is None else Decimal(pick["value"])


def _owners_balance(facts: FactSelection, metric: str) -> Decimal | None:
    """owners 归属的期末余额；facts.balance 只认 group/not_applicable，这里局部补充。"""
    if not facts.period:
        return None
    day = facts.period["end"]
    candidates = [
        f for f in facts.facts
        if f["metric"] == metric and f["scope"] == "consolidated"
        and f["attribution"] == "owners"
        and f["period"]["kind"] == "instant" and f["period"]["end"] == day
    ]
    pick, status, _reason = pick_usable(candidates)
    return None if status is not None or pick is None else Decimal(pick["value"])


def _growth(current: Decimal | None, base: Decimal | None) -> Decimal | None:
    if current is None or base is None or base <= 0:
        return None
    return current / base - 1


def _ratio_vs_revenue(facts: FactSelection, balance_metric: str, revenue: Decimal | None,
                      *, opening: bool = False) -> Decimal | None:
    value = _balance_value(facts, balance_metric, opening=opening)
    if value is None or revenue is None or revenue <= 0:
        return None
    return value / revenue


def _surge_flag(flag_id: str, current: Decimal | None, base: Decimal | None,
                factor: Decimal, unit: str) -> dict:
    if current is None or base is None:
        return _flag(flag_id, "insufficient_data", detail=f"needs current and prior {unit}")
    hit = base > 0 and current > base * factor
    return _flag(flag_id, "flagged" if hit else "clear",
                 value=format(current, "f"), threshold=format(base * factor, "f"),
                 detail=f"{unit}: current {current} vs prior {base} (x{factor})")


def _red_flags(facts: FactSelection) -> list[dict]:
    """三表可验证的造假红旗：恒定输出固定清单，事实不足记 insufficient_data。
    风险发现层——触发不改变退出码或 quality_status，结论表述归分析层。"""
    flags: list[dict] = []
    th = _RED_FLAG_THRESHOLDS
    revenue = _flow_value(facts, "revenue")
    revenue_prior = _flow_value(facts, "revenue", prior=True)

    cash_ratio = _ratio_vs_revenue(facts, "monetary_funds", revenue)
    st_debt = _balance_value(facts, "short_term_borrowings")
    lt_debt = _balance_value(facts, "long_term_borrowings")
    debt_values = [v for v in (st_debt, lt_debt) if v is not None]
    debt_ratio = (sum(debt_values) / revenue
                  if revenue and revenue > 0 and len(debt_values) == 2 else None)
    if cash_ratio is None or debt_ratio is None:
        flags.append(_flag("dual_high_cash_debt", "insufficient_data",
                           detail="needs monetary_funds, short/long borrowings and revenue"))
    else:
        hit = cash_ratio > th["dual_high_ratio"] and debt_ratio > th["dual_high_ratio"]
        flags.append(_flag(
            "dual_high_cash_debt", "flagged" if hit else "clear",
            value=f"cash={cash_ratio:.4f}, debt={debt_ratio:.4f}",
            threshold=f"both > {th['dual_high_ratio']}",
            detail="货币资金与有息负债同时高于营收警戒线"))

    ar_growth = _growth(
        _balance_value(facts, "accounts_receivable"),
        _balance_value(facts, "accounts_receivable", opening=True))
    rev_growth = _growth(revenue, revenue_prior)
    if ar_growth is None or rev_growth is None:
        flags.append(_flag("receivable_outpacing_revenue", "insufficient_data",
                           detail="needs current/prior receivables and revenue"))
    else:
        hit = ar_growth > rev_growth * th["outpacing_factor"]
        flags.append(_flag(
            "receivable_outpacing_revenue", "flagged" if hit else "clear",
            value=f"ar={ar_growth:.4f}, rev={rev_growth:.4f}",
            threshold=f"ar > rev x {th['outpacing_factor']}",
            detail="应收增速超过营收增速1.5倍"))

    flags.append(_surge_flag(
        "inventory_sudden_rise",
        _ratio_vs_revenue(facts, "inventory", revenue),
        _ratio_vs_revenue(facts, "inventory", revenue_prior, opening=True),
        th["inventory_surge_factor"], "存货/营收"))

    cfo = _flow_value(facts, "cfo")
    profit = _flow_value(facts, "net_profit_group")
    if cfo is None or profit is None:
        flags.append(_flag("negative_cfo_positive_profit", "insufficient_data",
                           detail="needs cfo and net_profit_group"))
    else:
        hit = cfo < 0 and profit > 0
        flags.append(_flag(
            "negative_cfo_positive_profit", "flagged" if hit else "clear",
            detail=f"cfo={cfo}, net_profit={profit}；纸面盈利但经营现金流为负"))

    np_group = _flow_value(facts, "net_profit_group")
    np_owners = _flow_value(facts, "net_profit_owners", attribution="owners")
    np_group_prior = _flow_value(facts, "net_profit_group", prior=True)
    np_owners_prior = _flow_value(facts, "net_profit_owners", attribution="owners", prior=True)

    def _minority_ratio(group: Decimal | None, owners: Decimal | None) -> Decimal | None:
        if group is None or owners is None or group <= 0:
            return None
        return (group - owners) / group

    ratio_cur = _minority_ratio(np_group, np_owners)
    ratio_prior = _minority_ratio(np_group_prior, np_owners_prior)
    if ratio_cur is None or ratio_prior is None:
        flags.append(_flag("minority_interest_anomaly", "insufficient_data",
                           detail="needs current/prior group and owners net profit"))
    else:
        hit = abs(ratio_cur - ratio_prior) > th["minority_shift"]
        flags.append(_flag(
            "minority_interest_anomaly", "flagged" if hit else "clear",
            value=f"cur={ratio_cur:.4f}, prior={ratio_prior:.4f}",
            threshold=f"shift > {th['minority_shift']}",
            detail="少数股东损益占净利润比例异常变动"))

    goodwill = _balance_value(facts, "goodwill")
    equity_owners = _owners_balance(facts, "total_equity_owners")
    if goodwill is None or equity_owners is None or equity_owners <= 0:
        flags.append(_flag("goodwill_heavy", "insufficient_data",
                           detail="needs goodwill and total_equity_owners"))
    else:
        ratio = goodwill / equity_owners
        hit = ratio > th["goodwill_ratio"]
        flags.append(_flag(
            "goodwill_heavy", "flagged" if hit else "clear",
            value=f"{ratio:.4f}", threshold=f"> {th['goodwill_ratio']}",
            detail="商誉/归母净资产超过警戒线"))

    flags.append(_surge_flag(
        "prepayment_surge",
        _ratio_vs_revenue(facts, "prepayments", revenue),
        _ratio_vs_revenue(facts, "prepayments", revenue_prior, opening=True),
        th["prepayment_surge_factor"], "预付/营收"))

    cip = _balance_value(facts, "construction_in_progress")
    fixed = _balance_value(facts, "fixed_assets")
    if cip is None or fixed is None or fixed <= 0:
        flags.append(_flag("construction_not_converting", "insufficient_data",
                           detail="needs construction_in_progress and fixed_assets"))
    else:
        ratio = cip / fixed
        hit = ratio > th["construction_ratio"]
        flags.append(_flag(
            "construction_not_converting", "flagged" if hit else "clear",
            value=f"{ratio:.4f}", threshold=f"> {th['construction_ratio']}",
            detail="在建工程/固定资产过高，关注长期不转固"))

    return flags


def calculate_metrics(document: dict) -> dict:
    facts = FactSelection(document)
    metrics: list[dict] = [        _yoy(facts, "revenue", "revenue_yoy"),
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
    for metric in metrics:
        if metric["status"] == "computed":
            mismatch = facts.measurement_error(metric["input_fact_ids"])
            if mismatch:
                metric.update(value=None, status="conflict", reason=mismatch)
    validation = [_cash_reconciliation(facts)]
    return {"schema_version": 1, "metrics": metrics, "validation": validation,
            "red_flags": _red_flags(facts)}


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
    report_path = run_dir / "document.json"
    if report_path.exists():
        document = {**document, "period": read_json(report_path).get("period") or document.get("period")}
    errors = validate_financials(document)
    if errors:
        for error in errors:
            print(
                f"contract violation: {error['fact_id']} {error['field']}: {error['error']}",
                file=sys.stderr,
            )
        raise SystemExit(1)

    result = calculate_metrics(document)

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
