#!/usr/bin/env python3
"""
从 akshare 抓取 CPI（居民消费价格指数）数据。
国家统计局每月9日发布上月数据（如3月数据在4月9日发布）。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

import akshare as ak

from fetch_common import (
    clean_month,
    is_valid_month,
    now as _now,
    published_month,
    read_cache,
    setup_logging,
    to_float,
    write_cache,
    year_month,
    LOGGER,
)

# CPI/PPI 数据发布时间：每月9日
PUBLISH_DAY = 9


def fetch_cpi(month: str | None = None) -> dict[str, Any]:
    """抓取 CPI 数据，支持指定月份。

    Args:
        month: YYYY-MM 格式目标月份，默认最新。数据未发布时自动降级到上月。
    """
    result: dict[str, Any] = {
        "cpi_national_yoy": None,
        "cpi_national_mom": None,
        "cpi_national_cumulative": None,
        "cpi_urban_yoy": None,
        "cpi_rural_yoy": None,
        "core_cpi_yoy": None,
        "unit": "%",
        "source_url": "https://akshare.akfamily.xyz",
        "published_at": None,
        "month": None,
        "fetched_at": _now(),
        "parse_status": "failed",
        "provider": "akshare",
    }

    today = datetime.now(timezone.utc)

    # 月份降级逻辑
    if month:
        if not is_valid_month(month):
            result["error"] = f"month 格式错误: {month}"
            return result
        actual_month = published_month(month, today, PUBLISH_DAY)
        if actual_month != month:
            LOGGER.info("请求月份 %s，数据尚未发布，降级到 %s", month, actual_month)
    else:
        actual_month = None

    # 缓存优先
    if actual_month:
        cached = read_cache("cpi", actual_month)
        if cached:
            LOGGER.info("CPI 缓存命中 [%s]", actual_month)
            cached["requested_month"] = month
            return cached

    try:
        df = ak.macro_china_cpi()
        df = df.sort_values("月份", ascending=False)

        if df.empty:
            result["error"] = "无 CPI 数据"
            return result

        # 指定月份过滤
        if actual_month:
            month_pattern = f"{actual_month[:5]}年{int(actual_month[5:7]):02d}月"
            df_matched = df[df["月份"].str.startswith(month_pattern[:7], na=False)]
            if not df_matched.empty:
                latest = df_matched.iloc[0]
            else:
                # 月份数据不存在，用最新
                LOGGER.warning("未找到 %s 月 CPI，使用最新数据", actual_month)
                latest = df.iloc[0]
        else:
            latest = df.iloc[0]

        result["cpi_national_yoy"] = to_float(latest.get("全国-同比增长"))
        result["cpi_national_mom"] = to_float(latest.get("全国-环比增长"))
        result["cpi_national_cumulative"] = to_float(latest.get("全国-累计"))
        result["cpi_urban_yoy"] = to_float(latest.get("城市-同比增长"))
        result["cpi_rural_yoy"] = to_float(latest.get("农村-同比增长"))
        result["published_at"] = clean_month(str(latest.get("月份", "")))
        result["month"] = year_month(str(latest.get("月份", "")))
        result["parse_status"] = "ok"

        if result["month"]:
            write_cache("cpi", result["month"], result)

        LOGGER.info(
            "CPI 获取成功 [%s]: 同比=%.1f%%, 环比=%.1f%%, 累计=%.1f%%",
            result["month"],
            result["cpi_national_yoy"] or 0,
            result["cpi_national_mom"] or 0,
            result["cpi_national_cumulative"] or 0,
        )
        return result

    except Exception as exc:
        LOGGER.warning("CPI 获取失败: %s", exc)
        result["error"] = str(exc)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 CPI 数据")
    parser.add_argument("--month", type=str, default=None, help="目标月份 YYYY-MM（默认最新）")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    args = parser.parse_args()

    setup_logging()
    data = fetch_cpi(args.month)
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()
