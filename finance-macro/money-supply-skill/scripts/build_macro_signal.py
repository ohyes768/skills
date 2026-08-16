#!/usr/bin/env python3
"""
构建 macro_signal.json(线上契约结构)- money-supply-skill

读取 run_all.py 抓取的 money_supply_latest.json,转换为 macro 后端契约结构:
    {"conclusion": "...", "data_date": "YYYY-MM-DD", "total_score": XX.X, "details": {key: number}}

评分:内置规则评分器(对齐 SKILL.md 分析框架,各区间取代表值)。
剪刀差口径:media 口径 M2同比 - M1同比(正值走阔代表资金沉淀)。

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

# 各维度权重(对齐 SKILL.md:社融 50% + 剪刀差 50%)
WEIGHTS = {
    "social": 0.50,
    "scissors": 0.50,
}

# 社融增速历史中枢(约8-10%),无环比数据时用于绝对水平粗判
SOCIAL_NEUTRAL_LOW, SOCIAL_NEUTRAL_HIGH = 8.0, 10.0


def score_social(change_pp: float | None, level: float | None) -> int:
    """社融存量同比得分(环比变化为主,缺失时按绝对水平粗判,区间代表值)"""
    if change_pp is not None:
        if change_pp >= 0.5:
            return 90  # 明显扩张(80-100)
        if change_pp >= 0.1:
            return 70  # 适度扩张(60-80)
        if change_pp > -0.1:
            return 50  # 中性(40-60)
        if change_pp > -0.5:
            return 30  # 适度收缩(20-40)
        return 10      # 明显收缩(0-20)
    if level is not None:
        # 无环比:高于中枢偏扩张,低于中枢偏收缩(粗判)
        if level >= SOCIAL_NEUTRAL_HIGH:
            return 70
        if level >= SOCIAL_NEUTRAL_LOW:
            return 55
        if level >= SOCIAL_NEUTRAL_LOW - 1:
            return 45
        return 35
    return 50


def score_scissors(spread_change_pp: float) -> int:
    """
    剪刀差环比得分(spread = M2同比 - M1同比;收窄即 spread 下降 → 活化提升 → 扩张)。
    区间代表值。
    """
    if spread_change_pp <= -1.0:
        return 90  # 收窄≥1pp → 明显扩张(80-100)
    if spread_change_pp <= -0.2:
        return 70  # 收窄0.2~1pp → 适度扩张(60-80)
    if spread_change_pp < 0.2:
        return 50  # 基本持平(40-60)
    if spread_change_pp < 1.0:
        return 30  # 走阔0.2~1pp → 适度收缩(20-40)
    return 10     # 走阔≥1pp → 明显收缩(0-20)


def map_conclusion(total: float) -> str:
    """总分 → 定性结论(对齐 SKILL.md 综合评分表)"""
    if total >= 80:
        return "明显信用扩张"
    if total >= 60:
        return "适度信用扩张"
    if total >= 40:
        return "中性"
    if total >= 20:
        return "适度信用收缩"
    return "明显信用收缩"


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


def build_signal(raw: dict[str, Any], conclusion_override: str | None = None) -> dict[str, Any]:
    """
    从 run_all 抓取结果构建契约结构。

    剪刀差环比从 m1_m2.history 前两月计算(直接用 yoy 差值,兼容历史 key 命名差异)。
    缺失维度按剩余权重归一化。
    """
    m1_m2 = raw.get("m1_m2") or {}
    latest = m1_m2.get("latest") or {}
    history = m1_m2.get("history") or []
    social = raw.get("social_financing") or {}

    details: dict[str, float] = {}
    parts: list[tuple[str, float, float]] = []  # (label, score, weight)

    # --- 社融存量同比(总量维度) ---
    social_yoy = _safe_float(social.get("balance_yoy_pct"))
    social_change = _safe_float(social.get("balance_yoy_change_pp"))
    if social_yoy is not None:
        details["social_yoy"] = round(social_yoy, 1)
        parts.append(("社融增速", score_social(social_change, social_yoy), WEIGHTS["social"]))

    # --- M2-M1 剪刀差(活化维度;环比从 history 计算) ---
    m1_yoy = _safe_float(latest.get("m1_yoy"))
    m2_yoy = _safe_float(latest.get("m2_yoy"))
    spread_now = _safe_float(latest.get("m2_m1_spread"))
    if spread_now is None and m1_yoy is not None and m2_yoy is not None:
        spread_now = round(m2_yoy - m1_yoy, 2)  # 当前代码输出 key 为 m2_m1_spread,旧数据回退计算
    if m2_yoy is not None:
        details["m2_yoy"] = round(m2_yoy, 1)
    if m1_yoy is not None:
        details["m1_yoy"] = round(m1_yoy, 1)
    if spread_now is not None:
        details["m2_m1_spread"] = round(spread_now, 2)

    spread_prev: float | None = None
    if len(history) >= 2:
        prev = history[1]
        spread_prev = _safe_float(prev.get("m2_m1_spread"))
        if spread_prev is None:
            prev_m1, prev_m2 = _safe_float(prev.get("m1_yoy")), _safe_float(prev.get("m2_yoy"))
            if prev_m1 is not None and prev_m2 is not None:
                spread_prev = round(prev_m2 - prev_m1, 2)

    spread_change = None
    if spread_now is not None and spread_prev is not None:
        spread_change = round(spread_now - spread_prev, 2)
        details["spread_change_pp"] = spread_change
        parts.append(("M2-M1剪刀差", score_scissors(spread_change), WEIGHTS["scissors"]))
    elif spread_now is not None:
        # 无上月对比时按中性处理
        parts.append(("M2-M1剪刀差", 50, WEIGHTS["scissors"]))

    # 加权总分(缺失维度按剩余权重归一化)
    total_weight = sum(w for _, _, w in parts)
    if total_weight > 0:
        total = sum(s * w for _, s, w in parts) / total_weight
    else:
        total = 0.0

    # 月度数据:data_date 取实际数据月份(社融月份优先,回退 actual_fetched_month)
    month = social.get("month") or raw.get("actual_fetched_month")
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
    parser.add_argument("--input", type=str, default=str(OUTPUT_DIR / "money_supply_latest.json"),
                        help="输入 money_supply_latest.json 路径")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR / "macro_signal.json"),
                        help="输出 macro_signal.json 路径")
    parser.add_argument("--conclusion", type=str, default="",
                        help="覆盖定性结论(默认按内置规则评分映射)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
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

    logger.info("已生成 %s", output_path)
    logger.info("conclusion=%s data_date=%s 总分=%s",
                signal["conclusion"], signal["data_date"], signal["total_score"])
    for dim in signal["score_detail"]["dimensions"]:
        logger.info("  %s: %s分 × %.0f%%", dim["label"], dim["score"], dim["weight"] * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
