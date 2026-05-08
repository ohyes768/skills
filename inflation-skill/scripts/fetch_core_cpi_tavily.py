#!/usr/bin/env python3
"""
两步搜索获取核心CPI：Tavily 搜索权威媒体 → DeepSeek 提取数值。
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from fetch_common import (
    build_session,
    is_valid_month,
    now as _now,
    published_month,
    read_cache,
    setup_logging,
    write_cache,
    LOGGER,
)

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"

# 核心CPI随CPI一同发布：每月9日
PUBLISH_DAY = 9


def build_result_template(target_month: str | None) -> dict[str, Any]:
    return {
        "core_cpi_yoy": None,
        "unit": "%",
        "month": target_month,
        "source_url": None,
        "published_at": None,
        "announcement_title": None,
        "raw_excerpt": None,
        "fetched_at": _now(),
        "parse_status": "failed",
        "provider": "tavily+deepseek",
    }


def search_tavily(
    api_key: str, query: str, max_results: int = 5, days: int | None = None
) -> dict[str, Any]:
    url = "https://api.tavily.com/search"
    payload: dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
    }
    if days is not None:
        payload["days"] = days
    response = requests.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


def call_deepseek_extract(
    session: requests.Session,
    api_key: str,
    model: str,
    tavily_results: list[dict],
    target_month: str,
) -> dict[str, Any]:
    """DeepSeek 从多篇搜索结果中提取目标月份的核心CPI同比值。"""

    articles_context = ""
    for i, r in enumerate(tavily_results, 1):
        title = r.get("title", "")
        content = r.get("content", "")[:800]
        url = r.get("url", "")
        articles_context += f"""
---
第{i}篇：
标题：{title}
链接：{url}
内容：{content}
---"""

    prompt = f"""你是宏观数据抽取助手。用户需要查找 **"{target_month}"** 月的 中国核心CPI（居民消费价格核心指数）同比数据。

以下是搜索到的多篇文章，请仔细阅读，找出**明确包含 "{target_month}" 月核心CPI同比数值**的报道。

核心CPI排除了食品和能源价格波动，是反映通胀趋势的关键指标。

{articles_context}

【关键判断规则】
1. 文章必须明确给出 "{target_month}" 月的核心CPI同比数值（如"0.6%"、"0.5%"等）
2. 如果文章只提到CPI总指数而未提核心CPI，不算命中
3. 如果文章是其他月份的核心CPI数据，不能选
4. 警惕！注意区分"核心CPI"和其他指标（如核心PPI、核心PCE等）

要求：
1. 返回包含核心CPI同比值的文章序号
2. 只返回 JSON，不要任何解释
3. 格式：{{"matched_article_index": 文章序号(1-5), "core_cpi_yoy": 数值(如0.6), "source_url": "链接", "source_publish_date": "YYYY-MM-DD", "article_title": "文章标题"}}

如果没有找到任何一篇包含 "{target_month}" 月核心CPI数据的文章，返回：{{"matched_article_index": null, "core_cpi_yoy": null}}"""

    messages = [{"role": "user", "content": prompt}]
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 512,
    }

    endpoint = f"{DEFAULT_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    response = session.post(endpoint, headers=headers, json=body, timeout=60)
    response.raise_for_status()
    result = response.json()

    try:
        content = result["choices"][0]["message"]["content"]
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
        if content.endswith("```"):
            content = re.sub(r"\s*```$", "", content)
        return json.loads(content.strip())
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        LOGGER.warning("DeepSeek 返回解析失败: %s, 内容: %s", e, content[:200] if 'content' in dir() else 'N/A')
        return {"core_cpi_yoy": None}


def fetch_core_cpi(target_month: str) -> dict[str, Any]:
    """两步搜索获取核心CPI。内部自动处理月份降级。"""
    # 自动判断数据是否已发布，未发布则降级到上月
    actual_month = published_month(target_month, datetime.now(timezone.utc), PUBLISH_DAY)
    requested_month = target_month

    result = build_result_template(actual_month)
    result["requested_month"] = requested_month
    result["actual_month"] = actual_month

    if not is_valid_month(target_month):
        result["error"] = f"month 格式错误: {target_month}"
        return result

    # 优先读缓存（用实际月份去读）
    cached = read_cache("core_cpi", actual_month)
    if cached:
        LOGGER.info("核心CPI 缓存命中 [%s]，跳过搜索", actual_month)
        cached["requested_month"] = requested_month
        cached["actual_month"] = actual_month
        return cached

    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

    if not tavily_key:
        result["error"] = "缺少 TAVILY_API_KEY"
        return result
    if not deepseek_key:
        result["error"] = "缺少 DEEPSEEK_API_KEY"
        return result

    year, month = actual_month.split("-")
    if requested_month != actual_month:
        LOGGER.info("请求月份 %s，数据尚未发布，降级到 %s", requested_month, actual_month)
    # 搜索词：核心CPI + 月份
    query = f"中国 核心CPI {year}年{month}月 同比"

    # 搜索时间窗口：月度数据通常在月中旬发布，搜索60天足够
    search_days = 60

    LOGGER.info("=== Step 1: Tavily 搜索核心CPI ===")
    LOGGER.info("查询词: %s", query)
    try:
        tavily_result = search_tavily(tavily_key, query, days=search_days)
    except Exception as exc:
        result["error"] = f"Tavily 搜索失败: {exc}"
        return result

    results = tavily_result.get("results", [])
    if not results:
        result["error"] = "Tavily 未找到结果"
        return result

    LOGGER.info("找到 %d 条结果，传给 DeepSeek 筛选", len(results))

    LOGGER.info("=== Step 2: DeepSeek 提取 ===")
    session = build_session()
    extracted = call_deepseek_extract(
        session, deepseek_key, DEFAULT_MODEL, results, actual_month
    )

    value = extracted.get("core_cpi_yoy")
    matched_idx = extracted.get("matched_article_index")
    published_date_str = extracted.get("source_publish_date")

    if value is not None and matched_idx is not None:
        source_result = results[matched_idx - 1]

        if published_date_str:
            try:
                pub_date = datetime.strptime(published_date_str, "%Y-%m-%d")
                target_start = datetime.strptime(f"{target_month}-01", "%Y-%m-%d")
                if pub_date < target_start:
                    result["error"] = f"文章发布于 {published_date_str}，早于目标月份 {target_month}，被过滤"
                    result["debug"] = extracted
                    LOGGER.warning("过滤历史文章: %s", extracted.get("article_title", ""))
                    return result
            except ValueError:
                LOGGER.warning("无法解析发布日期: %s", published_date_str)

        result["core_cpi_yoy"] = float(value)
        result["source_url"] = extracted.get("source_url") or source_result.get("url")
        result["announcement_title"] = (extracted.get("article_title", "") or source_result.get("title", ""))[:100]
        result["raw_excerpt"] = source_result.get("content", "")[:300]
        result["published_at"] = published_date_str
        result["matched_article_index"] = matched_idx
        result["parse_status"] = "ok"

        write_cache("core_cpi", actual_month, result)
        LOGGER.info("核心CPI获取成功 [%s]: %.1f%% (来自第%d篇文章, 发布于 %s)",
                    actual_month, result["core_cpi_yoy"], matched_idx, published_date_str)
    else:
        result["error"] = f"未找到 {actual_month} 月的核心CPI数据"
        result["debug"] = extracted

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="两步搜索获取核心CPI")
    parser.add_argument("--month", required=True, help="目标月份（YYYY-MM）")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    args = parser.parse_args()

    setup_logging()
    data = fetch_core_cpi(args.month)
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()
