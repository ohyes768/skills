#!/usr/bin/env python3
"""统一抓取 M1/M2 和社融数据，并输出 JSON。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal

# 将 monetary-policy-skill/scripts 加入路径，以复用 fetch_common
MONETARY_SKILL_DIR = Path(__file__).resolve().parents[2] / "monetary-policy-skill" / "scripts"
if MONETARY_SKILL_DIR.exists() and str(MONETARY_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(MONETARY_SKILL_DIR))

env_path = Path(__file__).resolve().parents[2] / "monetary-policy-skill" / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")

from fetch_common import build_session, setup_logging, to_iso_now
from fetch_m1_m2 import fetch_m1_m2_latest, fetch_m1_m2_historical
from fetch_social_financing_tavily import fetch_social_financing_monthly

# 数据发布时间：每月13日（中国人民银行调查统计司发布金融统计数据报告）
PUBLISH_DAY = 13


def determine_target_month(requested_month: str | None) -> tuple[str, Literal["same", "prev"]]:
    """判断实际应查的月份和数据所属月份。

    社融/M1M2 数据通常每月13-15日发布（如3月数据在4月13-15日发布）。

    返回: (实际查询月份, 数据属于的月份相对于请求的月份)
    """
    today = datetime.now()

    # 用户未指定月份 → 默认查上月
    if not requested_month:
        prev_month = get_prev_month(today)
        return prev_month, "prev"

    # 解析请求月份
    req_year, req_month = map(int, requested_month.split("-"))

    # 计算目标月份的下月13日
    if req_month == 12:
        publish_month_dt = datetime(req_year + 1, 1, PUBLISH_DAY)
    else:
        publish_month_dt = datetime(req_year, req_month + 1, PUBLISH_DAY)

    # 数据已发布 → 直接查请求月份
    if today >= publish_month_dt:
        return requested_month, "same"

    # 数据未发布 → 查上一月
    prev_month = get_prev_month(datetime(req_year, req_month, 1))
    return prev_month, "prev"


def get_prev_month(dt: datetime) -> str:
    """给定日期所在月的上一个月。"""
    if dt.month == 1:
        return f"{dt.year - 1}-12"
    return f"{dt.year}-{dt.month - 1:02d}"


def build_payload(requested_month: str | None = None) -> dict:
    """构建数据载荷。

    包含数据可用性判断逻辑，自动决定查"本月"还是"上月"。
    """
    actual_month, month_type = determine_target_month(requested_month)
    requested_for_display = requested_month or f"{get_prev_month(datetime.now())}（默认上月）"

    session = build_session()

    m1m2_hist_raw = fetch_m1_m2_historical(session, 6)
    sf = fetch_social_financing_monthly(actual_month)

    m1m2_hist = m1m2_hist_raw if isinstance(m1m2_hist_raw, dict) and "error" not in m1m2_hist_raw else {"latest": None, "historical": [], "error": str(m1m2_hist_raw)}

    latest_m1m2 = m1m2_hist.get("latest") or {}

    return {
        "as_of_date": datetime.now().strftime("%Y-%m-%d"),
        "requested_month": requested_for_display,
        "actual_fetched_month": actual_month,
        "data_month_type": month_type,  # "same"=请求月份数据, "prev"=上月数据（因发布日未到）
        "publish_day": PUBLISH_DAY,
        "m1_m2": {
            "latest": {
                "m2_yi": latest_m1m2.get("m2"),
                "m2_yoy": latest_m1m2.get("m2_yoy"),
                "m1_yi": latest_m1m2.get("m1"),
                "m1_yoy": latest_m1m2.get("m1_yoy"),
                "m0_yi": latest_m1m2.get("m0"),
                "m0_yoy": latest_m1m2.get("m0_yoy"),
                "m1_m2_spread": latest_m1m2.get("m1_m2_spread"),
            },
            "history": m1m2_hist.get("historical", []),
            "source": "eastmoney",
        },
        "social_financing": {
            "monthly_new_yi": sf.get("monthly_new_financing_yi"),
            "monthly_new_yoy_pct": sf.get("monthly_new_yoy_percent"),
            "balance_yi": sf.get("total_financing_balance_yi"),
            "balance_yoy_pct": sf.get("balance_yoy_percent"),
            "balance_yoy_prev_month": sf.get("balance_yoy_prev_month"),
            "balance_yoy_change_pp": sf.get("balance_yoy_change_pp"),
            "prev_month": sf.get("prev_month"),
            "month": sf.get("month"),
            "source_url": sf.get("source_url"),
            "parse_status": sf.get("parse_status"),
        },
        "fetched_at": to_iso_now(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 M1/M2 和社融数据")
    parser.add_argument(
        "--output",
        default="data/money_supply_latest.json",
        help="输出文件路径（默认 data/money_supply_latest.json）",
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
    month_type_msg = "（请求月份数据）" if payload["data_month_type"] == "same" else "（上月数据，因发布日未到）"
    print(f"[数据可用性] 请求月份: {payload['requested_month']}")
    print(f"[数据可用性] 实际获取: {payload['actual_fetched_month']} {month_type_msg}")
    print()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n输出文件: {out_path}")


if __name__ == "__main__":
    main()
