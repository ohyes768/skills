#!/usr/bin/env python3
"""从东方财富获取 M1/M2 货币供应数据。"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from fetch_common import build_session, setup_logging, to_iso_now, LOGGER

EM_API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
EM_REFERER = "https://data.eastmoney.com/cjsj/hbgyl.html"


def build_result_template() -> dict[str, Any]:
    return {
        "m2": None,                   # M2 余额（亿元）
        "m2_yoy": None,               # M2 同比（%）
        "m1": None,                   # M1 余额（亿元）
        "m1_yoy": None,               # M1 同比（%）
        "m0": None,                   # M0 余额（亿元）
        "m0_yoy": None,               # M0 同比（%）
        "m1_m2_spread": None,         # M1-M2剪刀差（百分点）
        "unit": "亿元/百分比",
        "month": None,
        "source_url": EM_REFERER,
        "published_at": None,
        "fetched_at": to_iso_now(),
        "parse_status": "failed",
        "provider": "eastmoney",
    }


def parse_month_from_date(date_str: str | None) -> str | None:
    """从日期字符串解析出 YYYY-MM 格式月份"""
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return dt.strftime("%Y-%m")
    except ValueError:
        return None


def fetch_m1_m2_latest(session: requests.Session) -> dict[str, Any]:
    """获取最新一期 M1/M2 数据"""
    result = build_result_template()

    params = {
        "sortColumns": "REPORT_DATE",
        "sortTypes": "-1",
        "pageSize": "1",
        "pageNumber": "1",
        "reportName": "RPT_ECONOMY_CURRENCY_SUPPLY",
        "columns": (
            "REPORT_DATE,TIME,"
            "BASIC_CURRENCY,BASIC_CURRENCY_SAME,"
            "CURRENCY,CURRENCY_SAME,"
            "FREE_CASH,FREE_CASH_SAME"
        ),
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "Referer": EM_REFERER,
        "Accept": "application/json",
    }

    try:
        response = session.get(
            EM_API_URL, params=params, headers=headers, timeout=20
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        result["error"] = f"请求失败: {e}"
        return result
    except json.JSONDecodeError as e:
        result["error"] = f"JSON解析失败: {e}"
        return result

    if not data.get("success"):
        result["error"] = f"API返回失败: {data.get('message', 'unknown')}"
        return result

    result_data = data.get("result", {})
    records = result_data.get("data", [])

    if not records:
        result["error"] = "未找到数据"
        return result

    record = records[0]

    m2_val = record.get("BASIC_CURRENCY")
    m2_yoy = record.get("BASIC_CURRENCY_SAME")
    m1_val = record.get("CURRENCY")
    m1_yoy = record.get("CURRENCY_SAME")
    m0_val = record.get("FREE_CASH")
    m0_yoy = record.get("FREE_CASH_SAME")

    result["m2"] = float(m2_val) if m2_val else None
    result["m2_yoy"] = float(m2_yoy) if m2_yoy else None
    result["m1"] = float(m1_val) if m1_val else None
    result["m1_yoy"] = float(m1_yoy) if m1_yoy else None
    result["m0"] = float(m0_val) if m0_val else None
    result["m0_yoy"] = float(m0_yoy) if m0_yoy else None

    if m1_yoy is not None and m2_yoy is not None:
        result["m1_m2_spread"] = round(m1_yoy - m2_yoy, 2)

    result["month"] = parse_month_from_date(record.get("REPORT_DATE"))
    result["published_at"] = record.get("REPORT_DATE", "")[:10]
    result["parse_status"] = "ok"

    LOGGER.info(
        "M1/M2 数据获取成功 [%s]: M1=%s(同比%s%%), M2=%s(同比%s%%), "
        "M1-M2剪刀差=%s%%",
        result["month"],
        _fmt_yi(result["m1"]),
        result["m1_yoy"],
        _fmt_yi(result["m2"]),
        result["m2_yoy"],
        result["m1_m2_spread"],
    )

    return result


def fetch_m1_m2_historical(
    session: requests.Session, months: int = 12
) -> dict[str, Any]:
    """获取历史 M1/M2 数据"""
    result = build_result_template()

    params = {
        "sortColumns": "REPORT_DATE",
        "sortTypes": "-1",
        "pageSize": str(months),
        "pageNumber": "1",
        "reportName": "RPT_ECONOMY_CURRENCY_SUPPLY",
        "columns": (
            "REPORT_DATE,TIME,"
            "BASIC_CURRENCY,BASIC_CURRENCY_SAME,"
            "CURRENCY,CURRENCY_SAME,"
            "FREE_CASH,FREE_CASH_SAME"
        ),
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "Referer": EM_REFERER,
        "Accept": "application/json",
    }

    try:
        response = session.get(
            EM_API_URL, params=params, headers=headers, timeout=20
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as e:
        result["error"] = f"请求失败: {e}"
        return result
    except json.JSONDecodeError as e:
        result["error"] = f"JSON解析失败: {e}"
        return result

    if not data.get("success"):
        result["error"] = f"API返回失败: {data.get('message', 'unknown')}"
        return result

    result_data = data.get("result", {})
    records = result_data.get("data", [])

    if not records:
        result["error"] = "未找到数据"
        return result

    historical = []
    for rec in records:
        entry = {
            "month": parse_month_from_date(rec.get("REPORT_DATE")),
            "m2": float(rec.get("BASIC_CURRENCY")) if rec.get("BASIC_CURRENCY") else None,
            "m2_yoy": float(rec.get("BASIC_CURRENCY_SAME")) if rec.get("BASIC_CURRENCY_SAME") else None,
            "m1": float(rec.get("CURRENCY")) if rec.get("CURRENCY") else None,
            "m1_yoy": float(rec.get("CURRENCY_SAME")) if rec.get("CURRENCY_SAME") else None,
            "m0": float(rec.get("FREE_CASH")) if rec.get("FREE_CASH") else None,
            "m0_yoy": float(rec.get("FREE_CASH_SAME")) if rec.get("FREE_CASH_SAME") else None,
        }
        if entry["m1_yoy"] is not None and entry["m2_yoy"] is not None:
            entry["m1_m2_spread"] = round(entry["m1_yoy"] - entry["m2_yoy"], 2)
        historical.append(entry)

    return {
        "historical": historical,
        "latest": historical[0] if historical else None,
        "fetched_at": to_iso_now(),
        "provider": "eastmoney",
    }


def _fmt_yi(val: float | None) -> str:
    """格式化亿元为单位显示"""
    if val is None:
        return "N/A"
    return f"{val / 10000:.2f}万亿" if val >= 10000 else f"{val:.2f}亿"


def main() -> None:
    parser = argparse.ArgumentParser(description="获取 M1/M2 货币供应数据")
    parser.add_argument(
        "--mode",
        choices=["latest", "history"],
        default="latest",
        help="latest=最新一期, history=历史数据",
    )
    parser.add_argument(
        "--months", type=int, default=12, help="历史数据月数（默认12）"
    )
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    args = parser.parse_args()

    setup_logging()
    session = build_session()

    if args.mode == "history":
        data = fetch_m1_m2_historical(session, args.months)
    else:
        data = fetch_m1_m2_latest(session)

    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()
