#!/usr/bin/env python3
"""
构建 macro_signal.json(线上契约结构)- monetary-policy-skill

读取 run_all.py 抓取的 monetary_indicators_latest.json,转换为 macro 后端契约结构:
    {"conclusion": "...", "data_date": "YYYY-MM-DD", "total_score": XX.X, "details": {key: number}}

评分:内置规则评分器(对齐 SKILL.md 分析框架,各区间取代表值),
     可用 --conclusion 覆盖(供 agent 按框架精调后指定)。

用法:
    uv run python scripts/build_macro_signal.py                    # 默认输入/输出
    uv run python scripts/build_macro_signal.py --conclusion 中性  # 覆盖结论
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("build_macro_signal")

OUTPUT_DIR = _SCRIPT_DIR.parent.parent / "output" / _SCRIPT_DIR.parent.name

# 政策基准:7 天逆回购利率(SKILL.md 指标一)
POLICY_RATE = 1.5

# 各维度权重(对齐 SKILL.md:DR007 40% + MLF 30% + LPR 30%)
WEIGHTS = {
    "dr007": 0.40,
    "mlf": 0.30,
    "lpr": 0.30,
}


def score_dr007(value: float) -> int:
    """DR007 得分(相对政策利率 1.5%,区间代表值)"""
    if value < POLICY_RATE - 0.2:
        return 90  # 低于政策利率20BP以上 → 明显宽松(90-100)
    if value <= POLICY_RATE:
        return 70  # 低于或接近政策利率 → 适度宽松(60-80)
    if value <= POLICY_RATE + 0.2:
        return 50  # 略高于政策利率 → 中性偏紧(40-60)
    return 30  # 显著高于政策利率 → 紧缩(<40)


def score_mlf(net_injection_yi: float) -> int:
    """MLF 净投放量得分(亿元,区间代表值)"""
    if net_injection_yi > 5000:
        return 85  # 流动性充裕(70-100)
    if net_injection_yi > 0:
        return 55  # 适度宽松/中性(40-70)
    if net_injection_yi > -1000:
        return 40  # 等量或微幅回笼 → 中性(30-50)
    return 15  # 净回笼>1000亿 → 紧缩(0-30)


def score_lpr(change_bp: float) -> int:
    """LPR 较上月变化得分(bp,区间代表值)"""
    if change_bp < 0:
        return 90  # 下调 → 宽松(80-100)
    if change_bp == 0:
        return 55  # 持平(50-60)
    return 15  # 上调 → 紧缩(0-30)


def map_conclusion(total: float) -> str:
    """总分 → 定性结论(对齐 SKILL.md 综合判断)"""
    if total >= 80:
        return "明显宽松"
    if total >= 60:
        return "适度宽松"
    if total >= 40:
        return "中性"
    if total >= 20:
        return "适度紧缩"
    return "明显紧缩"


def _safe_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def build_signal(
    raw: dict[str, Any],
    conclusion_override: str | None = None,
    data_date_override: str | None = None,
) -> dict[str, Any]:
    """
    从 run_all 抓取结果构建契约结构。

    缺失维度按剩余权重归一化(如 MLF 抓取失败时,DR007+LPR 归一)。
    附加字段(score_detail / indicator_meta 等)后端不读取 details 以外的部分,仅落盘备查;
    indicator_meta.month_avg 除外(后端已上线透传,日频指标月均卡片用)。

    data_date 规则(日频推送契约): 默认填推送当日,而非指标读数日——
    后端归档月份按 data_date 提取,月初盘后推送若写上月末读数日会归错月。
    """
    dr007_block = raw.get("dr007") or {}
    lpr_block = raw.get("lpr") or {}
    mlf_block = raw.get("mlf") or {}

    details: dict[str, float] = {}
    parts: list[tuple[str, float, float]] = []  # (label, score, weight)
    indicator_meta: dict[str, dict[str, Any]] = {}

    # --- DR007(每日) ---
    dr007 = _safe_float(dr007_block.get("value"))
    if dr007 is not None:
        details["dr007"] = round(dr007, 4)
        dr007_date = (dr007_block.get("published_at") or "")[:10] or None
        dr007_meta: dict[str, Any] = {"data_date": dr007_date, "frequency": "daily"}
        month_avg = _safe_float(dr007_block.get("month_avg"))
        if month_avg is not None:
            dr007_meta["month_avg"] = round(month_avg, 4)
        indicator_meta["dr007"] = dr007_meta
        parts.append(("DR007", score_dr007(dr007), WEIGHTS["dr007"]))

    # --- LPR(每月20日;变化取 1Y,缺失回退 5Y+) ---
    lpr_1y = _safe_float(lpr_block.get("lpr_1y"))
    lpr_5y = _safe_float(lpr_block.get("lpr_5y_plus"))
    prev_1y = _safe_float(lpr_block.get("prev_lpr_1y"))
    prev_5y = _safe_float(lpr_block.get("prev_lpr_5y_plus"))
    if lpr_1y is not None:
        details["lpr_1y"] = round(lpr_1y, 2)
    if lpr_5y is not None:
        details["lpr_5y"] = round(lpr_5y, 2)

    change_bp: float | None = None
    if lpr_1y is not None and prev_1y is not None:
        change_bp = round((lpr_1y - prev_1y) * 100, 2)
    elif lpr_5y is not None and prev_5y is not None:
        change_bp = round((lpr_5y - prev_5y) * 100, 2)
    if lpr_1y is not None or lpr_5y is not None:
        lpr_date = (lpr_block.get("published_at") or "")[:10] or None
        if lpr_1y is not None:
            indicator_meta["lpr_1y"] = {"data_date": lpr_date, "frequency": "monthly"}
        if lpr_5y is not None:
            indicator_meta["lpr_5y"] = {"data_date": lpr_date, "frequency": "monthly"}
        if change_bp is not None:
            parts.append(("LPR", score_lpr(change_bp), WEIGHTS["lpr"]))
        else:
            # 无上月对比时按"持平"处理(SKILL.md: 持平 50-60)
            parts.append(("LPR", 55, WEIGHTS["lpr"]))

    # --- MLF 净投放(每月2-3日) ---
    mlf_net = _safe_float(mlf_block.get("value"))
    if mlf_net is not None:
        details["mlf_net_yi"] = round(mlf_net, 0)
        mlf_date = (mlf_block.get("published_at") or "")[:10]
        if not mlf_date:
            mlf_month = mlf_block.get("actual_month")
            mlf_date = f"{mlf_month}-01" if isinstance(mlf_month, str) and len(mlf_month) == 7 else None
        indicator_meta["mlf_net_yi"] = {"data_date": mlf_date, "frequency": "monthly"}
        parts.append(("MLF净投放", score_mlf(mlf_net), WEIGHTS["mlf"]))

    # 加权总分(缺失维度按剩余权重归一化)
    total_weight = sum(w for _, _, w in parts)
    if total_weight > 0:
        total = sum(s * w for _, s, w in parts) / total_weight
    else:
        total = 0.0

    # 顶层 data_date = 推送当日(日频契约): 归档月份按它提取,不用读数日;
    # 手动补推历史月份时可用 --data-date 指定
    data_date = data_date_override or datetime.now().strftime("%Y-%m-%d")

    signal: dict[str, Any] = {
        "conclusion": conclusion_override or map_conclusion(total),
        "data_date": data_date,
        "total_score": round(total, 1),
        "details": details,
        "indicator_meta": indicator_meta,
        "score_detail": {
            "total_score": round(total, 1),
            "dimensions": [{"label": label, "score": score, "weight": weight} for label, score, weight in parts],
            "source_fetched_at": raw.get("fetched_at"),
        },
    }
    return signal


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 macro_signal.json(线上契约结构)")
    parser.add_argument("--input", type=str, default=str(OUTPUT_DIR / "monetary_indicators_latest.json"),
                        help="输入 monetary_indicators_latest.json 路径")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR / "macro_signal.json"),
                        help="输出 macro_signal.json 路径")
    parser.add_argument("--conclusion", type=str, default="",
                        help="覆盖定性结论(默认按内置规则评分映射)")
    parser.add_argument("--data-date", type=str, default="",
                        help="覆盖顶层 data_date(默认推送当日;手动补推历史月份时指定)")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("输入文件不存在: %s(先运行 scripts/run_all.py)", input_path)
        return 1

    with open(input_path, encoding="utf-8") as f:
        raw = json.load(f)

    signal = build_signal(
        raw,
        conclusion_override=args.conclusion or None,
        data_date_override=(args.data_date or None),
    )

    if not signal["details"]:
        logger.error("无任何可用指标(details 为空),不生成 macro_signal.json")
        return 1
    if not signal["data_date"]:
        logger.error("缺少 data_date(所有指标均无日期),不生成 macro_signal.json")
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(signal, f, ensure_ascii=False, indent=2)
        f.write("\n")

    logger.info("已生成 %s", output_path)
    logger.info("conclusion=%s data_date=%s 总分=%s",
                signal["conclusion"], signal["data_date"], signal["total_score"])
    for key, meta in signal.get("indicator_meta", {}).items():
        logger.info("  meta %s: %s", key, meta)
    for dim in signal["score_detail"]["dimensions"]:
        logger.info("  %s: %s分 × %.0f%%", dim["label"], dim["score"], dim["weight"] * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
