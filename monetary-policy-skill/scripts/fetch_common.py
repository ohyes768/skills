#!/usr/bin/env python3
"""
抓取脚本公共能力：会话、重试、日志、解析辅助。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Literal

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


LOGGER = logging.getLogger("monetary_fetch")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# parse_status 字段的合法值
ParseStatus = Literal["ok", "partial", "failed"]
PARSE_STATUS_OK: ParseStatus = "ok"
PARSE_STATUS_PARTIAL: ParseStatus = "partial"
PARSE_STATUS_FAILED: ParseStatus = "failed"


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def build_session() -> requests.Session:
    session = requests.Session()
    retries = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.6,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD", "POST"),
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(DEFAULT_HEADERS)
    return session


def fetch_text(session: requests.Session, url: str, *, timeout: int = 20) -> str:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    if not response.encoding:
        response.encoding = "utf-8"
    return response.text


def to_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_first_float(text: str, pattern: str) -> float | None:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    try:
        return float(match.group(1))
    except (ValueError, TypeError):
        return None


def parse_first_int(text: str, pattern: str) -> int | None:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        return int(raw)
    except (ValueError, TypeError):
        return None
