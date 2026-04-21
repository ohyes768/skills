#!/usr/bin/env python3
"""
从 akshare 抓取 LPR（贷款市场报价利率）最新值（1年期、5年期以上）。
"""

from __future__ import annotations

import argparse
import json
from typing import Any

import akshare as ak

from fetch_common import read_cache, setup_logging, to_iso_now, write_cache, LOGGER


def fetch_lpr_latest() -> dict[str, Any]:
    result: dict[str, Any] = {
        "lpr_1y": None,
        "lpr_5y_plus": None,
        "prev_lpr_1y": None,
        "prev_lpr_5y_plus": None,
        "unit": "%",
        "source_url": "https://akshare.akfamily.xyz",
        "published_at": None,
        "month": None,
        "fetched_at": to_iso_now(),
        "parse_status": "failed",
        "provider": "akshare",
    }

    try:
        df = ak.macro_china_lpr()
        # 筛选有效数据，按日期降序
        df_valid = df[df["LPR1Y"].notna()].sort_values("TRADE_DATE", ascending=False)

        if df_valid.empty:
            result["error"] = "无有效 LPR 数据"
            return result

        latest = df_valid.iloc[0]
        prev = df_valid.iloc[1] if len(df_valid) > 1 else None

        result["lpr_1y"] = float(latest["LPR1Y"])
        result["lpr_5y_plus"] = float(latest["LPR5Y"])
        result["published_at"] = str(latest["TRADE_DATE"])
        result["month"] = str(latest["TRADE_DATE"])[:7]  # YYYY-MM

        if prev is not None:
            result["prev_lpr_1y"] = float(prev["LPR1Y"])
            result["prev_lpr_5y_plus"] = float(prev["LPR5Y"])

        result["parse_status"] = "ok"

        # 写入月度缓存
        if result["month"]:
            write_cache("lpr", result["month"], result)

        LOGGER.info(
            "LPR 获取成功 [%s]: 1Y=%.2f%%, 5Y+=%.2f%%（上月: 1Y=%.2f%%, 5Y+=%.2f%%）",
            result["month"],
            result["lpr_1y"],
            result["lpr_5y_plus"],
            result["prev_lpr_1y"] or 0,
            result["prev_lpr_5y_plus"] or 0,
        )
        return result

    except Exception as exc:
        LOGGER.warning("LPR 获取失败: %s", exc)
        result["error"] = str(exc)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 LPR 最新值")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    args = parser.parse_args()

    setup_logging()
    data = fetch_lpr_latest()
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()
