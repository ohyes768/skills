"""Insurance research-quality scoring; explicit heuristic, not a regulator rating."""

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from insurance_data import TYPES, make_template, validate_insurance_data

POLICY = "insurance-research-v1"


def _above(value, bands):
    return next(
        (
            grade
            for threshold, grade in zip(bands, (5, 4, 3, 2))
            if value >= Decimal(str(threshold))
        ),
        1,
    )


def _below(value, bands):
    return next(
        (
            grade
            for threshold, grade in zip(bands, (5, 4, 3, 2))
            if value <= Decimal(str(threshold))
        ),
        1,
    )


def _value(row, key):
    return Decimal(str(row["metrics"][key]["value"]))


def score_insurance(stock, packet):
    data = validate_insurance_data(stock, packet)
    checks, risks, caps = [], [], []

    def check(rule, inputs, period, cap, reason):
        checks.append(
            {
                "rule": rule,
                "input": inputs,
                "period": period,
                "result": cap,
                "cap": cap,
                "reason": reason,
            }
        )
        if cap is not None:
            caps.append(cap)

    annuals = data["annuals"]
    if len(annuals) == 3 and all("roe" in row["metrics"] for row in annuals):
        mean = sum(_value(row, "roe") for row in annuals) / 3
        grade = _above(mean, (15, 12, 8, 5))
        check(
            "insurance_profitability",
            {
                "roe_avg_3y": float(mean),
                "observations": [
                    {"period": row["period_end"], "roe": row["metrics"]["roe"]} for row in annuals
                ],
            },
            [row["period_end"] for row in annuals],
            grade,
            "上市主体财务加权ROE的三年均值，不用子公司或营运ROE代替",
        )
        if grade <= 2:
            risks.append("上市保险主体三年盈利能力处于研究弱档")
    latest = data["latest"]
    if data["insurance_type"] == "group" and latest and "group_solvency_ratio" in latest["metrics"]:
        grade = _above(_value(latest, "group_solvency_ratio"), (250, 200, 150, 120))
        check(
            "group_solvency",
            {"group_solvency_ratio": latest["metrics"]["group_solvency_ratio"]},
            latest["period_end"],
            grade,
            "集团偿付能力质量分档，与保险法人核心/综合比率分别判断，不自行平均",
        )
        if grade <= 2:
            risks.append("集团偿付能力处于研究质量弱档，需核查资本缓冲")
    coverage = data["coverage"]
    if coverage:
        for assessment in (coverage, *coverage["other_segments"]):
            label = assessment.get("name", "重要业务覆盖评估")
            cap = (
                2
                if assessment["status"] == "adverse"
                else 5
                if assessment["status"] == "supported"
                else None
            )
            check(
                "insurance_coverage",
                {"name": label, "assessment": assessment},
                assessment["period_end"],
                cap,
                "重要业务分部单列事实，不用银行分部代表保险集团；该评估不是合规认证",
            )
            if cap == 2:
                risks.append(f"{label}有已记录的重要不利事实：{assessment['statement']}")
    for member in data["entities"]:
        prefix, name = member["id"], member["name"]
        snapshot = member["latest"]
        if snapshot:
            for key, bands, floor in (
                ("core_solvency", (150, 120, 100, 75), 50),
                ("comprehensive_solvency", (250, 200, 150, 120), 100),
            ):
                if key not in snapshot["metrics"]:
                    continue
                actual = _value(snapshot, key)
                grade = _above(actual, bands)
                check(
                    f"{prefix}.{key}",
                    {key: snapshot["metrics"][key]},
                    snapshot["period_end"],
                    grade,
                    "逐法人偿付能力质量分档，不与其他法人平均；研究高分线不是监管线",
                )
                if actual < floor:
                    risks.append(
                        f"{name} {snapshot['period_end']} {key}低于指定偿付能力数值底线{floor}%（不代表已核验全部监管条件）"
                    )
                elif grade <= 2:
                    risks.append(f"{name} {snapshot['period_end']} {key}资本缓冲处于研究弱档")
        rating = member["risk_rating"]
        if rating:
            grade = (
                1
                if rating["value"] in ("C", "D")
                else 4
                if rating["value"] in ("BBB", "BB", "B")
                else 5
            )
            check(
                f"{prefix}.risk_rating",
                rating,
                rating["period_end"],
                grade,
                "风险综合评级A/B家族及C/D；不同于监管1-5级与本skill星级",
            )
            if grade == 1:
                risks.append(
                    f"{name}风险综合评级为{rating['value']}，不满足所列偿付能力达标条件中的风险评级条件"
                )
        for key, assessment in member["assessments"].items():
            if assessment is None:
                continue
            grade = (
                (1 if key == "reserves" else 2)
                if assessment["status"] == "adverse"
                else 5
                if assessment["status"] == "supported"
                else None
            )
            check(
                f"{prefix}.{key}",
                assessment,
                assessment["period_end"],
                grade,
                "来源支持的准备金/资产负债匹配评估；unknown不作低分，亦不凭审计意见替代事实",
            )
            if assessment["status"] == "adverse":
                label = "准备金" if key == "reserves" else "资产负债匹配"
                risks.append(f"{name}{label}存在已记录的不利证据：{assessment['statement']}")
        rows = member["annuals"]
        if member["kind"] == "life":
            yields = [
                {"period": row["period_end"], "fact": row["metrics"]["net_investment_yield"]}
                for row in rows
                if "net_investment_yield" in row["metrics"]
            ]
            if yields:
                check(
                    f"{prefix}.investment_yield",
                    yields,
                    [row["period"] for row in yields],
                    None,
                    "展示投资收益与趋势，不设统一最低收益率，不以收益率单独证明无利差损",
                )
            key = member["value_metric"]
            if (
                member["comparable"]
                and len(rows) == 3
                and key in ("nbv", "new_business_csm")
                and all(key in row["metrics"] for row in rows)
            ):
                previous, current = _value(rows[-2], key), _value(rows[-1], key)
                change = (current / previous - 1) * 100 if previous > 0 else None
                grade = (
                    2
                    if current <= 0 or change is not None and change <= -20
                    else 3
                    if change is not None and change < 0
                    else 5
                )
                check(
                    f"{prefix}.life_value",
                    {
                        "value_metric": key,
                        "previous": rows[-2]["metrics"][key],
                        "latest": rows[-1]["metrics"][key],
                        "change_pct": float(change) if change is not None else None,
                    },
                    [rows[-2]["period_end"], rows[-1]["period_end"]],
                    grade,
                    "仅比较同一可比口径的新业务价值/新业务CSM；上期非正不编造增长率，NBV/CSM不是监管资本",
                )
                if grade <= 3:
                    risks.append(f"{name}可比口径的{key}下降或最新值非正，业务价值处于研究弱档")
        elif (
            member["comparable"]
            and len(rows) == 3
            and all("combined_ratio" in row["metrics"] for row in rows)
        ):
            mean = sum(_value(row, "combined_ratio") for row in rows) / 3
            current = _value(rows[-1], "combined_ratio")
            grade = min(
                _below(mean, (95, 98, 100, 103)), 1 if current > 105 else 2 if current > 100 else 5
            )
            check(
                f"{prefix}.combined_ratio",
                {"mean_3y": float(mean), "latest": rows[-1]["metrics"]["combined_ratio"]},
                [row["period_end"] for row in rows],
                grade,
                "综合成本率衡量承保质量，100%为承保盈亏含义，不是偿付能力违规线",
            )
            if current > 100:
                risks.append(f"{name}最近年度综合成本率高于100%，承保盈利承压")
    score = min(caps) if caps and not data["issues"] else None
    return {
        "score": score,
        "status": "scored" if score is not None else "insufficient_data",
        "sector": "insurance",
        "checks": checks,
        "issues": data["issues"],
        "risks": risks,
        "policy": POLICY,
        "warnings": [
            "insurance-research-v1是尚未实证校准的研究分档，不是监管评级、信用评级或未来收益预测",
            *data["warnings"],
        ],
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
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("template")
    template.add_argument("--stock", required=True)
    template.add_argument("--as-of", required=True)
    template.add_argument("--type", choices=TYPES, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--stock", required=True)
    validate.add_argument("--input", required=True)
    args = parser.parse_args(argv)
    try:
        original = _read(args.stock)
        result = (
            make_template(original, args.as_of, args.type)
            if args.command == "template"
            else validate_insurance_data(original, _read(args.input))
        )
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 2 if result.get("status") == "insufficient_data" else 0
    except (ValueError, TypeError, OSError, OverflowError) as exc:
        print(f"insurance_financial: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
