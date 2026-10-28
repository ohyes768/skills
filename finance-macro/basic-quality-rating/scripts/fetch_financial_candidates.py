"""Fetch sourced bank/insurance metric candidates, never an approved scoring sidecar.

Standard library only. Eastmoney is a third-party, undocumented website API;
official disclosure, entity scope and metric definitions still need confirmation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import tempfile
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from bank_financial import _date, stock_fingerprint
from financial_score import _sector

BASE_URL = "https://datacenter.eastmoney.com/securities/api/data/v1/get"
REPORT = "RPT_F10_FINANCE_MAINFINADATA"
MAX_BYTES = 4 * 1024 * 1024
CACHE_SECONDS = 3600
MAP_VERSION = 1
# Source field, label, candidate key, output unit, divisor. No annualization.
COMMON = [("ROEJQ", "加权净资产收益率", "roe", "pct", 1)]
BANK = [
    ("ZZCJLL", "总资产净利率（须核对银行ROA定义）", "roa", "pct", 1),
    ("NONPERLOAN", "不良贷款率", "npl_ratio", "pct", 1),
    ("BLDKBBL", "拨备覆盖率", "provision_coverage", "pct", 1),
    ("NEWCAPITALADER", "资本充足率", "total_capital_ratio", "pct", 1),
    ("HXYJBCZL", "核心一级资本充足率", "cet1_ratio", "pct", 1),
    ("FIRST_ADEQUACY_RATIO", "一级资本充足率", "tier1_ratio", "pct", 1),
    ("NET_INTEREST_MARGIN", "净息差", "nim", "pct", 1),
    ("LOAN_PROVISION_RATIO", "拨贷比", "loan_provision_ratio", "pct", 1),
    ("REVENUE_RATIO", "成本收入比（须核对定义）", "cost_income_ratio", "pct", 1),
]
INSURANCE = [
    ("SOLVENCY_AR", "偿付能力充足率（类型及主体未确认）", "solvency_ratio_unspecified", "pct", 1),
    ("NET_ROI", "净投资收益率（主体未确认）", "net_investment_yield", "pct", 1),
    ("TOTAL_ROI", "总投资收益率（主体未确认）", "total_investment_yield", "pct", 1),
    ("SURRENDER_RATE_LIFE", "寿险退保率（主体未确认）", "surrender_ratio", "pct", 1),
    ("NBV_LIFE", "寿险新业务价值（须核对主体、假设及重述）", "nbv", "cny_million", 1000000),
]


def _identity(stock):
    stock_fingerprint(stock)
    code = stock["code"]
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("stock.code 必须是六位A股代码，不带交易所后缀")
    sector = _sector(stock, [])
    if sector not in ("bank", "insurance"):
        raise ValueError("仅支持申万行业已明确的银行或保险，不从公司名字猜行业")
    suffix = "SH" if code.startswith("6") else "BJ" if code.startswith(("4", "8", "9")) else "SZ"
    return f"{code}.{suffix}", sector


def query_url(stock, as_of):
    secu, _ = _identity(stock)
    end = _date(as_of, "as_of")
    start = date(max(1, end.year - 4), 1, 1).isoformat()
    filters = (
        f"(SECUCODE=\"{secu}\")(REPORT_DATE>='{start}')"
        f"(REPORT_DATE<='{as_of}')(NOTICE_DATE<='{as_of}')"
    )
    return (
        BASE_URL
        + "?"
        + urlencode(
            {
                "reportName": REPORT,
                "columns": "ALL",
                "filter": filters,
                "pageSize": 100,
                "pageNumber": 1,
                "sortColumns": "REPORT_DATE",
                "sortTypes": -1,
                "source": "HSF10",
                "client": "PC",
            }
        )
    )


def _source_date(value, field):
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)?", value
    ):
        raise ValueError(f"{field} 缺失或日期格式无效")
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field} 日期或时间无效") from None
    return _date(value[:10], field)


def _reject_constant(value):
    raise ValueError("响应含非有限数字: " + value)


def _rows(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("接口响应超过4MiB，停止而非截断后继续")
    try:
        data = json.loads(raw, parse_constant=_reject_constant)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("接口响应不是有效JSON") from exc
    result = data.get("result") if isinstance(data, dict) else None
    if (
        not isinstance(data, dict)
        or data.get("success") is not True
        or not isinstance(result, dict)
    ):
        raise ValueError("接口失败或响应结构改变；不将接口错误当作无数据")
    rows = result.get("data")
    pages = result.get("pages")
    if type(pages) is not int or pages not in (0, 1):
        raise ValueError("响应页数异常或未完整覆盖查询窗口，不使用截断历史")
    if not isinstance(rows, list) or len(rows) > 100 or not all(isinstance(r, dict) for r in rows):
        raise ValueError("接口data必须为最多100行的对象数组")
    if pages == 0 and rows:
        raise ValueError("响应页数与数据行矛盾")
    return rows


def _target_period(report_date, as_of):
    if report_date is None:
        return None
    target = _date(report_date, "report_date")
    end = _date(as_of, "as_of")
    if target.strftime("%m-%d") not in ("03-31", "06-30", "09-30", "12-31"):
        raise ValueError("report_date 必须为季度末，如三季报2026-09-30")
    if not date(max(1, end.year - 4), 1, 1) <= target <= end:
        raise ValueError("report_date 须在查询历史窗口内且不晚于 as_of")
    return target


def _alignment(target, returned_periods, observations):
    requested = target.isoformat() if target is not None else None
    index = (
        next((i for i, item in enumerate(observations) if item["period_end"] == requested), None)
        if target is not None
        else None
    )
    status = (
        "not_requested"
        if target is None
        else "matched"
        if index is not None
        else "target_rejected"
        if target in returned_periods
        else "missing_target"
    )
    latest = max(returned_periods).isoformat() if returned_periods else None
    return {
        "check_scope": "report_period_only",
        "status": status,
        "requested_report_date": requested,
        "latest_returned_report_date": latest,
        "latest_usable_report_date": observations[0]["period_end"] if observations else None,
        "target_observation_index": index,
        "newer_report_returned": bool(requested and latest and latest > requested),
    }


def build_candidates(stock, as_of, rows, *, source_url, report_date=None):
    secu, sector = _identity(stock)
    end = _date(as_of, "as_of")
    target = _target_period(report_date, as_of)
    start = date(max(1, end.year - 4), 1, 1)
    issues, accepted = [], []
    returned_periods = set()
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise ValueError("候选原始记录必须为对象数组")
    for index, row in enumerate(rows):
        if (
            row.get("SECUCODE") != secu
            or row.get("SECURITY_CODE") != stock["code"]
            or row.get("SECURITY_NAME_ABBR") != stock["name"]
            or row.get("ORG_TYPE") != ("银行" if sector == "bank" else "保险")
        ):
            raise ValueError("接口返回的股票代码、名称或行业不匹配；停止，勿合并其他公司数据")
        try:
            period = _source_date(row.get("REPORT_DATE"), "REPORT_DATE")
            if period.strftime("%m-%d") not in ("03-31", "06-30", "09-30", "12-31"):
                raise ValueError("REPORT_DATE 不是支持的季度末")
            returned_periods.add(period)
            published = _source_date(row.get("NOTICE_DATE"), "NOTICE_DATE")
            updated = _source_date(row.get("UPDATE_DATE"), "UPDATE_DATE")
            if not start <= period <= published <= end or not published <= updated <= end:
                raise ValueError("报告/披露/更新日期不在有效窗口或含截止日后修订")
        except ValueError as exc:
            issues.append(f"row[{index}]: {exc}")
            continue
        accepted.append((period, published, updated, index, row))
    counts = Counter(item[0] for item in accepted)
    duplicates = sorted(p.isoformat() for p, count in counts.items() if count > 1)
    if duplicates:
        issues.append("重复或冲突报告期全部排除: " + ", ".join(duplicates))
    observations = []
    for period, published, updated, index, row in sorted(
        accepted, key=lambda r: r[0], reverse=True
    ):
        if counts[period] > 1:
            continue
        metrics = {}
        for field, label, key, unit, divisor in COMMON + (BANK if sector == "bank" else INSURANCE):
            raw = row.get(field)
            if raw is None:
                continue
            try:
                valid_number = type(raw) in (int, float) and math.isfinite(raw)
            except OverflowError:
                valid_number = False
            if not valid_number:
                issues.append(f"{period} {field}: 非有限数字/类型无效，未采用")
                continue
            if unit == "cny_million" and row.get("CURRENCY") != "CNY":
                issues.append(f"{period} {field}: 币种不是CNY，未换算或采用")
                continue
            metrics[key] = {
                "value": raw / divisor,
                "unit": unit,
                "raw_value": raw,
                "source_field": field,
                "source_label": label,
                "source_unit": "cny" if divisor != 1 else unit,
                "source_url": source_url,
                "locator": f"result.data[{index}].{field}",
                "needs_confirmation": True,
            }
        observations.append(
            {
                "period_end": period.isoformat(),
                "published_at": published.isoformat(),
                "updated_at": updated.isoformat(),
                "period_type": "annual"
                if period.month == 12
                else "interim"
                if period.month == 6
                else "quarter",
                "scope": "unconfirmed",
                "metrics": metrics,
            }
        )
    return {
        "schema_version": 1,
        "packet_type": "financial_metric_candidates",
        "mapping_version": MAP_VERSION,
        "code": stock["code"],
        "name": stock["name"],
        "stock_sha256": stock_fingerprint(stock),
        "as_of": as_of,
        "sector": sector,
        "provider": "eastmoney",
        "source_type": "third_party",
        "source_url": source_url,
        "status": "needs_confirmation" if observations else "no_usable_observations",
        "ready_for_scoring": False,
        "report_alignment": _alignment(target, returned_periods, observations),
        "observations": observations,
        "issues": issues,
        "still_required": [
            "所有拟入分数值须核对官方披露、集团/法人主体及指标定义",
            "核对最新已披露报告期及最近三年连续年度，不能用旧完整报告掩盖新缺口",
            *(
                ["本银行当期完整资本要求及适用日期", "同报告期LCR及NSFR及其披露口径"]
                if sector == "bank"
                else [
                    "重要保险法人名单、核心/综合偿付能力与风险综合评级",
                    "寿险NBV/CSM及收益率或产险成本率的三年同主体可比历史",
                    "准备金、资产负债匹配及集团重要业务覆盖评估",
                ]
            ),
        ],
        "limitations": [
            "第三方网页内部接口，无可用性承诺；不是官方披露或已确认评分证据包",
            "仅用当前接口返回的披露/更新日期过滤；不是可还原历史版本的时点数据库",
            "年度/中期/季度按原期间保留，未年化；不自动填集团/法人范围或偿付能力类型",
        ],
    }


def _write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, ensure_ascii=False, allow_nan=False, indent=2)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
    ) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _download(url, timeout):
    for attempt in range(2):
        try:
            with urlopen(
                Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}),
                timeout=timeout,
            ) as response:
                return response.read(MAX_BYTES + 1)
        except HTTPError as exc:
            exc.close()
            if exc.code < 500 or attempt:
                raise ValueError(f"接口HTTP {exc.code}，停止；不使用旧缓存冒充刷新成功") from exc
        except (URLError, TimeoutError, ConnectionError) as exc:
            if attempt:
                raise ValueError("接口网络失败（最多两次请求），停止本渠道") from exc
    raise ValueError("接口请求失败")


def fetch(stock, as_of, cache_dir, *, refresh=False, timeout=12, report_date=None):
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 1 <= timeout <= 30:
        raise ValueError("timeout 必须在1至30秒之间")
    url = query_url(stock, as_of)
    _target_period(report_date, as_of)
    cache = Path(cache_dir) / (hashlib.sha256(url.encode()).hexdigest() + ".json")
    now = datetime.now(UTC)
    cached, hit = None, False
    if cache.exists() and not refresh:
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            raw = cached["body"].encode("utf-8")
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            if (
                cached["schema_version"] != 1
                or cached["url"] != url
                or hashlib.sha256(raw).hexdigest() != cached["sha256"]
                or fetched_at.tzinfo is None
                or (now - fetched_at).total_seconds() < 0
            ):
                raise ValueError("缓存来源、哈希或时间不符")
            hit = (now - fetched_at).total_seconds() <= CACHE_SECONDS
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError("缓存损坏；检查路径后显式 --refresh，不静默重试") from exc
    if not hit:
        raw = _download(url, timeout)
        _rows(raw)
        cached = {
            "schema_version": 1,
            "url": url,
            "body": raw.decode("utf-8"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "fetched_at": now.isoformat(),
        }
    packet = build_candidates(stock, as_of, _rows(raw), source_url=url, report_date=report_date)
    if not hit:
        _write(cache, cached)
    packet.update(
        cache_hit=hit,
        fetched_at=cached["fetched_at"],
        response_sha256=cached["sha256"],
        cache_file=str(cache.resolve()),
    )
    return packet


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--report-date", help="Explicit target report quarter-end, e.g. 2026-09-30")
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument(
        "--output", help="Save candidates as JSON; stdout remains a compact receipt"
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--timeout", type=float, default=12)
    args = parser.parse_args(argv)
    try:
        if args.output and Path(args.output).resolve() == Path(args.stock).resolve():
            raise ValueError("output 不能覆盖原始 stock")
        stock = json.loads(
            Path(args.stock).read_text(encoding="utf-8"), parse_constant=_reject_constant
        )
        packet = fetch(
            stock,
            args.as_of,
            args.cache_dir,
            refresh=args.refresh,
            timeout=args.timeout,
            report_date=args.report_date,
        )
        if args.output:
            if Path(args.output).resolve() == Path(packet["cache_file"]).resolve():
                raise ValueError("output 不能覆盖原始API响应缓存")
            _write(args.output, packet)
            receipt = {
                key: packet[key]
                for key in (
                    "status",
                    "code",
                    "sector",
                    "ready_for_scoring",
                    "cache_hit",
                    "fetched_at",
                    "response_sha256",
                    "report_alignment",
                )
            }
            receipt.update(
                output=str(Path(args.output).resolve()),
                observations=len(packet["observations"]),
                issues=packet["issues"],
                still_required=packet["still_required"],
            )
            print(json.dumps(receipt, ensure_ascii=False, allow_nan=False))
        else:
            print(json.dumps(packet, ensure_ascii=False, allow_nan=False))
    except (OSError, ValueError, TypeError, OverflowError) as exc:
        print(f"fetch_financial_candidates: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
