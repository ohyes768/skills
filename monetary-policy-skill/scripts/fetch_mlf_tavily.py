#!/usr/bin/env python3
"""
两步搜索：Tavily 搜索财联社 → DeepSeek 提取数据。
更通用，不依赖正则。
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

from fetch_common import build_session, setup_logging, to_iso_now, LOGGER

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


def load_env_file() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def build_result_template(target_month: str | None) -> dict[str, Any]:
    return {
        "value": None,
        "unit": "亿元",
        "month": target_month,
        "source_url": None,
        "published_at": None,
        "announcement_title": None,
        "raw_excerpt": None,
        "fetched_at": to_iso_now(),
        "parse_status": "failed",
        "provider": "tavily+deepseek",
    }


def month_is_valid(month: str) -> bool:
    match = re.fullmatch(r"(\d{4})-(\d{2})", month)
    if not match:
        return False
    return 1 <= int(match.group(2)) <= 12


def search_tavily(api_key: str, query: str, max_results: int = 3) -> dict[str, Any]:
    """第一步：Tavily 搜索"""
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "include_answer": False,
    }
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
    """第二步：DeepSeek 从多个结果中选择正确的月份并提取数据"""

    # 构建多篇文章的上下文
    articles_context = ""
    for i, r in enumerate(tavily_results, 1):
        title = r.get("title", "")
        content = r.get("content", "")[:500]  # 限制每篇长度
        url = r.get("url", "")
        articles_context += f"""
---
第{i}篇：
标题：{title}
链接：{url}
内容：{content}
---"""

    prompt = f"""你是宏观数据抽取助手。
用户需要查找 "{target_month}" 月的 MLF（中期借贷便利）净投放数据。

以下是搜索到的多篇文章，请仔细阅读，找出**明确报道 "{target_month}" 月 MLF 净投放数据**的那篇文章。

{articles_context}

要求：
1. 找出内容中**明确提到 "{target_month}" 月 MLF 净投放**的文章
2. 从中找到 MLF 净投放数值（单位：亿元）
3. 只返回 JSON，不要任何解释
4. 格式：{{"matched_article_index": 文章序号(1/2/3), "mlf_net_injection_yi": 数值, "source_url": "链接", "source_publish_date": "YYYY-MM-DD", "article_title": "文章标题"}}

如果没有任何一篇提到 "{target_month}" 月的 MLF，返回：{{"matched_article_index": null, "mlf_net_injection_yi": null}}"""

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

    # 解析 DeepSeek 返回
    try:
        content = result["choices"][0]["message"]["content"]
        # 清理可能的 markdown
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
        if content.endswith("```"):
            content = re.sub(r"\s*```$", "", content)
        return json.loads(content.strip())
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        LOGGER.warning("DeepSeek 返回解析失败: %s, 内容: %s", e, content[:200])
        return {"mlf_net_injection_yi": None}


def fetch_mlf_monthly_net(target_month: str) -> dict[str, Any]:
    """两步搜索获取 MLF 净投放"""
    result = build_result_template(target_month)

    if not month_is_valid(target_month):
        result["error"] = f"month 格式错误: {target_month}"
        return result

    load_env_file()
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()

    if not tavily_key:
        result["error"] = "缺少 TAVILY_API_KEY"
        return result
    if not deepseek_key:
        result["error"] = "缺少 DEEPSEEK_API_KEY"
        return result

    # 构建搜索词
    year, month = target_month.split("-")
    query = f"财联社 MLF 净投放 {year}年{month}月"

    LOGGER.info("=== Step 1: Tavily 搜索 ===")
    try:
        tavily_result = search_tavily(tavily_key, query)
    except Exception as exc:
        result["error"] = f"Tavily 搜索失败: {exc}"
        return result

    results = tavily_result.get("results", [])
    if not results:
        result["error"] = "Tavily 未找到结果"
        return result

    LOGGER.info("找到 %d 条结果，传给 DeepSeek 筛选", len(results))

    # DeepSeek 从多结果中选择正确月份
    LOGGER.info("=== Step 2: DeepSeek 提取 ===")
    session = build_session()
    extracted = call_deepseek_extract(
        session, deepseek_key, DEFAULT_MODEL, results, target_month
    )

    value = extracted.get("mlf_net_injection_yi")
    matched_idx = extracted.get("matched_article_index")

    if value is not None and matched_idx is not None:
        # matched_idx 是 1-based，转为 0-based
        source_result = results[matched_idx - 1]
        result["value"] = int(value)
        result["source_url"] = extracted.get("source_url") or source_result.get("url")
        result["announcement_title"] = extracted.get("article_title", "")[:100] or source_result.get("title", "")[:100]
        result["raw_excerpt"] = source_result.get("content", "")[:300]
        result["published_at"] = extracted.get("source_publish_date")
        result["matched_article_index"] = matched_idx
        result["parse_status"] = "ok"
        LOGGER.info("MLF 净投放: %d 亿元 (来自第%d篇文章)", result["value"], matched_idx)
    else:
        result["error"] = f"未找到 {target_month} 月的 MLF 净投放数据"
        result["debug"] = extracted

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="两步搜索获取 MLF 月度净投放")
    parser.add_argument("--month", required=True, help="目标月份（YYYY-MM）")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    args = parser.parse_args()

    setup_logging()
    data = fetch_mlf_monthly_net(args.month)
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()