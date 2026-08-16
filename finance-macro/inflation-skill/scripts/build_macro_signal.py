#!/usr/bin/env python3
"""
构建 macro_signal.json(线上契约结构)- inflation-skill

读取 inflation_latest.json(或最新月份的 YYYY-MM/inflation.json),转换为 macro 后端契约结构:
    {"conclusion": "...", "data_date": "YYYY-MM-DD", "total_score": XX.X, "details": {key: number}}

评分:内置规则评分器(对齐 SKILL.md 分析框架,各区间取代表值)。

用法:
    uv run python scripts/build_macro_signal.py                    # 默认输入/输出
    uv run python scripts/build_macro_signal.py --conclusion 中性  # 覆盖结论
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("build_macro_signal")

OUTPUT_DIR = _SCRIPT_DIR.parent.parent / "output" / _SCRIPT_DIR.parent.name

# 各维度权重(对齐 SKILL.md:CPI 40% + PPI 30% + 核心CPI 30%)
WEIGHTS = {
    "cpi": 0.40,
    "ppi": 0.30,
    "core_cpi": 0.30,
}

# 各指标评分表(对齐 SKILL.md,区间代表值;低于全部阈值 → 10)
SCORE_CPI = [(2.5, 90), (2.0, 70), (1.0, 50), (0.0, 30)]
SCORE_PPI = [(3.0, 90), (2.0, 70), (0.0, 50), (-2.0, 30)]
SCORE_CORE = [(2.5, 90), (2.0, 70), (1.0, 50), (0.3, 30)]


def score_band(value: float, bands: list[tuple[float, int]], default: int = 10) -> int:
    """区间代表值打分:bands 从高到低 [(阈值, 分)],value > 阈值即命中。"""
    for threshold, score in bands:
        if value > threshold:
            return score
    return default


def map_conclusion(total: float) -> str:
    """总分 → 定性结论(对齐 SKILL.md 综合评分表)"""
    if total >= 80:
        return "明显通胀偏高"
    if total >= 60:
        return "通胀温和偏高"
    if total >= 40:
        return "通胀温和"
    if total >= 20:
        return "低通胀偏冷"
    return "通缩风险"


def _safe_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _month_to_date(month: Any) -> str | None:
    """'YYYY-MM' → 'YYYY-MM-01'(月度数据落到当月首日,供后端判断数据月份)"""
    if isinstance(month, str) and len(month) >= 7:
        head = month[:7]
        try:
            year, mon = head.split("-")
            return f"{int(year):04d}-{int(mon):02d}-01"
        except ValueError:
            return None
    return None


def _find_input(output_dir: Path) -> Path | None:
    """定位输入:优先 inflation_latest.json,回退扫描 YYYY-MM/inflation.json 取最大月份。"""
    latest = output_dir / "inflation_latest.json"
    if latest.exists():
        return latest
    monthly_dirs = sorted(
        (p for p in output_dir.glob("*/inflation.json") if p.parent.name[:2].isdigit()),
        key=lambda p: p.parent.name,
        reverse=True,
    )
    return monthly_dirs[0] if monthly_dirs else None


def build_signal(raw: dict[str, Any], conclusion_override: str | None = None) -> dict[str, Any]:
    """
    从 run_all 抓取结果构建契约结构。

    核心CPI 缺失时按剩余权重归一化(CPI+PPI)。
    """
    cpi_block = raw.get("cpi") or {}
    ppi_block = raw.get("ppi") or {}
    core_block = raw.get("core_cpi") or {}

    details: dict[str, float] = {}
    parts: list[tuple[str, float, float]] = []  # (label, score, weight)

    cpi = _safe_float(cpi_block.get("cpi_national_yoy"))
    if cpi is not None:
        details["cpi_yoy"] = round(cpi, 1)
        parts.append(("CPI同比", score_band(cpi, SCORE_CPI), WEIGHTS["cpi"]))

    ppi = _safe_float(ppi_block.get("ppi_yoy"))
    if ppi is not None:
        details["ppi_yoy"] = round(ppi, 1)
        parts.append(("PPI同比", score_band(ppi, SCORE_PPI), WEIGHTS["ppi"]))

    core = _safe_float(core_block.get("core_cpi_yoy"))
    if core is not None:
        details["core_cpi_yoy"] = round(core, 1)
        parts.append(("核心CPI同比", score_band(core, SCORE_CORE), WEIGHTS["core_cpi"]))

    # 加权总分(缺失维度按剩余权重归一化)
    total_weight = sum(w for _, _, w in parts)
    if total_weight > 0:
        total = sum(s * w for _, s, w in parts) / total_weight
    else:
        total = 0.0

    # 月度数据:data_date 取实际数据月份(CPI/PPI/core 任一)
    month = cpi_block.get("month") or ppi_block.get("month") or raw.get("month")
    data_date = _month_to_date(month)

    signal: dict[str, Any] = {
        "conclusion": conclusion_override or map_conclusion(total),
        "data_date": data_date,
        "total_score": round(total, 1),
        "details": details,
        "score_detail": {
            "total_score": round(total, 1),
            "dimensions": [{"label": label, "score": score, "weight": weight} for label, score, weight in parts],
            "source_fetched_at": raw.get("fetched_at"),
        },
    }
    return signal


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 macro_signal.json(线上契约结构)")
    parser.add_argument("--input", type=str, default="",
                        help="输入 inflation JSON 路径(默认自动定位 inflation_latest.json 或最新月份目录)")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR / "macro_signal.json"),
                        help="输出 macro_signal.json 路径")
    parser.add_argument("--conclusion", type=str, default="",
                        help="覆盖定性结论(默认按内置规则评分映射)")
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else _find_input(OUTPUT_DIR)
    if input_path is None or not input_path.exists():
        logger.error("输入文件不存在: %s(先运行 scripts/run_all.py)", input_path)
        return 1

    with open(input_path, encoding="utf-8") as f:
        raw = json.load(f)

    signal = build_signal(raw, conclusion_override=args.conclusion or None)

    if not signal["details"]:
        logger.error("无任何可用指标(details 为空),不生成 macro_signal.json")
        return 1
    if not signal["data_date"]:
        logger.error("缺少 data_date(无有效数据月份),不生成 macro_signal.json")
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(signal, f, ensure_ascii=False, indent=2)
        f.write("\n")

    logger.info("已生成 %s(输入: %s)", output_path, input_path)
    logger.info("conclusion=%s data_date=%s 总分=%s",
                signal["conclusion"], signal["data_date"], signal["total_score"])
    for dim in signal["score_detail"]["dimensions"]:
        logger.info("  %s: %s分 × %.0f%%", dim["label"], dim["score"], dim["weight"] * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
