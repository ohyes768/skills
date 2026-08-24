#!/usr/bin/env python3
"""
构建 macro_signal.json（线上契约结构）- exchange-rate-skill

读取 run_all.py 抓取的 exchange_rate_data.json，转换为 macro 后端契约结构：
    {"conclusion": "...", "data_date": "YYYY-MM-DD", "total_score": XX.X, "details": {key: number}}

对接契约: personal-web/.trellis/spec/guides/macro-signal-upload.md 第 2.3.A 节
评分：内置规则评分器（对齐 SKILL.md 评分框架，各区间取代表值），
     可用 --conclusion 覆盖（供 agent 按框架精调后指定）。

用法：
    uv run python scripts/build_macro_signal.py                 # 默认输入/输出
    uv run python scripts/build_macro_signal.py --conclusion 中性  # 覆盖结论
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from fetch_common import get_logger, setup_logging

logger = get_logger("build_macro_signal")

OUTPUT_DIR = _SCRIPT_DIR.parent.parent / "output" / _SCRIPT_DIR.parent.name

# 各维度权重（对齐 SKILL.md：美元指数30% + 人民币20% + 北向25% + TED25%）
WEIGHTS = {
    "dollar_index": 0.30,
    "usd_cny": 0.20,
    "north": 0.25,
    "ted_spread": 0.25,
}


def score_dollar_index(value: float) -> int:
    """美元指数 DTWEXBGS 得分（区间代表值）"""
    if value > 125:
        return 85  # 强势美元（极强）
    if value > 115:
        return 60  # 中性偏强
    if value > 105:
        return 45  # 中性
    if value > 95:
        return 35  # 中性偏弱
    return 15  # 弱势美元


def score_usd_cny(value: float) -> int:
    """美元兑人民币得分"""
    if value < 7.0:
        return 85  # 人民币强势
    if value <= 7.2:
        return 60  # 中性
    if value <= 7.5:
        return 40  # 人民币偏弱
    return 15  # 人民币弱势


def score_north(change_pct: float, turnover_today_yi: float | None) -> int:
    """北向资金得分（7日日均成交额环比）+ 辅助加减分"""
    if change_pct > 20:
        score = 85
    elif change_pct > 5:
        score = 65
    elif change_pct >= -5:
        score = 50
    elif change_pct >= -20:
        score = 30
    else:
        score = 10

    # 辅助：单日成交额超 100 亿 +3（SKILL.md 指标三辅助项，数据可得的部分）
    if turnover_today_yi is not None and turnover_today_yi > 100:
        score += 3

    return min(100, score)


def score_ted_spread(value: float) -> int:
    """TED 利差得分"""
    if value > 1.0:
        return 15  # 流动性紧张
    if value > 0.5:
        return 40  # 正常偏紧
    if value > 0.3:
        return 60  # 正常
    if value >= 0:
        return 80  # 宽松
    return 95  # 极度宽松


def map_conclusion(total: float) -> str:
    """总分 → 定性结论（注意：本 skill 高分=风险规避，与 risk-appetite 相反）"""
    if total >= 80:
        return "极度风险规避"
    if total >= 60:
        return "风险偏好偏低"
    if total >= 40:
        return "中性"
    if total >= 30:
        return "风险偏好偏高"
    return "极度乐观"


def _safe_float(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _daily_meta(block: dict[str, Any]) -> dict[str, Any]:
    """日频指标的 indicator_meta 条目：读数日 + daily + 当月日均（若有）。"""
    meta: dict[str, Any] = {
        "data_date": block.get("date"),
        "frequency": "daily",
    }
    month_avg = _safe_float(block.get("month_avg"))
    if month_avg is not None:
        meta["month_avg"] = round(month_avg, 4)
    return meta


def build_signal(
    raw: dict[str, Any],
    conclusion_override: str | None = None,
    data_date_override: str | None = None,
) -> dict[str, Any]:
    """
    从 run_all 抓取结果构建契约结构。

    缺失维度按剩余权重归一化（如 FRED 失败只剩北向时，北向得分即总分）。
    附加字段（score_detail / indicator_meta 等）仅落盘备查，
    其中 indicator_meta.month_avg 后端已上线透传（日频指标月均卡片用）。

    data_date 规则（日频推送契约）：默认填推送当日而非读数日——
    后端归档月份按 data_date 提取，月初盘后推送若写上月末读数日会归错月。
    """
    data = raw.get("data") or {}
    rates = data.get("exchange_rates") or {}
    flow = data.get("fund_flow") or {}
    ted = data.get("ted_spread") or {}
    north = flow.get("north") or {}
    north_cum = flow.get("north_cumulative") or {}

    details: dict[str, float] = {}
    parts: list[tuple[str, float, float]] = []  # (label, score, weight)
    indicator_meta: dict[str, dict[str, Any]] = {}

    di = rates.get("dollar_index")
    if isinstance(di, dict) and _safe_float(di.get("value")) is not None:
        details["dollar_index"] = round(float(di["value"]), 4)
        indicator_meta["dollar_index"] = _daily_meta(di)
        parts.append(("美元指数", score_dollar_index(di["value"]), WEIGHTS["dollar_index"]))

    uc = rates.get("usd_cny")
    if isinstance(uc, dict) and _safe_float(uc.get("value")) is not None:
        details["usd_cny"] = round(float(uc["value"]), 4)
        indicator_meta["usd_cny"] = _daily_meta(uc)
        parts.append(("人民币汇率", score_usd_cny(uc["value"]), WEIGHTS["usd_cny"]))

    turnover_avg = north_cum.get("turnover_7d_avg_yi")
    change_pct = north_cum.get("turnover_7d_change_pct")
    if isinstance(change_pct, (int, float)):
        if isinstance(turnover_avg, (int, float)):
            details["north_turnover_7d_yi"] = round(float(turnover_avg), 2)
        if isinstance(north.get("turnover_yi"), (int, float)):
            details["north_turnover_today_yi"] = round(float(north["turnover_yi"]), 2)
        details["north_change_pct"] = round(float(change_pct), 2)
        today_yi = north.get("turnover_yi") if isinstance(north.get("turnover_yi"), (int, float)) else None
        parts.append(("北向资金", score_north(change_pct, today_yi), WEIGHTS["north"]))

    if _safe_float(ted.get("ted_spread")) is not None:
        details["ted_spread"] = round(float(ted["ted_spread"]), 4)
        indicator_meta["ted_spread"] = _daily_meta(ted)
        parts.append(("TED利差", score_ted_spread(ted["ted_spread"]), WEIGHTS["ted_spread"]))

    # 加权总分（缺失维度按剩余权重归一化）
    total_weight = sum(w for _, _, w in parts)
    if total_weight > 0:
        total = sum(s * w for _, s, w in parts) / total_weight
    else:
        total = 0.0

    # 顶层 data_date = 推送当日（日频契约）：归档月份按它提取，不用读数日；
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
            "source_errors": raw.get("errors", []),
        },
    }
    return signal


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 macro_signal.json（线上契约结构）")
    parser.add_argument("--input", type=str, default=str(OUTPUT_DIR / "exchange_rate_data.json"),
                        help="输入 exchange_rate_data.json 路径")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR / "macro_signal.json"),
                        help="输出 macro_signal.json 路径")
    parser.add_argument("--conclusion", type=str, default="",
                        help="覆盖定性结论（默认按内置规则评分映射）")
    parser.add_argument("--data-date", type=str, default="",
                        help="覆盖顶层 data_date（默认推送当日；手动补推历史月份时指定）")
    args = parser.parse_args()

    setup_logging()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("输入文件不存在: %s（先运行 scripts/run_all.py）", input_path)
        return 1

    with open(input_path, encoding="utf-8") as f:
        raw = json.load(f)

    signal = build_signal(
        raw,
        conclusion_override=args.conclusion or None,
        data_date_override=(args.data_date or None),
    )

    if not signal["details"]:
        logger.error("无任何可用指标（details 为空），不生成 macro_signal.json")
        return 1
    if not signal["data_date"]:
        logger.error("缺少 data_date（所有指标均无日期），不生成 macro_signal.json")
        return 1

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(signal, f, ensure_ascii=False, indent=2)
        f.write("\n")

    logger.info("已生成 %s", output_path)
    logger.info("conclusion=%s data_date=%s 总分=%s",
                signal["conclusion"], signal["data_date"],
                signal["total_score"])
    for key, meta in signal.get("indicator_meta", {}).items():
        logger.info("  meta %s: %s", key, meta)
    for dim in signal["score_detail"]["dimensions"]:
        logger.info("  %s: %s分 × %.0f%%", dim["label"], dim["score"], dim["weight"] * 100)
    return 0


if __name__ == "__main__":
    sys.exit(main())
