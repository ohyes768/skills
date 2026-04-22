#!/usr/bin/env python3
"""两步搜索获取铁路货运数据：Tavily 搜索 → DeepSeek 提取。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

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

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"
SEARCH_URL = "https://api.tavily.com/search"


def _load_env() -> None:
    """加载环境变量。"""
    skill_dir = Path(__file__).parent.parent
    monetary_env = skill_dir.parent / "monetary-policy-skill" / ".env"
    for line in monetary_env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, val)


def month_is_valid(month: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}", month))


def search_tavily(api_key: str, query: str, max_results: int = 5, days: int | None = None) -> dict[str, Any]:
    """Tavily 搜索。"""
    payload: dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "include_answer": True,
    }
    if days is not None:
        payload["days"] = days
    resp = requests.post(SEARCH_URL, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def call_deepseek_extract(
    session: requests.Session,
    api_key: str,
    model: str,
    tavily_results: list[dict],
    target_month: str,
    month_int: int,
) -> dict[str, Any]:
    """DeepSeek 从搜索结果中提取铁路货运数据。"""
    articles_context = ""
    for i, r in enumerate(tavily_results, 1):
        title = r.get("title", "")
        content = r.get("content", "")[:600]
        url = r.get("url", "")
        articles_context += f"""
---
第{i}篇：
标题：{title}
链接：{url}
内容：{content}
---"""

    prompt = f"""你是宏观数据抽取助手。
用户需要查找 **"{target_month}"** 月的中国铁路货运数据。

请从以下搜索结果中提取铁路货运数据：

{articles_context}

【铁路货运核心指标】
1. **货运发送量**（亿吨）：当月铁路货运总发送量
2. **货运发送量同比**（%）：与上年同期相比的增长百分比
3. **货运周转量**（亿吨公里）：当月铁路货运总周转量（可选）

【关键判断规则】
1. 如果文章**标题或正文明确提到 "{target_month}" 月的单月铁路货运数据**，可选
2. 如果文章主要讲季度/累计数据，但**正文中有 "{month_int}月份...货运发送量X亿吨"** 的具体单月数据，也应该提取
3. 如果文章中只有季度/累计数据，没有单月 "{month_int}月份" 的具体数值，则不选
4. 优先选择来源可靠、数据完整的文章（如人民日报、国铁集团官网等）

要求：
1. 文章中只要能找到 "{month_int}月份" 的具体货运发送量数据，就应该提取
2. 如果文章中找不到 "{month_int}月份" 的具体数据，返回 matched_article_index=null
3. 只返回 JSON，不要任何解释
4. 格式：
{{
  "matched_article_index": 文章序号(1/2/3/4/5),
  "freight_send_volume_million_tons": 货运发送量（如 4.6）,
  "freight_send_yoy_percent": 同比增速（如 3.4）,
  "freight_turnover_billion_ton_km": 货运周转量（如 3342.67，可选）,
  "freight_turnover_yoy_percent": 周转量同比（如 6.9，可选）,
  "source_url": "链接",
  "source_publish_date": "YYYY-MM-DD",
  "article_title": "文章标题"
}}

如果没有任何一篇是关于 "{target_month}" 月铁路货运的主要报道，返回：
{{"matched_article_index": null, "error": "未找到匹配文章"}}

注意：所有百分比数值填写百分比数值（如 3.4 表示 3.4%），不是小数。"""

    messages = [{"role": "user", "content": prompt}]
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1024,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = session.post(f"{DEFAULT_BASE_URL}/chat/completions", headers=headers, json=body, timeout=60)
    resp.raise_for_status()
    result = resp.json()

    try:
        content = result["choices"][0]["message"]["content"]
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
        if content.endswith("```"):
            content = re.sub(r"\s*```$", "", content)
        return json.loads(content.strip())
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        LOGGER.warning("DeepSeek 返回解析失败: %s", e)
        return {"error": str(e)}


def _search_and_extract(
    session: requests.Session,
    tavily_key: str,
    deepseek_key: str,
    target_month: str,
) -> dict[str, Any]:
    """搜索并提取单个月份的铁路货运数据。"""
    year, month = target_month.split("-")
    month_int = int(month)

    query = f"{year}年{month_int}月 全国铁路 货运发送量 亿吨"
    target_date = datetime.strptime(f"{target_month}-15", "%Y-%m-%d").replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc)
    days_since_target = (today - target_date).days
    search_days = max(30, min(days_since_target + 15, 120))

    LOGGER.info("搜索词: %s (时间窗口: %d 天)", query, search_days)
    try:
        tavily_result = search_tavily(tavily_key, query, days=search_days)
        all_results = tavily_result.get("results", [])
        LOGGER.info("找到 %d 条结果", len(all_results))
    except Exception as e:
        LOGGER.warning("Tavily 搜索失败: %s", e)
        return {"error": str(e)}

    # 去重
    seen_urls: set[str] = set()
    unique_results: list[dict] = []
    for r in all_results:
        url = r.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(r)

    if not unique_results:
        return {"error": f"Tavily 未找到 {target_month} 月结果"}

    LOGGER.info("去重后共 %d 条结果，传给 DeepSeek 筛选", len(unique_results))

    # DeepSeek 提取
    extracted = call_deepseek_extract(
        session, deepseek_key, DEFAULT_MODEL, unique_results, target_month, month_int
    )
    matched_idx = extracted.get("matched_article_index")
    if matched_idx is not None and matched_idx != "null":
        source_result = unique_results[matched_idx - 1]
        published_date_str = extracted.get("source_publish_date")

        # 日期校验
        if published_date_str:
            try:
                pub_date = datetime.strptime(published_date_str, "%Y-%m-%d")
                target_start = datetime.strptime(f"{target_month}-01", "%Y-%m-%d")
                if pub_date < target_start:
                    return {"error": f"文章发布于 {published_date_str}，早于目标月份 {target_month}"}
            except ValueError:
                pass

        return {
            "month": target_month,
            "freight_send_volume_million_tons": extracted.get("freight_send_volume_million_tons"),
            "freight_send_yoy_percent": extracted.get("freight_send_yoy_percent"),
            "freight_turnover_billion_ton_km": extracted.get("freight_turnover_billion_ton_km"),
            "freight_turnover_yoy_percent": extracted.get("freight_turnover_yoy_percent"),
            "source_url": extracted.get("source_url") or source_result.get("url"),
            "published_at": published_date_str,
            "announcement_title": (extracted.get("article_title", "") or source_result.get("title", ""))[:100],
        }

    return {"error": f"DeepSeek 未找到 {target_month} 月的铁路货运数据"}


def fetch_railway_freight_monthly(target_month: str) -> dict[str, Any]:
    """抓取目标月份的铁路货运数据。

    国铁集团发布时间：每月5-7号发布上月数据
    """
    if not month_is_valid(target_month):
        return {"error": f"月份格式错误: {target_month}", "parse_status": "failed"}

    # 检查数据是否可能已发布（国铁每月7号发布）
    published, hint = is_data_published(target_month, publish_day=7)
    if not published:
        LOGGER.info("铁路货运 %s 数据尚未到发布时间（预计 %s）", target_month, hint)
        return {
            "month": target_month,
            "parse_status": "not_yet_published",
            "published_hint": hint,
            "fetched_at": to_iso_now(),
        }

    # 优先读缓存，避免 Tavily/DeepSeek 重复调用
    cached = read_cache("railway_freight", target_month)
    if cached:
        LOGGER.info("缓存命中: railway_freight/%s，直接返回", target_month)
        return cached

    result: dict[str, Any] = {
        "month": target_month,
        "freight_send_volume_million_tons": None,
        "freight_send_yoy_percent": None,
        "freight_turnover_billion_ton_km": None,
        "freight_turnover_yoy_percent": None,
        "unit": "亿吨/亿吨公里/百分比",
        "source_url": None,
        "published_at": None,
        "announcement_title": None,
        "fetched_at": to_iso_now(),
        "parse_status": "failed",
        "provider": "tavily+deepseek",
    }

    _load_env()
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

    if not tavily_key:
        result["error"] = "缺少 TAVILY_API_KEY"
        return result
    if not deepseek_key:
        result["error"] = "缺少 DEEPSEEK_API_KEY"
        return result

    session = build_session()
    data = _search_and_extract(session, tavily_key, deepseek_key, target_month)

    if "error" in data and data.get("freight_send_volume_million_tons") is None:
        result["error"] = data["error"]
        return result

    result.update({k: v for k, v in data.items() if k != "month"})
    result["parse_status"] = "ok"

    LOGGER.info("提取成功: %s 亿吨, 同比 %s%%",
               result["freight_send_volume_million_tons"],
               result["freight_send_yoy_percent"])

    # 写入月度缓存
    write_cache("railway_freight", target_month, result)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="两步搜索获取铁路货运量数据")
    parser.add_argument("--month", required=True, help="目标月份（YYYY-MM）")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    args = parser.parse_args()

    setup_logging()
    data = fetch_railway_freight_monthly(args.month)
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()
