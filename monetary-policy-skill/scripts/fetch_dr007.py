#!/usr/bin/env python3
"""
抓取 DR007（银行间7天期质押式回购利率）最新值。
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from fetch_common import (
    LOGGER,
    build_session,
    fetch_text,
    setup_logging,
    to_iso_now,
)


DR007_CSV_URL = "https://www.chinamoney.com.cn/r/cms/www/chinamoney/data/currency/prr-chrt.csv"


def parse_from_prr_csv(csv_text: str) -> tuple[float | None, str | None]:
    lines = [line.strip() for line in csv_text.splitlines() if line.strip()]
    if not lines:
        return None, None
    # 文件按日期倒序，第一行即最新数据
    latest = lines[0].split(",")
    if len(latest) < 8:
        return None, None
    published_at = latest[0]
    try:
        value = float(latest[7])
    except ValueError:
        return None, published_at
    return value, published_at


def fetch_dr007_latest() -> dict[str, Any]:
    session = build_session()
    result: dict[str, Any] = {
        "value": None,
        "unit": "%",
        "source_url": DR007_CSV_URL,
        "published_at": None,
        "fetched_at": to_iso_now(),
        "parse_status": "failed",
    }

    try:
        csv_text = fetch_text(session, DR007_CSV_URL)
        value, published_at = parse_from_prr_csv(csv_text)
        if value is not None:
            result["value"] = value
            result["published_at"] = published_at
            result["parse_status"] = "ok"
            return result

        result["parse_status"] = "partial"
        return result
    except Exception as exc:
        LOGGER.warning("DR007 抓取失败: %s", exc)
        result["error"] = str(exc)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 DR007 最新值")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    args = parser.parse_args()

    setup_logging()
    data = fetch_dr007_latest()
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()
