#!/usr/bin/env python3
"""Send one Markdown message to a DingTalk custom robot.

Configuration comes from `DINGTALK_WEBHOOK` (环境变量优先，其次 .env)。the token is
never printed, logged or returned in results.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1
SENT = "sent"
DRY_RUN = "dry_run"
KEYWORD_MISSING = "keyword_missing"
NOT_CONFIGURED = "not_configured"
REJECTED = "rejected"
UNKNOWN = "unknown"

EXIT_CODES = {SENT: 0, DRY_RUN: 0, KEYWORD_MISSING: 2, NOT_CONFIGURED: 2,
              REJECTED: 4, UNKNOWN: 3}
# 310000: 关键词不匹配 / 加签校验失败。改文案或密钥后重试有意义，原样重试没有。
KEYWORD_ERRCODES = {310000}
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def result(status, *, errcode=None, errmsg=None):
    return {"schema_version": SCHEMA_VERSION, "status": status,
            "errcode": errcode, "errmsg": errmsg}


def read_env_file(path):
    """Parse KEY=VALUE lines; ignore blanks and `#` comments; strip one quote pair."""
    values = {}
    text = path.read_text(encoding="utf-8-sig")
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def lookup(name, env_file=None):
    """进程环境变量优先，其次 .env；两者都没有返回空串。"""
    value = os.environ.get(name)
    if value:
        return value
    path = Path(env_file) if env_file else DEFAULT_ENV_FILE
    try:
        return read_env_file(path).get(name, "")
    except OSError:
        return ""


def resolve_webhook(explicit=None, env_file=None):
    webhook = (explicit or lookup("DINGTALK_WEBHOOK", env_file)).strip()
    if not webhook:
        raise ValueError("DINGTALK_WEBHOOK 未配置：在 .env 或环境变量中设置机器人 Webhook")
    return webhook


def resolve_keyword(explicit=None, env_file=None):
    return (explicit or lookup("DINGTALK_KEYWORD", env_file)).strip()


def keyword_present(title, text, keyword):
    """关键词按原文整串匹配；钉钉机器人校验区分大小写。"""
    return True if not keyword else keyword in (title or "") + (text or "")


def classify(markdown_title, payload):
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return result(REJECTED, errmsg="钉钉返回非 JSON 响应，无法确认是否送达")
    if not isinstance(data, dict):
        return result(REJECTED, errmsg="钉钉返回结构无法识别")
    errcode = data.get("errcode")
    errmsg = data.get("errmsg")
    if errcode == 0 or errmsg == "ok":
        return result(SENT, errcode=0, errmsg="ok")
    if isinstance(errcode, int) and errcode in KEYWORD_ERRCODES:
        return result(KEYWORD_MISSING, errcode=errcode,
                      errmsg=f"{errmsg}：正文或标题需包含关键词（当前标题「{markdown_title}」）")
    return result(REJECTED, errcode=errcode, errmsg=str(errmsg))


def send(webhook, title, text, timeout=10):
    """POST one markdown message. Network/HTTP failures are classified, never raised."""
    parts = urlsplit(webhook)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("Webhook 地址无效：需要 http(s) 完整 URL")
    body = json.dumps({"msgtype": "markdown", "markdown": {"title": title, "text": text}}).encode("utf-8")
    request = Request(webhook, data=body, method="POST",
                      headers={"Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except HTTPError as exc:
        try:
            payload = exc.read()
        except OSError:
            payload = b""
        if payload:
            return classify(title, payload)
        return result(REJECTED, errmsg=f"钉钉 HTTP {exc.code}")
    except (URLError, OSError):
        return result(UNKNOWN, errmsg="网络异常或超时，消息可能已送达，先核对再重发")
    return classify(title, payload)


def positive_timeout(value):
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("超时必须为正数") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("超时必须为正数")
    return timeout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True, help="钉钉消息标题（关键词校验也看标题）")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="正文 Markdown")
    source.add_argument("--file", help="正文文件路径，- 表示从 stdin 读取")
    parser.add_argument("--env-file", type=Path, help=".env 路径，默认 skill 目录下的 .env")
    parser.add_argument("--keyword", default=None, help="机器人关键词，默认读 DINGTALK_KEYWORD")
    parser.add_argument("--timeout", type=positive_timeout, default=10)
    parser.add_argument("--dry-run", action="store_true", help="只校验配置与关键词，不发送")
    args = parser.parse_args(argv)

    try:
        text = sys.stdin.read() if args.file == "-" else (
            args.text if args.text is not None else Path(args.file).read_text(encoding="utf-8"))
    except OSError as exc:
        print(json.dumps(result(REJECTED, errmsg=f"读取正文失败：{exc.strerror or exc}"), ensure_ascii=False))
        return EXIT_CODES[REJECTED]

    keyword = resolve_keyword(args.keyword, args.env_file)
    if not keyword_present(args.title, text, keyword):
        print(json.dumps(result(KEYWORD_MISSING, errmsg=f"标题或正文未包含关键词「{keyword}」，未发送"),
                         ensure_ascii=False))
        return EXIT_CODES[KEYWORD_MISSING]
    try:
        webhook = resolve_webhook(None, args.env_file)
    except ValueError as exc:
        print(json.dumps(result(NOT_CONFIGURED, errmsg=str(exc)), ensure_ascii=False))
        return EXIT_CODES[NOT_CONFIGURED]
    if args.dry_run:
        print(json.dumps(dict(result(DRY_RUN, errmsg="未发送"), title=args.title), ensure_ascii=False))
        return EXIT_CODES[DRY_RUN]
    outcome = send(webhook, args.title, text, timeout=args.timeout)
    print(json.dumps(outcome, ensure_ascii=False))
    return EXIT_CODES[outcome["status"]]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
