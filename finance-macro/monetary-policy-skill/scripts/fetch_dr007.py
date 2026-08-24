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
    write_cache,
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


def parse_month_series(csv_text: str, month: str) -> list[tuple[str, float]]:
    """解析 CSV 中指定月份（YYYY-MM）的全部读数，返回 [(date, value)] 按日期升序。

    用于计算 DR007 月内日均（月均口径：本月至今算术平均，月末自动收敛为全月均值）。
    单行解析失败即跳过（缺日不补），分母为实际取到的交易日数。
    """
    rows: list[tuple[str, float]] = []
    seen: set[str] = set()
    for line in csv_text.splitlines():
        cols = line.strip().split(",")
        if len(cols) < 8:
            continue
        date = cols[0].strip()[:10]
        if not date.startswith(month) or date in seen:
            continue
        try:
            value = float(cols[7])
        except ValueError:
            continue
        rows.append((date, value))
        seen.add(date)
    return sorted(rows)


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
            # 当月日均（本月至今均值，随日期推进自动收敛为全月均值）
            month = published_at[:7] if published_at else None
            if month:
                series = parse_month_series(csv_text, month)
                if series:
                    result["month_avg"] = round(sum(v for _, v in series) / len(series), 4)
                    result["month_days"] = len(series)
                # 写入月度缓存
                write_cache("dr007", month, result)
            return result

        result["parse_status"] = "partial"
        return result
    except Exception as exc:
        LOGGER.warning("DR007 抓取失败: %s", exc)
        result["error"] = str(exc)
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 DR007 最新值与当月日均")
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
