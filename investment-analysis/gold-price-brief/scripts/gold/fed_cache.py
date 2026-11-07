"""金十利率预测 HTTP 获取及日快照缓存。独立运行只预览，不发消息。"""
import json
import logging
import os
from pathlib import Path
import tempfile
from datetime import datetime

import requests

from .fed_expectations import build_report, china_now, valid_records

LOGGER = logging.getLogger(__name__)
API_URL = "https://mp-api.jin10.com/api/long-pictures/list"
HEADERS = {"x-app-id": "fiXF2nOnDycGutVA", "x-version": "1.0",
           "Referer": "https://www.jin10.com/", "User-Agent": "Mozilla/5.0", "Accept": "application/json"}
DEFAULT_CACHE = Path(__file__).resolve().parents[2] / "data" / "gold_fed_expectations.json"
FETCH_INTERVAL_SECONDS = 3600


def _read_cache(path, now):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1:
            return [], None
        records = valid_records(data.get("records"), now=now)
        fetched = datetime.fromisoformat(data["fetched_at"])
        if fetched.tzinfo is None or fetched > now:
            return records, None
        return records, fetched
    except (OSError, ValueError, KeyError, TypeError):
        return [], None


def _write_cache(path, records, now):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as file:
            temporary = Path(file.name)
            json.dump({"version": 1, "fetched_at": now.isoformat(), "records": records},
                      file, ensure_ascii=False, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def get_fed_expectations(*, cache_path=None, now=None, request_get=None, force_refresh=False):
    """失败返回显式降级报告，不中断金价推送。"""
    now = china_now(now)
    path = Path(cache_path) if cache_path is not None else Path(os.environ.get("GOLD_FED_CACHE_PATH") or DEFAULT_CACHE)
    cached, fetched_at = _read_cache(path, now)
    if not force_refresh and cached and fetched_at and (now - fetched_at).total_seconds() < FETCH_INTERVAL_SECONDS:
        return build_report(cached, now=now, status="cached")
    getter = request_get or requests.get
    try:
        response = getter(API_URL, params={"category": "interestRateForecast", "attr_id": 0,
                                          "time_gte": "", "time_lte": ""},
                          headers=HEADERS, timeout=(5, 15))
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("status") != 200:
            raise ValueError("金十响应状态异常")
        incoming = valid_records(payload.get("data"), now=now)
        if not incoming:
            raise ValueError("没有有效利率快照")
        merged = valid_records(cached + incoming, now=now)
        # 服务端意外回退时保留较新缓存，并明确不是本次获取的最新行情。
        if cached and incoming[0]["time"] < cached[0]["time"]:
            report = build_report(merged, now=now, status="fallback")
            report["warnings"].append("数据源返回较旧快照，沿用本地较新记录")
            return report
        is_new = not cached or incoming[0]["time"] > cached[0]["time"]
        report = build_report(merged, now=now, is_new_snapshot=is_new)
        try:
            _write_cache(path, merged, now)
        except (OSError, ValueError, TypeError):
            LOGGER.warning("利率预期缓存写入失败")
            report["warnings"].append("缓存写入失败")
        return report
    except (requests.RequestException, ValueError, TypeError):
        LOGGER.warning("金十利率预期获取失败，尝试已有快照")
        report = build_report(cached, now=now, status="fallback")
        report["warnings"].append("本次获取失败")
        return report


if __name__ == "__main__":
    import argparse
    from .formatter import format_fed_expectations

    parser = argparse.ArgumentParser(description="预览金十利率预期，不调用模型、不发钉钉")
    parser.add_argument("--refresh", action="store_true", help="跳过一小时获取缓存")
    parser.add_argument("--json", action="store_true", help="输出归一化数据")
    args = parser.parse_args()
    result = get_fed_expectations(force_refresh=args.refresh)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else format_fed_expectations(result))
