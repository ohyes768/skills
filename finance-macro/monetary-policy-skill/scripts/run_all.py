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
from typing import Literal

from fetch_common import setup_logging, to_iso_now
from fetch_dr007 import fetch_dr007_latest
from fetch_lpr import fetch_lpr_latest
from fetch_mlf_tavily import fetch_mlf_monthly_net


def build_payload(requested_month: str | None = None) -> dict:
    """构建数据载荷。

    各指标获取逻辑由各自脚本内部处理：
    - DR007：每日更新，直接查
    - MLF：每月2-3日发布，脚本内部自动降级未发布的月份
    - LPR：直接API获取最新值（每月20日发布）
    """
    today = datetime.now()
    requested_display = requested_month or "上月（默认）"

    with ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(fetch_dr007_latest)
        f2 = executor.submit(fetch_lpr_latest)
        f3 = executor.submit(fetch_mlf_monthly_net, requested_month)
        dr007, lpr, mlf = f1.result(), f2.result(), f3.result()

    # MLF 脚本内部已处理月份降级，从返回值中获取实际月份
    actual_mlf_month = mlf.get("actual_month", requested_month or "unknown")
    mlf_type = "prev" if mlf.get("requested_month") != actual_mlf_month else "same"

    return {
        "as_of_date": today.strftime("%Y-%m-%d"),
        "requested_month": requested_display,
        "actual_fetched_month": {
            "mlf": actual_mlf_month,
        },
        "data_month_type": {
            "mlf": mlf_type,
        },
        "publish_days": {
            "mlf": "每月2-3日发布（脚本自动降级未发布月份）",
            "lpr": "每月20日（直接API获取最新值）",
            "dr007": "每日更新",
        },
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
        help="目标月份（YYYY-MM），默认查上月",
    )
    args = parser.parse_args()

    setup_logging()
    payload = build_payload(requested_month=(args.month or None))

    # 输出数据可用性提示
    print(f"[数据可用性] 请求月份: {payload['requested_month']}")
    mlf_type_msg = "（请求月份数据）" if payload["data_month_type"]["mlf"] == "same" else "（上月数据，因发布日未到）"
    print(f"[数据可用性] MLF实际获取: {payload['actual_fetched_month']['mlf']} {mlf_type_msg}")
    print(f"[数据可用性] LPR: {payload['publish_days']['lpr']}")
    print(f"[数据可用性] DR007: {payload['publish_days']['dr007']}")
    print()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n输出文件: {out_path}")


if __name__ == "__main__":
    main()
