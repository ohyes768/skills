#!/usr/bin/env python3
"""构建 monetary-policy-skill 的线上 macro_signal.json。"""

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

WEIGHTS = {"mlf": 0.50, "lpr": 0.50}


def score_mlf(net_injection_yi: float) -> int:
    if net_injection_yi > 5000:
        return 85
    if net_injection_yi > 0:
        return 55
    if net_injection_yi > -1000:
        return 40
    return 15


def score_lpr(change_bp: float) -> int:
    if change_bp < 0:
        return 90
    if change_bp == 0:
        return 55
    return 15


def map_conclusion(total: float) -> str:
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


def build_signal(raw: dict[str, Any], conclusion_override: str | None = None, data_date_override: str | None = None) -> dict[str, Any]:
    """从 MLF 与 LPR 原始数据构建上传契约；缺项按剩余权重归一化。"""
    lpr_block = raw.get("lpr") or {}
    mlf_block = raw.get("mlf") or {}
    details: dict[str, float] = {}
    parts: list[tuple[str, float, float]] = []
    indicator_meta: dict[str, dict[str, Any]] = {}

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
        parts.append(("LPR", score_lpr(change_bp) if change_bp is not None else 55, WEIGHTS["lpr"]))

    mlf_net = _safe_float(mlf_block.get("value"))
    if mlf_net is not None:
        details["mlf_net_yi"] = round(mlf_net, 0)
        mlf_date = (mlf_block.get("published_at") or "")[:10]
        if not mlf_date:
            mlf_month = mlf_block.get("actual_month")
            mlf_date = f"{mlf_month}-01" if isinstance(mlf_month, str) and len(mlf_month) == 7 else None
        indicator_meta["mlf_net_yi"] = {"data_date": mlf_date, "frequency": "monthly"}
        parts.append(("MLF净投放", score_mlf(mlf_net), WEIGHTS["mlf"]))

    total_weight = sum(weight for _, _, weight in parts)
    total = sum(score * weight for _, score, weight in parts) / total_weight if total_weight else 0.0
    data_date = data_date_override or datetime.now().strftime("%Y-%m-%d")
    return {
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


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 macro_signal.json（MLF/LPR）")
    parser.add_argument("--input", default=str(OUTPUT_DIR / "monetary_indicators_latest.json"))
    parser.add_argument("--output", default=str(OUTPUT_DIR / "macro_signal.json"))
    parser.add_argument("--conclusion", default="")
    parser.add_argument("--data-date", default="")
    args = parser.parse_args()
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("输入文件不存在: %s（先运行 scripts/run_all.py）", input_path)
        return 1
    signal = build_signal(json.loads(input_path.read_text(encoding="utf-8")), args.conclusion or None, args.data_date or None)
    if not signal["details"]:
        logger.error("无任何可用指标，跳过生成")
        return 1
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(signal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())