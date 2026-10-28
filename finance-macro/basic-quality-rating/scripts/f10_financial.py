"""Unified F10 financial MVP: third-party statements and disclosed indicators, no web research."""

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlencode

from bank_financial import stock_fingerprint
from fetch_financial_candidates import BASE_URL, _download, _rows, _source_date, _write
from financial_score import _sector, score_financial

REPORTS = {
    "main": "RPT_F10_FINANCE_MAINFINADATA",
    "balance": "RPT_F10_FINANCE_GBALANCE",
    "income": "RPT_F10_FINANCE_GINCOME",
    "cashflow": "RPT_F10_FINANCE_GCASHFLOW",
}
LIMITATION = "基础财务评分：未评估监管资本、偿付能力、流动性及逐法人风险"


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def identity(stock):
    stock_fingerprint(stock)
    code = stock["code"]
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("code 须为六位A股代码")
    suffix = "SH" if code.startswith("6") else "BJ" if code.startswith(("4", "8", "9")) else "SZ"
    return code + "." + suffix


def accepted(stock, as_of, rows):
    end = date.fromisoformat(as_of)
    secu = identity(stock)
    by_period, issues = {}, []
    for row in rows:
        if row.get("SECUCODE") != secu or row.get("SECURITY_NAME_ABBR") != stock["name"]:
            raise ValueError("F10证券身份与输入不一致")
        try:
            period = _source_date(row.get("REPORT_DATE"), "REPORT_DATE")
            pub = _source_date(row.get("NOTICE_DATE"), "NOTICE_DATE")
            update = _source_date(row.get("UPDATE_DATE", row.get("NOTICE_DATE")), "UPDATE_DATE")
            if not date(end.year - 4, 1, 1) <= period <= pub <= update <= end:
                raise ValueError("期间或披露/修订日越界")
            if period.strftime("%m-%d") not in ("03-31", "06-30", "09-30", "12-31"):
                raise ValueError("非季度末")
        except ValueError as exc:
            issues.append(str(exc))
            continue
        by_period.setdefault(period.isoformat(), []).append(row)
    result = {}
    for period, candidates in by_period.items():
        if len(candidates) != 1:
            issues.append("重复期间已排除: " + period)
        else:
            result[period] = candidates[0]
    return result, issues


def normalize(stock, packet):
    if packet.get("schema_version") != 1 or packet.get("source") != "eastmoney_f10":
        raise ValueError("不支持的F10数据包")
    if packet.get("stock_sha256") != stock_fingerprint(stock):
        raise ValueError("F10数据包不属于该原始输入")
    as_of = packet["as_of"]
    end = date.fromisoformat(as_of)
    if packet.get("report_date") and date.fromisoformat(packet["report_date"]) > end:
        raise ValueError("目标财报期晚于研究截止日")
    datasets, issues = {}, list(packet.get("fetch_issues", []))
    for kind in REPORTS:
        source = packet["datasets"][kind]
        rows = _rows(source["body"].encode()) if source.get("body") else []
        if (
            source.get("body")
            and hashlib.sha256(source["body"].encode()).hexdigest() != source["sha256"]
        ):
            raise ValueError("F10原始响应哈希不一致")
        datasets[kind], errors = accepted(stock, as_of, rows)
        issues.extend(f"{kind}: {e}" for e in errors)
    main = datasets["main"]
    target = packet.get("report_date") or max(main, default=None)
    if target is None:
        issues.append("没有可用主要指标报告期")
        elapsed = [
            f"{end.year}-{day}"
            for day in ("03-31", "06-30", "09-30", "12-31")
            if f"{end.year}-{day}" <= as_of
        ]
        target = elapsed[-1] if elapsed else f"{end.year - 1}-12-31"
    if target not in main:
        issues.append("目标报告期主要指标缺失，不回退旧期")
    anchor = date.fromisoformat(target).year - (not target.endswith("12-31"))
    years = list(range(anchor - 2, anchor + 1))
    history = [{"year": y, "value": number(main.get(f"{y}-12-31", {}).get("ROEJQ"))} for y in years]
    avg = (
        sum(h["value"] for h in history) / 3
        if all(h["value"] is not None for h in history)
        else None
    )
    latest = main.get(target, {})
    annual = main.get(f"{anchor}-12-31", {})
    balance = datasets["balance"].get(target, {})
    assets, debt = number(balance.get("TOTAL_ASSETS")), number(balance.get("TOTAL_LIABILITIES"))

    def quarterly(year, quarter):
        day = ("03-31", "06-30", "09-30", "12-31")[quarter - 1]
        current = number(main.get(f"{year}-{day}", {}).get("KCFJCXSYJLR"))
        if quarter == 1 or current is None:
            return current
        previous = number(
            main.get(f"{year}-" + ("03-31", "06-30", "09-30")[quarter - 2], {}).get("KCFJCXSYJLR")
        )
        return current - previous if previous is not None else None

    def yoy(year, quarter):
        value, prior = quarterly(year, quarter), quarterly(year - 1, quarter)
        return (
            (value - prior) / abs(prior) * 100
            if value is not None and prior not in (None, 0)
            else None
        )

    year = int(target[:4])
    quarter = {"03-31": 1, "06-30": 2, "09-30": 3, "12-31": 4}.get(target[5:])
    if quarter is None:
        raise ValueError("目标期间须为季度末")
    prev_year, prev_quarter = (year, quarter - 1) if quarter > 1 else (year - 1, 4)
    payload = {k: stock[k] for k in ("code", "name", "sw_level1", "sw_level2") if k in stock}
    payload.update(
        roe_avg_3y=avg,
        roe_history=history,
        roe_year=anchor,
        annual_profit_year=anchor,
        annual_net_profit_ex_non_recurring=number(annual.get("KCFJCXSYJLR")),
        net_profit_ex_non_recurring_yoy=number(annual.get("KCFJCXSYJLRTZ")),
        previous_quarter_label=f"{prev_year}Q{prev_quarter}",
        latest_quarter_label=f"{year}Q{quarter}",
        previous_quarter_yoy_pct=yoy(prev_year, prev_quarter),
        latest_quarter_yoy_pct=yoy(year, quarter),
        debt_asset_ratio=debt / assets * 100
        if assets is not None and assets > 0 and debt is not None
        else None,
    )
    if target not in main:
        payload["latest_quarter_yoy_pct"] = None
    return (
        payload,
        issues,
        {
            "target_period": target,
            "annual_year": anchor,
            "source": "东方财富F10（第三方，未逐项官方核验）",
            "latest_weighted_roe": number(latest.get("ROEJQ")),
        },
    )


def score_f10(stock, packet):
    payload, issues, coverage = normalize(stock, packet)
    sector = _sector(stock, [])
    if sector in ("bank", "insurance", "nonbank_financial"):
        avg = payload["roe_avg_3y"]
        profits = [
            payload[k]
            for k in (
                "net_profit_ex_non_recurring_yoy",
                "previous_quarter_yoy_pct",
                "latest_quarter_yoy_pct",
            )
        ]
        missing = avg is None or any(v is None for v in profits)
        if missing:
            score = None
        else:
            base = 1 + sum(avg >= t for t in (5, 8, 12, 15))
            negative = sum(v < 0 for v in profits[1:])
            cap = (
                2
                if negative == 2
                else 3
                if negative == 1
                else 4
                if any(v <= 0 for v in profits)
                else 5
            )
            trend = [h["value"] for h in payload["roe_history"]]
            score = min(base, cap, 4 if trend[0] > trend[1] > trend[2] else 5)
        result = {
            "score": score,
            "status": "insufficient_data" if missing else "scored",
            "sector": sector,
            "checks": [{"rule": "f10_profitability_v1", "input": payload, "cap": score}],
            "risks": [],
            "issues": ["缺少三年ROE或年度/相邻单季扣非同比"] if missing else [],
        }
        if not missing:
            if any(v < 0 for v in profits):
                result["risks"].append("F10扣非盈利同比存在负增长，详见年度与单季期间")
            if trend[0] > trend[1] > trend[2]:
                result["risks"].append("最近三年加权ROE连续下降")
        result["limitations"] = [LIMITATION]
    else:
        result = score_financial(payload)
        result["limitations"] = []
    result["issues"].extend(issues)
    result.update(policy="f10-basic-v1", coverage=coverage, normalized_input=payload)
    return result


def fetch(stock, as_of, report_date, cache_dir, refresh=False):
    end = date.fromisoformat(as_of)
    if report_date:
        target = date.fromisoformat(report_date)
        if target > end or target.strftime("%m-%d") not in ("03-31", "06-30", "09-30", "12-31"):
            raise ValueError("目标财报期须为截止日前季度末")
    secu = identity(stock)
    packet = {
        "schema_version": 1,
        "source": "eastmoney_f10",
        "stock_sha256": stock_fingerprint(stock),
        "as_of": as_of,
        "report_date": report_date,
        "datasets": {},
        "fetch_issues": [],
    }
    for kind, report in REPORTS.items():
        stored = None
        url = (
            BASE_URL
            + "?"
            + urlencode(
                {
                    "reportName": report,
                    "columns": "ALL",
                    "filter": f"(SECUCODE=\"{secu}\")(REPORT_DATE>='{end.year - 4}-01-01')(REPORT_DATE<='{as_of}')(NOTICE_DATE<='{as_of}')",
                    "pageSize": 100,
                    "pageNumber": 1,
                    "sortColumns": "REPORT_DATE",
                    "sortTypes": -1,
                    "source": "HSF10",
                    "client": "PC",
                }
            )
        )
        cache = Path(cache_dir) / (hashlib.sha256(url.encode()).hexdigest() + ".json")
        try:
            stored = json.loads(cache.read_text()) if cache.exists() and not refresh else None
            fresh = (
                stored
                and 0
                <= (
                    datetime.now(UTC) - datetime.fromisoformat(stored["fetched_at"])
                ).total_seconds()
                <= 3600
            )
            if fresh:
                raw = stored["body"].encode()
                if stored["url"] != url or hashlib.sha256(raw).hexdigest() != stored["sha256"]:
                    raise ValueError("缓存哈希或URL不匹配")
            else:
                raw = _download(url, 12)
                stored = {
                    "url": url,
                    "body": raw.decode(),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "fetched_at": datetime.now(UTC).isoformat(),
                }
                _rows(raw)
                _write(cache, stored)
            packet["datasets"][kind] = stored
        except (ValueError, OSError, KeyError, TypeError) as exc:
            packet["datasets"][kind] = {"url": url, "body": None, "failed_response": stored}
            packet["fetch_issues"].append(f"{kind}: {exc}")
    packet["financial"] = score_f10(stock, packet)
    return packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stock", required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--report-date")
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    try:
        if Path(args.output).resolve() == Path(args.stock).resolve():
            raise ValueError("不得覆盖原始输入")
        stock = json.loads(Path(args.stock).read_text())
        packet = fetch(stock, args.as_of, args.report_date, args.cache_dir, args.refresh)
        _write(args.output, packet)
        print(
            json.dumps(
                {"output": args.output, "financial": packet["financial"]},
                ensure_ascii=False,
                allow_nan=False,
            )
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f"f10_financial: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
