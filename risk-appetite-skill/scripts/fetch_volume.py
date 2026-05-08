#!/usr/bin/env python3
"""
抓取两市成交额和换手率数据

优先使用沪深交易所官方API（真实汇总数据）：
  - 上交所: https://www.sse.com.cn/market/stockdata/overview/day/
  - 深交所: https://www.szse.cn/market/overview/index.html

Fallback 使用 akshare（指数成交额估算，有10-20%误差）

换手率：使用上证指数换手率作为全市场参考
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 确保本地 scripts 目录可导入
_SCRIPT_DIR = Path(__file__).resolve().parent
for _p in [str(_SCRIPT_DIR)]:
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(_SCRIPT_DIR))

import pandas as pd
import akshare as ak

from fetch_common import (
    LOGGER,
    read_cache,
    setup_logging,
    to_float,
    to_iso_now,
    write_cache,
)


# stock_zh_a_hist 返回的列名
HIST_COLUMNS = [
    "日期", "股票代码", "开盘", "收盘", "最高", "最低",
    "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"
]


def _detect_hist_columns(columns: list[str]) -> dict[str, str]:
    """检测历史行情数据的列名映射"""
    col_map: dict[str, str] = {}
    for col in columns:
        col_lower = col.lower()
        if "日期" in col or "date" in col_lower:
            col_map["date"] = col
        elif "成交额" in col or "amount" in col_lower:
            col_map["amount"] = col
        elif "成交量" in col or "volume" in col_lower:
            col_map["volume"] = col
        elif "换手率" in col or "turnover" in col_lower:
            col_map["turnover"] = col
        elif "涨跌幅" in col or "change" in col_lower:
            col_map["change_pct"] = col
    return col_map


def fetch_turnover_rate(symbol: str = "000001", days: int = 5) -> dict[str, Any]:
    """
    获取换手率数据

    优先使用上交所官方API（加权平均换手率）
    Fallback 使用 akshare（指数换手率）
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # 尝试读取缓存
    cached = read_cache("turnover", today)
    if cached:
        LOGGER.info("使用缓存: turnover/%s", today)
        return cached

    result: dict[str, Any] = {
        "date": None,
        "turnover_rate": None,
        "volume": None,
        "amount": None,
        "amount_yi": None,
        "change_pct": None,
        "source": "akshare",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    # 优先尝试上交所官方API
    try:
        from fetch_volume_exchange import fetch_sse_turnover
        sse_data = fetch_sse_turnover(today)
        if sse_data.get("status") == "ok":
            result.update({
                "date": sse_data.get("date"),
                "turnover_rate": sse_data.get("turnover_rate"),
                "source": "exchange_official",
                "status": "ok",
            })
            write_cache("turnover", today, result)
            LOGGER.info("换手率获取成功(官方API): %.4f%%", result["turnover_rate"])
            return result
    except Exception as exc:
        LOGGER.warning("上交所换手率API失败，切换到akshare fallback: %s", exc)

    # Fallback: 使用akshare指数换手率
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")

        df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date)
        df.columns = [c.strip() for c in df.columns]

        if df.empty:
            LOGGER.warning("获取到空数据")
            return result

        col_map = _detect_hist_columns(df.columns.tolist())
        latest = df.iloc[0]

        date_str = str(latest[col_map.get("date", df.columns[0])])[:10]
        turnover_rate = to_float(latest[col_map.get("turnover", df.columns[11])])
        volume = to_float(latest[col_map.get("volume", df.columns[6])])
        amount = to_float(latest[col_map.get("amount", df.columns[7])])
        change_pct = to_float(latest[col_map.get("change_pct", df.columns[9])])

        result.update({
            "date": date_str,
            "turnover_rate": round(turnover_rate, 2) if turnover_rate else None,
            "volume": int(volume) if volume else None,
            "amount": amount,
            "amount_yi": round(amount / 1e8, 2) if amount else None,
            "change_pct": round(change_pct, 2) if change_pct else None,
            "source": "akshare",
            "status": "ok",
        })

        write_cache("turnover", date_str, result)
        LOGGER.info("换手率数据获取成功: %s 换手率=%.2f%%, 成交额=%.2f亿",
                    date_str, turnover_rate or 0, (amount or 0) / 1e8)

    except Exception as exc:
        LOGGER.warning("换手率数据获取失败: %s", exc)
        result["error"] = str(exc)

    return result


def fetch_market_volume(days: int = 5) -> dict[str, Any]:
    """
    获取沪深两市合计成交额

    优先使用沪深交易所官方API（真实汇总数据）
    Fallback 使用 akshare（指数成交额估算）
    返回两市合计成交额（亿元）
    """
    result: dict[str, Any] = {
        "date": None,
        "sh_amount_yi": None,
        "sz_amount_yi": None,
        "total_amount_yi": None,
        "source": "akshare",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    # 优先尝试交易所官方API
    try:
        from fetch_volume_exchange import fetch_both_exchanges
        exchange_data = fetch_both_exchanges()
        if exchange_data.get("status") == "ok":
            result.update({
                "date": exchange_data.get("date"),
                "sh_amount_yi": exchange_data.get("sh_amount_yi"),
                "sz_amount_yi": exchange_data.get("sz_amount_yi"),
                "total_amount_yi": exchange_data.get("total_amount_yi"),
                "source": "exchange_official",
                "status": "ok",
            })
            LOGGER.info("两市成交额获取成功(官方API): 沪市=%.2f亿, 深市=%.2f亿, 合计=%.2f亿",
                        result["sh_amount_yi"] or 0, result["sz_amount_yi"] or 0, result["total_amount_yi"] or 0)
            return result
    except Exception as exc:
        LOGGER.warning("交易所官方API失败，切换到akshare fallback: %s", exc)

    # Fallback: 使用akshare指数成交额估算
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")

        # 上证指数 (000001) -> 沪市
        df_sh = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date=start_date, end_date=end_date)
        # 深证成指 (399001) -> 深市
        df_sz = ak.stock_zh_a_hist(symbol="399001", period="daily", start_date=start_date, end_date=end_date)

        if df_sh.empty or df_sz.empty:
            LOGGER.warning("市场成交额数据为空")
            return result

        df_sh.columns = [c.strip() for c in df_sh.columns]
        df_sz.columns = [c.strip() for c in df_sz.columns]

        # 检测列名
        col_map_sh = _detect_hist_columns(df_sh.columns.tolist())
        col_map_sz = _detect_hist_columns(df_sz.columns.tolist())

        latest_sh = df_sh.iloc[0]
        latest_sz = df_sz.iloc[0]

        # 提取成交额
        sh_amount = to_float(latest_sh[col_map_sh.get("amount", df_sh.columns[7])])
        sz_amount = to_float(latest_sz[col_map_sz.get("amount", df_sz.columns[7])])

        if sh_amount and sz_amount:
            total = sh_amount + sz_amount
        elif sh_amount:
            total = sh_amount * 2  # 粗略估算
        elif sz_amount:
            total = sz_amount * 2
        else:
            total = None

        result.update({
            "date": str(latest_sh[col_map_sh.get("date", df_sh.columns[0])])[:10],
            "sh_amount_yi": round(sh_amount / 1e8, 2) if sh_amount else None,
            "sz_amount_yi": round(sz_amount / 1e8, 2) if sz_amount else None,
            "total_amount_yi": round(total / 1e8, 2) if total else None,
            "source": "akshare",
            "status": "ok",
        })

        LOGGER.info("两市成交额获取成功(akshare): 沪市=%.2f亿, 深市=%.2f亿, 合计=%.2f亿",
                    result["sh_amount_yi"] or 0, result["sz_amount_yi"] or 0, result["total_amount_yi"] or 0)

    except Exception as exc:
        LOGGER.warning("akshare成交额获取也失败了: %s", exc)
        result["error"] = str(exc)

    return result


def fetch_history(days: int = 20) -> list[dict[str, Any]]:
    """获取最近N个交易日的成交额和换手率历史数据"""
    results = []

    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 30)).strftime("%Y%m%d")

        df_sh = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date=start_date, end_date=end_date)
        df_sz = ak.stock_zh_a_hist(symbol="399001", period="daily", start_date=start_date, end_date=end_date)

        df_sh.columns = [c.strip() for c in df_sh.columns]
        df_sz.columns = [c.strip() for c in df_sz.columns]

        col_map_sh = _detect_hist_columns(df_sh.columns.tolist())
        col_map_sz = _detect_hist_columns(df_sz.columns.tolist())

        # 取最近N天
        min_len = min(days, len(df_sh), len(df_sz))
        df_sh = df_sh.head(min_len)
        df_sz = df_sz.head(min_len)

        for i in range(min_len):
            row_sh = df_sh.iloc[i]
            row_sz = df_sz.iloc[i]

            sh_amount = to_float(row_sh[col_map_sh.get("amount", df_sh.columns[7])])
            sz_amount = to_float(row_sz[col_map_sz.get("amount", df_sz.columns[7])])
            turnover_rate = to_float(row_sh[col_map_sh.get("turnover", df_sh.columns[11])])

            results.append({
                "date": str(row_sh[col_map_sh.get("date", df_sh.columns[0])])[:10],
                "sh_amount_yi": round(sh_amount / 1e8, 2) if sh_amount else None,
                "sz_amount_yi": round(sz_amount / 1e8, 2) if sz_amount else None,
                "total_amount_yi": round((sh_amount + sz_amount) / 1e8, 2) if sh_amount and sz_amount else None,
                "turnover_rate": round(turnover_rate, 2) if turnover_rate else None,
            })

    except Exception as exc:
        LOGGER.warning("历史数据获取失败: %s", exc)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取两市成交额和换手率")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    parser.add_argument("--days", type=int, default=5, help="历史数据天数")
    parser.add_argument("--history", action="store_true", help="获取历史数据模式")
    args = parser.parse_args()

    setup_logging()

    if args.history:
        data = fetch_history(args.days)
    else:
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
