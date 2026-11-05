"""Validate traceable insurance evidence without certifying source truth."""

from __future__ import annotations

import math
import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlsplit

from bank_financial import _date, stock_fingerprint

TYPES = ("life", "property", "group")
RATINGS = ("AAA", "AA", "A", "BBB", "BB", "B", "C", "D")
METRIC_SCHEMA = {
    "roe": ("pct", "period"),
    "group_solvency_ratio": ("pct", "point_in_time"),
    "core_solvency": ("pct", "point_in_time"),
    "comprehensive_solvency": ("pct", "point_in_time"),
    "net_investment_yield": ("pct", "period"),
    "total_investment_yield": ("pct", "period"),
    "comprehensive_investment_yield": ("pct", "period"),
    "nbv": ("cny_million", "period"),
    "new_business_csm": ("cny_million", "period"),
    "combined_ratio": ("pct", "period"),
    "csm_balance": ("cny_million", "point_in_time"),
    "continuation_ratio": ("pct", "period"),
    "surrender_ratio": ("pct", "period"),
    "net_profit": ("cny_million", "period"),
}


def make_template(stock, as_of, insurance_type):
    _date(as_of, "as_of")
    if insurance_type not in TYPES:
        raise ValueError("insurance_type 必须为 life/property/group")
    fingerprint = stock_fingerprint(stock)
    return {
        "schema_version": 1,
        "code": stock.get("code"),
        "name": stock.get("name"),
        "stock_sha256": fingerprint,
        "as_of": as_of,
        "insurance_type": insurance_type,
        "reports": [],
        "entities": [],
        "coverage": None,
    }


def _text(value, name, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} 必须为非空、有界文本")
    return value


def _source(value, field):
    source = _text(value.get("source_url"), f"{field}.source_url", 2048)
    parsed = urlsplit(source)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        raise ValueError(f"{field}.source_url 必须为 http(s) URL")
    return {"source_url": source, "locator": _text(value.get("locator"), f"{field}.locator")}


def _period(row, field, as_of):
    end, published = (
        _date(row.get(key), f"{field}.{key}") for key in ("period_end", "published_at")
    )
    if end >= published or published > as_of:
        raise ValueError(f"{field} 报告期必须早于披露日，披露日不得晚于 as_of")
    return end, published


def _metric(raw, key, field):
    if not isinstance(raw, dict):
        raise TypeError(f"{field} 必须为数值/单位/来源对象")
    value = raw.get("value")
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        raise ValueError(f"{field}.value 必须为有限数字，不接受布尔值/字符串")
    unit, basis = METRIC_SCHEMA[key]
    if raw.get("unit") != unit or raw.get("basis") != basis:
        raise ValueError(f"{field} 必须使用 unit={unit}, basis={basis}")
    numeric = Decimal(str(value))
    if unit == "pct":
        lower = (
            -1000
            if key
            in (
                "roe",
                "net_investment_yield",
                "total_investment_yield",
                "comprehensive_investment_yield",
            )
            else 0
        )
        if key in ("core_solvency", "comprehensive_solvency", "group_solvency_ratio"):
            # Negative regulatory capital can produce a valid negative ratio;
            # preserve it as known weakness rather than inventing a data gap.
            lower = -1000000
        upper = 100 if key in ("continuation_ratio", "surrender_ratio") else 1000000
        if not Decimal(lower) <= numeric <= Decimal(upper):
            raise ValueError(f"{field} 超出合理百分数范围")
    elif abs(numeric) > Decimal("1e15"):
        raise ValueError(f"{field} 超出合理金额范围")
    return {"value": value, "unit": unit, "basis": basis, **_source(raw, field)}


def _metrics(raw, field, issues):
    if not isinstance(raw, dict):
        issues.append(f"{field} 必须为指标对象")
        return {}
    result = {}
    for key, value in raw.items():
        try:
            if key not in METRIC_SCHEMA:
                raise ValueError(f"{field} 含未知指标 {key}")
            result[key] = _metric(value, key, f"{field}.{key}")
        except (ValueError, TypeError, OverflowError) as exc:
            issues.append(str(exc))
    return result


def _reports(rows, scope, as_of, field, issues):
    if not isinstance(rows, list) or len(rows) > 24:
        issues.append(f"{field} 必须为最多24条报告的数组")
        return []
    result, seen, conflicts = [], set(), set()
    for index, row in enumerate(rows):
        item = f"{field}[{index}]"
        try:
            if not isinstance(row, dict):
                raise TypeError(f"{item} 必须为对象")
            end, published = _period(row, item, as_of)
            kind = row.get("period_type")
            ends = {
                "annual": ((12, 31),),
                "interim": ((6, 30),),
                "quarter": ((3, 31), (9, 30), (12, 31)),
            }
            if (
                not isinstance(kind, str)
                or kind not in ends
                or (end.month, end.day) not in ends[kind]
            ):
                raise ValueError(f"{item} 报告类型/期末不匹配")
            if row.get("scope") != scope:
                raise ValueError(f"{item}.scope 应为 {scope}，不得混用集团/法人")
            if end in seen:
                issues.append(f"{item} 报告期重复/冲突")
                conflicts.add(end.isoformat())
            seen.add(end)
            result.append(
                {
                    "period_end": end.isoformat(),
                    "published_at": published.isoformat(),
                    "period_type": kind,
                    "scope": scope,
                    "comparability_id": row.get("comparability_id"),
                    "metrics": _metrics(row.get("metrics"), f"{item}.metrics", issues),
                }
            )
        except (ValueError, TypeError, OverflowError) as exc:
            issues.append(str(exc))
    # Neither ordering nor last-write wins can establish which conflicting
    # observation is true. Preserve unrelated periods, exclude every duplicate
    # period from trusted derived checks; the issue still blocks grading.
    return sorted(
        (row for row in result if row["period_end"] not in conflicts),
        key=lambda row: row["period_end"],
    )


def _annual_window(reports, as_of, required, field, issues, *, comparable=False):
    annuals = {int(row["period_end"][:4]): row for row in reports if row["period_type"] == "annual"}
    anchor = as_of.year - 1
    if as_of.month < 5 and anchor not in annuals:
        anchor -= 1
    selected = []
    for year in range(anchor - 2, anchor + 1):
        row = annuals.get(year)
        if row is None:
            issues.append(f"{field} 缺少最近连续年度 {year}，不得回退旧窗口")
            continue
        selected.append(row)
        for key in required:
            if key not in row["metrics"]:
                issues.append(f"{field} {year} 缺少核心指标 {key}")
    if comparable and selected:
        ids = [row.get("comparability_id") for row in selected]
        if any(
            not isinstance(value, str) or not value.strip() or len(value) > 200 for value in ids
        ) or any(value != ids[0] for value in ids):
            issues.append(f"{field} comparability_id 缺失或不一致，不能跨会计/精算假设比较")
            return selected, False
    return selected, True


def _assessment(raw, period, as_of, field, issues):
    try:
        if not isinstance(raw, dict):
            raise TypeError(f"{field} 缺少有来源的评估")
        end, published = _period(raw, field, as_of)
        if not period or end.isoformat() != period:
            raise ValueError(f"{field} 评估期与最新快照不一致")
        status = raw.get("status")
        if status not in ("supported", "adverse", "unknown"):
            raise ValueError(f"{field}.status 应为 supported/adverse/unknown")
        result = {
            "status": status,
            "statement": _text(raw.get("statement"), f"{field}.statement", 1600),
            "period_end": end.isoformat(),
            "published_at": published.isoformat(),
            **_source(raw, field),
        }
        if status == "unknown":
            issues.append(f"{field} 核心评估仍为 unknown，不能据此评分")
        return result
    except (ValueError, TypeError, OverflowError) as exc:
        issues.append(str(exc))
        return None


def _entity(raw, index, latest_period, as_of, issues):
    field = f"entities[{index}]"
    if not isinstance(raw, dict):
        issues.append(f"{field} 必须为法人对象")
        return None
    try:
        id_ = _text(raw.get("id"), f"{field}.id", 80)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", id_):
            raise ValueError(f"{field}.id 仅支持字母数字下划线连字符")
        name = _text(raw.get("name"), f"{field}.name", 200)
        kind = raw.get("kind")
        if kind not in ("life", "property") or raw.get("scope") != "solo":
            raise ValueError(f"{field} 必须是 scope=solo 的 life/property 法人")
    except (ValueError, TypeError) as exc:
        issues.append(str(exc))
        return None
    result = {
        "id": id_,
        "name": name,
        "kind": kind,
        "scope": "solo",
        "latest": None,
        "risk_rating": None,
        "annuals": [],
        "assessments": {},
        "comparable": False,
        "value_metric": raw.get("value_metric"),
    }
    try:
        latest = raw.get("latest")
        if not isinstance(latest, dict):
            raise TypeError(f"{field}.latest 缺少偿付能力快照")
        end, published = _period(latest, f"{field}.latest", as_of)
        if end.isoformat() != latest_period:
            raise ValueError(f"{field}.latest 与集团最新快照期间不一致")
        metrics = _metrics(latest.get("metrics"), f"{field}.latest.metrics", issues)
        for key in ("core_solvency", "comprehensive_solvency"):
            if key not in metrics:
                issues.append(f"{field}.latest 缺少 {key}")
        if (
            all(key in metrics for key in ("core_solvency", "comprehensive_solvency"))
            and metrics["core_solvency"]["value"] > metrics["comprehensive_solvency"]["value"]
        ):
            issues.append(f"{field} 核心偿付能力高于综合偿付能力，口径冲突")
            metrics = {
                key: value
                for key, value in metrics.items()
                if key not in ("core_solvency", "comprehensive_solvency")
            }
        result["latest"] = {
            "period_end": end.isoformat(),
            "published_at": published.isoformat(),
            "metrics": metrics,
        }
    except (ValueError, TypeError, OverflowError) as exc:
        issues.append(str(exc))
    try:
        rating = raw.get("risk_rating")
        if not isinstance(rating, dict):
            raise TypeError(f"{field}.risk_rating 缺少风险综合评级")
        end, published = _period(rating, f"{field}.risk_rating", as_of)
        snapshot = date.fromisoformat(latest_period) if result["latest"] else None
        if snapshot is None or not 0 <= (snapshot - end).days <= 183:
            raise ValueError(f"{field}.risk_rating 期末晚于快照或滞后超过183天")
        value = rating.get("value")
        if value not in RATINGS:
            raise ValueError(
                f"{field}.risk_rating 必须为风险综合A/B/C/D及细分类，不能用监管1-5级或星级"
            )
        result["risk_rating"] = {
            "value": value,
            "period_end": end.isoformat(),
            "published_at": published.isoformat(),
            **_source(rating, f"{field}.risk_rating"),
        }
    except (ValueError, TypeError, OverflowError) as exc:
        issues.append(str(exc))
    reports = _reports(raw.get("annuals"), "solo", as_of, f"{field}.annuals", issues)
    value_metric = raw.get("value_metric")
    if kind == "life" and value_metric not in ("nbv", "new_business_csm"):
        issues.append(f"{field}.value_metric 必须为 nbv/new_business_csm")
        required = ("net_investment_yield",)
    else:
        required = ("net_investment_yield", value_metric) if kind == "life" else ("combined_ratio",)
    result["annuals"], result["comparable"] = _annual_window(
        reports, as_of, required, f"{field}.annuals", issues, comparable=True
    )
    assessments = raw.get("assessments")
    if not isinstance(assessments, dict):
        assessments = {}
    for key in ("asset_liability", "reserves"):
        result["assessments"][key] = _assessment(
            assessments.get(key),
            latest_period if result["latest"] else None,
            as_of,
            f"{field}.assessments.{key}",
            issues,
        )
    return result


def validate_insurance_data(stock, packet):
    """Return validated JSON-safe facts, with explicit core gaps and warnings."""
    result = {
        "status": "insufficient_data",
        "issues": [],
        "warnings": [],
        "insurance_type": None,
        "reports": [],
        "latest": None,
        "annuals": [],
        "entities": [],
        "coverage": None,
    }
    issues = result["issues"]
    try:
        fingerprint = stock_fingerprint(stock)
        if not isinstance(packet, dict):
            raise TypeError("缺少 insurance-data 证据包，E 未评分")
        if type(packet.get("schema_version")) is not int or packet["schema_version"] != 1:
            raise ValueError("insurance-data schema_version 必须为整数1")
        if (
            any(packet.get(key) != stock[key] for key in ("code", "name"))
            or packet.get("stock_sha256") != fingerprint
        ):
            raise ValueError("insurance-data 身份/原始输入哈希不一致")
        as_of = _date(packet.get("as_of"), "as_of")
        kind = packet.get("insurance_type")
        if kind not in TYPES:
            raise ValueError("insurance_type 必须为 life/property/group")
        result["insurance_type"] = kind
        result["reports"] = _reports(packet.get("reports"), "group", as_of, "reports", issues)
        result["annuals"], _ = _annual_window(result["reports"], as_of, ("roe",), "reports", issues)
        latest = result["latest"] = result["reports"][-1] if result["reports"] else None
        period = latest["period_end"] if latest else None
        if latest is None:
            issues.append("缺少上市主体最新财务快照")
        elif (as_of - date.fromisoformat(period)).days > 400:
            issues.append("最新保险快照超过400天，不得回填旧数据评级")
        if kind == "group" and (latest is None or "group_solvency_ratio" not in latest["metrics"]):
            issues.append("保险集团缺少 group_solvency_ratio，不能用子公司指标替代")
        raw_entities = packet.get("entities")
        if not isinstance(raw_entities, list) or not 1 <= len(raw_entities) <= 16:
            issues.append("entities 必须为1至16个重要保险法人的数组")
            raw_entities = []
        for index, raw in enumerate(raw_entities):
            member = _entity(raw, index, period, as_of, issues)
            if member is not None:
                result["entities"].append(member)
        ids = [member["id"] for member in result["entities"]]
        if len(set(ids)) != len(ids):
            issues.append("重要保险法人ID重复")
        kinds = {member["kind"] for member in result["entities"]}
        if kind == "group" and kinds != {"life", "property"}:
            issues.append("综合保险集团须覆盖重要寿险及产险法人")
        elif kind != "group" and kinds != {kind}:
            issues.append("单一险种上市主体与重要法人类型不一致")
        raw_coverage = packet.get("coverage")
        coverage = _assessment(raw_coverage, period, as_of, "coverage", issues)
        if coverage is not None:
            declared = raw_coverage.get("entity_ids")
            if (
                not isinstance(declared, list)
                or any(not isinstance(item, str) for item in declared)
                or len(declared) != len(set(declared))
                or set(declared) != set(ids)
            ):
                issues.append("coverage.entity_ids 与重要保险法人名单不一致/重复")
            coverage["entity_ids"] = ids
            coverage["other_segments"] = []
            segments = raw_coverage.get("other_segments")
            if not isinstance(segments, list) or len(segments) > 16:
                issues.append("coverage.other_segments 必须为最多16个重要非保险分部数组")
                segments = []
            seen = set()
            for index, raw in enumerate(segments):
                field = f"coverage.other_segments[{index}]"
                item = _assessment(raw, period, as_of, field, issues)
                if item is not None:
                    try:
                        name = _text(raw.get("name"), f"{field}.name", 200)
                        if name in seen or raw.get("kind") not in (
                            "bank",
                            "asset_management",
                            "other",
                        ):
                            raise ValueError(f"{field} 分部名称重复或类型无效")
                        seen.add(name)
                        coverage["other_segments"].append(
                            {**item, "name": name, "kind": raw["kind"]}
                        )
                    except (ValueError, TypeError) as exc:
                        issues.append(str(exc))
            result["coverage"] = coverage
        result["warnings"].append(
            "仅校验引用/单位/期间结构；重要法人覆盖、精算可比性、资产负债匹配和准备金事实仍须分析者核对原文"
        )
    except (ValueError, TypeError, OverflowError) as exc:
        issues.append(str(exc))
    result["status"] = "insufficient_data" if issues else "ready"
    return result
