#!/usr/bin/env python3
"""
统一抓取 DR007、MLF、LPR，并输出 JSON。
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fetch_common import setup_logging, to_iso_now
from fetch_dr007 import fetch_dr007_latest
from fetch_lpr import fetch_lpr_latest
from fetch_mlf_tavily import fetch_mlf_monthly_net


def get_default_month() -> str:
    """上个月（MLF 净投放在月初公布，默认查上月）"""
    today = datetime.now()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


def to_prev_month(year_month: str) -> str:
    """将 YYYY-MM 转为上月 YYYY-MM"""
    y, m = year_month.split("-")
    y, m = int(y), int(m)
    if m == 1:
        return f"{y - 1}-12"
    return f"{y}-{m - 1:02d}"


def build_payload(month: str | None = None) -> dict:
    target_month = month or get_default_month()
    # MLF 净投放对应的是 target_month 的上一个月（次月1，2号公布）
    mlf_month = to_prev_month(target_month)
    with ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(fetch_dr007_latest)
        f2 = executor.submit(fetch_lpr_latest)
        f3 = executor.submit(fetch_mlf_monthly_net, mlf_month)
        dr007, lpr, mlf = f1.result(), f2.result(), f3.result()

    return {
        "as_of_date": datetime.now().strftime("%Y-%m-%d"),
        "dr007": dr007,
        "mlf": mlf,
        "lpr": lpr,
        "fetched_at": to_iso_now(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 DR007/MLF/LPR 最新指标")
    parser.add_argument(
        "--output",
        default="data/monetary_indicators_latest.json",
        help="输出文件路径（默认 data/monetary_indicators_latest.json）",
    )
    parser.add_argument(
        "--month",
        default="",
        help="目标月份（YYYY-MM）",
    )
    args = parser.parse_args()

    setup_logging()
    payload = build_payload(month=(args.month or None))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n输出文件: {out_path}")


if __name__ == "__main__":
    main()
