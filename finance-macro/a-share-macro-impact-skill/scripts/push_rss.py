#!/usr/bin/env python3
"""把完成分析的 report.md 推送到 RSS Relay。标准库实现，无第三方依赖。"""
from __future__ import annotations

import argparse
import json
import re
import ssl
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_ENDPOINT = "https://web.duomi77.cn:9443/rss/api/rss-relay/post"
DEFAULT_POSTS_ENDPOINT = "https://web.duomi77.cn:9443/rss/api/rss-relay/posts"
REPORT_START_MARKER = "<!-- MACRO_REPORT_START -->"
SKILL_ECHO_MARKERS = (
    "阅读 [分析框架]",
    "## 时间和证据约束",
    "## 执行",
    "运行 `python scripts/fetch_snapshot.py`",
)
REQUIRED_MARKERS = ["核心判断", "驱动", "未来四周情景", "观察清单", "数据限制"]
TITLE_PATTERN = r"^\d{4}-\d{2}-\d{2} A股宏观展望｜[^｜]+｜[^｜]+$"
DIRECTION_HINT = "标题格式应为：YYYY-MM-DD A股宏观展望｜偏支撑/中性分化/偏压制｜相对利于成长/相对利于价值/风格无明显倾向"
MIN_CHARS = 1800


def http_json(url: str, payload: dict | None, verify: bool, timeout: int = 20) -> dict:
    context = None if verify else ssl._create_unverified_context()
    data = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers=headers)
    with urlopen(request, timeout=timeout, context=context) as response:
        return json.load(response)


def sanitize_report(content: str) -> tuple[str, list[str]]:
    """裁掉模型复读的 skill/prompt，只保留报告正文。"""
    warnings: list[str] = []
    marker_index = content.rfind(REPORT_START_MARKER)
    if marker_index >= 0:
        content = content[marker_index + len(REPORT_START_MARKER):].lstrip()
    if any(marker in content for marker in SKILL_ECHO_MARKERS):
        warnings.append("报告疑似包含 SKILL.md/提示词回显，请人工检查后再推送")
    return content, warnings


def validate_report(content: str) -> list[str]:
    errors = [f"缺少章节：{marker}" for marker in REQUIRED_MARKERS if marker not in content]
    if len(content) < MIN_CHARS:
        errors.append(f"报告少于 {MIN_CHARS} 字符，疑似仍是数据骨架")
    if "http://" not in content and "https://" not in content:
        errors.append("报告没有任何可核验来源链接")
    return errors


def extract_section(content: str, heading: str) -> str:
    match = re.search(rf"(?ms)^##\s+.*?{re.escape(heading)}.*?\s*$\n(.*?)(?=^##\s+|\Z)", content)
    return match.group(1).strip() if match else ""


def validate_title(title: str, content: str) -> list[str]:
    errors = [] if re.match(TITLE_PATTERN, title) else [DIRECTION_HINT]
    date_match = re.match(r"^(\d{4}-\d{2}-\d{2})", title)
    analysis_match = re.search(r"分析时点[：:]\s*(\d{4}-\d{2}-\d{2})", content)
    if date_match and analysis_match and date_match.group(1) != analysis_match.group(1):
        errors.append(
            f"标题日期 {date_match.group(1)} 与正文分析时点 {analysis_match.group(1)} 不一致"
        )
    parts = title.split("｜")
    if len(parts) == 3:
        section = extract_section(content, "核心判断")
        if section and parts[1] not in section:
            errors.append(f"标题整体方向「{parts[1]}」未出现在核心判断章节，疑似标题与结论不符")
    return errors


def is_duplicate(posts_endpoint: str, title: str, verify: bool) -> bool:
    payload = http_json(posts_endpoint + "?" + urlencode({"limit": 100}), None, verify)
    posts = payload.get("posts", [])
    return any(post.get("title") == title for post in posts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", help="最终 report.md 路径")
    parser.add_argument("--title", required=True)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--posts-endpoint", default=DEFAULT_POSTS_ENDPOINT)
    parser.add_argument("--source", default="a-share-macro-impact-skill")
    parser.add_argument("--url", default="")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--strict", action="store_true", help="质量检查有问题时阻止推送；默认只告警")
    parser.add_argument("--force", action="store_true", help="兼容旧用法：即使 --strict 也继续推送")
    parser.add_argument("--allow-duplicate", action="store_true", help="允许同标题重复发布")
    args = parser.parse_args()

    raw_content = Path(args.markdown).read_text(encoding="utf-8")
    content, sanitize_warnings = sanitize_report(raw_content)
    errors = sanitize_warnings + validate_report(content) + validate_title(args.title, content)
    if errors and args.strict and not args.force:
        print(json.dumps({"pushed": False, "quality_errors": errors, "strict": True}, ensure_ascii=False, indent=2))
        return 2

    if not args.allow_duplicate and is_duplicate(args.posts_endpoint, args.title, not args.insecure):
        print(json.dumps({"pushed": False, "duplicate": True, "title": args.title}, ensure_ascii=False, indent=2))
        return 3

    response = http_json(
        args.endpoint,
        {"title": args.title, "content": content, "url": args.url, "source": args.source},
        not args.insecure,
    )
    result = {"pushed": True, "response": response}
    if errors:
        result["quality_warnings"] = errors
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
