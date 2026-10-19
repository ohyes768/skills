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
        fx = ZERO
        issues.append("fx_effect_on_cash not disclosed; treated as 0")

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


def calculate_metrics(document: dict) -> dict:
    facts = FactSelection(document)
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
    for metric in metrics:
        if metric["status"] == "computed":
            mismatch = facts.measurement_error(metric["input_fact_ids"])
            if mismatch:
                metric.update(value=None, status="conflict", reason=mismatch)
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
