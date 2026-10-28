"""紧凑分析包：分层覆盖、利润桥和可拦截的定性条件。

空值保持缺失，不转成零。投资收益未映射时不能充当利润的主要来源。
余额方向不能确认转固。可比杜邦因子不齐时不能指定同比驱动。
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from artifacts import read_json
from fact_selection import pick_usable, prior_year

FLOW_METRICS = (
    "revenue", "cost_of_sales", "selling_expenses", "admin_expenses",
    "r_and_d_expense", "finance_costs", "operating_profit",
    "net_profit_before_tax", "net_profit_group", "gross_profit",
)
BALANCE_METRICS = (
    "total_assets", "total_liabilities", "total_equity", "fixed_assets",
    "construction_in_progress", "accounts_receivable", "inventory",
)
MARGIN_SPECS = (
    ("gross_margin", "gross_profit", "revenue"),
    ("selling_expense_ratio", "selling_expenses", "revenue"),
    ("admin_expense_ratio", "admin_expenses", "revenue"),
    ("rd_expense_ratio", "r_and_d_expense", "revenue"),
    ("finance_expense_ratio", "finance_costs", "revenue"),
)
ATTRIBUTION_METRICS = (
    "revenue", "cost_of_sales", "selling_expenses", "admin_expenses",
    "r_and_d_expense", "finance_costs", "investment_income",
)
INCLUDED_METRICS = set(FLOW_METRICS) | set(BALANCE_METRICS)
_KINDS = ("balance", "income", "cashflow")
_BALANCE_PHRASES = (
    "比较期资产负债表未取得",
    "未取得比较期资产负债表",
    "资产负债表未取得",
)
_TRANSFER_PHRASES = ("确认转固", "已转固", "转入固定资产", "完成转固")
_PROFIT_WORDS = ("利润", "盈利", "净利")
_PROFIT_CLAIM_WORDS = ("主要来自", "主要驱动", "主要归因", "主要贡献")


def _money(value: Decimal) -> str:
    return format(value, "f")


def _period_ends(period: dict) -> tuple[str, str, str]:
    current = period["end"]
    opening = (date.fromisoformat(period["start"]) - timedelta(days=1)).isoformat()
    return current, prior_year(current), opening


def _slots(period: dict, archive: dict) -> list[dict]:
    current, prior, opening = _period_ends(period)
    dates = sorted({current, prior, opening, *list(archive.get("reports") or {})})
    failures = archive.get("fetch_failures") or {}
    records = []
    for day in dates:
        for kind in _KINDS:
            rows = (archive.get("reports") or {}).get(day, {}).get(kind)
            failure = failures.get(f"{day}/{kind}") or {}
            if rows:
                availability, reason = "present", None
            elif failure.get("reason") in {"no_data", "fetch_failed"}:
                availability, reason = failure["reason"], failure.get("detail")
            elif failure:
                availability, reason = "fetch_failed", failure.get("detail")
            else:
                availability, reason = "not_requested", None
            records.append({
                "layer": "archive", "report_date": day, "report_kind": kind,
                "availability": availability, "reason": reason,
            })
    return records


def _slot_index(slots: list[dict]) -> dict[tuple[str, str], dict]:
    return {(row["report_date"], row["report_kind"]): row for row in slots}


def fact_availability(fact: dict, slots: dict[tuple[str, str], dict]) -> str:
    """把一条事实分成留档、字段、映射或未计算，不把空值当成零。"""
    field = (fact.get("source_ref") or {}).get("field") or fact.get("raw_label")
    if field == "__UNMAPPED__":
        return "unmapped"
    if fact.get("value") is not None and fact.get("review_status") == "verified":
        return "present"
    if fact.get("source") == "derived":
        return "not_calculated"
    ref = fact.get("source_ref") or {}
    slot = slots.get((ref.get("report_date"), ref.get("report_kind")))
    if slot and slot["availability"] != "present":
        return slot["availability"]
    return "field_null"


def _facts_for(facts: list[dict], metric: str, end: str, kind: str) -> dict | None:
    candidates = [
        fact for fact in facts
        if fact.get("metric") == metric and fact.get("scope") == "consolidated"
        and (fact.get("period") or {}).get("end") == end
        and (fact.get("period") or {}).get("kind") == kind
    ]
    chosen, status, _reason = pick_usable(candidates)
    return None if status else chosen


def _component(facts: list[dict], metric: str, current: str, prior: str, kind: str) -> dict:
    left = _facts_for(facts, metric, current, kind)
    right = _facts_for(facts, metric, prior, kind)
    base = {
        "metric": metric,
        "current": None if left is None else left["value"],
        "prior": None if right is None else right["value"],
        "fact_ids": [fact["fact_id"] for fact in (left, right) if fact],
        "delta": None,
    }
    if left is None or right is None:
        return {**base, "status": "missing", "reason": "missing operand"}
    delta = Decimal(left["value"]) - Decimal(right["value"])
    return {**base, "status": "computed", "delta": _money(delta), "reason": None}


def _investment_component() -> dict:
    return {
        "metric": "investment_income", "status": "unmapped", "current": None,
        "prior": None, "delta": None, "fact_ids": [],
        "reason": "投资收益不在已核对的字段映射中，缺失不是零",
    }


def profit_attribution(components: list[dict]) -> dict:
    """单一科目只有在桥接项都有差额、且绝对值严格最大时才可称为主要来源。"""
    by_metric = {row["metric"]: row for row in components}
    missing = [
        metric for metric in ATTRIBUTION_METRICS
        if by_metric.get(metric, {}).get("status") != "computed"
        or by_metric.get(metric, {}).get("delta") is None
    ]
    if missing:
        return {
            "supported": False, "driver": None, "missing": missing,
            "reason": "利润桥存在缺失项，不能把单一科目写成主要来源",
        }
    ranked = sorted(
        ATTRIBUTION_METRICS,
        key=lambda metric: abs(Decimal(by_metric[metric]["delta"])),
        reverse=True,
    )
    top, second = ranked[0], ranked[1]
    if abs(Decimal(by_metric[top]["delta"])) <= abs(Decimal(by_metric[second]["delta"])):
        return {
            "supported": False, "driver": None, "missing": [],
            "reason": "没有单一科目的差额严格大于其余科目",
        }
    return {
        "supported": True, "driver": top, "missing": [],
        "reason": "单一科目差额严格大于其余已映射桥接项",
    }


def asset_transfer_support(fixed_delta: Decimal | None, cip_delta: Decimal | None) -> dict:
    observed = None
    if fixed_delta is not None and cip_delta is not None and fixed_delta > 0 and cip_delta < 0:
        observed = "fixed_up_cip_down"
    return {
        "supported": False, "observed": observed,
        "reason": "余额方向不能确认在建工程转入固定资产",
    }


def dupont_driver(
    current: tuple[Decimal | None, Decimal | None, Decimal | None],
    prior: tuple[Decimal | None, Decimal | None, Decimal | None],
) -> dict:
    """用连环替代看净利率、周转率和权益乘数。缺可比因子时不指定驱动。"""
    names = ("net_margin", "asset_turnover", "equity_multiplier")
    if any(value is None for value in (*current, *prior)):
        return {
            "supported": False, "driver": None, "effects": None,
            "reason": "缺少可比杜邦因子，不能确定同比驱动",
        }
    pm_c, at_c, em_c = current
    pm_p, at_p, em_p = prior
    effects = {
        "net_margin": (pm_c - pm_p) * at_p * em_p,
        "asset_turnover": pm_c * (at_c - at_p) * em_p,
        "equity_multiplier": pm_c * at_c * (em_c - em_p),
    }
    ranked = sorted(names, key=lambda name: abs(effects[name]), reverse=True)
    unique = abs(effects[ranked[0]]) > abs(effects[ranked[1]]) and effects[ranked[0]] != 0
    roe_change = pm_c * at_c * em_c - pm_p * at_p * em_p
    same_direction = roe_change == 0 or (roe_change > 0) == (effects[ranked[0]] > 0)
    supported = bool(unique and same_direction)
    return {
        "supported": supported,
        "driver": ranked[0] if supported else None,
        "effects": {name: _money(effects[name]) for name in names},
        "reason": "可比因子已齐，最大贡献可复核" if supported else "贡献不唯一或与 ROE 变动方向不一致",
    }


def _ratio(numerator: dict | None, denominator: dict | None, name: str) -> dict:
    fact_ids = [fact["fact_id"] for fact in (numerator, denominator) if fact]
    if numerator is None or denominator is None:
        return {"name": name, "status": "missing", "value": None, "fact_ids": fact_ids}
    den = Decimal(denominator["value"])
    if den <= 0:
        return {"name": name, "status": "not_applicable", "value": None, "fact_ids": fact_ids}
    return {
        "name": name, "status": "computed", "fact_ids": fact_ids,
        "value": _money(Decimal(numerator["value"]) / den),
    }


def _average(facts, metric: str, end: str, start: str) -> Decimal | None:
    closing = _facts_for(facts, metric, end, "instant")
    opening_day = (date.fromisoformat(start) - timedelta(days=1)).isoformat()
    opening = _facts_for(facts, metric, opening_day, "instant")
    if closing is None or opening is None:
        return None
    return (Decimal(closing["value"]) + Decimal(opening["value"])) / 2


def _dupont_inputs(facts, period, current: bool):
    end = period["end"] if current else prior_year(period["end"])
    start = period["start"] if current else prior_year(period["start"])
    profit = _facts_for(facts, "net_profit_group", end, "duration")
    revenue = _facts_for(facts, "revenue", end, "duration")
    assets = _average(facts, "total_assets", end, start)
    equity = _average(facts, "total_equity", end, start)
    if (profit is None or revenue is None or assets is None or equity is None
            or Decimal(revenue["value"]) <= 0 or assets <= 0 or equity <= 0):
        return (None, None, None)
    revenue_value = Decimal(revenue["value"])
    return (
        Decimal(profit["value"]) / revenue_value,
        revenue_value / assets,
        assets / equity,
    )


def _limits(slots: list[dict], counts: dict) -> list[dict]:
    opening = next(
        (row for row in slots if row["layer"] == "archive" and row["report_kind"] == "balance"
         and row.get("role") == "opening"),
        None,
    )
    availability = opening["availability"] if opening else "not_requested"
    if availability == "present":
        balance_text = "比较期资产负债表已留档。不得写成比较期资产负债表未取得。"
    elif availability == "no_data":
        balance_text = "比较期资产负债表无记录（no_data），不是请求失败。"
    elif availability == "fetch_failed":
        balance_text = "比较期资产负债表请求失败（fetch_failed），不是无记录。"
    else:
        balance_text = "比较期资产负债表没有可分类的留档结果。不得写成已取得或请求失败。"
    limits = [{
        "code": "comparison_balance_sheet", "availability": availability, "text": balance_text,
    }, {
        "code": "null_is_not_zero", "availability": "field_null",
        "text": "字段为空不是零，也不是整张报表未取得。",
    }, {
        "code": "not_in_model_input", "availability": "not_in_model_input",
        "text": "未纳入分析包数值的科目不代表报表未取得。",
    }]
    if counts["unmapped"]:
        limits.append({
            "code": "unmapped", "availability": "unmapped",
            "text": "未映射科目不能按零或按已披露数字使用。",
        })
    if counts["not_calculated"]:
        limits.append({
            "code": "not_calculated", "availability": "not_calculated",
            "text": "指标未计算时，应写未计算，不要写成源报表未取得。",
        })
    return limits


def _mark_opening(slots: list[dict], opening: str) -> None:
    for row in slots:
        if row["report_date"] == opening and row["report_kind"] == "balance":
            row["role"] = "opening"


def build_analysis_pack(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    document = read_json(run_dir / "document.json")
    financials = read_json(run_dir / "financials.json")
    metrics_doc = read_json(run_dir / "metrics.json")
    archive_path = run_dir / "structured_financials.json"
    archive = read_json(archive_path) if archive_path.exists() else {
        "reports": {}, "fetch_failures": {},
    }
    period = document["period"]
    current, prior, opening = _period_ends(period)
    facts = list(financials.get("facts") or [])
    slots = _slots(period, archive)
    _mark_opening(slots, opening)
    indexed = _slot_index(slots)
    records = list(slots)
    for fact in facts:
        availability = fact_availability(fact, indexed)
        if availability == "present":
            continue
        records.append({
            "layer": "field", "metric": fact.get("metric"), "fact_id": fact.get("fact_id"),
            "period_end": (fact.get("period") or {}).get("end"), "availability": availability,
        })
    metrics = []
    for metric in metrics_doc.get("metrics") or []:
        compact = {
            "metric_id": metric.get("metric_id"), "status": metric.get("status"),
            "value": metric.get("value"), "formula": metric.get("formula"),
            "input_fact_ids": list(metric.get("input_fact_ids") or []),
            "reason": metric.get("reason"),
        }
        metrics.append(compact)
        if metric.get("status") != "computed":
            records.append({
                "layer": "calculation", "metric_id": metric.get("metric_id"),
                "availability": "not_calculated", "status": metric.get("status"),
                "reason": metric.get("reason"),
            })
    withheld = sorted({
        fact["metric"] for fact in facts
        if fact.get("value") is not None and fact.get("review_status") == "verified"
        and fact.get("metric") not in INCLUDED_METRICS
    })
    if withheld:
        records.append({
            "layer": "model_input", "availability": "not_in_model_input", "metrics": withheld,
        })
    components = [
        _component(facts, metric, current, prior, "duration") for metric in FLOW_METRICS
    ]
    components.append(_investment_component())
    spread = next(row for row in components if row["metric"] == "revenue")
    cost = next(row for row in components if row["metric"] == "cost_of_sales")
    if spread["status"] == "computed" and cost["status"] == "computed":
        revenue_minus_cost = _money(Decimal(spread["delta"]) - Decimal(cost["delta"]))
        spread_status = "computed"
    else:
        revenue_minus_cost, spread_status = None, "missing"
    balances = []
    for metric in BALANCE_METRICS:
        row = _component(facts, metric, current, opening, "instant")
        balances.append(row)
    margins = []
    for name, numerator, denominator in MARGIN_SPECS:
        margins.append(_ratio(
            _facts_for(facts, numerator, current, "duration"),
            _facts_for(facts, denominator, current, "duration"),
            name,
        ))
    fixed = next(row for row in balances if row["metric"] == "fixed_assets")
    cip = next(row for row in balances if row["metric"] == "construction_in_progress")
    fixed_delta = Decimal(fixed["delta"]) if fixed["status"] == "computed" else None
    cip_delta = Decimal(cip["delta"]) if cip["status"] == "computed" else None
    support = {
        "profit_primary_attribution": profit_attribution(components),
        "asset_transfer": asset_transfer_support(fixed_delta, cip_delta),
        "dupont_yoy_driver": dupont_driver(
            _dupont_inputs(facts, period, True), _dupont_inputs(facts, period, False),
        ),
    }
    counts = {
        "archive_present": sum(row["availability"] == "present" for row in slots),
        "no_data": sum(row["availability"] == "no_data" for row in slots),
        "fetch_failed": sum(row["availability"] == "fetch_failed" for row in slots),
        "field_null": sum(row.get("availability") == "field_null" for row in records),
        "unmapped": sum(row.get("availability") == "unmapped" for row in records),
        "not_calculated": sum(row.get("availability") == "not_calculated" for row in records),
        "not_in_model_input": len(withheld),
    }
    return {
        "schema_version": 1,
        "counts": counts,
        "records": records,
        "narrative_limits": _limits(slots, counts),
        "profit_bridge": {
            "components": components,
            "revenue_minus_cost_of_sales": {
                "status": spread_status, "delta": revenue_minus_cost,
                "meaning": "营业收入减营业成本的增量，不是营业总成本，也不含未映射的投资收益",
            },
        },
        "margins": margins,
        "balance_changes": balances,
        "qualitative_support": support,
        "metrics": metrics,
        "red_flags": [
            {"flag_id": flag.get("flag_id"), "status": flag.get("status"),
             "detail": flag.get("detail")}
            for flag in metrics_doc.get("red_flags") or []
        ],
        "validation": [
            {"check_id": check.get("check_id"), "status": check.get("status")}
            for check in metrics_doc.get("validation") or []
        ],
        "source": {
            "source": financials.get("source") or archive.get("source"),
            "security_code": document.get("stock_code"),
            "period_end": current,
            "source_sha256": financials.get("source_sha256"),
        },
    }


def project_items(pack: dict) -> list[dict]:
    """把分析包拆成可分页的小项。来源细节仍通过 fact_id 回查。"""
    items = []
    for record in pack["records"]:
        if record["layer"] == "archive":
            identity = f"{record['report_date']}/{record['report_kind']}"
        elif record["layer"] == "field":
            identity = record.get("fact_id")
        elif record["layer"] == "calculation":
            identity = record.get("metric_id")
        else:
            identity = "withheld"
        items.append({"kind": "coverage", "id": f"coverage:{record['layer']}:{identity}", **record})
    for limit in pack["narrative_limits"]:
        items.append({"kind": "limit", "id": f"limit:{limit['code']}", **limit})
    bridge = pack["profit_bridge"]
    for component in bridge["components"]:
        items.append({"kind": "profit_bridge", "id": f"bridge:{component['metric']}", **component})
    items.append({
        "kind": "profit_bridge", "id": "bridge:revenue_minus_cost_of_sales",
        **bridge["revenue_minus_cost_of_sales"],
    })
    for margin in pack["margins"]:
        items.append({"kind": "margin", "id": f"margin:{margin['name']}", **margin})
    for change in pack["balance_changes"]:
        items.append({"kind": "balance_change", "id": f"balance:{change['metric']}", **change})
    for key, value in pack["qualitative_support"].items():
        items.append({"kind": "qualitative_support", "id": f"support:{key}", "name": key, **value})
    for metric in pack["metrics"]:
        items.append({"kind": "metric", "id": f"metric:{metric['metric_id']}", **metric})
    for flag in pack["red_flags"]:
        items.append({"kind": "red_flag", "id": f"flag:{flag['flag_id']}", **flag})
    for check in pack["validation"]:
        items.append({"kind": "check", "id": f"check:{check['check_id']}", **check})
    items.append({"kind": "source", "id": "source", **pack["source"]})
    return items


def packet_items(run_dir: Path) -> list[dict]:
    return project_items(build_analysis_pack(run_dir))


def analysis_pack_errors(run_dir: Path) -> list[str]:
    path = Path(run_dir) / "analysis_pack.json"
    if not path.exists():
        return ["analysis pack missing"]
    try:
        actual = read_json(path)
        expected = build_analysis_pack(run_dir)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        return [f"analysis pack validation unavailable: {exc}"]
    if actual != expected:
        return ["analysis pack differs from source facts"]
    return []


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


def qualitative_claim_errors(pack: dict, texts: list[str]) -> list[str]:
    """只拦截已经能确定不成立的归因，不把其余句子当成已验证。"""
    text = "\n".join(texts)
    if not text.strip():
        return []
    errors = []
    limits = {row["code"]: row for row in pack.get("narrative_limits") or []}
    balance = limits.get("comparison_balance_sheet") or {}
    if balance.get("availability") == "present" and _contains_any(text, _BALANCE_PHRASES):
        errors.append("comparison balance sheet is archived; do not claim it is missing")
    support = pack.get("qualitative_support") or {}
    profit = support.get("profit_primary_attribution") or {}
    profit_claim = (
        ("投资收益" in text and _contains_any(text, ("主要", "驱动", "来自")))
        or (_contains_any(text, _PROFIT_CLAIM_WORDS) and _contains_any(text, _PROFIT_WORDS))
    )
    if profit_claim and not profit.get("supported"):
        errors.append("primary profit attribution is not supported by the bridge")
    if (profit_claim and profit.get("supported") and "投资收益" in text
            and profit.get("driver") != "investment_income"):
        errors.append("investment income is not the supported profit driver")
    transfer = support.get("asset_transfer") or {}
    if _contains_any(text, _TRANSFER_PHRASES) and not transfer.get("supported"):
        errors.append("asset transfer to fixed assets is not supported")
    dupont = support.get("dupont_yoy_driver") or {}
    dupont_claim = _contains_any(text, ("杜邦", "ROE")) and _contains_any(
        text, ("主要驱动", "同比改善"))
    if dupont_claim and not dupont.get("supported"):
        errors.append("DuPont year-over-year driver is not supported")
    return errors


def sentence_budget(statement_count: int) -> dict:
    """核心结论按三到五句计，每条 statement 占一句。"""
    return {
        "section": "## 核心结论",
        "core_statement_sentences": statement_count,
        "core_total_min": 3,
        "core_total_max": 5,
        "qualitative_sentences_min": max(0, 3 - statement_count),
        "qualitative_sentences_max": max(0, 5 - statement_count),
    }
