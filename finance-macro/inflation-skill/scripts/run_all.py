#!/usr/bin/env python3
"""
统一抓取 CPI、PPI 和核心CPI数据，输出 JSON 文件。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from fetch_common import now as _now, setup_logging
from fetch_cpi import fetch_cpi
from fetch_ppi import fetch_ppi
from fetch_core_cpi_tavily import fetch_core_cpi

# 统一输出目录：finance-macro/output/<skill 目录名>
_SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = str(_SKILL_DIR.parent / "output" / _SKILL_DIR.name / "inflation_latest.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 CPI、PPI 和核心CPI")
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        help="指定月份 YYYY-MM（默认查已发布的最新月份）",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"输出 JSON 文件路径（默认 {DEFAULT_OUTPUT}）",
    )
    args = parser.parse_args()

    setup_logging()

    target_month = args.month  # 由各抓取函数内部处理降级

    print("=== CPI 抓取 ===")
    cpi = fetch_cpi(target_month)
    print(json.dumps(cpi, ensure_ascii=False, indent=2))

    print("\n=== PPI 抓取 ===")
    ppi = fetch_ppi(target_month)
    print(json.dumps(ppi, ensure_ascii=False, indent=2))

    # 核心CPI使用CPI/PPI中实际获取的月份
    actual_for_core = cpi.get("month") or ppi.get("month")
    core_cpi: dict = {}
    if actual_for_core:
        print(f"\n=== 核心CPI 抓取 ({actual_for_core}) ===")
        core_cpi = fetch_core_cpi(actual_for_core)
        print(json.dumps(core_cpi, ensure_ascii=False, indent=2))

    combined = {
        "month": actual_for_core,
        "fetched_at": _now(),
        "cpi": cpi,
        "ppi": ppi,
        "core_cpi": core_cpi,
    }

    out_path = Path(args.output)
    if actual_for_core:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n已写入 {out_path}")


if __name__ == "__main__":
    main()
