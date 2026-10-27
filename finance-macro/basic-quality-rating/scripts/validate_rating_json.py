"""Read-only rating validation using the canonical rating_math contract.

Usage: python validate_rating_json.py rating.json [--stock stock.json]
Exit 0: structural/numeric checks pass; exit 2: invalid input or contract.
Report wording checks are advisory and do not certify research quality.
"""

import argparse
import json
import math
import re
import sys

from rating_math import DERIVED, LABELS, OUTPUT_FIELDS, _read, finalize


def _report_warnings(data):
    warnings = []
    text = data["report_md"]
    for label in ("业务核实", "五维", "边界", "结论", "风险", "证据来源"):
        if label not in text:
            warnings.append(f"报告可能缺少 {label} 内容，请人工复核")
    for label in LABELS.values():
        if label not in text:
            warnings.append(f"报告可能未解释 {label}，请人工复核")
    if any(value is None for value in data["dimensions"].values()):
        prefix = "灰色地带（证据不足，未评级）"
        if not data["summary"].startswith(prefix) or "未评级" not in text:
            warnings.append(f"存在未评分维度，请在摘要开头与报告注明 {prefix}")
        if not data["watch_points"]:
            warnings.append("存在未评分维度，请补充具体待验证问题")
    if not re.search(r"\[[^\]]+\]\(https?://[^\s)]+\)", text):
        warnings.append("请人工确认关键论断有可访问的 Markdown 来源链接与日期")
    advice = r"目标价|建议买|建议卖|加仓|减仓|重仓|建仓|清仓"
    for sentence in re.split(r"[\n。；]", text):
        if re.search(advice, sentence) and not re.search(
            r"不含|不提供|不做|禁止|不涉及|不得", sentence
        ):
            warnings.append("发现可能涉及估值或交易建议的措辞，请人工复核上下文")
            break
    return warnings


def validate(data, stock=None, *, check_financial=False):
    """Validate without correcting or mutating the supplied rating."""
    errors = []
    try:
        if not isinstance(data, dict) or set(data) != set(OUTPUT_FIELDS):
            raise ValueError("评级必须为固定 10 字段 JSON 对象")
        expected = finalize(data, stock, check_financial=check_financial)
        for field in DERIVED:
            actual, wanted = data[field], expected[field]
            if wanted is None:
                if actual is not None:
                    errors.append(f"{field} 应为 null")
            elif field == "stars":
                if type(actual) is not int or actual != wanted:
                    errors.append(f"stars 应为整数 {wanted}")
            elif field == "weighted_score":
                if (
                    type(actual) not in (int, float)
                    or (type(actual) is float and not math.isfinite(actual))
                    or actual != wanted
                ):
                    errors.append(f"weighted_score 应为 {wanted}")
            elif actual != wanted:
                errors.append("boundary 应原样使用 calculate 生成的规范文本")
    except (ValueError, TypeError, KeyError) as exc:
        errors.append(str(exc))
    return {
        "status": "failed" if errors else "passed",
        "errors": errors,
        "warnings": [] if errors else _report_warnings(data),
        "scope": "数值与结构；文字检查仅作提示，不证明事实、来源或研究质量",
    }


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Final rating JSON (not a draft)")
    parser.add_argument("--stock", help="Original stock JSON for identity verification")
    parser.add_argument("--check-financial", action="store_true", help="Verify E against --stock")
    args = parser.parse_args(argv)
    try:
        if args.check_financial and not args.stock:
            raise ValueError("--check-financial 必须配合 --stock")
        result = validate(
            _read(args.input),
            _read(args.stock) if args.stock else None,
            check_financial=args.check_financial,
        )
    except (OSError, ValueError, TypeError) as exc:
        result = {"status": "failed", "errors": [str(exc)], "warnings": []}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 2 if result["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
