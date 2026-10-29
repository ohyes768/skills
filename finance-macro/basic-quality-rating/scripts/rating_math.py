"""Deterministic rating arithmetic and JSON assembly; Python standard library only."""

import argparse
import json
import os
import re
import sys
import tempfile
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
    "skill_version",
)
DERIVED = {"weighted_score", "stars", "boundary"}
THRESHOLDS = (200, 300, 400, 450)


def read_skill_version():
    """Stamp provenance from this installed skill, never from the caller/model."""
    text = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text(encoding="utf-8-sig")
    frontmatter = text.split("---", 2)[1]
    match = re.search(r"(?m)^  version: *([0-9]+\.[0-9]+\.[0-9]+) *$", frontmatter)
    if not match:
        raise ValueError("SKILL.md metadata.version 缺失或无效")
    return match.group(1)


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
    f10_data=None,
    progress=None,
):
    if progress is not None and research_state is not None:
        raise ValueError("--progress 与旧 --research-state 不能混用")
    if f10_data is not None and (bank_data is not None or insurance_data is not None):
        raise ValueError("F10数据包不能与旧行业证据包混用")
    if f10_data is not None and not check_financial:
        raise ValueError("F10数据包须配合 --stock 与 --check-financial")
    if check_financial and stock is None:
        raise ValueError("财务评分校验必须提供 --stock 原始输入")
    if bank_data is not None and insurance_data is not None:
        raise ValueError("--bank-data 与 --insurance-data 不能同时提供")
    if (bank_data is not None or insurance_data is not None) and not check_financial:
        raise ValueError("金融证据包必须配合 --stock 与 --check-financial，不能忽略资料")
    if not isinstance(draft, dict):
        raise TypeError("草稿必须为 JSON 对象")
    required = set(OUTPUT_FIELDS) - DERIVED - {"skill_version"}
    if required - set(draft) or set(draft) - set(OUTPUT_FIELDS):
        raise ValueError(
            f"草稿缺少字段 {sorted(required - set(draft))}；多余字段 {sorted(set(draft) - set(OUTPUT_FIELDS))}"
        )
    for field in ("code", "name", "summary", "report_md"):
        _text(draft[field], field)
    skill_version = read_skill_version()
    if "skill_version" in draft and draft["skill_version"] != skill_version:
        raise ValueError(f"skill_version 必须与实际 skill 版本 {skill_version} 一致")
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

        if f10_data is not None:
            from f10_financial import LIMITATION, score_f10

            financial_result = score_f10(stock, f10_data)
            if financial_result.get("limitations") and (
                LIMITATION not in draft["report_md"]
                or not any(LIMITATION in item for item in draft["watch_points"])
            ):
                raise ValueError("金融企业F10基础评分须在报告和watch_points披露专用风险未评估")
        else:
            financial_result = score_financial(
                stock, bank_data=bank_data, insurance_data=insurance_data
            )
        expected = financial_result["score"]
        dimensions = draft["dimensions"]
        if not isinstance(dimensions, dict) or dimensions.get("financial") != expected:
            raise ValueError(f"financial 与原始输入计算不一致，应为 {expected!r}")
        if (
            financial_result.get("sector") == "bank"
            and expected is not None
            and financial_result.get("liquidity_status") in ("unverified", "partial")
            and (
                "流动性未验证" not in draft["report_md"]
                or not any("流动性未验证" in item for item in draft["watch_points"])
            )
        ):
            raise ValueError(
                "银行流动性证据不完整：report_md 和 watch_points 均须标明“流动性未验证”"
            )
    derived = calculate(draft["dimensions"])
    if progress is not None:
        from research_progress import check_progress

        check_progress(progress, draft["dimensions"], stock, identity=draft)
    if research_state is not None:
        from research_state import check_research

        check_research(
            research_state,
            draft,
            stock,
            require_bank=bank_data is not None,
            require_insurance=insurance_data is not None,
            require_f10=f10_data is not None,
        )
    result = {**draft, **derived, "skill_version": skill_version}
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
    progress_flags = parser.add_mutually_exclusive_group()
    progress_flags.add_argument("--progress", help="Verify lightweight A-D evidence progress")
    progress_flags.add_argument(
        "--research-state", help="Bind calculated dimensions or verify terminal ledger"
    )
    parser.add_argument("--output", help="Atomically save final ten-field JSON (finalize only)")
    sidecars = parser.add_mutually_exclusive_group()
    sidecars.add_argument("--f10-data", help="Unified F10 data packet (financial/finalize)")
    sidecars.add_argument("--bank-data", help="Explicit bank evidence sidecar (financial/finalize)")
    sidecars.add_argument(
        "--insurance-data", help="Explicit insurance evidence sidecar (financial/finalize)"
    )
    args = parser.parse_args()
    try:
        data = _read(args.input)
        if args.output and args.command != "finalize":
            raise ValueError("--output 仅用于 finalize")
        if args.output and Path(args.output).resolve() in {
            Path(value).resolve()
            for value in (
                args.input,
                args.stock,
                args.research_state,
                args.progress,
                args.bank_data,
                args.insurance_data,
                args.f10_data,
            )
            if value
        }:
            raise ValueError("输出不能覆盖草稿、原始输入、账本或行业证据包")
        if args.command != "finalize":
            if (
                args.stock
                or args.check_financial
                or (args.research_state and args.command == "financial")
                or (args.progress and args.command == "financial")
            ):
                raise ValueError(
                    "--stock、--check-financial 仅用于 finalize；financial 不接受进度/账本参数"
                )
            if args.command == "financial":
                from financial_score import score_financial

                if args.f10_data:
                    from f10_financial import score_f10

                    result = score_f10(data, _read(args.f10_data))
                else:
                    result = score_financial(
                        data,
                        bank_data=_read_bank(args.bank_data) if args.bank_data else None,
                        insurance_data=_read_sidecar(args.insurance_data, "--insurance-data")
                        if args.insurance_data
                        else None,
                    )
            else:
                if args.bank_data or args.insurance_data or args.f10_data:
                    raise ValueError("金融证据包仅用于 financial/finalize")
                if args.research_state:
                    from research_state import ResearchRun

                    result = ResearchRun(args.research_state).seal(data)
                else:
                    result = calculate(data)
                    if args.progress:
                        from research_progress import check_progress

                        check_progress(args.progress, data)
        else:
            result = finalize(
                data,
                _read(args.stock) if args.stock else None,
                check_financial=args.check_financial,
                research_state=args.research_state,
                progress=args.progress,
                f10_data=_read(args.f10_data) if args.f10_data else None,
                bank_data=_read_bank(args.bank_data) if args.bank_data else None,
                insurance_data=_read_sidecar(args.insurance_data, "--insurance-data")
                if args.insurance_data
                else None,
            )
        serialized = json.dumps(result, ensure_ascii=False, allow_nan=False)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix=output.name + ".", dir=output.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    stream.write(serialized + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(name, output)
            finally:
                Path(name).unlink(missing_ok=True)
        print(serialized)
    except (OSError, ValueError, TypeError) as exc:
        print(f"rating_math: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
