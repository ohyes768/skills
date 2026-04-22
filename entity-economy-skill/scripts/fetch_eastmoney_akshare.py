#!/usr/bin/env python3
"""
通过 akshare 抓取 5 个实体经济核心指标：
- 制造业 PMI / 非制造业 PMI
- 工业增加值
- 城镇固定资产投资
- 社会消费品零售总额

数据以追加去重方式写入 data/{indicator}/ 目录。
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 确保 fetch_common 可导入（本地 scripts 目录优先）
_SCRIPT_DIR = Path(__file__).resolve().parent
_LOCAL_COMMON = _SCRIPT_DIR / "fetch_common.py"
_PARENT_COMMON = (
    Path(__file__).resolve().parents[2]
    / "monetary-policy-skill"
    / "scripts"
    / "fetch_common.py"
)
# 确保本地路径在最前（先去重，再插到 0 位）
for _p in [str(_SCRIPT_DIR), str(_PARENT_COMMON.parent)]:
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(_SCRIPT_DIR))  # 本地永远优先

import pandas as pd
import akshare as ak
from fetch_common import setup_logging, to_iso_now, LOGGER

# 指标配置：(akshare 函数名, 数据目录, CSV 文件名, 关键列映射)
INDICATOR_CONFIG: dict[str, dict[str, Any]] = {
    "pmi": {
        "func": ak.macro_china_pmi,
        "dir": "pmi_manufacturing",
        "file": "pmi_m.csv",
        "indicator": "pmi_m",
        "desc": "制造业/非制造业 PMI",
    },
    "gyzjz": {
        "func": ak.macro_china_gyzjz,
        "dir": "gyzjz",
        "file": "gyzjz.csv",
        "indicator": "gyzjz",
        "desc": "工业增加值",
    },
    "gdzctz": {
        "func": ak.macro_china_gdzctz,
        "dir": "gdzctz",
        "file": "gdzctz.csv",
        "indicator": "gdzctz",
        "desc": "城镇固定资产投资",
    },
    "consumer_retail": {
        "func": ak.macro_china_consumer_goods_retail,
        "dir": "consumer_retail",
        "file": "consumer_retail.csv",
        "indicator": "consumer_retail",
        "desc": "社会消费品零售总额",
    },
}


def ensure_dir(base_dir: Path, sub_dir: str) -> Path:
    path = base_dir / sub_dir
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_existing_months(csv_path: Path) -> set[str]:
    """读取已有 CSV 的月份集合，用于去重。"""
    if not csv_path.exists():
        return set()
    months: set[str] = set()
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            month = row.get("月份", "").strip()
            if month:
                months.add(month)
    return months


def save_incremental(
    df_rows: list[dict[str, Any]],
    csv_path: Path,
    existing_months: set[str],
    indicator: str,
) -> int:
    """增量写入：跳过已有月份，返回新增行数。"""
    new_rows = [r for r in df_rows if r.get("月份", "").strip() not in existing_months]
    if not new_rows:
        LOGGER.info("  %s: 无新数据，跳过写入", csv_path.name)
        return 0

    fieldnames = list(df_rows[0].keys())
    fetched_at = to_iso_now()

    for row in new_rows:
        row["fetched_at"] = fetched_at
        row["indicator"] = indicator

    file_exists = csv_path.exists()
    with open(csv_path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(new_rows)

    LOGGER.info("  %s: 新增 %d 行 → %s", csv_path.name, len(new_rows), csv_path)
    return len(new_rows)


def normalize_month(month_str: str) -> str:
    """将 akshare 返回的月份格式统一为 '2026年03月份' 格式。"""
    # akshare 返回格式如 "2026-03" 或 "2026年03月"
    s = month_str.strip()
    # 如果是 2026-03 格式，转为 2026年03月份
    import re

    m = re.match(r"(\d{4})-(\d{2})", s)
    if m:
        return f"{m.group(1)}年{m.group(2)}月份"
    # 如果已经是 2026年03月份 格式，直接返回
    if "月份" not in s and "月" in s:
        return s.replace("月", "月份")
    return s


def fetch_indicator(
    key: str,
    config: dict[str, Any],
    data_dir: Path,
) -> int:
    """抓取单个指标，返回新增行数。"""
    LOGGER.info("抓取 %s: %s", key, config["desc"])

    try:
        df = config["func"]()
    except Exception as exc:
        LOGGER.warning("  %s 调用失败: %s", key, exc)
        return 0

    if df is None or df.empty:
        LOGGER.warning("  %s 返回空数据", key)
        return 0

    # 标准化列名
    df.columns = [c.strip() for c in df.columns]

    # 找出月份/日期列并标准化
    date_col = None
    for col in ["月份", "日期", "TRADE_DATE", "统计日期"]:
        if col in df.columns:
            date_col = col
            break
    if date_col is None:
        LOGGER.warning("  %s 未找到月份列，可用列: %s", key, list(df.columns))
        return 0

    # 标准化月份格式
    df["月份"] = df[date_col].apply(lambda x: normalize_month(str(x)) if pd_notnull(x) else "")

    # 只保留有月份的行
    df = df[df["月份"] != ""].copy()

    # 删除月份重复行，保留最后一条（最新数据）
    df = df.drop_duplicates(subset=["月份"], keep="last")

    # 按月份降序排列
    df = df.sort_values("月份", ascending=False)

    # 转为 dict 列表
    rows = df.to_dict(orient="records")

    csv_path = data_dir / config["dir"] / config["file"]
    existing_months = read_existing_months(csv_path)
    return save_incremental(rows, csv_path, existing_months, config["indicator"])


def pd_notnull(val: Any) -> bool:
    """兼容 pandas 和普通值的 notnull 检查。"""
    if hasattr(val, "__float__"):
        import numpy as np

        return not np.isnan(float(val))
    return val is not None and str(val).strip() != ""


def main() -> None:
    parser = argparse.ArgumentParser(description="通过 akshare 抓取实体经济指标")
    parser.add_argument(
        "--indicators",
        type=str,
        default="all",
        help="指标名称（逗号分隔），如 pmi,gyzjz,gdzctz,consumer_retail；默认 all",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="",
        help="数据根目录，默认使用脚本所在目录的 data/",
    )
    args = parser.parse_args()

    setup_logging()

    if args.data_dir:
        base_dir = Path(args.data_dir)
    else:
        base_dir = _SCRIPT_DIR.parent / "data"

    if args.indicators == "all":
        targets = list(INDICATOR_CONFIG.keys())
    else:
        targets = [t.strip() for t in args.indicators.split(",")]

    total_new = 0
    for key in targets:
        if key not in INDICATOR_CONFIG:
            LOGGER.warning("未知指标: %s，可用: %s", key, list(INDICATOR_CONFIG.keys()))
            continue
        config = INDICATOR_CONFIG[key]
        ensure_dir(base_dir, config["dir"])
        n = fetch_indicator(key, config, base_dir)
        total_new += n

    LOGGER.info("完成，共新增 %d 行", total_new)


if __name__ == "__main__":
    main()
