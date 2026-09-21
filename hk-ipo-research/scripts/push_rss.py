#!/usr/bin/env python3
"""把已经完成研究和质检的 Markdown 推送到 RSS Relay。"""

import argparse
import json
import re
from pathlib import Path

import httpx


DEFAULT_ENDPOINT = "https://web.duomi77.cn:9443/rss/api/rss-relay/post"
DEFAULT_POSTS_ENDPOINT = "https://web.duomi77.cn:9443/rss/api/rss-relay/posts"
REPORT_START_MARKER = "<!-- HK_IPO_REPORT_START -->"
SKILL_ECHO_MARKERS = (
    "name: hk-ipo-research",
    "# 港股 IPO 研究",
    "## 每日 RSS / cron path",
    "## PITFALLS（save these",
)
REQUIRED_MARKERS = [
    "## 关键 Offer Terms",
    "## 热度",
    "## 财务基本面",
    "## 业务与股东",
    "## 评分",
    "## 风险提示",
    "## 数据来源",
]
BACKTEST_REQUIRED_MARKERS = [
    "## 回测状态",
    "## 历史候选全集",
    "## 数据泄漏审计",
    "## 真实结果",
    "## 命中表",
    "## 误差复盘",
    "## 限制与声明",
]
PLACEHOLDERS = ["行业 | 未找到", "基石投资者 | 未找到", "保荐人 | 未找到", "评级 | 未找到"]
UNAVAILABLE_TERMS = ("未找到", "公开渠道暂缺", "无法获取", "待手工核对")


def sanitize_report(content: str) -> tuple[str, list[str]]:
    """裁掉模型复读的 skill/prompt，只保留报告正文。"""
    warnings = []
    marker_index = content.rfind(REPORT_START_MARKER)
    if marker_index >= 0:
        content = content[marker_index + len(REPORT_START_MARKER):].lstrip()
    elif any(marker in content for marker in SKILL_ECHO_MARKERS):
        starts = []
        for pattern in (
            r"(?m)^#\s+\d{4}-\d{2}-\d{2}\s+港股",
            r"(?m)^##\s+排名总览\s*$",
            r"(?m)^##\s+关键 Offer Terms\s*$",
            r"(?m)^##\s+回测状态\s*$",
        ):
            match = re.search(pattern, content)
            if match:
                starts.append(match.start())
        if starts:
            content = content[min(starts):].lstrip()
            warnings.append("检测到 SKILL.md/提示词回显，推送前已自动裁剪")
        else:
            warnings.append("检测到 SKILL.md/提示词回显，但未找到可靠报告起点")

    if any(marker in content for marker in SKILL_ECHO_MARKERS):
        warnings.append("净化后的正文仍疑似包含 SKILL.md 内容")
    return content, warnings


def extract_section(content: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", content
    )
    return match.group(1).strip() if match else ""


def field_has_number(section: str, labels: tuple[str, ...]) -> bool:
    for line in section.splitlines():
        if any(label in line for label in labels):
            if any(term in line for term in UNAVAILABLE_TERMS):
                continue
            if re.search(r"\d", line):
                return True
    return False


def field_has_text(section: str, labels: tuple[str, ...]) -> bool:
    for line in section.splitlines():
        if not any(label in line for label in labels):
            continue
        if any(term in line for term in UNAVAILABLE_TERMS):
            continue
        if "未披露" in line and "已核验" not in line:
            continue
        parts = re.split(r"[：:]", line, maxsplit=1)
        if len(parts) < 2:
            continue
        value = re.sub(r"[*_`#>\s]", "", parts[1])
        if len(value) >= 2:
            return True
    return False


def validate_financial_section(content: str) -> list[str]:
    section = extract_section(content, "财务基本面")
    if not section:
        return []  # REQUIRED_MARKERS 已负责报告缺失章节。

    errors = []
    if not field_has_number(section, ("营业收入", "营收", "收益")):
        errors.append("财务基本面缺少带数值的营业收入/收益")
    if not field_has_number(section, ("净利润", "净亏损", "期内利润", "期内亏损")):
        errors.append("财务基本面缺少带数值的净利润/净亏损")
    if not any(
        field_has_number(section, labels)
        for labels in (("毛利率", "净利率"), ("现金流", "现金及现金等价物"), ("客户集中度", "前五大客户", "最大客户"))
    ):
        errors.append("财务基本面至少需要毛利率、现金流或客户集中度中的一类数值证据")
    if "HKEX" in section and ("反爬" in section or "自行翻阅招股书" in section):
        errors.append("不得以 HKEX PDF 抓取失败代替实时全网财务研究")
    return errors


def validate_ownership_section(content: str) -> list[str]:
    section = extract_section(content, "业务与股东")
    if not section:
        return []  # REQUIRED_MARKERS 已负责报告缺失章节。

    errors = []
    controller_labels = ("创始人", "联合创始人", "实际控制人", "控股股东")
    investor_labels = ("主要机构或产业股东", "机构股东", "产业股东", "主要投资者")
    if not field_has_text(section, controller_labels):
        errors.append("业务与股东缺少创始人/实际控制人/控股股东的有效结论")
    if not field_has_text(section, investor_labels):
        errors.append("业务与股东缺少主要机构/产业股东；未披露时须写明已核验来源")
    if "招股书内" in section and "未找到" in section:
        errors.append("不得以“招股书内未找到”代替实时全网股东研究")
    return errors


def validate_report(content: str, report_type: str = "research") -> list[str]:
    markers = BACKTEST_REQUIRED_MARKERS if report_type == "backtest" else REQUIRED_MARKERS
    errors = [f"缺少章节：{marker}" for marker in markers if marker not in content]
    if report_type == "research":
        errors.extend(f"仍有关键占位符：{marker}" for marker in PLACEHOLDERS if marker in content)
        errors.extend(validate_financial_section(content))
        errors.extend(validate_ownership_section(content))
    elif "回测无效" in content:
        errors.append("回测状态为无效")
    if len(content) < 1800:
        errors.append("报告少于 1800 字符，疑似仍是数据骨架")
    if "http://" not in content and "https://" not in content:
        errors.append("报告没有任何可核验来源链接")
    return errors


def validate_title(title: str, content: str, report_type: str = "research") -> list[str]:
    if report_type == "backtest":
        expected = r"^\d{4}-\d{2}-\d{2} 港股IPO回测｜.+（\d{5}\.HK）｜(?:预测命中|部分命中|预测未命中)$"
        hint = "标题格式应为：YYYY-MM-DD 港股IPO回测｜公司名（00000.HK）｜预测命中/部分命中/预测未命中"
    else:
        expected = r"^\d{4}-\d{2}-\d{2} 港股打新｜.+（\d{5}\.HK）｜\d{1,3}分 [A-D][+-]?$"
        hint = "标题格式应为：YYYY-MM-DD 港股打新｜公司名（00000.HK）｜66分 B"
    errors = [] if re.match(expected, title) else [hint]
    code_match = re.search(r"(\d{5})\.HK", content)
    if code_match and code_match.group(1) not in title:
        errors.append(f"标题股票代码与正文不一致：正文为 {code_match.group(1)}.HK")
    return errors


def is_duplicate(posts_endpoint: str, title: str, verify_tls: bool) -> bool:
    response = httpx.get(posts_endpoint, params={"limit": 100}, timeout=20, verify=verify_tls)
    response.raise_for_status()
    posts = response.json().get("posts", [])
    code_match = re.search(r"(\d{5})\.HK", title)
    day = title[:10]
    if not code_match:
        return any(post.get("title") == title for post in posts)
    code = code_match.group(1)
    for post in posts:
        post_title = post.get("title", "")
        post_content = post.get("content", "")
        post_day = str(post.get("created_at", ""))[:10]
        if (day in post_title or day == post_day) and (code in post_title or code in post_content):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", help="最终 Markdown 文件")
    parser.add_argument("--title", required=True)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--posts-endpoint", default=DEFAULT_POSTS_ENDPOINT)
    parser.add_argument("--source", default="hk-ipo-research")
    parser.add_argument("--report-type", choices=("research", "backtest"), default="research")
    parser.add_argument("--url", default="")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--strict", action="store_true", help="质量检查有问题时阻止推送；默认只告警")
    parser.add_argument("--force", action="store_true", help="兼容旧用法：即使 --strict 也继续推送")
    parser.add_argument("--allow-duplicate", action="store_true", help="允许同日同代码重复发布")
    args = parser.parse_args()

    raw_content = Path(args.markdown).read_text(encoding="utf-8")
    content, sanitize_warnings = sanitize_report(raw_content)
    errors = sanitize_warnings + validate_report(content, args.report_type) + validate_title(
        args.title, content, args.report_type
    )
    if errors and args.strict and not args.force:
        print(json.dumps({"pushed": False, "quality_errors": errors, "strict": True}, ensure_ascii=False, indent=2))
        return 2

    if not args.allow_duplicate and is_duplicate(args.posts_endpoint, args.title, not args.insecure):
        print(json.dumps({"pushed": False, "duplicate": True, "title": args.title}, ensure_ascii=False, indent=2))
        return 3

    response = httpx.post(
        args.endpoint,
        json={"title": args.title, "content": content, "url": args.url, "source": args.source},
        timeout=20,
        verify=not args.insecure,
    )
    response.raise_for_status()
    result = {"pushed": True, "response": response.json()}
    if errors:
        result["quality_warnings"] = errors
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
