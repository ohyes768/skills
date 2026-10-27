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
    return "或".join(labels) if len(labels) <= 2 else "、".join(labels[:-1]) + "或" + labels[-1]


def calculate(dimensions):
    if not isinstance(dimensions, dict) or set(dimensions) != set(WEIGHTS):
        raise ValueError("dimensions 必须恰含 business/moat/industry/management/financial 五键")
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
                if 1 <= dimensions[key] + delta <= 5 and _stars(total + delta * weight) != stars
            ]
            if crossings:
                target = _stars(total + delta * WEIGHTS[crossings[0]])
                parts.append(f"{_group(crossings)}{direction}1分即{movement}至{target}星")
            else:
                parts.append(f"单维{direction}1分不足以{movement}星")
        boundary = f"踩线 {stars} 星：" + "，".join(parts)
    return {"weighted_score": total / 100, "stars": stars, "boundary": boundary}


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须为非空字符串")


def finalize(
    draft,
    stock=None,
    *,
    check_financial=False,
    research_state=None,
    bank_data=None,
    insurance_data=None,
):
    if check_financial and stock is None:
        raise ValueError("财务评分校验必须提供 --stock 原始输入")
    if bank_data is not None and insurance_data is not None:
        raise ValueError("--bank-data 与 --insurance-data 不能同时提供")
    if (bank_data is not None or insurance_data is not None) and not check_financial:
        raise ValueError("金融证据包必须配合 --stock 与 --check-financial，不能忽略资料")
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
    if check_financial:
        from financial_score import score_financial

        expected = score_financial(stock, bank_data=bank_data, insurance_data=insurance_data)[
            "score"
        ]
        dimensions = draft["dimensions"]
        if not isinstance(dimensions, dict) or dimensions.get("financial") != expected:
            raise ValueError(f"financial 与原始输入计算不一致，应为 {expected!r}")
    derived = calculate(draft["dimensions"])
    if research_state is not None:
        from research_state import check_research

        check_research(
            research_state,
            draft,
            stock,
            require_bank=bank_data is not None,
            require_insurance=insurance_data is not None,
        )
    result = {**draft, **derived}
    return {field: result[field] for field in OUTPUT_FIELDS}


def _reject_constant(value):
    raise ValueError(f"JSON 不允许 {value}")


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), parse_constant=_reject_constant)


def _read_sidecar(path, flag):
    packet = _read(path)
    if not isinstance(packet, dict):
        raise TypeError(f"{flag} 文件必须为证据 JSON 对象，不能为 null 或数组")
    return packet


def _read_bank(path):
    return _read_sidecar(path, "--bank-data")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("financial", "calculate", "finalize"))
    parser.add_argument(
        "--input",
        required=True,
        help="UTF-8 JSON file; dimensions for calculate, report draft for finalize",
    )
    parser.add_argument(
        "--stock",
        help="Optional original stock JSON for exact code/name verification (finalize only)",
    )
    parser.add_argument(
        "--check-financial",
        action="store_true",
        help="Verify E against original --stock (finalize only)",
    )
    parser.add_argument("--research-state", help="Verify terminal research ledger (finalize only)")
    sidecars = parser.add_mutually_exclusive_group()
    sidecars.add_argument("--bank-data", help="Explicit bank evidence sidecar (financial/finalize)")
    sidecars.add_argument(
        "--insurance-data", help="Explicit insurance evidence sidecar (financial/finalize)"
    )
    args = parser.parse_args()
    try:
        data = _read(args.input)
        if args.command != "finalize":
            if args.stock or args.check_financial or args.research_state:
                raise ValueError("--stock、--check-financial 与 --research-state 仅用于 finalize")
            if args.command == "financial":
                from financial_score import score_financial

                result = score_financial(
                    data,
                    bank_data=_read_bank(args.bank_data) if args.bank_data else None,
                    insurance_data=_read_sidecar(args.insurance_data, "--insurance-data")
                    if args.insurance_data
                    else None,
                )
            else:
                if args.bank_data or args.insurance_data:
                    raise ValueError("金融证据包仅用于 financial/finalize")
                result = calculate(data)
        else:
            result = finalize(
                data,
                _read(args.stock) if args.stock else None,
                check_financial=args.check_financial,
                research_state=args.research_state,
                bank_data=_read_bank(args.bank_data) if args.bank_data else None,
                insurance_data=_read_sidecar(args.insurance_data, "--insurance-data")
                if args.insurance_data
                else None,
            )
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, TypeError) as exc:
        print(f"rating_math: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
