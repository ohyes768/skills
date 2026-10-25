"""Deterministic rating arithmetic and JSON assembly; Python standard library only."""

import argparse
import json
import sys
from pathlib import Path

WEIGHTS = {
    "business": 25,
    "moat": 25,
    "industry": 20,
    "management": 15,
    "financial": 15,
}
LABELS = {
    "business": "业务模式",
    "moat": "护城河",
    "industry": "行业前景",
    "management": "管理层",
    "financial": "财务质量",
}
OUTPUT_FIELDS = (
    "code",
    "name",
    "dimensions",
    "weighted_score",
    "stars",
    "boundary",
    "summary",
    "risks",
    "watch_points",
    "report_md",
)
DERIVED = {"weighted_score", "stars", "boundary"}
THRESHOLDS = (200, 300, 400, 450)


def _stars(total):
    return 1 + sum(total >= threshold for threshold in THRESHOLDS)


def _group(keys):
    if len(keys) == len(WEIGHTS):
        return "任一维度"
    labels = [LABELS[key] for key in keys]
    return (
        "或".join(labels)
        if len(labels) <= 2
        else "、".join(labels[:-1]) + "或" + labels[-1]
    )


def calculate(dimensions):
    if not isinstance(dimensions, dict) or set(dimensions) != set(WEIGHTS):
        raise ValueError(
            "dimensions 必须恰含 business/moat/industry/management/financial 五键"
        )
    if any(
        value is not None and (type(value) is not int or not 1 <= value <= 5)
        for value in dimensions.values()
    ):
        raise ValueError("五维分数必须为 1-5 整数或 null（不接受布尔值、小数或字符串）")
    if any(value is None for value in dimensions.values()):
        return {"weighted_score": None, "stars": None, "boundary": None}
    total = sum(dimensions[key] * weight for key, weight in WEIGHTS.items())
    stars = _stars(total)
    boundary = None
    if min(abs(total - threshold) for threshold in THRESHOLDS) < 25:
        parts = []
        for delta, direction, movement in ((-1, "降", "降"), (1, "升", "升")):
            crossings = [
                key
                for key, weight in WEIGHTS.items()
                if 1 <= dimensions[key] + delta <= 5
                and _stars(total + delta * weight) != stars
            ]
            if crossings:
                target = _stars(total + delta * WEIGHTS[crossings[0]])
                parts.append(
                    f"{_group(crossings)}{direction}1分即{movement}至{target}星"
                )
            else:
                parts.append(f"单维{direction}1分不足以{movement}星")
        boundary = f"踩线 {stars} 星：" + "，".join(parts)
    return {"weighted_score": total / 100, "stars": stars, "boundary": boundary}


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须为非空字符串")


def finalize(draft, stock=None):
    if not isinstance(draft, dict):
        raise TypeError("草稿必须为 JSON 对象")
    required = set(OUTPUT_FIELDS) - DERIVED
    if required - set(draft) or set(draft) - set(OUTPUT_FIELDS):
        raise ValueError(
            f"草稿缺少字段 {sorted(required - set(draft))}；多余字段 {sorted(set(draft) - set(OUTPUT_FIELDS))}"
        )
    for field in ("code", "name", "summary", "report_md"):
        _text(draft[field], field)
    for field in ("risks", "watch_points"):
        if not isinstance(draft[field], list):
            raise TypeError(f"{field} 必须为字符串数组")
        for value in draft[field]:
            _text(value, field)
    if stock is not None:
        if not isinstance(stock, dict):
            raise ValueError("stock 必须为输入股票 JSON 对象")
        for field in ("code", "name"):
            _text(stock.get(field), f"stock.{field}")
            if stock[field] != draft[field]:
                raise ValueError(f"{field} 与输入股票不一致")
    result = {**draft, **calculate(draft["dimensions"])}
    return {field: result[field] for field in OUTPUT_FIELDS}


def _reject_constant(value):
    raise ValueError(f"JSON 不允许 {value}")


def _read(path):
    return json.loads(
        Path(path).read_text(encoding="utf-8-sig"), parse_constant=_reject_constant
    )


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("calculate", "finalize"))
    parser.add_argument(
        "--input",
        required=True,
        help="UTF-8 JSON file; dimensions for calculate, report draft for finalize",
    )
    parser.add_argument(
        "--stock",
        help="Optional original stock JSON for exact code/name verification (finalize only)",
    )
    args = parser.parse_args()
    try:
        data = _read(args.input)
        if args.command == "calculate":
            if args.stock:
                raise ValueError("--stock 仅用于 finalize")
            result = calculate(data)
        else:
            result = finalize(data, _read(args.stock) if args.stock else None)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, TypeError) as exc:
        print(f"rating_math: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
