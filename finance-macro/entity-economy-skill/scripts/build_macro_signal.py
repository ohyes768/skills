#!/usr/bin/env python3
"""
构建 macro_signal.json(线上契约结构)- entity-economy-skill

读取统一输出目录下的 7 个 CSV(PMI/工业增加值/固投/社零/用电量/铁路货运/央行信贷),
按 SKILL.md 评分体系计算五大指标得分与加权总分,生成 macro 后端契约结构:
    {"conclusion": "...", "data_date": "YYYY-MM-DD", "total_score": XX.X, "details": {key: number}}

克强指数 = 工业用电量增速×40% + 中长期贷款余额增速×35% + 铁路货运量增速×25%
(三子项任一缺失则跳过克强指标,总权重重新分配,对齐 SKILL.md)。

用法:
    uv run python scripts/build_macro_signal.py                    # 默认输入/输出
    uv run python scripts/build_macro_signal.py --conclusion 中性  # 覆盖结论
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

_SCRIPT_DIR = Path(__file__).resolve().parent
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("build_macro_signal")

OUTPUT_DIR = _SCRIPT_DIR.parent.parent / "output" / _SCRIPT_DIR.parent.name

# 各维度权重(对齐 SKILL.md:PMI 30% + 工业 20% + 固投 20% + 社零 20% + 克强 10%)
WEIGHTS = {
    "pmi": 0.30,
    "industrial": 0.20,
    "fai": 0.20,
    "retail": 0.20,
    "keqiang": 0.10,
}

# 克强指数子项权重
KEQIANG_WEIGHTS = {"electricity": 0.40, "credit": 0.35, "railway": 0.25}

_MONTH_RE = re.compile(r"^(\d{4})年(\d{1,2})月")


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_month_cell(text: Any) -> str | None:
    """'2026年3月份' → '2026-03';'2026年1-02月份'(跨月合并)等无法解析的返回 None。"""
    if not isinstance(text, str):
        return None
    m = _MONTH_RE.match(text.strip())
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"


def _read_csv(path: Path) -> pd.DataFrame | None:
    if not path.exists():
        logger.warning("CSV 不存在,跳过: %s", path)
        return None
    try:
        return pd.read_csv(path, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="gbk")


def latest_row(df: pd.DataFrame) -> tuple[str, pd.Series] | None:
    """取第一行可解析月份的数据(CSV 按时间降序,跨月合并行跳过)。"""
    for _, row in df.iterrows():
        month = parse_month_cell(row.iloc[0])
        if month:
            return month, row
    return None


def score_band(value: float, bands: list[tuple[float, int]], default: int = 10) -> int:
    """区间代表值打分:bands 从高到低 [(阈值, 分)],value > 阈值即命中。"""
    for threshold, score in bands:
        if value > threshold:
            return score
    return default


# 各指标评分表(对齐 SKILL.md,区间代表值)
SCORE_PMI = [(53, 90), (50, 70), (49, 50), (47, 30)]
SCORE_INDUSTRIAL = [(7, 90), (5.5, 70), (4.5, 50), (3, 30)]
SCORE_FAI = [(5, 90), (3.5, 70), (2, 50), (0, 30)]
SCORE_RETAIL = [(5, 90), (4, 70), (2.5, 50), (1, 30)]
SCORE_KEQIANG = [(8, 90), (5, 70), (3, 50), (1, 30)]


def map_conclusion(total: float) -> str:
    """总分 → 定性结论(对齐 SKILL.md 定性判断表)"""
    if total >= 80:
        return "经济过热"
    if total >= 60:
        return "经济偏热"
    if total >= 40:
        return "经济稳健"
    if total >= 20:
        return "经济偏冷"
    return "经济过冷"


def _credit_yoy(base_dir: Path, month: str) -> float | None:
    """企业中长期贷款余额同比:当月值 vs 上年同期(2025 基准表)。"""
    cur = _read_csv(base_dir / "pbc_credit_balance" / "pbc_credit_balance.csv")
    if cur is None:
        return None
    col = next((c for c in cur.columns if "中长期企业贷款" in c or "企业中长期贷款" in c), None)
    if col is None:
        return None
    row = cur[cur.iloc[:, 0].astype(str).str.contains(month.replace("-", "年") + "月", regex=False)]
    if row.empty:
        return None
    current = _safe_float(row.iloc[0][col])
    if current is None:
        return None

    prev_csv = _read_csv(base_dir / "pbc_credit_balance" / "pbc_credit_balance_2025.csv")
    if prev_csv is None:
        return None
    prev_col = next((c for c in prev_csv.columns if "中长期企业贷款" in c or "企业中长期贷款" in c), None)
    if prev_col is None:
        return None
    year = int(month[:4]) - 1
    prev_key = f"{year}年{int(month[5:])}月"
    prev_row = prev_csv[prev_csv.iloc[:, 0].astype(str).str.startswith(prev_key)]
    if prev_row.empty:
        return None
    previous = _safe_float(prev_row.iloc[0][prev_col])
    if previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def build_signal(conclusion_override: str | None = None) -> dict[str, Any]:
    """从各 CSV 最新数据构建契约结构。缺失维度按剩余权重归一化。"""
    base_dir = OUTPUT_DIR

    details: dict[str, float] = {}
    months: list[str] = []
    parts: list[tuple[str, float, float]] = []  # (label, score, weight)

    # --- 制造业 PMI(30%) ---
    df = _read_csv(base_dir / "pmi_manufacturing" / "pmi_m.csv")
    if df is not None:
        hit = latest_row(df)
        pmi_col = next((c for c in df.columns if "制造业-指数" in c), None)
        if hit and pmi_col:
            month, row = hit
            pmi = _safe_float(row[pmi_col])
            if pmi is not None:
                details["pmi_manufacturing"] = round(pmi, 1)
                months.append(month)
                parts.append(("制造业PMI", score_band(pmi, SCORE_PMI), WEIGHTS["pmi"]))

    # --- 工业增加值同比(20%) ---
    df = _read_csv(base_dir / "gyzjz" / "gyzjz.csv")
    if df is not None:
        hit = latest_row(df)
        if hit and "同比增长" in df.columns:
            month, row = hit
            val = _safe_float(row["同比增长"])
            if val is not None:
                details["industrial_yoy"] = round(val, 1)
                months.append(month)
                parts.append(("工业增加值", score_band(val, SCORE_INDUSTRIAL), WEIGHTS["industrial"]))

    # --- 固定资产投资当月同比(20%) ---
    df = _read_csv(base_dir / "gdzctz" / "gdzctz.csv")
    if df is not None:
        hit = latest_row(df)
        if hit and "同比增长" in df.columns:
            month, row = hit
            val = _safe_float(row["同比增长"])
            if val is not None:
                details["fai_yoy"] = round(val, 1)
                months.append(month)
                parts.append(("固定资产投资", score_band(val, SCORE_FAI), WEIGHTS["fai"]))

    # --- 社零同比(20%) ---
    df = _read_csv(base_dir / "consumer_retail" / "consumer_retail.csv")
    if df is not None:
        hit = latest_row(df)
        if hit and "同比增长" in df.columns:
            month, row = hit
            val = _safe_float(row["同比增长"])
            if val is not None:
                details["retail_yoy"] = round(val, 1)
                months.append(month)
                parts.append(("社会消费品零售", score_band(val, SCORE_RETAIL), WEIGHTS["retail"]))

    # --- 克强指数(10%;三子项缺一即整体跳过) ---
    elec = rail = None
    df = _read_csv(base_dir / "electricity_consumption" / "electricity_consumption.csv")
    if df is not None:
        hit = latest_row(df)
        if hit and "yoy_percent" in df.columns:
            month, row = hit
            elec = _safe_float(row["yoy_percent"])
            if elec is not None:
                details["electricity_yoy"] = round(elec, 1)
                months.append(month)
    df = _read_csv(base_dir / "railway_freight" / "railway_freight.csv")
    if df is not None:
        hit = latest_row(df)
        if hit and "freight_send_yoy_percent" in df.columns:
            month, row = hit
            rail = _safe_float(row["freight_send_yoy_percent"])
            if rail is not None:
                details["railway_yoy"] = round(rail, 1)
                months.append(month)
    latest_month = max(months) if months else None
    credit = _credit_yoy(base_dir, latest_month) if latest_month else None

    if elec is not None and rail is not None and credit is not None:
        keqiang = (elec * KEQIANG_WEIGHTS["electricity"]
                   + credit * KEQIANG_WEIGHTS["credit"]
                   + rail * KEQIANG_WEIGHTS["railway"])
        details["keqiang_index"] = round(keqiang, 1)
        parts.append(("克强指数", score_band(keqiang, SCORE_KEQIANG), WEIGHTS["keqiang"]))
    else:
        logger.info("克强指数子项不全(用电量=%s 贷款同比=%s 货运=%s),跳过该指标",
                    elec, credit, rail)

    # 加权总分(缺失维度按剩余权重归一化)
    total_weight = sum(w for _, _, w in parts)
    if total_weight > 0:
        total = sum(s * w for _, s, w in parts) / total_weight
    else:
        total = 0.0

    # 各指标数据月份不一(PMI 当月,其他上月),取最大月份作 data_date
    data_date = f"{latest_month}-01" if latest_month else None

    signal: dict[str, Any] = {
        "conclusion": conclusion_override or map_conclusion(total),
        "data_date": data_date,
        "total_score": round(total, 1),
        "details": details,
        "score_detail": {
            "total_score": round(total, 1),
            "dimensions": [{"label": label, "score": score, "weight": weight} for label, score, weight in parts],
        },
    }
    return signal


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 macro_signal.json(线上契约结构)")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR / "macro_signal.json"),
                        help="输出 macro_signal.json 路径")
    parser.add_argument("--conclusion", type=str, default="",
                        help="覆盖定性结论(默认按内置规则评分映射)")
    args = parser.parse_args()

    signal = build_signal(conclusion_override=args.conclusion or None)

    if not signal["details"]:
        logger.error("无任何可用指标(details 为空),不生成 macro_signal.json")
        return 1
    if not signal["data_date"]:
        logger.error("缺少 data_date(所有 CSV 均无有效月份),不生成 macro_signal.json")
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
