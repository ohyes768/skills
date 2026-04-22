#!/usr/bin/env python3
"""从国家能源局官网抓取全社会用电量月度数据。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── 本地 fetch_common（永远优先）─────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parents[0]
_LOCAL_COMMON = _SCRIPT_DIR / "fetch_common.py"
_MONETARY_COMMON = (
    Path(__file__).resolve().parents[2]
    / "monetary-policy-skill"
    / "scripts"
    / "fetch_common.py"
)

for _p in [str(_SCRIPT_DIR), str(_MONETARY_COMMON.parent)]:
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(_SCRIPT_DIR))

from fetch_common import build_session, setup_logging, to_iso_now, write_cache, read_cache, is_data_published, LOGGER

NEA_BASE = "https://www.nea.gov.cn"


def _build_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(total=3, connect=3, read=3, backoff_factor=0.5,
                    status_forcelist=(429, 500, 502, 503, 504))
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": NEA_BASE,
    })
    return session


def _find_article_url(session: requests.Session, year: int, month: int) -> str | None:
    """从 NEA 首页找到目标月份用电量文章 URL。"""
    resp = session.get(NEA_BASE + "/", timeout=15)
    resp.encoding = "utf-8"
    text = resp.text

    if month == 1:
        title_marker = f"{year}年1-2月"
    else:
        title_marker = f"{year}年{month}月"

    pattern = re.compile(r'href="([^"]*?/c\.html)"[^>]*>\s*([^<]+)\s*</a>')
    for m in pattern.finditer(text):
        url_rel = m.group(1).strip()
        link_text = m.group(2).strip()
        if title_marker in link_text:
            if url_rel.startswith("/"):
                url = NEA_BASE + url_rel
            elif url_rel.startswith("http"):
                url = url_rel
            else:
                url = NEA_BASE + "/" + url_rel
            LOGGER.info("找到 NEA 文章: %s", link_text)
            return url

    LOGGER.warning("NEA 首页未找到: %s", title_marker)
    return None


def _parse_article(html: str, target_month: str) -> dict[str, Any]:
    """解析 NEA 文章页面，提取用电量数据。"""
    result: dict[str, Any] = {
        "month": target_month,
        "total_electricity_billion_kwh": None,
        "yoy_percent": None,
        "primary_industry_kwh": None,
        "secondary_industry_kwh": None,
        "tertiary_industry_kwh": None,
        "residential_kwh": None,
        "unit": "亿千瓦时/百分比",
        "source_url": None,
        "published_at": None,
        "announcement_title": None,
        "parse_status": "failed",
        "provider": "nea.gov.cn",
    }

    # 标题
    title_m = re.search(r'<div class="titles">\s*([^<]+)', html)
    if title_m:
        result["announcement_title"] = title_m.group(1).strip()

    # 发布日期
    date_m = re.search(r'发布时间[：:]\s*(\d{4}-\d{2}-\d{2})', html)
    if date_m:
        result["published_at"] = date_m.group(1)

    # 判断是单月还是 1-2 月累计
    is_cumulative = "1-2月" in (result.get("announcement_title") or "")
    month_int = int(target_month.split("-")[1].lstrip("0"))

    if is_cumulative:
        # 1-2月累计：1-2月，全社会用电量累计16546亿千瓦时，同比增长6.1%
        m = re.search(r'1-2月[，,]\s*[^0-9]*?累计\s*(\d[\d,]+)\s*亿千瓦时', html)
        if m:
            result["total_electricity_billion_kwh"] = float(m.group(1).replace(",", ""))
        yoy_m = re.search(r'1-2月[^%]*?同比增长\s*([\d.]+)\s*%', html)
        if yoy_m:
            result["yoy_percent"] = float(yoy_m.group(1))
    else:
        # 单月：3月份，全社会用电量8595亿千瓦时，同比增长3.5%
        m = re.search(rf'{month_int}月[份]?[,，]?\s*[^0-9]*?(\d[\d,]+)\s*亿千瓦时', html)
        if m:
            result["total_electricity_billion_kwh"] = float(m.group(1).replace(",", ""))
        if result["total_electricity_billion_kwh"]:
            yoy_m = re.search(rf'{month_int}月[份]?[^%]*?同比增长\s*([\d.]+)\s*%', html)
            if yoy_m:
                result["yoy_percent"] = float(yoy_m.group(1))

    # 产业用电量
    for label, key in [("第一产业", "primary_industry_kwh"),
                        ("第二产业", "secondary_industry_kwh"),
                        ("第三产业", "tertiary_industry_kwh"),
                        ("城乡居民生活", "residential_kwh")]:
        m = re.search(rf'{label}[用电量]*\s*(\d+)\s*亿千瓦时', html)
        if m:
            result[key] = float(m.group(1))

    if result["total_electricity_billion_kwh"] and result["yoy_percent"]:
        result["parse_status"] = "ok"
    else:
        result["error"] = "解析失败：未能提取完整数据"

    return result


def fetch_electricity_consumption_monthly(target_month: str) -> dict[str, Any]:
    """抓取目标月份的全社会用电量数据。

    NEA 发布时间：每月20号左右发布上月数据
    """
    if not re.fullmatch(r"\d{4}-\d{2}", target_month):
        return {"error": f"月份格式错误: {target_month}", "parse_status": "failed"}

    # 检查是否到发布时间
    published, hint = is_data_published(target_month, publish_day=20)
    if not published:
        LOGGER.info("用电量 %s 数据尚未发布（预计 %s）", target_month, hint)
        return {
            "month": target_month,
            "parse_status": "not_yet_published",
            "published_hint": hint,
            "fetched_at": to_iso_now(),
        }

    # 优先读缓存
    cached = read_cache("electricity", target_month)
    if cached:
        LOGGER.info("缓存命中: electricity/%s", target_month)
        return cached

    year, month = int(target_month.split("-")[0]), int(target_month.split("-")[1])
    session = _build_session()

    # 找文章 URL
    url = _find_article_url(session, year, month)
    if not url:
        return {
            "month": target_month,
            "parse_status": "failed",
            "error": f"未找到 {target_month} 月的 NEA 文章",
            "fetched_at": to_iso_now(),
            "provider": "nea.gov.cn",
        }

    # 解析数据
    resp = session.get(url, timeout=20)
    resp.encoding = "utf-8"
    result = _parse_article(resp.text, target_month)
    result["source_url"] = url
    result["fetched_at"] = to_iso_now()

    if result["parse_status"] == "ok":
        LOGGER.info("提取成功: %s 亿千瓦时, 同比 %s%%",
                   result["total_electricity_billion_kwh"], result["yoy_percent"])
        write_cache("electricity", target_month, result)
    else:
        LOGGER.warning("解析失败: %s", result.get("error"))

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="从国家能源局抓取全社会用电量数据")
    parser.add_argument("--month", required=True, help="目标月份（YYYY-MM）")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    args = parser.parse_args()

    setup_logging()
    data = fetch_electricity_consumption_monthly(args.month)
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()
