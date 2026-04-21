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

from fetch_common import build_session, read_cache, setup_logging, to_iso_now, write_cache, LOGGER

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


def search_tavily(
    api_key: str, query: str, max_results: int = 3, days: int | None = None
) -> dict[str, Any]:
    """第一步：Tavily 搜索

    Args:
        days: 限制搜索结果的时间范围（天数）。例如 days=30 表示只返回最近30天发布的文章。
              对于月度数据，建议覆盖到目标月份即可（通常不超过60天）。
    """
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
用户需要查找 **"{target_month}"** 月的 MLF（中期借贷便利）净投放数据。

以下是搜索到的多篇文章，请仔细阅读，找出**明确以 "{target_month}" 月 MLF 净投放为主题的主要报道**。

{articles_context}

【关键判断规则】
1. 文章必须是**关于 "{target_month}" 月 MLF 操作的主要报道**，而不仅仅是提到该月数据
2. 如果一篇文章主要在讲其他月份的 MLF 操作，只是顺便提及 "{target_month}" 的数据作为对比或引用，则不能选
3. 如果文章标题或正文中出现"**{target_month}月MLF**"的明确表述（如"3月MLF净投放"、"{target_month}月MLF操作"），且正文围绕该月展开，则可选
4. 警惕！文章中可能出现"{target_month}"之前的月份数据（如"1月MLF续作加量7000亿"），这通常是背景介绍，不是目标月份数据

要求：
1. 确认文章是关于 "{target_month}" 月 MLF 的主要报道，才提取数值
2. 如果文章不符合要求，返回 matched_article_index=null
3. 只返回 JSON，不要任何解释
4. 格式：{{"matched_article_index": 文章序号(1/2/3), "mlf_net_injection_yi": 数值, "source_url": "链接", "source_publish_date": "YYYY-MM-DD", "article_title": "文章标题"}}

如果没有任何一篇是关于 "{target_month}" 月 MLF 的主要报道，返回：{{"matched_article_index": null, "mlf_net_injection_yi": null}}"""

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


def determine_published_mlf_month(target_month: str, today: datetime) -> str:
    """MLF 每月2-3日发布上月数据，自动降级到已发布的月份。

    例如：2026-04-21 查询 2026-04，应降级为 2026-03（3月数据在4月2-3日已发布）。
    """
    req_year, req_month = map(int, target_month.split("-"))
    next_month = req_month + 1
    next_year = req_year
    if next_month > 12:
        next_month = 1
        next_year += 1
    publish_dt = datetime(next_year, next_month, MLF_PUBLISH_DAY)
    if today >= publish_dt:
        return target_month
    # 未发布，降级查上月
    prev_month = req_month - 1 if req_month > 1 else 12
    prev_year = req_year if req_month > 1 else req_year - 1
    return f"{prev_year}-{prev_month:02d}"


MLF_PUBLISH_DAY = 3


def fetch_mlf_monthly_net(target_month: str) -> dict[str, Any]:
    """两步搜索获取 MLF 净投放。内部自动处理月份降级。"""
    # 自动判断数据是否已发布，未发布则降级到上月
    actual_month = determine_published_mlf_month(target_month, datetime.now())
    requested_month = target_month

    # 优先读缓存（用实际月份去读）
    cached = read_cache("mlf", actual_month)
    if cached:
        LOGGER.info("MLF 缓存命中 [%s]，跳过搜索", actual_month)
        cached["requested_month"] = requested_month
        cached["actual_month"] = actual_month
        return cached

    result = build_result_template(actual_month)
    result["requested_month"] = requested_month
    result["actual_month"] = actual_month

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
    year, month = actual_month.split("-")
    query = f"财联社 MLF 净投放 {year}年{month}月"

    # 计算日期范围：实际月份数据已发布，搜索窗口覆盖发布日之后
    # actual_month 的数据在 next_month 的 2-3日 发布
    req_year, req_month = map(int, actual_month.split("-"))
    next_month = req_month + 1
    next_year = req_year
    if next_month > 12:
        next_month = 1
        next_year += 1
    publish_dt = datetime(next_year, next_month, MLF_PUBLISH_DAY).replace(tzinfo=timezone.utc)
    today = datetime.now(timezone.utc)
    days_since_publish = (today - publish_dt).days
    # 最多搜索90天；发布后立即可查，覆盖发布日之后的时间
    search_days = max(15, min(days_since_publish + 5, 90))
    LOGGER.info("目标月份: %s（实际查询月份: %s），搜索时间窗口: %d 天",
                requested_month, actual_month, search_days)

    LOGGER.info("=== Step 1: Tavily 搜索 ===")
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

    # DeepSeek 从多结果中选择正确月份
    LOGGER.info("=== Step 2: DeepSeek 提取 ===")
    session = build_session()
    extracted = call_deepseek_extract(
        session, deepseek_key, DEFAULT_MODEL, results, target_month
    )

    value = extracted.get("mlf_net_injection_yi")
    matched_idx = extracted.get("matched_article_index")
    published_date_str = extracted.get("source_publish_date")

    if value is not None and matched_idx is not None:
        # matched_idx 是 1-based，转为 0-based
        source_result = results[matched_idx - 1]

        # 日期校验：文章必须发布在目标月份之后
        if published_date_str:
            try:
                pub_date = datetime.strptime(published_date_str, "%Y-%m-%d")
                target_start = datetime.strptime(f"{target_month}-01", "%Y-%m-%d")
                if pub_date < target_start:
                    result["error"] = f"文章发布于 {published_date_str}，早于目标月份 {target_month}，被过滤"
                    result["debug"] = extracted
                    LOGGER.warning("过滤历史文章: %s (发布于 %s，早于 %s)",
                                   extracted.get("article_title", ""), published_date_str, target_month)
                    return result
            except ValueError:
                LOGGER.warning("无法解析发布日期: %s", published_date_str)

        result["value"] = int(value)
        result["source_url"] = extracted.get("source_url") or source_result.get("url")
        result["announcement_title"] = extracted.get("article_title", "")[:100] or source_result.get("title", "")[:100]
        result["raw_excerpt"] = source_result.get("content", "")[:300]
        result["published_at"] = published_date_str
        result["matched_article_index"] = matched_idx
        result["parse_status"] = "ok"
        # 写入月度缓存
        write_cache("mlf", target_month, result)
        LOGGER.info("MLF 净投放: %d 亿元 (来自第%d篇文章, 发布于 %s)",
                    result["value"], matched_idx, published_date_str)
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

    # 自动判断数据是否已发布（未发布则查上月）
    requested_month = args.month
    actual_month = determine_published_mlf_month(requested_month, datetime.now())
    data = fetch_mlf_monthly_net(actual_month)

    # 在返回结果中标注请求月份与实际月份的关系
    data["requested_month"] = requested_month
    data["actual_month"] = actual_month
    if requested_month != actual_month:
        LOGGER.info("请求月份 %s，数据尚未发布，降级到 %s", requested_month, actual_month)

    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()