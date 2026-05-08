#!/usr/bin/env python3
"""
两市成交额爬虫 - 直接抓取沪深交易所官方数据
数据来源：
  - 上交所: https://www.sse.com.cn/market/stockdata/overview/day/
  - 深交所: https://www.szse.cn/market/overview/index.html
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import requests

from fetch_common import LOGGER, to_iso_now

# 缓存
_sse_cache: dict[str, Any] = {}
_szse_cache: dict[str, Any] = {}

# 请求会话（复用连接）
_session = requests.Session()


def _clean_number(s: str | None) -> float | None:
    """清洗数字字符串，移除逗号、空格等"""
    if s is None:
        return None
    s = s.strip().replace(",", "").replace(" ", "")
    if not s or s == "-" or s == "NaN":
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def fetch_sse_turnover(trade_date: str | None = None) -> dict[str, Any]:
    """
    获取上交所换手率数据

    返回:
        {
            "date": "2026-04-28",
            "turnover_rate": 1.42,      # 加权换手率 %
            "total_turnover_rate": 1.42, # 同上，兼容性别名
            "source": "sse",
            "fetched_at": "ISO时间"
        }
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    result: dict[str, Any] = {
        "date": trade_date,
        "turnover_rate": None,
        "total_turnover_rate": None,
        "source": "sse",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    try:
        url = "https://query.sse.com.cn/commonQuery.do"
        params = {
            "jsonCallBack": "cb",
            "sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C",
            "PRODUCT_CODE": "01,02,03,11,17",
            "type": "inParams",
            "SEARCH_DATE": trade_date,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.sse.com.cn/",
        }

        resp = _session.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()

        text = resp.text
        json_str = text[text.index("(") + 1 : text.rindex(")")]
        import json

        data = json.loads(json_str)

        if not data.get("result"):
            LOGGER.warning("SSE换手率API返回空数据")
            return result

        # 计算加权换手率（按成交额加权）
        total_amount = 0.0
        weighted_turnover = 0.0

        for item in data["result"]:
            trade_amt = _clean_number(item.get("TRADE_AMT")) or 0.0
            to_rate = _clean_number(item.get("TOTAL_TO_RATE")) or 0.0
            total_amount += trade_amt
            weighted_turnover += trade_amt * to_rate

        if total_amount > 0:
            turnover_rate = weighted_turnover / total_amount
            result.update({
                "turnover_rate": round(turnover_rate, 4),
                "total_turnover_rate": round(turnover_rate, 4),
                "status": "ok",
            })
            LOGGER.info("上交所换手率获取成功: %.4f%% (日期=%s)", turnover_rate, trade_date)
        else:
            LOGGER.warning("SSE换手率计算失败：总成交额为0")

    except Exception as exc:
        LOGGER.warning("上交所换手率获取失败: %s", exc)
        result["error"] = str(exc)

    return result


def fetch_sse_volume(trade_date: str | None = None) -> dict[str, Any]:
    """
    获取上交所成交额数据

    参数:
        trade_date: 交易日期，格式 YYYY-MM-DD，默认今日

    返回:
        {
            "date": "2026-04-28",
            "total_amount_yi": 11145.48,    # 沪市总成交额（亿元）
            "main_board_yi": 7841.52,        # 主板A成交额
            "main_board_b_yi": 2.42,         # 主板B成交额
            "star_board_yi": 3301.54,        # 科创板成交额
            "source": "sse",
            "fetched_at": "ISO时间"
        }
    """
    global _sse_cache

    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    # 读缓存
    if trade_date in _sse_cache:
        LOGGER.info("使用SSE缓存: %s", trade_date)
        return _sse_cache[trade_date]

    result: dict[str, Any] = {
        "date": trade_date,
        "total_amount_yi": None,
        "main_board_yi": None,
        "main_board_b_yi": None,
        "star_board_yi": None,
        "source": "sse",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    try:
        # 日期转 YYYYMMDD
        date_str = trade_date.replace("-", "")

        # 上交所 API
        url = "https://query.sse.com.cn/commonQuery.do"
        params = {
            "jsonCallBack": "cb",
            "sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C",
            "PRODUCT_CODE": "01,02,03,11,17",
            "type": "inParams",
            "SEARCH_DATE": trade_date,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.sse.com.cn/",
        }

        resp = _session.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()

        # 解析 JSONP
        text = resp.text
        json_str = text[text.index("(") + 1 : text.rindex(")")]
        import json

        data = json.loads(json_str)

        if not data.get("result"):
            LOGGER.warning("SSE API 返回空数据: %s", data)
            return result

        # 汇总各板块成交额
        total = 0.0
        main_board = 0.0
        main_board_b = 0.0
        star_board = 0.0

        for item in data["result"]:
            product_code = item.get("PRODUCT_CODE", "")
            trade_amt = _clean_number(item.get("TRADE_AMT")) or 0.0

            if product_code == "01":
                main_board = trade_amt
                total += trade_amt
            elif product_code == "02":
                main_board_b = trade_amt
                total += trade_amt
            elif product_code == "03":
                total += trade_amt
            elif product_code == "11":
                total += trade_amt
            elif product_code == "17":
                star_board = trade_amt
                total += trade_amt

        result.update({
            "date": trade_date,
            "total_amount_yi": round(total, 2),
            "main_board_yi": round(main_board, 2),
            "main_board_b_yi": round(main_board_b, 2),
            "star_board_yi": round(star_board, 2),
            "status": "ok",
        })

        _sse_cache[trade_date] = result
        LOGGER.info("上交所成交额获取成功: %.2f亿元 (日期=%s)", total, trade_date)

    except Exception as exc:
        LOGGER.warning("上交所成交额获取失败: %s", exc)
        result["error"] = str(exc)

    return result


def fetch_szse_volume(trade_date: str | None = None) -> dict[str, Any]:
    """
    获取深交所成交额数据

    参数:
        trade_date: 交易日期，格式 YYYY-MM-DD，默认今日

    返回:
        {
            "date": "2026-04-28",
            "total_amount_yi": 14245.86,     # 深市总成交额（亿元）
            "main_board_a_yi": 7546.79,      # 主板A股成交额
            "main_board_b_yi": 1.18,          # 主板B成交额
            "chinext_yi": 6697.88,            # 创业板成交额
            "source": "szse",
            "fetched_at": "ISO时间"
        }
    """
    global _szse_cache

    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    if trade_date in _szse_cache:
        LOGGER.info("使用SZSE缓存: %s", trade_date)
        return _szse_cache[trade_date]

    result: dict[str, Any] = {
        "date": trade_date,
        "total_amount_yi": None,
        "main_board_a_yi": None,
        "main_board_b_yi": None,
        "chinext_yi": None,
        "source": "szse",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    try:
        url = "https://www.szse.cn/api/report/ShowReport/data"
        params = {
            "SHOWTYPE": "JSON",
            "CATALOGID": "1803_sczm",
            "TABKEY": "tab1",
            "txtQueryDate": trade_date,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.szse.cn/market/overview/index.html",
        }

        resp = _session.get(url, params=params, headers=headers, timeout=15)
        resp.raise_for_status()

        import json

        data = json.loads(resp.text)

        if not data or not data[0].get("data"):
            LOGGER.warning("SZSE API 返回空数据")
            return result

        # 汇总股票类别成交额（主板A股+主板B股+创业板）
        total = 0.0
        main_board_a = 0.0
        main_board_b = 0.0
        chinext = 0.0

        for item in data[0]["data"]:
            lbmc = item.get("lbmc", "")
            cjje = _clean_number(item.get("cjje")) or 0.0

            if "主板A股" in lbmc:
                main_board_a = cjje
                total += cjje
            elif "主板B股" in lbmc:
                main_board_b = cjje
                total += cjje
            elif "创业板" in lbmc:
                chinext = cjje
                total += cjje

        result.update({
            "date": trade_date,
            "total_amount_yi": round(total, 2),
            "main_board_a_yi": round(main_board_a, 2),
            "main_board_b_yi": round(main_board_b, 2),
            "chinext_yi": round(chinext, 2),
            "status": "ok",
        })

        _szse_cache[trade_date] = result
        LOGGER.info("深交所成交额获取成功: %.2f亿元 (日期=%s)", total, trade_date)

    except Exception as exc:
        LOGGER.warning("深交所成交额获取失败: %s", exc)
        result["error"] = str(exc)

    return result


def fetch_both_exchanges(trade_date: str | None = None) -> dict[str, Any]:
    """
    获取沪深两市合计成交额

    返回:
        {
            "date": "2026-04-28",
            "sh_amount_yi": 11145.48,       # 上交所成交额
            "sz_amount_yi": 14245.86,       # 深交所成交额
            "total_amount_yi": 25391.34,    # 两市合计
            "source": "exchange_official",
            "details": {
                "sse": {...},
                "szse": {...}
            },
            "fetched_at": "ISO时间"
        }
    """
    sse_data = fetch_sse_volume(trade_date)
    szse_data = fetch_szse_volume(trade_date)

    sh = sse_data.get("total_amount_yi") or 0
    sz = szse_data.get("total_amount_yi") or 0

    return {
        "date": sse_data.get("date") or trade_date,
        "sh_amount_yi": sse_data.get("total_amount_yi"),
        "sz_amount_yi": szse_data.get("total_amount_yi"),
        "total_amount_yi": round(sh + sz, 2) if sh and sz else None,
        "source": "exchange_official",
        "details": {
            "sse": sse_data,
            "szse": szse_data,
        },
        "fetched_at": to_iso_now(),
        "status": "ok" if (sse_data.get("status") == "ok" and szse_data.get("status") == "ok") else "failed",
    }


def main() -> None:
    import argparse, json

    parser = argparse.ArgumentParser(description="抓取沪深交易所官方成交额")
    parser.add_argument("--date", type=str, default=None, help="交易日期 YYYY-MM-DD")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    args = parser.parse_args()

    data = fetch_both_exchanges(args.date)
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")


if __name__ == "__main__":
    main()
