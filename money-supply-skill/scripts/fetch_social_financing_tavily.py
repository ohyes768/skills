#!/usr/bin/env python3
"""两步搜索获取社融数据：Tavily 搜索 → DeepSeek 提取。"""

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
        "total_financing_balance_yi": None,          # 社融余额（万亿元）
        "balance_yoy_percent": None,                # 余额同比增速（%）
        "balance_yoy_prev_month": None,             # 上月余额同比（%，用于计算环比）
        "balance_yoy_change_pp": None,              # 余额同比环比变化（百分点）
        "monthly_new_financing_yi": None,          # 当月新增社融（亿元）
        "monthly_new_yoy_change_yi": None,         # 同比变化量（亿元）
        "monthly_new_yoy_percent": None,           # 同比增速（%）
        "unit": "亿元/万亿元",
        "month": target_month,
        "prev_month": None,                        # 上月月份
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


def get_prev_month(target_month: str) -> str:
    """计算上一个月，例如 2026-03 -> 2026-02"""
    year, month = target_month.split("-")
    month_int = int(month)
    if month_int == 1:
        return f"{int(year) - 1}-12"
    return f"{year}-{month_int - 1:02d}"


def search_tavily(
    api_key: str, query: str, max_results: int = 5, days: int | None = None
) -> dict[str, Any]:
    """第一步：Tavily 搜索"""
    url = "https://api.tavily.com/search"
    payload: dict[str, Any] = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "include_answer": True,
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
    """第二步：DeepSeek 从多个结果中提取社融数据"""

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
用户需要查找 **"{target_month}"** 月的中国社会融资规模（社融）数据。

请从以下搜索结果中提取社融数据：

{articles_context}

【社融数据包含两个核心指标】
1. **社融余额**（也叫社融规模存量）：指截至月末的累计总量，通常以"万亿元"为单位，同比增速反映整体规模增长
2. **社融新增**（也叫社融增量）：指当月新增的社会融资规模，反映当月实体经济获得的融资情况

【关键判断规则】
1. 文章必须是**关于 "{target_month}" 月社融数据的主要报道**
2. 如果文章主要在讲其他月份数据，只是顺便提及目标月份，则不能选
3. 警惕！文章中可能出现对比数据（如"1月新增5000亿，2月..."），这是背景不是目标月份
4. 优先选择来源可靠、数据完整的文章（如央行、统计局、财联社等）

要求：
1. 确认文章是关于 "{target_month}" 月社融的主要报道，才提取数值
2. 如果文章不符合要求，返回 matched_article_index=null
3. 只返回 JSON，不要任何解释
4. 格式：
{{
  "matched_article_index": 文章序号(1/2/3/4/5),
  "total_financing_balance_yi": 余额数值（万亿元，如 456.46）,
  "balance_yoy_percent": 余额同比增速（如 7.9）,
  "monthly_new_financing_yi": 当月新增社融（亿元，如 52253）,
  "monthly_new_yoy_change_yi": 同比变化量（亿元，如 6708）,
  "monthly_new_yoy_percent": 同比增速（如 11.4）,
  "source_url": "链接",
  "source_publish_date": "YYYY-MM-DD",
  "article_title": "文章标题"
}}

如果没有任何一篇是关于 "{target_month}" 月社融的主要报道，返回：
{{"matched_article_index": null, "error": "未找到匹配文章"}}

注意：所有数值都是百分比的填写百分比数值（如 7.9 表示 7.9%），不是小数。"""

    messages = [{"role": "user", "content": prompt}]
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1024,
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
        return {"error": str(e)}


def _search_and_extract(
    session: requests.Session,
    tavily_key: str,
    deepseek_key: str,
    target_month: str,
) -> dict[str, Any]:
    """搜索并提取单个月份的社融数据"""
    year, month = target_month.split("-")

    query = f"{year}年{month}月 社会融资规模 社融余额 新增 同比 人民银行"
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
    seen_urls = set()
    unique_results = []
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
        session, deepseek_key, DEFAULT_MODEL, unique_results, target_month
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
            "balance_yoy_percent": extracted.get("balance_yoy_percent"),
            "total_financing_balance_yi": extracted.get("total_financing_balance_yi"),
            "monthly_new_financing_yi": extracted.get("monthly_new_financing_yi"),
            "monthly_new_yoy_change_yi": extracted.get("monthly_new_yoy_change_yi"),
            "monthly_new_yoy_percent": extracted.get("monthly_new_yoy_percent"),
            "source_url": extracted.get("source_url") or source_result.get("url"),
            "published_at": published_date_str,
            "announcement_title": (extracted.get("article_title", "") or source_result.get("title", ""))[:100],
            "raw_excerpt": source_result.get("content", "")[:300],
        }

    return {"error": f"DeepSeek 未找到 {target_month} 月的社融数据"}


def fetch_social_financing_monthly(target_month: str) -> dict[str, Any]:
    """两步搜索获取社融月度数据，同时获取当月和上月用于计算环比变化"""
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

    prev_month = get_prev_month(target_month)
    result["prev_month"] = prev_month

    LOGGER.info("=== 搜索当月 %s ===", target_month)
    session = build_session()
    current_data = _search_and_extract(session, tavily_key, deepseek_key, target_month)

    if "error" in current_data and "balance_yoy_percent" not in current_data:
        result["error"] = current_data["error"]
        return result

    LOGGER.info("=== 搜索上月 %s ===", prev_month)
    prev_data = _search_and_extract(session, tavily_key, deepseek_key, prev_month)

    # 填充当月数据
    result["total_financing_balance_yi"] = current_data.get("total_financing_balance_yi")
    result["balance_yoy_percent"] = current_data.get("balance_yoy_percent")
    result["monthly_new_financing_yi"] = current_data.get("monthly_new_financing_yi")
    result["monthly_new_yoy_change_yi"] = current_data.get("monthly_new_yoy_change_yi")
    result["monthly_new_yoy_percent"] = current_data.get("monthly_new_yoy_percent")
    result["source_url"] = current_data.get("source_url")
    result["published_at"] = current_data.get("published_at")
    result["announcement_title"] = current_data.get("announcement_title")
    result["raw_excerpt"] = current_data.get("raw_excerpt")

    # 填充上月数据并计算环比
    if "error" not in prev_data and prev_data.get("balance_yoy_percent") is not None:
        result["balance_yoy_prev_month"] = prev_data.get("balance_yoy_percent")
        current_yoy = current_data.get("balance_yoy_percent")
        prev_yoy = prev_data.get("balance_yoy_percent")
        if current_yoy is not None and prev_yoy is not None:
            result["balance_yoy_change_pp"] = round(current_yoy - prev_yoy, 1)
            LOGGER.info("环比变化计算成功: %s%% - %s%% = %s%%",
                       current_yoy, prev_yoy, result["balance_yoy_change_pp"])
    else:
        LOGGER.warning("上月数据获取失败，将不计算环比变化: %s", prev_data.get("error", "未知错误"))

    result["parse_status"] = "ok"

    LOGGER.info("社融数据提取成功:")
    LOGGER.info("  当月余额: %s 万亿元, 同比 %s%%",
               result["total_financing_balance_yi"], result["balance_yoy_percent"])
    LOGGER.info("  上月同比: %s%%, 环比变化: %s%%",
               result.get("balance_yoy_prev_month"), result.get("balance_yoy_change_pp"))
    LOGGER.info("  当月新增: %s 亿元, 同比 %s%%",
               result["monthly_new_financing_yi"], result["monthly_new_yoy_percent"])

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="两步搜索获取社融月度数据")
    parser.add_argument("--month", required=True, help="目标月份（YYYY-MM）")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    args = parser.parse_args()

    setup_logging()
    data = fetch_social_financing_monthly(args.month)
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()
