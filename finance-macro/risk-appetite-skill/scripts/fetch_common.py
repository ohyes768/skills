#!/usr/bin/env python3
"""
公共工具模块 - risk-appetite-skill
提供日志、HTTP会话、数据缓存等通用功能
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

# ============ 日志配置 ============

LOGGER = logging.getLogger("risk-appetite")
_LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(verbose: bool = False) -> None:
    """配置日志输出到文件和控制台"""
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"risk-appetite_{datetime.now().strftime('%Y%m%d')}.log"

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format=_LOG_FMT,
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def get_logger(name: str = "risk-appetite") -> logging.Logger:
    """获取 logger 实例"""
    return logging.getLogger(name)


# ============ HTTP 会话 ============

_session: requests.Session | None = None


def build_session() -> requests.Session:
    """构建带重试机制的 HTTP 会话"""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
        })
        adapter = requests.adapters.HTTPAdapter(
            max_retries=3,
            backoff_factor=0.5,
        )
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
    return _session


def fetch_text(url: str, session: requests.Session | None = None, timeout: int = 30) -> str:
    """GET 请求获取文本内容"""
    if session is None:
        session = build_session()
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_json(url: str, session: requests.Session | None = None, timeout: int = 30) -> Any:
    """GET 请求获取 JSON"""
    if session is None:
        session = build_session()
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# ============ 时间工具 ============

def to_iso_now() -> str:
    """返回当前 UTC 时间 ISO 格式字符串"""
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def today_str() -> str:
    """返回今日日期字符串 YYYY-MM-DD"""
    return datetime.now().strftime("%Y-%m-%d")


def now_date() -> str:
    """返回今日日期 YYYYMMDD"""
    return datetime.now().strftime("%Y%m%d")


def parse_date(date_str: str) -> datetime:
    """解析日期字符串"""
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法解析日期: {date_str}")


def date_range(start: str, end: str) -> list[str]:
    """生成日期范围内的所有日期（YYYY-MM-DD）"""
    start_dt = parse_date(start)
    end_dt = parse_date(end)
    dates = []
    current = start_dt
    while current <= end_dt:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


# ============ 缓存工具 ============

def get_cache_dir() -> Path:
    """获取缓存目录"""
    cache_dir = Path(__file__).resolve().parent.parent.parent / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def write_cache(indicator: str, date_key: str, data: dict[str, Any]) -> Path:
    """写入缓存文件"""
    cache_dir = get_cache_dir() / indicator
    cache_dir.mkdir(parents=True, exist_ok=True)
    file_path = cache_dir / f"{date_key}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return file_path


def read_cache(indicator: str, date_key: str) -> dict[str, Any] | None:
    """读取缓存"""
    cache_dir = get_cache_dir() / indicator
    file_path = cache_dir / f"{date_key}.json"
    if not file_path.exists():
        return None
    try:
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_env_file(env_path: str | Path | None = None) -> None:
    """加载 .env 环境变量文件"""
    if env_path is None:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    else:
        env_path = Path(env_path)

    if not env_path.exists():
        return

    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()


# ============ 数据工具 ============

def to_float(val: Any, default: float = 0.0) -> float:
    """安全转换为浮点数"""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", "").replace("%", "").strip())
    except (ValueError, AttributeError):
        return default


def clean_month(val: Any) -> str:
    """清理月份格式为 YYYY-MM"""
    s = str(val).strip()
    # 移除常见后缀
    s = s.replace("年", "-").replace("月", "").replace("日", "").replace("号", "")
    # 处理如 202603 这样的格式
    if len(s) == 6 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}"
    return s


def is_valid_month(val: str) -> bool:
    """检查是否为有效的 YYYY-MM 格式"""
    if not val or len(val) != 7:
        return False
    try:
        year, month = val.split("-")
        return 2010 <= int(year) <= 2100 and 1 <= int(month) <= 12
    except (ValueError, AttributeError):
        return False


def published_month(target_month: str, publish_day: int) -> str:
    """判断实际发布的月份（用于月末数据发布延迟场景）"""
    today = datetime.now()
    if today.day < publish_day:
        prev = today - timedelta(days=1)
        return prev.strftime("%Y-%m")
    return target_month


def now() -> str:
    """返回当前时间字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
