#!/usr/bin/env python3
"""Compatibility delegator: sends one Markdown message through the public dingtalk-push CLI.

Canonical source: personal-tools/dingtalk-push/scripts/dingtalk_send.py.
This module keeps the csi300-brief business API (statuses, argv contract, .env
keys) but carries no HTTP of its own: the public CLI owns transport, receipts,
dedupe and the unknown/no-blind-retry semantics. The webhook travels by
environment variable so it never appears in argv; dedupe is scoped per title
date (`csi300:{date}`), so re-running the same brief does not spam the group.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

SCHEMA_VERSION = 1
SENT = "sent"
DRY_RUN = "dry_run"
KEYWORD_MISSING = "keyword_missing"
NOT_CONFIGURED = "not_configured"
REJECTED = "rejected"
UNKNOWN = "unknown"

EXIT_CODES = {SENT: 0, DRY_RUN: 0, KEYWORD_MISSING: 2, NOT_CONFIGURED: 2,
              REJECTED: 4, UNKNOWN: 3}
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def result(status, *, errcode=None, errmsg=None):
    return {"schema_version": SCHEMA_VERSION, "status": status,
            "errcode": errcode, "errmsg": errmsg}


def read_env_file(path):
    """Parse KEY=VALUE lines; ignore blanks and `#` comments; strip one quote pair."""
    values = {}
    text = Path(path).read_text(encoding="utf-8-sig")
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


def locate_send_script():
    configured = os.environ.get("DINGTALK_PUSH_SKILL_DIR")
    if configured:
        candidate = Path(configured).expanduser() / "scripts" / "dingtalk_send.py"
        if not candidate.is_file():
            raise ValueError("DINGTALK_PUSH_SKILL_DIR 必须包含 scripts/dingtalk_send.py")
        return str(candidate.resolve())
    relatives = ("dingtalk-push/scripts/dingtalk_send.py",
                 "personal-tools/dingtalk-push/scripts/dingtalk_send.py")
    for parent in Path(__file__).resolve().parents:
        for relative in relatives:
            candidate = parent / relative
            if candidate.is_file():
                return str(candidate)
    home = Path.home()
    for root in (home / ".hermes/skills", home / ".codex/skills", home / ".agents/skills"):
        candidate = root / "dingtalk-push/scripts/dingtalk_send.py"
        if candidate.is_file():
            return str(candidate)
    raise ValueError("未找到公共 dingtalk-push 包：安装后设置 DINGTALK_PUSH_SKILL_DIR 指向其目录")


def validate_webhook(webhook):
    parts = urlsplit(webhook)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError("Webhook 地址无效：需要 http(s) 完整 URL")
    return webhook


def dedupe_key_for(title):
    """同一价格日期的简报只投一次；显式修订请改标题日期或换键。"""
    match = re.search(r"(\d{4}-\d{2}-\d{2})", title or "")
    date = match.group(1) if match else datetime.now().strftime("%Y-%m-%d")
    return f"csi300:{date}"


def map_public_result(payload):
    """把公共 CLI 的结果映射回本 skill 的业务状态词汇。"""
    if not isinstance(payload, dict) or payload.get("status") not in (
            "sent", "duplicate", "preview", "failed", "unknown", "conflict"):
        return result(UNKNOWN, errmsg="公共 CLI 无有效结果，消息可能已送达，先核对再重发")
    status = payload["status"]
    errcode = payload.get("errcode")
    errmsg = payload.get("errmsg") or ""
    code = (payload.get("error") or {}).get("code")
    if status == "sent":
        return result(SENT, errcode=0, errmsg="ok")
    if status == "duplicate":
        return result(SENT, errcode=0, errmsg="已发送过同内容（公共回执 duplicate），未重复投递")
    if status == "preview":
        return result(DRY_RUN, errmsg="未发送")
    if status == "failed" and code == "keyword_rejected":
        return result(KEYWORD_MISSING, errcode=errcode,
                      errmsg=f"钉钉关键词不匹配（errcode {errcode}）：标题或正文需包含机器人关键词，补关键词后重试一次")
    if status == "unknown":
        detail = errmsg if errmsg and errmsg != "ok" else ""
        return result(UNKNOWN, errmsg=(detail + "；" if detail else "")
                      + "消息可能已送达，先核对群消息再重发")
    return result(REJECTED, errcode=errcode, errmsg=errmsg or "钉钉拒绝或同键内容冲突")


def delegate(webhook, title, text, *, keyword="", timeout=10, dry_run=False):
    script = locate_send_script()
    args = [sys.executable, script, "send", "--title", title, "--file", "-",
            "--dedupe-key", dedupe_key_for(title), "--timeout", str(timeout)]
    if keyword:
        args.extend(["--keyword", keyword])
    env = {**os.environ, "DINGTALK_WEBHOOK": webhook}
    try:
        completed = subprocess.run(args, input=text, capture_output=True, text=True,
                                   encoding="utf-8", env=env, timeout=timeout + 5)
    except subprocess.TimeoutExpired:
        return result(UNKNOWN, errmsg="公共 CLI 超时被中止，消息可能已送达，先核对再重发")
    except OSError as exc:
        return result(REJECTED, errmsg=f"无法启动公共 dingtalk-push CLI：{exc.strerror or exc}")
    try:
        payload = json.loads(completed.stdout)
    except ValueError:
        payload = None
    return map_public_result(payload)


def send(webhook, title, text, timeout=10):
    """Delegate one markdown message; delivery failures are classified, never raised."""
    validate_webhook(webhook)
    keyword = resolve_keyword()
    return delegate(webhook, title, text, keyword=keyword, timeout=timeout)


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
    outcome = delegate(webhook, args.title, text, keyword=keyword, timeout=args.timeout)
    print(json.dumps(outcome, ensure_ascii=False))
    return EXIT_CODES[outcome["status"]]


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
