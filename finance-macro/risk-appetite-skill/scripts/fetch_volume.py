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
    """逐日拉取当月两市加权换手率，返回按读数日升序的列表。

    沪市取上交所加权换手率，深市取成交额/流通市值；两市按成交额加权合成。
    月均口径：只取当月内实际取到的交易日读数，缺失日跳过，
    分母为实际取到的交易日数；缓存优先（finance-macro/cache/turnover/），缺日才回源。
    注意两市底层抓取查非交易日会回退到前一交易日，序列按返回的读数日去重。
    """
    from datetime import datetime, timedelta

    from fetch_volume_exchange import fetch_sse_turnover, fetch_szse_turnover

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
        if cached and isinstance(cached.get("turnover_rate"), (int, float)) and cached.get("sz_turnover_rate") is not None:
            read_date = cached.get("date") or date_str
            if read_date not in seen:
                rows.append({"date": read_date, "turnover_rate": cached["turnover_rate"]})
                seen.add(read_date)
            continue

        sse_data = fetch_sse_turnover(date_str)
        szse_data = fetch_szse_turnover(date_str)
        if sse_data.get("status") != "ok" or szse_data.get("status") != "ok":
            continue  # 非交易日/接口异常：跳过该日
        sh_rate = sse_data.get("turnover_rate")
        sz_rate = szse_data.get("turnover_rate")
        sh_amt = sse_data.get("amount_yi") or 0.0
        sz_amt = szse_data.get("amount_yi") or 0.0
        if sh_rate is None or sz_rate is None or (sh_amt + sz_amt) <= 0:
            continue
        combined = round((sh_amt * sh_rate + sz_amt * sz_rate) / (sh_amt + sz_amt), 4)
        read_date = sse_data.get("date") or szse_data.get("date") or date_str
        if read_date not in seen:
            rows.append({"date": read_date, "turnover_rate": combined})
            seen.add(read_date)
            # 按读数日写缓存（两市结构），与返回值自洽（回退场景避免重复回源）
            write_cache("turnover", read_date, {
                "date": read_date,
                "sh_turnover_rate": sh_rate,
                "sz_turnover_rate": sz_rate,
                "sh_amount_yi": sh_amt,
                "sz_amount_yi": sz_amt,
                "turnover_rate": combined,
                "source": "exchange_official",
                "fetched_at": to_iso_now(),
                "status": "ok",
            })

    rows.sort(key=lambda r: r["date"])
    return rows


def fetch_turnover_rate(days: int = 5) -> dict[str, Any]:
    """
    获取两市加权换手率（沪市+深市按成交额加权合成）。

    沪市取上交所官方加权平均换手率，深市由成交额/流通市值计算；
    两市按成交额加权合成全市场换手率。单市缺失时退化为单值（partial）。
    """
    from fetch_volume_exchange import get_trade_date, fetch_sse_turnover, fetch_szse_turnover

    trade_date = get_trade_date()

    cached = read_cache("turnover", trade_date)
    if cached and cached.get("sz_turnover_rate") is not None:
        LOGGER.info("使用缓存: turnover/%s", trade_date)
        return cached

    result: dict[str, Any] = {
        "date": None,
        "sh_turnover_rate": None,
        "sz_turnover_rate": None,
        "sh_amount_yi": None,
        "sz_amount_yi": None,
        "turnover_rate": None,
        "source": "exchange_official",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    try:
        sse_data = fetch_sse_turnover(trade_date)
        szse_data = fetch_szse_turnover(trade_date)

        sh_rate = sse_data.get("turnover_rate")
        sh_amt = sse_data.get("amount_yi")
        sz_rate = szse_data.get("turnover_rate")
        sz_amt = szse_data.get("amount_yi")

        result.update({
            "date": sse_data.get("date") or szse_data.get("date"),
            "sh_turnover_rate": sh_rate,
            "sz_turnover_rate": sz_rate,
            "sh_amount_yi": sh_amt,
            "sz_amount_yi": sz_amt,
        })

        # 两市按成交额加权合成
        if sh_rate is not None and sz_rate is not None and ((sh_amt or 0) + (sz_amt or 0)) > 0:
            combined = (sh_amt * sh_rate + sz_amt * sz_rate) / (sh_amt + sz_amt)
            result["turnover_rate"] = round(combined, 4)
            result["status"] = "ok"
            write_cache("turnover", trade_date, result)
            LOGGER.info("两市加权换手率: %.4f%% (沪=%.4f%% 深=%.4f%%, 日期=%s)",
                        combined, sh_rate, sz_rate, result["date"])
            return result

        # 单市可用时退化为单值
        single = sh_rate if sh_rate is not None else sz_rate
        if single is not None:
            result["turnover_rate"] = round(single, 4)
            result["status"] = "partial"
            write_cache("turnover", trade_date, result)
            LOGGER.warning("仅单市换手率可用，退化为单值: %.4f%%", single)
            return result

        LOGGER.warning("换手率获取失败: 沪=%s 深=%s", sh_rate, sz_rate)
    except Exception as exc:
        LOGGER.warning("换手率获取异常: %s", exc)
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