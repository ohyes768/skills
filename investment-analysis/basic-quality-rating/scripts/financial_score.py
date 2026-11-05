"""Deterministic financial-quality scoring from the original v3 stock payload."""

from __future__ import annotations

import math
import re
from decimal import Decimal

ORDINARY_INDUSTRIES = frozenset(
    [
        "农林牧渔",
        "基础化工",
        "化工",
        "钢铁",
        "有色金属",
        "电子",
        "家用电器",
        "食品饮料",
        "纺织服饰",
        "纺织服装",
        "轻工制造",
        "医药生物",
        "房地产",
        "商贸零售",
        "商业贸易",
        "社会服务",
        "休闲服务",
        "综合",
        "建筑材料",
        "建筑装饰",
        "电力设备",
        "电气设备",
        "国防军工",
        "计算机",
        "传媒",
        "通信",
        "煤炭",
        "石油石化",
        "环保",
        "美容护理",
        "汽车",
        "机械设备",
        "采掘",
    ]
)
BANK_SUBINDUSTRIES = frozenset(
    ("国有大型银行", "股份制银行", "城商行", "农商行", "其他银行", "商业银行")
)
NONBANK_SUBINDUSTRIES = frozenset(("证券", "多元金融", "金融控股", "资产管理", "信托"))
UTILITY_SUBINDUSTRIES = frozenset(("电力", "燃气", "铁路公路", "航空机场", "航运港口", "物流"))
FINANCIAL_ISSUES = {
    "nonbank_financial": "非银金融输入缺少适用的监管资本、杠杆与资产质量指标，E 未评分",
}


def _industry_name(value):
    if not isinstance(value, str):
        return None
    return re.sub(r"(?:Ⅲ|Ⅱ|III|II)$", "", value.strip())


def _sector(stock, issues):
    first, second = (_industry_name(stock.get(key)) for key in ("sw_level1", "sw_level2"))
    if first == "银行":
        primary = "bank"
    elif first == "非银金融":
        primary = "nonbank_financial"
    elif first in ("公用事业", "交通运输"):
        primary = "utility_transport"
    elif first in ORDINARY_INDUSTRIES:
        primary = "ordinary"
    else:
        primary = None
    if second in BANK_SUBINDUSTRIES or second == "银行":
        secondary = "bank"
    elif second == "保险":
        secondary = "insurance"
    elif second in NONBANK_SUBINDUSTRIES:
        secondary = "nonbank_financial"
    elif second in UTILITY_SUBINDUSTRIES:
        secondary = "utility_transport"
    else:
        secondary = None
    if primary == "nonbank_financial" and secondary == "insurance":
        return secondary
    if primary and secondary and primary != secondary:
        issues.append("sw_level1/sw_level2 行业分类冲突，无法选择财务评分口径")
        return None
    result = primary or secondary
    if result is None:
        issues.append("sw_level1/sw_level2 缺失或不在支持的申万行业分类中，E 未评分")
    return result


def _number(stock, field, issues):
    value = stock.get(field)
    if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
        issues.append(f"{field} 缺失或不是有限数字（不接受布尔值或数字字符串）")
        return None
    return Decimal(str(value))


def _year(value):
    if type(value) is int and 1900 <= value <= 9999:
        return value
    if isinstance(value, str) and re.fullmatch(r"(?:19|[2-9]\d)\d{2}", value.strip()):
        return int(value)
    return None


def _quarter(label):
    if not isinstance(label, str) or re.search(r"累计|年初|至今|YTD|H[12]", label, re.IGNORECASE):
        return None
    text = re.sub(r"\s+", "", label)
    explicit_single = "单季" in text
    text = text.replace("（单季）", "").replace("(单季)", "").replace("单季", "")
    match = re.fullmatch(r"(\d{4})[Qq]([1-4])", text)
    if match:
        return (_year(match[1]), int(match[2])) if _year(match[1]) else None
    match = re.fullmatch(r"(\d{4})年?第?([1-4一二三四])季度", text)
    if match:
        quarter = "一二三四".find(match[2]) + 1 if not match[2].isdigit() else int(match[2])
        return (_year(match[1]), quarter) if _year(match[1]) else None
    match = re.fullmatch(r"(\d{4})年?(一季报|半年报|三季报|年报)", text)
    if match and (match[2] == "一季报" or explicit_single):
        quarter = {"一季报": 1, "半年报": 2, "三季报": 3, "年报": 4}[match[2]]
        return (_year(match[1]), quarter) if _year(match[1]) else None
    return None


def _history(stock, anchor, issues):
    rows = stock.get("roe_history")
    if not isinstance(rows, list) or anchor is None:
        issues.append("roe_history 缺失或无法按 roe_year 定位最近三年")
        return None
    window = set(range(anchor - 2, anchor + 1))
    by_year = {}
    invalid = False
    for row in rows:
        if not isinstance(row, dict) or _year(row.get("year")) is None:
            issues.append("roe_history 存在无效年份或条目，无法确认最近窗口")
            invalid = True
            continue
        year = _year(row["year"])
        if year > anchor:
            issues.append("roe_history 存在晚于 roe_year 的年份，最近年度口径冲突")
            invalid = True
        if year not in window:
            continue
        value = row.get("value")
        if type(value) not in (int, float) or (type(value) is float and not math.isfinite(value)):
            # Null values carry no observation; a separately supplied valid value
            # for the same year is still usable, consistent with ignoring nulls.
            if value is not None:
                issues.append(f"roe_history {year} 的 ROE 不是有限数字")
                invalid = True
            continue
        value = Decimal(str(value))
        if year in by_year and by_year[year] != value:
            issues.append(f"roe_history {year} 同年数值冲突")
            invalid = True
        by_year[year] = value
    missing = sorted(window - set(by_year))
    if missing:
        issues.append(f"roe_history 最近三年不连续或有缺口：{missing}，不得回退旧窗口")
    return None if invalid or missing else [by_year[year] for year in sorted(window)]


def score_financial(stock: dict, bank_data=None, insurance_data=None) -> dict:
    """Return a score or explicit ungraded state plus an auditable rule trace.

    Values are percentages in the caller's original units. This function never
    fetches, imputes or replaces financial values and never mutates the payload.
    """
    if not isinstance(stock, dict):
        raise TypeError("stock 必须为原始股票 JSON 对象")
    issues, risks, checks = [], [], []
    sector = _sector(stock, issues)
    if bank_data is not None and insurance_data is not None:
        raise ValueError("bank_data 与 insurance_data 不能同时提供")
    if bank_data is not None and sector != "bank":
        raise ValueError("bank_data 仅用于行业已确认为银行的原始输入")
    if insurance_data is not None and sector != "insurance":
        raise ValueError("insurance_data 仅用于行业已确认为保险的原始输入")
    if sector == "insurance":
        from insurance_financial import score_insurance

        return score_insurance(stock, insurance_data)
    if sector == "bank":
        from bank_financial import score_bank

        return score_bank(stock, bank_data)
    if sector in FINANCIAL_ISSUES:
        return {
            "score": None,
            "status": "not_applicable",
            "sector": sector,
            "checks": [
                {
                    "rule": "sector",
                    "input": {key: stock.get(key) for key in ("sw_level1", "sw_level2")},
                    "period": None,
                    "result": "不适用普通企业评分",
                    "cap": None,
                    "reason": FINANCIAL_ISSUES[sector],
                }
            ],
            "issues": [FINANCIAL_ISSUES[sector]],
            "risks": [],
        }

    values = {
        key: _number(stock, key, issues)
        for key in (
            "roe_avg_3y",
            "debt_asset_ratio",
            "net_profit_ex_non_recurring_yoy",
            "previous_quarter_yoy_pct",
            "latest_quarter_yoy_pct",
        )
    }
    annual_year, roe_year = (_year(stock.get(key)) for key in ("annual_profit_year", "roe_year"))
    for key, value in (("annual_profit_year", annual_year), ("roe_year", roe_year)):
        if value is None:
            issues.append(f"{key} 缺失或年份无效")
    if annual_year and roe_year and annual_year != roe_year:
        issues.append("annual_profit_year 与 roe_year 不一致，年度评分口径无法对齐")
    previous = _quarter(stock.get("previous_quarter_label"))
    latest = _quarter(stock.get("latest_quarter_label"))
    for key, value in (
        ("previous_quarter_label", previous),
        ("latest_quarter_label", latest),
    ):
        if value is None:
            issues.append(f"{key} 缺失或不是明确单季报告期；累计口径不能替代单季")
    adjacent_quarters = bool(
        previous and latest and latest[0] * 4 + latest[1] == previous[0] * 4 + previous[1] + 1
    )
    if previous and latest and not adjacent_quarters:
        issues.append("previous_quarter_label/latest_quarter_label 不是相邻两季")
    history = _history(stock, roe_year, issues)

    def check(rule, input_fields, period, result, cap, reason):
        checks.append(
            {
                "rule": rule,
                "input": input_fields,
                "period": period,
                "result": result,
                "cap": cap,
                "reason": reason,
            }
        )

    avg = values["roe_avg_3y"]
    base = (
        next(
            (score for threshold, score in ((15, 5), (12, 4), (8, 3), (5, 2)) if avg >= threshold),
            1,
        )
        if avg is not None
        else None
    )
    check(
        "roe_base",
        {"roe_avg_3y": stock.get("roe_avg_3y")},
        {"start_year": roe_year - 2, "end_year": roe_year} if roe_year else None,
        base,
        base,
        "按三年平均 ROE 阈值确定基础分" if base else "缺少有效三年平均 ROE",
    )
    if base is not None and base <= 2:
        risks.append("三年平均 ROE 偏低，已触发财务质量弱项")

    debt = values["debt_asset_ratio"]
    thresholds = (55, 70, 80) if sector == "utility_transport" else (40, 60, 75)
    debt_grade = (
        next(
            (
                grade
                for threshold, grade in zip(thresholds, ("优", "良", "中"))
                if debt <= threshold
            ),
            "差",
        )
        if debt is not None and sector
        else None
    )
    debt_cap = {"优": 5, "良": 4, "中": 4, "差": 2}.get(debt_grade)
    check(
        "debt",
        {"debt_asset_ratio": stock.get("debt_asset_ratio")},
        "调用方未提供独立负债率报告期",
        debt_grade,
        debt_cap,
        f"行业 {sector}，阈值 {thresholds}" if debt_grade else "负债率或适用行业无法确认",
    )
    if debt_grade == "差":
        risks.append("负债率达到适用行业的差档，财务质量上限为 2")

    profit_fields = (
        "net_profit_ex_non_recurring_yoy",
        "previous_quarter_yoy_pct",
        "latest_quarter_yoy_pct",
    )
    annual, prev_profit, last_profit = (values[key] for key in profit_fields)
    profit_grade = None
    annual_period_valid = annual_year is not None and annual_year == roe_year
    if (
        annual_period_valid
        and adjacent_quarters
        and all(value is not None for value in (annual, prev_profit, last_profit))
    ):
        profit_grade = (
            "弱"
            if prev_profit < 0 and last_profit < 0
            else "中"
            if prev_profit < 0 or last_profit < 0
            else "优"
            if annual > 0 and prev_profit > 0 and last_profit > 0
            else "良"
        )
    profit_cap = {"优": 5, "良": 4, "中": 3, "弱": 2}.get(profit_grade)
    check(
        "earnings",
        {key: stock.get(key) for key in profit_fields},
        {
            "annual": annual_year,
            "previous_quarter": stock.get("previous_quarter_label"),
            "latest_quarter": stock.get("latest_quarter_label"),
        },
        profit_grade,
        profit_cap,
        "按年度和相邻两季扣非同比符号分档" if profit_grade else "盈利数值或报告期间不足，未分档",
    )
    consecutive_decline = bool(
        adjacent_quarters
        and prev_profit is not None
        and last_profit is not None
        and prev_profit < 0
        and last_profit < 0
    )
    if consecutive_decline:
        risks.append("已知连续两季单季扣非同比为负，属于盈利弱项")
    else:
        for field, value, period in (
            ("previous_quarter_yoy_pct", prev_profit, previous),
            ("latest_quarter_yoy_pct", last_profit, latest),
        ):
            if value is not None and value < 0:
                period_note = (
                    f"对应 {period[0]}Q{period[1]} 单季" if period else "报告期或单季口径未确认"
                )
                risks.append(f"输入 {field} 为负（{period_note}），不据此推断连续下滑")

    trend, trend_cap = None, None
    if history is not None:
        trend = (
            "连续两次下降"
            if history[0] > history[1] > history[2]
            else "最近一年下降"
            if history[1] > history[2]
            else "无下滑扣分"
        )
        trend_cap = {"连续两次下降": 2, "最近一年下降": 4, "无下滑扣分": 5}[trend]
    check(
        "roe_trend",
        {"roe_history": stock.get("roe_history")},
        {"start_year": roe_year - 2, "end_year": roe_year} if roe_year else None,
        trend,
        trend_cap,
        "仅检查最近三年连续窗口" if trend else "最近 ROE 历史窗口不可用",
    )
    if trend == "连续两次下降":
        risks.append("最近三年 ROE 连续两次下降，属于趋势弱项")

    weak = {
        "roe": base is not None and base <= 2,
        "debt": debt_grade == "差",
        "earnings": consecutive_decline,
        "roe_trend": trend == "连续两次下降",
    }
    weak_count = sum(weak.values())
    severity_cap = 1 if (base == 1 or weak_count >= 2) else 5
    check(
        "severe_weaknesses",
        weak,
        None,
        weak_count,
        severity_cap,
        "基础 ROE <5 或至少两类严重弱项时最终为 1；缺失不计弱项",
    )
    if weak_count >= 2:
        risks.append("已核实至少两类严重弱项，数据完整时触发 1 分规则")
    score = min(base, debt_cap, profit_cap, trend_cap, severity_cap) if not issues else None
    return {
        "score": score,
        "status": "scored" if score is not None else "insufficient_data",
        "checks": checks,
        "issues": issues,
        "risks": risks,
        "sector": sector,
    }
