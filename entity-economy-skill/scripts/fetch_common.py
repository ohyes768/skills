#!/usr/bin/env python3
"""
抓取脚本公共能力：会话、重试、日志、解析辅助。
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
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


def _load_skill_dotenv() -> None:
    """加载 skill 目录下的 .env 环境变量（如果存在）。"""
    skill_dir = Path(__file__).parent.resolve().parent
    env_path = skill_dir / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue  # 跳过空行和注释
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


# 模块加载时自动加载 skill .env
_load_skill_dotenv()


# ─── 缓存 ────────────────────────────────────────────────────────────────────

def get_data_dir() -> Path:
    """返回 data/ 目录路径（相对于 skill 根目录）。"""
    return Path(__file__).resolve().parents[1] / "data"


def read_cache(indicator: str, month: str) -> dict[str, Any] | None:
    """读取指定月份的指标缓存。

    Args:
        indicator: 指标名
        month:      月份，格式 "YYYY-MM"

    Returns:
        缓存数据（dict），无缓存则返回 None。
    """
    path = get_data_dir() / month / f"{indicator}.json"
    if not path.exists():
        return None
    try:
        import json
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def write_cache(indicator: str, month: str, data: dict[str, Any]) -> None:
    """将指标数据写入指定月份的缓存。

    Args:
        indicator: 指标名
        month:     月份，格式 "YYYY-MM"
        data:      要缓存的数据
    """
    import json
    cache_dir = get_data_dir() / month
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{indicator}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    LOGGER.info("缓存写入: data/%s/%s.json", month, indicator)


# ─── 发布时间判断 ────────────────────────────────────────────────────────────

def is_data_published(target_month: str, publish_day: int) -> tuple[bool, str]:
    """判断目标月份的数据是否可能已发布。

    Args:
        target_month: 目标月份，"YYYY-MM"
        publish_day:  每月发布日（相对于目标月份的下个月）

    Returns:
        (is_published, reason)：
        - (True, "") 表示当前日期已过 publish_day，数据可能已发布
        - (False, "数据通常在 {month+X} 月 {publish_day} 号后发布") 表示数据尚未发布
    """
    now = datetime.now(timezone.utc)
    year, month = map(int, target_month.split("-"))

    # 数据发布日 = 目标月份下个月的 publish_day 号
    publish_month = month + 1
    publish_year = year
    if publish_month > 12:
        publish_month = 1
        publish_year += 1

    publish_date = datetime(publish_year, publish_month, publish_day, tzinfo=timezone.utc)

    if now >= publish_date:
        return True, ""
    else:
        expected = f"{publish_year}年{publish_month}月{publish_day}号"
        return False, expected
