"""Traceable bank evidence validation and deterministic research-quality scoring.

All metric values are percentages (15 means 15%). This is an explicitly
uncalibrated research heuristic, not a regulatory or credit rating. Source
references are validated structurally; the analyst verifies their contents.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

POLICY = "bank-research-v1"
CAPITAL_METRICS = ("cet1_ratio", "tier1_ratio", "total_capital_ratio")
SNAPSHOT_METRICS = ("npl_ratio", "provision_coverage", *CAPITAL_METRICS, "lcr", "nsfr")
ANNUAL_METRICS = ("roe", "roa", "npl_ratio")
OPTIONAL_METRICS = (
    "loan_provision_ratio",
    "special_mention_ratio",
    "overdue_90_ratio",
    "nim",
    "cost_income_ratio",
)
METRICS = frozenset((*ANNUAL_METRICS, *SNAPSHOT_METRICS, *OPTIONAL_METRICS))
PERIOD_METRICS = frozenset(("roe", "roa", "nim", "cost_income_ratio"))
REQUIREMENT_METRICS = frozenset((*CAPITAL_METRICS, "provision_coverage", "loan_provision_ratio"))


def stock_fingerprint(stock):
    """Hash the immutable original input, using canonical UTF-8 JSON."""
    if not isinstance(stock, dict):
        raise TypeError("stock 必须为 JSON 对象")
    for key in ("code", "name"):
        if not isinstance(stock.get(key), str) or not stock[key].strip():
            raise ValueError(f"stock.{key} 必须为非空字符串")
    return hashlib.sha256(
        json.dumps(
            stock, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def _date(value, field):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{field} 必须为 YYYY-MM-DD 日期")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} 日期无效") from None


def make_template(stock, as_of):
    _date(as_of, "as_of")
    fingerprint = stock_fingerprint(stock)
    return {
        "schema_version": 1,
        "code": stock.get("code"),
        "name": stock.get("name"),
        "stock_sha256": fingerprint,
        "as_of": as_of,
        "liquidity_regime": "lcr_nsfr",
        "reports": [],
        "requirements": {},
        "requirements_period_end": None,
        "requirements_published_at": None,
        "peers": [],
    }


def _metric(value, name, field, *, requirement=False):
    if not isinstance(value, dict):
        raise TypeError(f"{field} 必须为含 value/source_url/locator/basis 的对象")
    number = value.get("value")
    if type(number) not in (int, float) or (type(number) is float and not math.isfinite(number)):
        raise ValueError(f"{field}.value 必须为有限数字，不接受布尔值或数字字符串")
    numeric = Decimal(str(number))
    lower = Decimal(-1000) if name in ("roe", "roa", "nim") and not requirement else Decimal(0)
    upper = (
        Decimal(1000000)
        if name in ("provision_coverage", "lcr", "nsfr")
        else Decimal(1000 if name == "roe" else 100)
    )
    if numeric < lower or numeric > upper:
        raise ValueError(f"{field}.value 超出百分数指标合理范围")
    source = value.get("source_url")
    try:
        url = urlsplit(source) if isinstance(source, str) else None
    except ValueError:
        url = None
    if not url or url.scheme not in ("http", "https") or not url.netloc or len(source) > 2048:
        raise ValueError(f"{field}.source_url 必须为 http(s) 来源 URL")
    locator = value.get("locator")
    if not isinstance(locator, str) or not locator.strip() or len(locator) > 500:
        raise ValueError(f"{field}.locator 必须为非空、有界的网页栏目/表格定位")
    expected = {"point_in_time"} if requirement or name not in PERIOD_METRICS else {"period"}
    if name == "lcr" and not requirement:
        expected.add("quarter_average")
    if value.get("basis") not in expected:
        raise ValueError(f"{field}.basis 应为 {sorted(expected)}")
    return {"value": number, "source_url": source, "locator": locator, "basis": value["basis"]}


def _metrics(values, field, *, requirement=False, issues=None):
    if not isinstance(values, dict):
        raise TypeError(f"{field} 必须为指标对象")
    accepted = REQUIREMENT_METRICS if requirement else METRICS
    unknown = set(values) - accepted
    if unknown:
        error = f"{field} 有未知指标 {sorted(unknown)}"
        if issues is None:
            raise ValueError(error)
        issues.append(error)
    result = {}
    for key, value in values.items():
        if key not in accepted:
            continue
        try:
            result[key] = _metric(value, key, f"{field}.{key}", requirement=requirement)
        except (ValueError, TypeError) as exc:
            if issues is None:
                raise
            issues.append(str(exc))
    return result


def _report(row, index, as_of, issues):
    field = f"reports[{index}]"
    if not isinstance(row, dict):
        raise TypeError(f"{field} 必须为对象")
    end, published = (
        _date(row.get(key), f"{field}.{key}") for key in ("period_end", "published_at")
    )
    if end >= published or published > as_of:
        raise ValueError(f"{field} 报告期必须早于披露日，披露日不得晚于 as_of")
    kind = row.get("period_type")
    allowed_ends = {
        "annual": {(12, 31)},
        "interim": {(6, 30)},
        "quarter": {(3, 31), (9, 30), (12, 31)},
    }
    if kind not in allowed_ends or (end.month, end.day) not in allowed_ends[kind]:
        raise ValueError(f"{field} period_type 与报告期不匹配")
    if row.get("scope") != "group":
        raise ValueError(f"{field}.scope 必须为 group，不能混用集团/母行")
    return {
        "period_end": end.isoformat(),
        "published_at": published.isoformat(),
        "period_type": kind,
        "scope": "group",
        "metrics": _metrics(row.get("metrics"), f"{field}.metrics", issues=issues),
    }


def _values(metrics):
    return {key: Decimal(str(row["value"])) for key, row in metrics.items()}


def _check_ratios(report, issues):
    values = _values(report["metrics"])
    if all(key in values for key in CAPITAL_METRICS) and not (
        values["cet1_ratio"] <= values["tier1_ratio"] <= values["total_capital_ratio"]
    ):
        issues.append(f"{report['period_end']} 三项资本充足率次序冲突")
    if all(key in values for key in ("npl_ratio", "provision_coverage", "loan_provision_ratio")):
        expected = values["npl_ratio"] * values["provision_coverage"] / 100
        if abs(expected - values["loan_provision_ratio"]) > Decimal("0.1"):
            issues.append(
                f"{report['period_end']} loan_provision_ratio 与不良率×覆盖率存在重大口径冲突"
            )


def _peers(packet, latest, as_of, warnings):
    peers = packet.get("peers", [])
    if not isinstance(peers, list) or len(peers) > 100:
        warnings.append("peers 无效或超过 100 家，忽略同业比较")
        return []
    result, seen = [], set()
    for index, row in enumerate(peers):
        try:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("code"), str)
                or not row["code"].strip()
            ):
                raise ValueError("缺少同业代码")
            if row["code"] in seen or row["code"] == packet["code"]:
                raise ValueError("同业重复或是自身")
            if (
                not isinstance(packet.get("peer_group"), str)
                or not packet["peer_group"].strip()
                or row.get("peer_group") != packet["peer_group"]
            ):
                raise ValueError("同组标签不一致")
            if (
                row.get("scope") != "group"
                or not latest
                or row.get("period_end") != latest["period_end"]
            ):
                raise ValueError("同业期间/集团口径不一致")
            published = _date(row.get("published_at"), "peer.published_at")
            if not _date(row["period_end"], "peer.period_end") < published <= as_of:
                raise ValueError("同业披露日不在可用范围")
            metrics = _metrics(row.get("metrics"), "peer.metrics")
            if not metrics:
                raise ValueError("同业指标为空")
            seen.add(row["code"])
            result.append({**row, "metrics": metrics})
        except (ValueError, TypeError) as exc:
            warnings.append(f"peer[{index}] 忽略：{exc}")
    return result


def validate_bank_data(stock, packet):
    """Return JSON-safe validated evidence and issues; never mutate either input."""
    result = {
        "status": "insufficient_data",
        "issues": [],
        "warnings": [],
        "reports": [],
        "latest": None,
        "annuals": [],
        "requirements": {},
        "requirements_applicable": False,
        "liquidity_applicable": False,
        "peers": [],
    }
    issues, warnings = result["issues"], result["warnings"]
    try:
        fingerprint = stock_fingerprint(stock)
        if not isinstance(packet, dict):
            raise TypeError("缺少银行 bank-data 证据包，E 未评分")
        if type(packet.get("schema_version")) is not int or packet["schema_version"] != 1:
            raise ValueError("bank-data schema_version 必须为整数 1")
        for field in ("code", "name"):
            if packet.get(field) != stock[field]:
                raise ValueError(f"bank-data.{field} 与原始股票输入不一致")
        if packet.get("stock_sha256") != fingerprint:
            raise ValueError("bank-data.stock_sha256 与原始股票输入不一致")
        as_of = _date(packet.get("as_of"), "as_of")
        result["liquidity_applicable"] = packet.get("liquidity_regime") == "lcr_nsfr"
        if not result["liquidity_applicable"]:
            issues.append("liquidity_regime 不支持：目前仅支持 LCR/NSFR 口径；不得用代理指标补分")
        rows = packet.get("reports")
        if not isinstance(rows, list) or len(rows) > 24:
            raise ValueError("reports 必须为最多 24 个报告的数组")
        seen = set()
        for index, row in enumerate(rows):
            try:
                report = _report(row, index, as_of, issues)
                if report["period_end"] in seen:
                    issues.append(f"reports 报告期重复/冲突：{report['period_end']}")
                seen.add(report["period_end"])
                result["reports"].append(report)
                _check_ratios(report, issues)
            except (ValueError, TypeError) as exc:
                issues.append(str(exc))
        result["reports"].sort(key=lambda row: row["period_end"])
        if result["reports"]:
            latest = result["latest"] = result["reports"][-1]
            if (as_of - date.fromisoformat(latest["period_end"])).days > 400:
                issues.append("最新银行快照已超过 400 天，不能回填旧数据评级")
            for key in SNAPSHOT_METRICS:
                if key not in latest["metrics"]:
                    issues.append(f"最新快照缺少核心指标 {key}")
            try:
                declared = _date(packet.get("requirements_period_end"), "requirements_period_end")
                published = _date(
                    packet.get("requirements_published_at"), "requirements_published_at"
                )
                if declared.isoformat() != latest["period_end"]:
                    raise ValueError("requirements_period_end 与最新快照不一致")
                if published > as_of:
                    raise ValueError("requirements_published_at 晚于 as_of，适用要求尚不可得")
                result["requirements_applicable"] = True
            except ValueError as exc:
                issues.append(str(exc))
        else:
            issues.append("reports 缺少可用银行快照")
        annuals = {
            int(row["period_end"][:4]): row
            for row in result["reports"]
            if row["period_type"] == "annual"
        }
        anchor = as_of.year - 1
        if as_of.month < 5 and anchor not in annuals:
            anchor -= 1
        for year in range(anchor - 2, anchor + 1):
            annual = annuals.get(year)
            if annual is None:
                issues.append(f"缺少最近三年连续年度 {year}，不得回退旧窗口")
                continue
            result["annuals"].append(annual)
            for key in ANNUAL_METRICS:
                if key not in annual["metrics"]:
                    issues.append(f"年度 {year} 缺少核心指标 {key}")
        try:
            result["requirements"] = _metrics(
                packet.get("requirements"), "requirements", requirement=True, issues=issues
            )
        except (ValueError, TypeError) as exc:
            issues.append(str(exc))
        for key in CAPITAL_METRICS:
            if key not in result["requirements"]:
                issues.append(f"缺少该银行完整适用资本要求 requirements.{key}")
            elif result["requirements"][key]["value"] <= 0:
                issues.append(f"requirements.{key} 不得为零或负值")
        if all(key in result["requirements"] for key in CAPITAL_METRICS):
            values = _values(result["requirements"])
            if not values["cet1_ratio"] <= values["tier1_ratio"] <= values["total_capital_ratio"]:
                issues.append("三项适用资本要求次序冲突")
        result["peers"] = _peers(packet, result["latest"], as_of, warnings)
        if not result["peers"]:
            warnings.append("缺少可用同组同期间 peer 数据，未作同业排名；不因此自动扣分")
        warnings.append(
            "来源仅通过引用结构校验；原文、完整适用监管要求、集团口径与单位仍需分析者确认"
        )
    except (ValueError, TypeError, OverflowError) as exc:
        issues.append(str(exc))
    result["status"] = "insufficient_data" if issues else "ready"
    return result


def _above(value, thresholds):
    return next(
        (
            score
            for threshold, score in zip(thresholds, (5, 4, 3, 2))
            if value >= Decimal(str(threshold))
        ),
        1,
    )


def _below(value, thresholds):
    return next(
        (
            score
            for threshold, score in zip(thresholds, (5, 4, 3, 2))
            if value <= Decimal(str(threshold))
        ),
        1,
    )


def score_bank(stock, packet):
    validated = validate_bank_data(stock, packet)
    checks, risks, caps = [], [], []
    warnings = [
        "bank-research-v1 为尚未经实证校准的研究分档，不是监管评级或信用评级",
        *validated["warnings"],
    ]

    def check(rule, values, period, cap, reason):
        checks.append(
            {
                "rule": rule,
                "input": values,
                "period": period,
                "result": cap,
                "cap": cap,
                "reason": reason,
            }
        )
        if cap is not None:
            caps.append(cap)

    annuals = validated["annuals"]
    latest = validated["latest"]
    annual_values = [_values(row["metrics"]) for row in annuals]
    if len(annual_values) == 3 and all(
        all(key in row for key in ANNUAL_METRICS) for row in annual_values
    ):
        roe = sum(row["roe"] for row in annual_values) / 3
        roa = sum(row["roa"] for row in annual_values) / 3
        profit = min(_above(roe, (15, 12, 8, 5)), _above(roa, (1, 0.8, 0.5, 0.25)))
        check(
            "bank_profitability",
            {"roe_avg_3y": float(roe), "roa_avg_3y": float(roa)},
            [row["period_end"] for row in annuals],
            profit,
            "三年 ROE/ROA 较弱项定基础分；研究阈值，不以高杠杆替代盈利能力",
        )
        if profit <= 2:
            risks.append("银行三年盈利能力偏弱，已触发财务质量低分档")
        npl_rise = annual_values[-1]["npl_ratio"] - annual_values[-2]["npl_ratio"]
        trend_cap = 2 if npl_rise >= Decimal(".5") else 3 if npl_rise >= Decimal(".2") else 5
        roe_declines = annual_values[0]["roe"] > annual_values[1]["roe"] > annual_values[2]["roe"]
        if roe_declines:
            trend_cap = min(trend_cap, 4)
            risks.append("最近三年银行 ROE 连续两次下降，需结合息差与拨备解释")
        if npl_rise >= Decimal(".2"):
            risks.append(f"最近年度不良贷款率上升 {npl_rise} 个百分点")
        check(
            "bank_annual_trend",
            {"npl_change_pp": float(npl_rise), "roe_two_declines": roe_declines},
            [row["period_end"] for row in annuals],
            trend_cap,
            "不良率按百分点看变化；连续 ROE 下降仅封顶4，不套普通企业季度利润重罚",
        )
    if latest:
        metrics, period = latest["metrics"], latest["period_end"]
        values, required = _values(metrics), _values(validated["requirements"])
        for name, label, function, bands in (
            ("npl_ratio", "不良贷款率", _below, (1, 1.5, 2, 3)),
            ("provision_coverage", "拨备覆盖率", _above, (300, 200, 150, 120)),
        ):
            if name in values:
                cap = function(values[name], bands)
                check(
                    f"bank_{name}",
                    {name: metrics[name]},
                    period,
                    cap,
                    f"{label}质量分档，不代表监管合规结论",
                )
                if cap <= 2:
                    risks.append(f"{label}处于研究质量弱档")
        capital_breach = validated["requirements_applicable"] and any(
            values[key] < required[key]
            for key in CAPITAL_METRICS
            if key in values and key in required
        )
        if capital_breach:
            risks.append("至少一项资本充足率低于证据包提供的完整适用资本要求")
        if validated["requirements_applicable"] and all(
            key in values and key in required for key in CAPITAL_METRICS
        ):
            surpluses = {key: values[key] - required[key] for key in CAPITAL_METRICS}
            cap = _above(min(surpluses.values()), (3, 2, 1, 0))
            check(
                "bank_capital_buffer",
                {
                    "surplus_pp": {key: float(value) for key, value in surpluses.items()},
                    "actual": {key: metrics[key] for key in CAPITAL_METRICS},
                    "requirements": validated["requirements"],
                },
                period,
                cap,
                "按三项资本相对该银行完整适用要求的最小余量，单位百分点",
            )
            if not capital_breach and cap <= 2:
                risks.append("银行资本余量较薄")
        elif not validated["requirements_applicable"]:
            check(
                "bank_capital_buffer",
                {
                    "actual": {key: metrics[key] for key in CAPITAL_METRICS if key in metrics},
                    "unconfirmed_requirements": validated["requirements"],
                },
                period,
                None,
                "适用要求的期间或披露日期未确认；仅保留数值，不计算余量或判断达标",
            )
        liquidity_breach = validated["liquidity_applicable"] and any(
            values[key] < 100 for key in ("lcr", "nsfr") if key in values
        )
        if liquidity_breach:
            risks.append("LCR 或 NSFR 低于适用制度的100%监管底线")
        if validated["liquidity_applicable"] and all(key in values for key in ("lcr", "nsfr")):
            cap = _above(min(values["lcr"], values["nsfr"]), (130, 120, 110, 100))
            check(
                "bank_liquidity",
                {key: metrics[key] for key in ("lcr", "nsfr")},
                period,
                cap,
                "仅适用于 LCR/NSFR 制度；两项较弱值决定流动性质量分档",
            )
            if not liquidity_breach and cap <= 2:
                risks.append("银行流动性指标距离底线较近")
        elif not validated["liquidity_applicable"]:
            check(
                "bank_liquidity",
                {key: metrics[key] for key in ("lcr", "nsfr") if key in metrics},
                period,
                None,
                "流动性制度不受支持；仅保留数值，不套用 LCR/NSFR 评分或监管底线",
            )
        for name in ("provision_coverage", "loan_provision_ratio"):
            if validated["requirements_applicable"] and name in required and name in values:
                breach = values[name] < required[name]
                check(
                    f"bank_regulatory_{name}",
                    {"actual": metrics[name], "requirement": validated["requirements"][name]},
                    period,
                    1 if breach else 5,
                    "仅在有该银行明确适用拨备要求时判断是否低于要求",
                )
                if breach:
                    risks.append(f"{name} 低于适用拨备监管要求")
        if (
            "overdue_90_ratio" in values
            and "npl_ratio" in values
            and values["overdue_90_ratio"] > values["npl_ratio"]
        ):
            risks.append(
                "逾期90天以上贷款比例高于不良率，需核查分类范围与时点，不能仅凭低不良率认定安全"
            )
        for name in OPTIONAL_METRICS:
            if name in metrics:
                check(
                    f"bank_auxiliary_{name}",
                    {name: metrics[name]},
                    period,
                    None,
                    "辅助事实不单独加分；缺失不自动扣分",
                )
        comparisons = []
        for peer in validated["peers"]:
            common = set(metrics) & set(peer["metrics"])
            comparisons.append(
                {
                    "code": peer["code"],
                    "differences_pp": {
                        key: float(values[key] - Decimal(str(peer["metrics"][key]["value"])))
                        for key in sorted(common)
                        if metrics[key]["basis"] == peer["metrics"][key]["basis"]
                    },
                }
            )
        if comparisons:
            check(
                "peer_comparison",
                comparisons,
                period,
                None,
                "同组同期间同口径的指标差值，仅供解释；不是代表性行业排名，不直接改变分数",
            )
    score = min(caps) if caps and not validated["issues"] else None
    return {
        "score": score,
        "status": "scored" if score is not None else "insufficient_data",
        "sector": "bank",
        "checks": checks,
        "issues": validated["issues"],
        "risks": risks,
        "policy": POLICY,
        "warnings": warnings,
    }


def _read(path):
    def reject(value):
        raise ValueError(f"JSON 不允许 {value}")

    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=reject)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    template = commands.add_parser("template")
    template.add_argument("--stock", required=True)
    template.add_argument("--as-of", required=True)
    validate = commands.add_parser("validate")
    validate.add_argument("--stock", required=True)
    validate.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    try:
        stock = _read(args.stock)
        result = (
            make_template(stock, args.as_of)
            if args.command == "template"
            else validate_bank_data(stock, _read(args.input))
        )
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 2 if result.get("status") == "insufficient_data" else 0
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        print(f"bank_financial: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
