#!/usr/bin/env python3
"""发现今日可申购港股，逐只调用 hkipo 分析，并生成或推送 Markdown。"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup


SINA_IPO_LIST = "http://vip.stock.finance.sina.com.cn/q/view/hk_IPOList.php"
DEFAULT_RELAY = "https://web.duomi77.cn:9443/rss/api/rss-relay/post"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
]
SCRIPT_DIR = Path(__file__).resolve().parent
HKIPO = SCRIPT_DIR / "hkipo.py"


def parse_date(value: str) -> date | None:
    value = value.strip().split()[0]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def normalize_code(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return digits.zfill(5) if digits else value.strip()


def discover_active_ipos(as_of: date) -> list[dict[str, Any]]:
    """复用 stock-info-dingding 的新浪列表解析思路，筛选招股期覆盖 as_of 的股票。"""
    headers = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    with httpx.Client(timeout=15, follow_redirects=True) as client:
        response = client.get(SINA_IPO_LIST, headers=headers)
        response.raise_for_status()
    response.encoding = "gbk"
    soup = BeautifulSoup(response.text, "lxml")
    tables = soup.find_all("table")
    if len(tables) < 2:
        raise RuntimeError("新浪港股 IPO 页面未找到预期数据表")

    active: list[dict[str, Any]] = []
    for row in tables[1].find_all("tr"):
        cols = row.find_all(["td", "th"])
        if len(cols) < 7:
            continue
        code = normalize_code(cols[0].get_text(strip=True))
        name = cols[1].get_text(strip=True)
        raw_range = cols[5].get_text(strip=True)
        listing = parse_date(cols[6].get_text(strip=True))
        if not code.isdigit() or not name or "至" not in raw_range:
            continue
        start_raw, end_raw = raw_range.split("至", 1)
        start, end = parse_date(start_raw), parse_date(end_raw)
        if start and end and start <= as_of <= end and (not listing or listing > as_of):
            active.append(
                {
                    "code": code,
                    "name": name,
                    "offer_price_range": cols[2].get_text(strip=True) or None,
                    "offer_shares": cols[3].get_text(strip=True) or None,
                    "subscription_start": start.isoformat(),
                    "subscription_end": end.isoformat(),
                    "listing_date": listing.isoformat() if listing else None,
                    "discovery_source": SINA_IPO_LIST,
                }
            )
    return active


def analyze_code(code: str, timeout: int) -> tuple[dict[str, Any] | None, str | None]:
    command = [sys.executable, str(HKIPO), "analyze", code]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return None, f"分析超过 {timeout} 秒"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        primary_error = detail[-1] if detail else f"分析命令退出码 {result.returncode}"
        try:
            sys.path.insert(0, str(SCRIPT_DIR))
            from hkipo.tradesmart import get_tracker_margin

            tracker = get_tracker_margin(code)
            if tracker:
                return {
                    "code": code,
                    "margin": {
                        "total_billion": tracker["margin_total_hkd_yi"],
                        "oversubscription_forecast": tracker["oversubscription_ratio"],
                        "observed_at": tracker["observed_at"],
                        "source": "TradeSmart IPO Tracker",
                        "source_url": tracker["tracker_url"],
                    },
                    "partial": True,
                    "primary_error": primary_error,
                }, None
        except Exception as fallback_error:
            return None, f"{primary_error}；TradeSmart 回退失败：{fallback_error}"
        return None, primary_error
    try:
        return json.loads(result.stdout), None
    except json.JSONDecodeError:
        return None, "分析输出不是有效 JSON"


def money(value: Any, unit: str = "") -> str:
    if value in (None, "", "--"):
        return "未找到"
    if isinstance(value, float):
        value = f"{value:.2f}".rstrip("0").rstrip(".")
    return f"{value}{unit}"


def render_stock(stock: dict[str, Any], analysis: dict[str, Any] | None, error: str | None) -> list[str]:
    lines = [f"## {stock['name']}（{stock['code']}）", ""]
    lines.extend(
        [
            "| 项目 | 数据 |",
            "|---|---|",
            f"| 招股期 | {stock['subscription_start']} 至 {stock['subscription_end']} |",
            f"| 招股价 | {money(stock.get('offer_price_range'))} |",
            f"| 上市日期 | {money(stock.get('listing_date'))} |",
        ]
    )
    if error:
        lines.extend(["", f"> 聚合分析源暂时失败：{error}。以下仅确认招股窗口，不补造孖展、基石或评级数据。"])
        return lines

    analysis = analysis or {}
    brief = analysis.get("brief") or {}
    subscription = analysis.get("subscription") or {}
    margin = analysis.get("margin") or {}
    cornerstone = analysis.get("cornerstone") or {}
    rating = analysis.get("rating") or {}
    sponsor = analysis.get("sponsor_history") or {}
    lines.extend(
        [
            f"| 行业 | {money(brief.get('industry'))} |",
            f"| 入场费 | {money(brief.get('entry_fee') or subscription.get('minimum_amount_hkd'), ' HKD')} |",
            f"| 市盈率 | {money(brief.get('pe'), 'x')} |",
            f"| 孖展总额 | {money(margin.get('total_billion'), ' 亿港元')} |",
            f"| 预计超购 | {money(margin.get('oversubscription_forecast'), ' 倍')} |",
            f"| 基石投资者 | {money(cornerstone.get('count'), ' 家')} |",
            f"| 评级 | {money(rating.get('avg_score'))}（{money(rating.get('count'), ' 家')}） |",
            f"| 保荐人 | {money(sponsor.get('sponsor'))} |",
        ]
    )
    positives, risks = [], []
    if (margin.get("total_billion") or 0) >= 50:
        positives.append("孖展金额达到热门区间")
    if (cornerstone.get("count") or 0) > 0:
        positives.append("已披露基石投资者")
    if brief.get("pe") in (None, "", "--"):
        risks.append("估值数据缺失")
    if not margin:
        risks.append("孖展数据未找到")
    if analysis.get("partial"):
        risks.append("TradeSmart 当前仅提供部分聚合数据，未取得基石和评级")
    lines.extend(
        [
            "",
            f"- **正面因素：** {'；'.join(positives) if positives else '当前数据不足以确认明显优势'}",
            f"- **主要风险：** {'；'.join(risks) if risks else '仍需关注定价、市场情绪及最终配售变化'}",
            "- **数据置信度：** 招股窗口已由新浪列表确认；其余字段来自 skill 聚合源，关键结论仍应与港交所公告交叉核验。",
        ]
    )
    if margin.get("observed_at"):
        lines.append(f"- **孖展时点：** {margin['observed_at']}（来源：{margin.get('source', 'TradeSmart')}）")
    return lines


def build_report(as_of: date, stocks: list[dict[str, Any]], timeout: int) -> tuple[str, list[dict[str, Any]]]:
    lines = [f"# {as_of.isoformat()} 港股打新研究", "", f"**生成时间：** {datetime.now().astimezone().isoformat(timespec='seconds')}", ""]
    results: list[dict[str, Any]] = []
    if not stocks:
        lines.extend(["今天没有从新浪港股 IPO 列表确认到仍在招股的新股。", "", "> 这表示当前数据源未发现，不等于港交所绝对没有；建议复核披露易或券商新股中心。"])
    else:
        lines.extend([f"今天确认有 **{len(stocks)} 只**仍在招股：" + "、".join(f"{s['name']}（{s['code']}）" for s in stocks), ""])
        for stock in stocks:
            analysis, error = analyze_code(stock["code"], timeout)
            results.append({"stock": stock, "analysis": analysis, "error": error})
            lines.extend(render_stock(stock, analysis, error))
            lines.append("")
    lines.extend(
        [
            "---",
            "",
            "## 数据来源与声明",
            "",
            f"- 当日可申购列表：[新浪港股 IPO 列表]({SINA_IPO_LIST})",
            "- 孖展及预计超购：TradeSmart IPO Tracker；保荐人历史使用集思录、经济通等公开来源。",
            "- 第三方数据可能延迟或口径不同；本文仅供研究，不构成认购、买卖或收益承诺。",
        ]
    )
    return "\n".join(lines), results


def push_report(
    endpoint: str,
    title: str,
    content: str,
    source: str,
    url: str = "",
    verify_tls: bool = True,
) -> dict[str, Any]:
    payload = {"title": title, "content": content, "url": url, "source": source}
    response = httpx.post(endpoint, json=payload, timeout=20, verify=verify_tls)
    response.raise_for_status()
    try:
        return response.json()
    except json.JSONDecodeError:
        return {"status_code": response.status_code, "body": response.text[:500]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="研究日期，格式 YYYY-MM-DD；默认今天")
    parser.add_argument("--output", help="把 Markdown 写到指定文件")
    parser.add_argument("--push", action="store_true", help="推送到 RSS Relay；默认只预览")
    parser.add_argument("--allow-incomplete", action="store_true", help="允许推送数据骨架；默认禁止")
    parser.add_argument("--endpoint", default=DEFAULT_RELAY)
    parser.add_argument("--source", default="hk-ipo-research")
    parser.add_argument("--insecure", action="store_true", help="仅对自签名内网 Relay 关闭 TLS 证书校验")
    parser.add_argument("--analysis-timeout", type=int, default=45)
    args = parser.parse_args()

    as_of = date.fromisoformat(args.date) if args.date else date.today()
    stocks = discover_active_ipos(as_of)
    markdown, _ = build_report(as_of, stocks, args.analysis_timeout)
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    if args.push:
        if not args.allow_incomplete:
            raise SystemExit(
                "已阻止推送：daily_rss_report.py 只生成采集骨架。请由 agent 完成招股书/网页研究后，"
                "使用 scripts/push_rss.py 推送最终 Markdown。"
            )
        title = f"{as_of.isoformat()} 港股打新研究（{len(stocks)}只）"
        result = push_report(args.endpoint, title, markdown, args.source, verify_tls=not args.insecure)
        print(json.dumps({"pushed": True, "response": result}, ensure_ascii=False), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
