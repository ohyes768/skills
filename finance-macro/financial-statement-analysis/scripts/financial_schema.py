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
_EVIDENCE_ID_RE = re.compile(r"^ev-\d{4,}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
        if value is not None:
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
