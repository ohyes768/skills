#!/usr/bin/env python3
"""
抓取 LPR 最新值（1年期、5年期以上）。
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from bs4 import BeautifulSoup

from fetch_common import LOGGER, build_session, fetch_text, parse_first_float, setup_logging, to_iso_now


SOURCE_URL = "https://www.chinamoney.com.cn/chinese/bklpr/"
LPR_API_URL = "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-currency/LprHis?lang=CN"


def parse_lpr_from_text(text: str) -> tuple[float | None, float | None]:
    lpr_1y = parse_first_float(text, r"(?:1年期|1Y)[^0-9]*(\d+\.\d+)")
    lpr_5y = parse_first_float(text, r"(?:5年期以上|5年期|5Y)[^0-9]*(\d+\.\d+)")
    if lpr_1y is not None and lpr_5y is not None:
        return lpr_1y, lpr_5y
    lpr_1y = lpr_1y or parse_first_float(text, r"1年期LPR[^0-9]*(\d+\.\d+)")
    lpr_5y = lpr_5y or parse_first_float(text, r"5年期以上LPR[^0-9]*(\d+\.\d+)")
    return lpr_1y, lpr_5y


def fetch_lpr_latest() -> dict[str, Any]:
    result: dict[str, Any] = {
        "lpr_1y": None,
        "lpr_5y_plus": None,
        "prev_lpr_1y": None,
        "prev_lpr_5y_plus": None,
        "unit": "%",
        "source_url": SOURCE_URL,
        "published_at": None,
        "fetched_at": to_iso_now(),
        "parse_status": "failed",
    }
    session = build_session()

    try:
        # 先访问页面，初始化站点 Cookie
        html = fetch_text(session, SOURCE_URL)
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(" ", strip=True)

        api_resp = session.post(
            LPR_API_URL,
            timeout=20,
            headers={"Referer": SOURCE_URL},
        )
        api_resp.raise_for_status()
        payload = api_resp.json()
        records = payload.get("records", [])
        if records:
            latest = records[0]
            if latest.get("1Y") is not None:
                result["lpr_1y"] = float(latest["1Y"])
            if latest.get("5Y") is not None:
                result["lpr_5y_plus"] = float(latest["5Y"])
            result["published_at"] = latest.get("showDateCN")
            result["source_url"] = LPR_API_URL

            # 取上月数据（records[1]）
            if len(records) > 1:
                prev = records[1]
                if prev.get("1Y") is not None:
                    result["prev_lpr_1y"] = float(prev["1Y"])
                if prev.get("5Y") is not None:
                    result["prev_lpr_5y_plus"] = float(prev["5Y"])
        else:
            # API 不可用时回退到页面文本解析
            lpr_1y, lpr_5y = parse_lpr_from_text(text)
            if lpr_1y is not None:
                result["lpr_1y"] = lpr_1y
            if lpr_5y is not None:
                result["lpr_5y_plus"] = lpr_5y

        result["parse_status"] = (
            "ok"
            if result["lpr_1y"] is not None and result["lpr_5y_plus"] is not None
            else "partial"
        )
        return result
    except Exception as exc:
        LOGGER.warning("LPR 抓取失败: %s", exc)
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
