#!/usr/bin/env python3
"""
统一抓取 CPI、PPI 和核心CPI数据，并缓存到 data/YYYY-MM/ 目录。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from fetch_common import now as _now
from fetch_cpi import fetch_cpi
from fetch_ppi import fetch_ppi
from fetch_core_cpi_tavily import fetch_core_cpi


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 CPI、PPI 和核心CPI")
    parser.add_argument("--month", type=str, default=None, help="指定月份 YYYY-MM（默认最新）")
    args = parser.parse_args()

    target_month = args.month  # 由 core_cpi 内部处理降级，CPI/PPI 用最新数据

    print("=== CPI 抓取 ===")
    cpi = fetch_cpi(target_month)
    print(json.dumps(cpi, ensure_ascii=False, indent=2))

    print("\n=== PPI 抓取 ===")
    ppi = fetch_ppi(target_month)
    print(json.dumps(ppi, ensure_ascii=False, indent=2))

    # 实际月份由 core_cpi 内部降级逻辑决定
    actual_for_core = cpi.get("month") or ppi.get("month")
    if actual_for_core:
        print(f"\n=== 核心CPI 抓取 ({actual_for_core}) ===")
        core_cpi = fetch_core_cpi(actual_for_core)
        print(json.dumps(core_cpi, ensure_ascii=False, indent=2))
    else:
        core_cpi = {}

    combined = {
        "month": actual_for_core,
        "fetched_at": _now(),
        "cpi": cpi,
        "ppi": ppi,
        "core_cpi": core_cpi,
    }

    if actual_for_core:
        data_dir = Path(__file__).resolve().parents[1] / "data" / actual_for_core
        data_dir.mkdir(parents=True, exist_ok=True)
        out = data_dir / "inflation.json"
        out.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n已写入 {out}")


if __name__ == "__main__":
    main()
