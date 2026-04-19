#!/usr/bin/env python3
"""统一抓取 M1/M2 和社融数据，并输出 JSON。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

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


def get_default_month() -> str:
    """上个月（社融在月初公布，默认查上月）"""
    today = datetime.now()
    if today.month == 1:
        return f"{today.year - 1}-12"
    return f"{today.year}-{today.month - 1:02d}"


def build_payload(target_month: str | None = None) -> dict:
    month = target_month or get_default_month()
    session = build_session()

    m1m2_hist_raw = fetch_m1_m2_historical(session, 6)
    sf = fetch_social_financing_monthly(month)

    m1m2_hist = m1m2_hist_raw if isinstance(m1m2_hist_raw, dict) and "error" not in m1m2_hist_raw else {"latest": None, "historical": [], "error": str(m1m2_hist_raw)}

    latest_m1m2 = m1m2_hist.get("latest") or {}

    return {
        "as_of_date": datetime.now().strftime("%Y-%m-%d"),
        "month": month,
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
    payload = build_payload(target_month=(args.month or None))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n输出文件: {out_path}")


if __name__ == "__main__":
    main()
