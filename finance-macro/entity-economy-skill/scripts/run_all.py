#!/usr/bin/env python3
"""
统一抓取全部5个实体经济核心指标，并输出 JSON。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── 路径设置（本地 fetch_common 优先）─────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_LOCAL_COMMON = _SCRIPT_DIR / "fetch_common.py"
_MONETARY_COMMON = (
    Path(__file__).resolve().parents[2]
    / "monetary-policy-skill"
    / "scripts"
    / "fetch_common.py"
)
for _p in [str(_SCRIPT_DIR), str(_MONETARY_COMMON.parent)]:
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(_SCRIPT_DIR))

# 加载 .env（从 monetary-policy-skill 复用）
env_path = (
    Path(__file__).resolve().parents[2]
    / "monetary-policy-skill"
    / ".env"
)
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from fetch_common import setup_logging, to_iso_now

from fetch_eastmoney_akshare import (
    fetch_indicator,
    INDICATOR_CONFIG,
    ensure_dir,
)
from fetch_electricity_consumption import fetch_electricity_consumption_monthly
from fetch_railway_freight import fetch_railway_freight_monthly
from fetch_pbc_credit_balance import fetch_pbc_credit_balance


# 数据发布时间（每月）
PUBLISH_DAYS = {
    "pmi": 1,          # 每月1日
    "gyzjz": 18,       # 每月18日
    "gdzctz": 18,      # 每月18日
    "consumer_retail": 18,  # 每月18日
    "electricity": 20,  # 每月20日
    "railway_freight": 7,   # 每月7日
    "pbc_credit": 20,   # 每月20日
}


def _default_month(publish_day: int) -> str:
    """根据发布日推断当前应查的月份（已发布的上月）。"""
    today = datetime.now(timezone.utc)
    day = today.day
    if day >= publish_day:
        # 数据已发布，查上月
        month = today.month - 1 or 12
        year = today.year if today.month > 1 else today.year - 1
    else:
        # 数据未发布，查上上月
        month = today.month - 2 or (12 if today.month > 2 else 12)
        year = today.year if today.month > 2 else today.year - 1
    return f"{year}-{month:02d}"


def _fetch_all_akshare(base_dir: Path) -> dict[str, Any]:
    """抓取 PMI、工业增加值、固定资产投资、消费品零售（akshare）。"""
    results: dict[str, Any] = {}
    for key in INDICATOR_CONFIG:
        config = INDICATOR_CONFIG[key]
        ensure_dir(base_dir, config["dir"])
        n = fetch_indicator(key, config, base_dir)
        results[key] = {"new_rows": n, "indicator": config["indicator"]}
    return results


def fetch_all(requested_month: str | None = None) -> dict[str, Any]:
    """统一抓取全部5个实体经济指标。"""
    today = datetime.now(timezone.utc)

    # 各指标实际月份
    pmi_month = _default_month(PUBLISH_DAYS["pmi"])
    gyzjz_month = _default_month(PUBLISH_DAYS["gyzjz"])
    elec_month = _default_month(PUBLISH_DAYS["electricity"])
    rail_month = _default_month(PUBLISH_DAYS["railway_freight"])
    pbc_month = _default_month(PUBLISH_DAYS["pbc_credit"])

    base_dir = _SCRIPT_DIR.parent / "data"
    base_dir.mkdir(parents=True, exist_ok=True)

    # 并行抓取（akshare 4项 + 电力 + 铁路 + 央行信贷）
    with ThreadPoolExecutor(max_workers=7) as executor:
        f_akshare = executor.submit(_fetch_all_akshare, base_dir)
        f_elec = executor.submit(fetch_electricity_consumption_monthly, elec_month)
        f_rail = executor.submit(fetch_railway_freight_monthly, rail_month)
        f_pbc = executor.submit(fetch_pbc_credit_balance, pbc_month)

        akshare_results = f_akshare.result()
        elec_result = f_elec.result()
        rail_result = f_rail.result()
        pbc_result = f_pbc.result()

    return {
        "as_of_date": today.strftime("%Y-%m-%d"),
        "fetched_at": to_iso_now(),
        "requested_month": requested_month,
        "actual_months": {
            "pmi": pmi_month,
            "gyzjz": gyzjz_month,
            "electricity": elec_month,
            "railway_freight": rail_month,
            "pbc_credit": pbc_month,
        },
        "publish_days": PUBLISH_DAYS,
        "data": {
            "akshare": akshare_results,
            "electricity": elec_result,
            "railway_freight": rail_result,
            "pbc_credit": pbc_result,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取全部实体经济指标")
    parser.add_argument(
        "--output",
        default="data/entity_economy_latest.json",
        help="输出文件路径",
    )
    args = parser.parse_args()

    setup_logging()
    payload = fetch_all()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n输出文件: {out_path}")


if __name__ == "__main__":
    main()
