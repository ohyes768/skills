#!/usr/bin/env python3
"""
抓取两市成交额和换手率数据
仅使用沪深交易所官方API（真实汇总数据）：
  - 上交所: https://www.sse.com.cn/market/stockdata/overview/day/
  - 深交所: https://www.szse.cn/market/overview/index.html
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fetch_common import (
    LOGGER,
    read_cache,
    setup_logging,
    to_iso_now,
    write_cache,
)


def fetch_turnover_month_series(month: str, end_date: str | None = None) -> list[dict[str, Any]]:
    """逐日拉取当月上交所加权换手率，返回按读数日升序的列表。

    月均口径：只取当月内实际取到的交易日读数，缺失日跳过，
    分母为实际取到的交易日数；缓存优先（finance-macro/cache/turnover/），缺日才回源。
    注意 fetch_sse_turnover 查非交易日会回退到前一交易日，序列按返回的读数日去重。
    """
    from datetime import datetime, timedelta

    from fetch_volume_exchange import fetch_sse_turnover

    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    try:
        start = datetime.strptime(f"{month}-01", "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        LOGGER.warning("换手率月序列参数非法: month=%s end_date=%s", month, end_date)
        return []
    if end < start:
        return []

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    current = start
    while current <= end:
        if current.weekday() >= 5:  # 周末直接跳过，不发请求
            current += timedelta(days=1)
            continue
        date_str = current.strftime("%Y-%m-%d")
        current += timedelta(days=1)

        cached = read_cache("turnover", date_str)
        if cached and isinstance(cached.get("turnover_rate"), (int, float)):
            read_date = cached.get("date") or date_str
            if read_date not in seen:
                rows.append({"date": read_date, "turnover_rate": cached["turnover_rate"]})
                seen.add(read_date)
            continue

        sse_data = fetch_sse_turnover(date_str)
        if sse_data.get("status") != "ok":
            continue  # 非交易日/接口异常：跳过该日
        read_date = sse_data.get("date") or date_str
        if read_date not in seen:
            rows.append({"date": read_date, "turnover_rate": sse_data["turnover_rate"]})
            seen.add(read_date)
            # 按读数日写缓存，与返回值自洽（回退场景避免重复回源）
            write_cache("turnover", read_date, sse_data)

    rows.sort(key=lambda r: r["date"])
    return rows


def fetch_turnover_rate(days: int = 5) -> dict[str, Any]:
    """
    获取换手率数据，仅使用上交所官方API加权平均换手率
    """
    from fetch_volume_exchange import get_trade_date, fetch_sse_turnover
    trade_date = get_trade_date()

    cached = read_cache("turnover", trade_date)
    if cached:
        LOGGER.info("使用缓存: turnover/%s", trade_date)
        return cached

    result: dict[str, Any] = {
        "date": None,
        "turnover_rate": None,
        "volume": None,
        "amount": None,
        "amount_yi": None,
        "change_pct": None,
        "source": "exchange_official",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    try:
        sse_data = fetch_sse_turnover(trade_date)
        if sse_data.get("status") == "ok":
            result.update({
                "date": sse_data.get("date"),
                "turnover_rate": sse_data.get("turnover_rate"),
                "status": "ok",
            })
            write_cache("turnover", trade_date, result)
            LOGGER.info("换手率获取成功: %.4f%% (日期=%s)", result["turnover_rate"], result["date"])
            return result
        else:
            LOGGER.warning("上交所换手率获取失败: status=%s", sse_data.get("status"))
    except Exception as exc:
        LOGGER.warning("上交所换手率API异常: %s", exc)
        result["error"] = str(exc)

    return result


def fetch_market_volume(days: int = 5) -> dict[str, Any]:
    """
    获取沪深两市合计成交额，仅使用交易所官方API
    """
    from fetch_volume_exchange import fetch_both_exchanges

    result: dict[str, Any] = {
        "date": None,
        "sh_amount_yi": None,
        "sz_amount_yi": None,
        "total_amount_yi": None,
        "source": "exchange_official",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    try:
        exchange_data = fetch_both_exchanges()
        if exchange_data.get("status") in ("ok", "partial"):
            result.update({
                "date": exchange_data.get("date"),
                "sh_amount_yi": exchange_data.get("sh_amount_yi"),
                "sz_amount_yi": exchange_data.get("sz_amount_yi"),
                "total_amount_yi": exchange_data.get("total_amount_yi"),
                "status": "ok",
            })
            LOGGER.info("两市成交额获取成功: 沪市=%.2f亿, 深市=%.2f亿, 合计=%.2f亿",
                        result["sh_amount_yi"] or 0, result["sz_amount_yi"] or 0, result["total_amount_yi"] or 0)
            return result
        else:
            LOGGER.warning("交易所API返回status=%s", exchange_data.get("status"))
    except Exception as exc:
        LOGGER.warning("两市成交额获取异常: %s", exc)
        result["error"] = str(exc)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取两市成交额和换手率")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    parser.add_argument("--days", type=int, default=5, help="历史数据天数")
    args = parser.parse_args()

    setup_logging()

    volume_data = fetch_market_volume(args.days)
    turnover_data = fetch_turnover_rate(days=args.days)
    data = {
        "volume": volume_data,
        "turnover": turnover_data,
    }

    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()