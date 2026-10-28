"""财务事实合同：金额解析、事实校验与维度筛选。金额一律 Decimal，禁止二进制浮点。"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

_UNIT_FACTORS = {
    "元": Decimal(1),
    "千元": Decimal(1_000),
    "万元": Decimal(10_000),
    "亿元": Decimal(100_000_000),
}

_SCOPE_VALUES = {"consolidated", "parent"}
_ATTRIBUTION_VALUES = {"group", "owners", "not_applicable"}
_BASIS_VALUES = {"as_reported", "restated"}
_REVIEW_STATUS_VALUES = {"verified", "ambiguous", "missing", "conflict"}
_PERIOD_KINDS = {"instant", "duration"}
_FREQUENCIES = {"annual", "half_year", "quarter"}
_AGGREGATIONS = {"instant", "cumulative", "single_period"}
_FACT_FIELDS = {
    "fact_id",
    "metric",
    "raw_label",
    "raw_value",
    "raw_unit",
    "value",
    "unit",
    "currency",
    "scope",
    "attribution",
    "period",
    "basis",
    "evidence_ids",
    "review_status",
    "missing_reason",
}
# source 为可选字段（缺省视为 extracted），保证旧产物与既有生成器兼容。
_SOURCE_VALUES = {"structured", "extracted"}
_STRUCTURED_EVIDENCE_BASES = {"sample_match", "value_presence"}
_EVIDENCE_ID_RE = re.compile(r"^ev-\d{4,}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# 指标合同：模型只提交规范 metric 名，归属与期间类型由合同固定，不可在输入里改写。
# monetary_funds（货币资金）与 cash_equivalents（现金及现金等价物）含义不同，别名绝不互通。
METRIC_CONTRACTS: dict[str, dict] = {
    "revenue": {"period_kind": "duration", "attribution": "group",
                "aliases": ("operating_revenue", "营业总收入", "营业收入")},
    "cost_of_sales": {"period_kind": "duration", "attribution": "group",
                      "aliases": ("cost_of_revenue", "cost_of_goods_sold", "营业成本")},
    "gross_profit": {"period_kind": "duration", "attribution": "group",
                     "aliases": ("毛利润",)},
    "selling_expenses": {"period_kind": "duration", "attribution": "group",
                         "aliases": ("销售费用",)},
    "admin_expenses": {"period_kind": "duration", "attribution": "group",
                       "aliases": ("管理费用",)},
    "finance_costs": {"period_kind": "duration", "attribution": "group",
                      "aliases": ("财务费用",)},
    "r_and_d_expense": {"period_kind": "duration", "attribution": "group",
                        "aliases": ("研发费用", "research_and_development_expense")},
    "operating_profit": {"period_kind": "duration", "attribution": "group",
                         "aliases": ("营业利润",)},
    "net_profit_before_tax": {"period_kind": "duration", "attribution": "group",
                              "aliases": ("利润总额", "total_profit")},
    "income_tax_expense": {"period_kind": "duration", "attribution": "group",
                           "aliases": ("所得税费用",)},
    "net_profit_group": {"period_kind": "duration", "attribution": "group",
                         "aliases": ("净利润", "net_profit")},
    "net_profit_owners": {"period_kind": "duration", "attribution": "owners",
                          "aliases": ("归属于母公司股东的净利润", "归属于母公司所有者的净利润",
                                      "归母净利润", "net_profit_attributable_to_owners")},
    "cfo": {"period_kind": "duration", "attribution": "group",
            "aliases": ("经营活动产生的现金流量净额", "net_cash_flow_from_operating_activities")},
    "cfi": {"period_kind": "duration", "attribution": "group",
            "aliases": ("投资活动产生的现金流量净额", "net_cash_flow_from_investing_activities")},
    "cff": {"period_kind": "duration", "attribution": "group",
            "aliases": ("筹资活动产生的现金流量净额", "net_cash_flow_from_financing_activities")},
    "fx_effect_on_cash": {"period_kind": "duration", "attribution": "group",
                          "aliases": ("汇率变动对现金及现金等价物的影响",)},
    "capex_purchase_fixed_assets": {"period_kind": "duration", "attribution": "group",
                                    "aliases": ("购建固定资产、无形资产和其他长期资产支付的现金",)},
    "total_assets": {"period_kind": "instant", "attribution": "not_applicable",
                     "aliases": ("资产总计", "资产总额")},
    "total_liabilities": {"period_kind": "instant", "attribution": "not_applicable",
                          "aliases": ("负债合计", "负债总额")},
    "total_equity": {"period_kind": "instant", "attribution": "not_applicable",
                     "aliases": ("所有者权益合计", "股东权益合计", "equity")},
    "total_equity_owners": {"period_kind": "instant", "attribution": "owners",
                            "aliases": ("归属于母公司股东权益合计", "归属于母公司所有者权益合计", "归母净资产")},
    "monetary_funds": {"period_kind": "instant", "attribution": "not_applicable",
                       "aliases": ("货币资金",)},
    "cash_equivalents": {"period_kind": "instant", "attribution": "not_applicable",
                         "aliases": ("现金及现金等价物余额", "期末现金及现金等价物余额")},
    "accounts_receivable": {"period_kind": "instant", "attribution": "not_applicable",
                            "aliases": ("应收账款",)},
    "notes_receivable": {"period_kind": "instant", "attribution": "not_applicable",
                         "aliases": ("应收票据",)},
    "inventory": {"period_kind": "instant", "attribution": "not_applicable",
                  "aliases": ("存货",)},
    "fixed_assets": {"period_kind": "instant", "attribution": "not_applicable",
                     "aliases": ("固定资产",)},
    "goodwill": {"period_kind": "instant", "attribution": "not_applicable",
                 "aliases": ("商誉",)},
    "total_current_assets": {"period_kind": "instant", "attribution": "not_applicable",
                             "aliases": ("流动资产合计",)},
    "total_current_liabilities": {"period_kind": "instant", "attribution": "not_applicable",
                                  "aliases": ("流动负债合计",)},
    "short_term_borrowings": {"period_kind": "instant", "attribution": "not_applicable",
                              "aliases": ("短期借款",)},
    "long_term_borrowings": {"period_kind": "instant", "attribution": "not_applicable",
                             "aliases": ("长期借款",)},
    "contract_liabilities": {"period_kind": "instant", "attribution": "not_applicable",
                             "aliases": ("合同负债",)},
    "prepayments": {"period_kind": "instant", "attribution": "not_applicable",
                    "aliases": ("预付款项", "预付账款")},
    "construction_in_progress": {"period_kind": "instant", "attribution": "not_applicable",
                                 "aliases": ("在建工程",)},
}

_ALIAS_TABLE: dict[str, str] = {}
for _metric, _contract in METRIC_CONTRACTS.items():
    for _alias in (_metric, *_contract["aliases"]):
        _ALIAS_TABLE.setdefault(_alias.lower(), _metric)


# 结构化数据源字段映射：metric → (报表 kind, 东财 F10 字段)。字段名以实测响应为准。
# gross_profit / fx_effect_on_cash 无直接披露字段：前者可在下游做确定性派生，
# 后者缺失时勾稽按 0 处理（既有语义），均不在此映射。
STRUCTURED_FIELD_MAP: dict[str, tuple[str, str]] = {
    "revenue": ("income", "TOTAL_OPERATE_INCOME"),
    "cost_of_sales": ("income", "OPERATE_COST"),
    "selling_expenses": ("income", "SALE_EXPENSE"),
    "admin_expenses": ("income", "MANAGE_EXPENSE"),
    "finance_costs": ("income", "FINANCE_EXPENSE"),
    "r_and_d_expense": ("income", "RESEARCH_EXPENSE"),
    "operating_profit": ("income", "OPERATE_PROFIT"),
    "net_profit_before_tax": ("income", "TOTAL_PROFIT"),
    "income_tax_expense": ("income", "INCOME_TAX"),
    "net_profit_group": ("income", "NETPROFIT"),
    "net_profit_owners": ("income", "PARENT_NETPROFIT"),
    "cfo": ("cashflow", "NETCASH_OPERATE"),
    "cfi": ("cashflow", "NETCASH_INVEST"),
    "cff": ("cashflow", "NETCASH_FINANCE"),
    "capex_purchase_fixed_assets": ("cashflow", "CONSTRUCT_LONG_ASSET"),
    "cash_equivalents": ("cashflow", "END_CCE"),
    "total_assets": ("balance", "TOTAL_ASSETS"),
    "total_liabilities": ("balance", "TOTAL_LIABILITIES"),
    "total_equity": ("balance", "TOTAL_EQUITY"),
    "total_equity_owners": ("balance", "TOTAL_PARENT_EQUITY"),
    "monetary_funds": ("balance", "MONETARYFUNDS"),
    "accounts_receivable": ("balance", "ACCOUNTS_RECE"),
    "notes_receivable": ("balance", "NOTE_RECE"),
    "inventory": ("balance", "INVENTORY"),
    "fixed_assets": ("balance", "FIXED_ASSET"),
    "goodwill": ("balance", "GOODWILL"),
    "total_current_assets": ("balance", "TOTAL_CURRENT_ASSETS"),
    "total_current_liabilities": ("balance", "TOTAL_CURRENT_LIAB"),
    "short_term_borrowings": ("balance", "SHORT_LOAN"),
    "long_term_borrowings": ("balance", "LONG_LOAN"),
    "contract_liabilities": ("balance", "CONTRACT_LIAB"),
}
STRUCTURED_UNSUPPORTED = ("gross_profit", "fx_effect_on_cash")


def metric_aliases() -> dict[str, list[str]]:
    """公开别名表副本：规范 metric 名 → 接受的标签列表（含自身）。"""
    return {
        metric: [metric, *contract["aliases"]]
        for metric, contract in METRIC_CONTRACTS.items()
    }


def resolve_metric_label(metric: str | None, raw_label: str | None) -> str | None:
    """先按提交的 metric 名解析，再退回 PDF 原文标签；都未注册则 None。"""
    for candidate in (metric, raw_label):
        if not candidate:
            continue
        resolved = _ALIAS_TABLE.get(candidate.strip().lower())
        if resolved:
            return resolved
    return None


def parse_amount(raw_value: str | None, raw_unit: str | None) -> Decimal | None:
    """把报表原始字符串转为基本单位（元）的 Decimal；缺失记号返回 None。

    括号表示负数；千分位逗号被去除；破折号、空白、None 均视为未披露。
    """
    if raw_value is None or raw_unit is None:
        return None
    factor = _UNIT_FACTORS.get(raw_unit.strip())
    if factor is None:
        return None
    text = raw_value.strip()
    if not text or text in {"—", "–", "-", "--"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    text = text.replace(",", "")
    try:
        amount = Decimal(text)
    except InvalidOperation:
        return None
    if negative:
        amount = -amount
    return amount * factor


def _error(fact_id: str, field: str, message: str) -> dict:
    return {"fact_id": fact_id, "field": field, "error": message}


def _check_period(fact: dict, errors: list[dict]) -> None:
    period = fact.get("period")
    if not isinstance(period, dict):
        errors.append(_error(fact["fact_id"], "period", "period must be an object"))
        return
    for field, allowed in (
        ("kind", _PERIOD_KINDS),
        ("frequency", _FREQUENCIES),
        ("aggregation", _AGGREGATIONS),
    ):
        if period.get(field) not in allowed:
            errors.append(
                _error(fact["fact_id"], f"period.{field}", f"illegal value: {period.get(field)!r}")
            )
    end = period.get("end")
    if not isinstance(end, str) or not _DATE_RE.match(end):
        errors.append(_error(fact["fact_id"], "period.end", f"bad date: {end!r}"))
    start = period.get("start")
    if period.get("kind") == "instant":
        if start is not None and not (isinstance(start, str) and _DATE_RE.match(start)):
            errors.append(_error(fact["fact_id"], "period.start", f"bad date: {start!r}"))
    elif not (isinstance(start, str) and _DATE_RE.match(start)):
        errors.append(_error(fact["fact_id"], "period.start", f"bad date: {start!r}"))


def validate_financials(document: dict) -> list[dict]:
    """校验 financials 文档；返回错误列表，空列表表示通过。"""
    errors: list[dict] = []
    facts = document.get("facts")
    if not isinstance(facts, list):
        errors.append(_error("-", "facts", "facts must be a list"))
        return errors

    seen_ids: set[str] = set()
    for index, fact in enumerate(facts):
        fact_id = fact.get("fact_id") or f"<index {index}>"
        missing_fields = _FACT_FIELDS - set(fact)
        if missing_fields:
            errors.append(
                _error(fact_id, "fields", f"missing fields: {sorted(missing_fields)}")
            )
            continue
        if fact_id in seen_ids:
            errors.append(_error(fact_id, "fact_id", "duplicate fact_id"))
        seen_ids.add(fact_id)

        value = fact["value"]
        if value is not None:
            if isinstance(value, float):
                errors.append(
                    _error(fact_id, "value", "binary float forbidden; use decimal string")
                )
            elif not isinstance(value, str):
                errors.append(_error(fact_id, "value", f"expected decimal string, got {type(value).__name__}"))
            else:
                try:
                    Decimal(value)
                except InvalidOperation:
                    errors.append(_error(fact_id, "value", f"not a decimal string: {value!r}"))

        evidence_ids = fact["evidence_ids"]
        source = fact.get("source", "extracted")
        if source not in _SOURCE_VALUES:
            errors.append(_error(fact_id, "source", f"illegal value: {source!r}"))
        if source == "structured":
            # 结构化事实由抽样核对（structured_check）把关；只有与原文对上的才可挂
            # evidence，并须用 evidence_basis 标明是抽查一致还是原文同值。
            basis = fact.get("evidence_basis")
            if evidence_ids and basis not in _STRUCTURED_EVIDENCE_BASES:
                errors.append(_error(
                    fact_id, "evidence_basis",
                    f"structured fact with evidence_ids needs evidence_basis in "
                    f"{sorted(_STRUCTURED_EVIDENCE_BASES)}"))
            elif evidence_ids and not all(
                isinstance(e, str) and _EVIDENCE_ID_RE.match(e) for e in evidence_ids
            ):
                errors.append(_error(fact_id, "evidence_ids", "invalid evidence id format"))
        elif value is not None:
            if not evidence_ids or not all(
                isinstance(e, str) and _EVIDENCE_ID_RE.match(e) for e in evidence_ids
            ):
                errors.append(
                    _error(fact_id, "evidence_ids", "non-null value requires valid evidence_ids")
                )
        elif evidence_ids and not all(
            isinstance(e, str) and _EVIDENCE_ID_RE.match(e) for e in evidence_ids
        ):
            errors.append(_error(fact_id, "evidence_ids", "invalid evidence id format"))

        missing_reason = fact["missing_reason"]
        if value is None and not missing_reason:
            errors.append(
                _error(fact_id, "missing_reason", "null value requires a missing_reason")
            )
        if value is not None and missing_reason is not None:
            errors.append(
                _error(fact_id, "missing_reason", "missing_reason must be null for a valued fact")
            )

        if fact["scope"] not in _SCOPE_VALUES:
            errors.append(_error(fact_id, "scope", f"illegal value: {fact['scope']!r}"))
        if fact["attribution"] not in _ATTRIBUTION_VALUES:
            errors.append(_error(fact_id, "attribution", f"illegal value: {fact['attribution']!r}"))
        if fact["basis"] not in _BASIS_VALUES:
            errors.append(_error(fact_id, "basis", f"illegal value: {fact['basis']!r}"))
        if fact["review_status"] not in _REVIEW_STATUS_VALUES:
            errors.append(
                _error(fact_id, "review_status", f"illegal value: {fact['review_status']!r}")
            )

        _check_period(fact, errors)

    return errors


def select_facts(
    document: dict, metric: str, scope: str, attribution: str, aggregation: str
) -> list[dict]:
    """按维度筛选候选事实；返回全部匹配项，调用方必须自行核对期间与版本。"""
    return [
        fact
        for fact in document.get("facts", [])
        if fact.get("metric") == metric
        and fact.get("scope") == scope
        and fact.get("attribution") == attribution
        and fact.get("period", {}).get("aggregation") == aggregation
    ]
