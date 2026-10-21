"""拉取东财 F10 结构化三表，全量留档 structured_financials.json。

只封装 datacenter 接口 HTTP（不引入 akshare）；响应原样保存，映射规则演进时无需重拉。
数值以 Decimal 解析留档（parse_float），避免 float 失真。缓存按「已拉取的 (日期, 报表)
集合」增量复用——远程数据可能合法更新，哈希仅作审计留档。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

import httpx
from artifacts import emit_status, write_json

DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1, 2)
SCHEMA_VERSION = 1

REPORTS = {
    "balance": "RPT_F10_FINANCE_GBALANCE",
    "income": "RPT_F10_FINANCE_GINCOME",
    "cashflow": "RPT_F10_FINANCE_GCASHFLOW",
}
_BASE_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/json",
}

_cli_client: httpx.Client | None = None
_cli_sleep: Callable[[float], None] | None = None


class FetchStructuredError(RuntimeError):
    """致命拉取失败：退出 1。"""


class _TransientError(RuntimeError):
    """可重试的临时错误。"""


def secucode(code: str) -> str:
    """301313 → 301313.SZ；600519 → 600519.SH。"""
    code = code.strip()
    if "." in code:
        return code.upper()
    if len(code) != 6 or not code.isdigit():
        raise FetchStructuredError(f"illegal security code: {code!r}")
    return f"{code}.{'SH' if code.startswith('6') else 'SZ'}"


def _report_url(report_name: str, secu: str, report_date: str) -> str:
    filt = f'(SECUCODE="{secu}")(REPORT_DATE=\'{report_date}\')'
    query = (
        f"reportName={report_name}&columns=ALL&filter={quote(filt)}"
        f"&pageSize=10&source=HSF10&client=PC"
    )
    return f"{_BASE_URL}?{query}"


def _parse_rows(payload: bytes, label: str) -> list[dict]:
    try:
        doc = json.loads(payload.decode("utf-8"), parse_float=Decimal)
    except (ValueError, UnicodeDecodeError) as exc:
        raise _TransientError(f"{label}: response is not valid JSON") from exc
    rows = ((doc or {}).get("result") or {}).get("data") or []
    if not rows:
        raise FetchStructuredError(f"{label}: no data for the requested security/report date")
    return rows


def _request_once(client: httpx.Client, url: str) -> bytes:
    try:
        with client.stream("GET", url) as response:
            if 500 <= response.status_code < 600:
                raise _TransientError(f"HTTP {response.status_code}")
            if response.status_code != 200:
                raise FetchStructuredError(f"HTTP {response.status_code} for datacenter API")
            return b"".join(response.iter_bytes())
    except httpx.TransportError as exc:
        raise _TransientError(str(exc)) from exc


def _fetch_report(client: httpx.Client, label: str, url: str, max_attempts: int,
                  sleep: Callable[[float], None]) -> tuple[list[dict], str]:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            payload = _request_once(client, url)
            return _parse_rows(payload, label), hashlib.sha256(payload).hexdigest()
        except _TransientError as exc:
            last_error = exc
            if attempt < max_attempts:
                sleep(RETRY_BACKOFF_SECONDS[min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)])
    raise FetchStructuredError(f"{label}: failed after {max_attempts} attempts: {last_error}")


def _cached_entries(doc: dict | None, dates: list[str]) -> set[tuple[str, str]]:
    done: set[tuple[str, str]] = set()
    if not doc:
        return done
    reports = doc.get("reports") or {}
    for date, kinds in reports.items():
        for kind in kinds:
            if kinds.get(kind):
                done.add((date, kind))
    return {(d, k) for d, k in done if d in dates}


def fetch_structured(code: str, dates: list[str], run_dir: Path, *,
                     client: httpx.Client | None = None,
                     sleep: Callable[[float], None] | None = time.sleep,
                     timeout: float = DEFAULT_TIMEOUT,
                     max_attempts: int = DEFAULT_MAX_ATTEMPTS,
                     refresh: bool = False) -> dict:
    """拉取多期三表并写 structured_financials.json；返回带 reused 标记的留档文档。

    dates 为报告期末列表（如本期、上年同期、上年末）；已拉取的 (日期, 报表) 增量复用。
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = run_dir / "structured_financials.json"
    secu = secucode(code)
    dates = sorted({d.strip() for d in dates if d.strip()})
    if not dates:
        raise FetchStructuredError("no report dates requested")

    previous = None
    if not refresh and output_path.exists():
        try:
            candidate = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            candidate = None
        if (candidate and candidate.get("schema_version") == SCHEMA_VERSION
                and candidate.get("source") == "structured_eastmoney"
                and candidate.get("security_code") == code):
            previous = candidate
    done = _cached_entries(previous, dates)

    owned_client = client is None
    if client is None:
        client = httpx.Client(timeout=httpx.Timeout(DEFAULT_TIMEOUT, read=timeout),
                              headers=_HEADERS, follow_redirects=True)
    effective_sleep = sleep if sleep is not None else time.sleep

    reports: dict[str, dict[str, list[dict]]] = {
        date: {} for date in dates}
    digests: dict[str, str] = {}
    if previous:
        for date in dates:
            for kind in REPORTS:
                if (date, kind) in done:
                    reports[date][kind] = previous["reports"][date][kind]

    try:
        for date in dates:
            for kind, report_name in REPORTS.items():
                if reports[date].get(kind):
                    continue
                label = f"{report_name}@{date}"
                url = _report_url(report_name, secu, date)
                rows, digest = _fetch_report(client, label, url, max_attempts,
                                             effective_sleep)
                reports[date][kind] = rows
                digests[f"{date}/{kind}"] = digest
    finally:
        if owned_client:
            client.close()

    fetched_all = previous.get("response_sha256", {}) if previous else {}
    fetched_all.update(digests)
    fetched_at = (previous or {}).get("fetched_at")
    doc = {
        "schema_version": SCHEMA_VERSION,
        "source": "structured_eastmoney",
        "security_code": code,
        "secucode": secu,
        "report_dates": dates,
        "fetched_at": fetched_at or datetime.now(UTC).isoformat(),
        "requested": {"report_names": sorted(REPORTS.values()), "secucode": secu,
                      "report_dates": dates},
        "response_sha256": fetched_all,
        "reports": reports,
    }
    write_json(output_path, doc)
    reused = bool(previous) and not digests
    return {**doc, "reused": reused}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="拉取东财 F10 结构化三表并留档")
    parser.add_argument("--code", required=True)
    parser.add_argument("--dates", required=True,
                        help="报告期末列表，逗号分隔：本期,上年同期,上年末")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--refresh", action="store_true", help="绕过缓存强制重新拉取")
    parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
    args = parser.parse_args(argv)

    try:
        doc = fetch_structured(args.code, args.dates.split(","), Path(args.run_dir),
                               client=_cli_client,
                               sleep=_cli_sleep if _cli_sleep is not None else time.sleep,
                               max_attempts=args.max_attempts,
                               refresh=args.refresh)
    except FetchStructuredError as exc:
        print(f"fetch_structured failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    emit_status("reused" if doc["reused"] else "ok",
                {"structured_financials": str(Path(args.run_dir) / "structured_financials.json"),
                 "report_dates": doc["report_dates"]},
                [])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
