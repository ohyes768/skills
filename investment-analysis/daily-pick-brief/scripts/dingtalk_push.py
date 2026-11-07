"""钉钉发送统一入口：委托公共 dingtalk-push CLI。

Canonical transport: ``skills/personal-tools/dingtalk-push/scripts/dingtalk_send.py``。
本模块**不含任何 HTTP 发送**，也不做加签——各群机器人统一使用「自定义关键词」
安全设置（2026-11-07 起 ``*_DINGTALK_SECRET`` 全部弃用）。

公共 CLI 负责：有界 POST、sqlite 回执去重、关键词预检、unknown 不盲重、token 不落日志。
本模块负责：定位 CLI、组 argv（webhook 走环境变量、正文走 stdin）、把 CLI 的
sent/duplicate/preview/failed/unknown/conflict 映射回调用方习惯的布尔结果。

找不到公共包时明确报错，**不回退内联 POST**（回退会产生第二份漂移实现）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_TIMEOUT = 20
# 公共 CLI 里 sent/duplicate 退 0；failed=2、unknown=3、conflict=4。
SUCCESS_STATUSES = frozenset({"sent", "duplicate"})


class DingTalkPushError(RuntimeError):
    """配置或环境问题：CLI 缺失、webhook 未配置、输出不可解析。"""


def locate_cli() -> Path:
    """定位公共 CLI：显式变量 > 逐级父目录/同级 skills 探测 > 用户级 skills 目录。"""
    configured = os.environ.get("DINGTALK_PUSH_SKILL_DIR")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser() / "scripts" / "dingtalk_send.py")
    for parent in Path(__file__).resolve().parents:
        for relative in ("dingtalk-push/scripts/dingtalk_send.py",
                         "personal-tools/dingtalk-push/scripts/dingtalk_send.py",
                         "skills/personal-tools/dingtalk-push/scripts/dingtalk_send.py"):
            candidates.append(parent / relative)
    home = Path.home()
    for root in (home / ".hermes" / "skills", home / ".codex" / "skills",
                 home / ".agents" / "skills"):
        candidates.append(root / "dingtalk-push" / "scripts" / "dingtalk_send.py")
    for path in candidates:
        if path.is_file():
            return path
    raise DingTalkPushError(
        "未找到公共 dingtalk-push CLI：安装 dingtalk-push skill，"
        "或把 DINGTALK_PUSH_SKILL_DIR 指向其包目录（容器内需挂载该目录）")


def validate_webhook(webhook: str) -> str:
    parts = urlsplit((webhook or "").strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise DingTalkPushError("webhook 未配置或不是 http(s) 完整 URL")
    return webhook.strip()


def keyword_from_env(var: str, default: str | None = None) -> str | None:
    """关键词优先取环境变量，其次用频道常量；都没有则不做预检。"""
    value = (os.environ.get(var) or "").strip()
    return value or default


def send(title: str, text: str, *, webhook: str, keyword: str | None = None,
         dedupe_key: str | None = None, timeout: float = DEFAULT_TIMEOUT,
         dry_run: bool = False) -> dict:
    """调公共 CLI 发送一条 markdown；返回 CLI 的 JSON 结果（附带 exit_code）。"""
    if not (title or "").strip() or not (text or "").strip():
        raise DingTalkPushError("标题和正文都不能为空")
    webhook = validate_webhook(webhook)
    args = [sys.executable, str(locate_cli()), "send", "--title", title, "--file", "-",
            "--timeout", str(timeout)]
    if keyword:
        args.extend(["--keyword", keyword])
    if dedupe_key:
        args.extend(["--dedupe-key", dedupe_key])
    if dry_run:
        args.append("--dry-run")
    # webhook 只经环境变量传递，绝不出现在 argv（会进 ps / 容器 inspect）。
    env = {**os.environ, "DINGTALK_WEBHOOK": webhook}
    # 不在父进程设短超时：CLI 已带自身有界超时，强杀会丢掉“已送达”的判定。
    try:
        proc = subprocess.run(args, input=(text or "").encode("utf-8"),
                              capture_output=True, env=env)
    except OSError as exc:
        raise DingTalkPushError(f"无法启动公共 dingtalk-push CLI：{exc.strerror or exc}") from exc
    try:
        payload = json.loads(proc.stdout.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise DingTalkPushError(
            "公共 CLI 未返回有效 JSON，消息可能已送达，请先核对群消息；"
            f"stdout={proc.stdout.decode('utf-8', 'replace')[:200]!r} "
            f"stderr={proc.stderr.decode('utf-8', 'replace')[:200]!r}") from None
    payload["exit_code"] = proc.returncode
    return payload


def describe(result: dict) -> str:
    """把 CLI 结果压成一行中文，供调用方打印。"""
    status = result.get("status")
    code = (result.get("error") or {}).get("code")
    if status == "sent":
        return "推送成功"
    if status == "duplicate":
        return "相同内容此前已发送，按回执跳过"
    if status == "preview":
        return "预览（未发送）"
    if status == "unknown":
        return "未知：消息可能已送达，先核对群消息再决定是否重发"
    if code == "keyword_missing":
        return f"关键词不匹配：标题/正文需包含机器人关键词 {(result.get('error') or {}).get('message') or ''}".strip()
    detail = result.get("errmsg") or (result.get("error") or {}).get("message") or ""
    return f"推送失败（{status}）：{detail}".strip()


def push_markdown(title: str, text: str, *, webhook: str, keyword: str | None = None,
                  dedupe_key: str | None = None, timeout: float = DEFAULT_TIMEOUT) -> bool:
    """发送一条 markdown，返回是否投递成功（sent/duplicate 视为成功）。"""
    result = send(title, text, webhook=webhook, keyword=keyword,
                  dedupe_key=dedupe_key, timeout=timeout)
    ok = result.get("status") in SUCCESS_STATUSES
    if not ok:
        print(f"[钉钉] {describe(result)}", file=sys.stderr)
    return ok


class DingTalkPusher:
    """保持既有调用方式的最小门面：``DingTalkPusher(webhook=..., keyword=...).push_markdown()``。"""

    def __init__(self, webhook: str | None = None, keyword: str | None = None,
                 dedupe_key: str | None = None):
        self.webhook = webhook if webhook is not None else os.environ.get("DINGTALK_WEBHOOK", "")
        self.keyword = keyword
        self.dedupe_key = dedupe_key

    def push_markdown(self, title: str, content: str) -> bool:
        return push_markdown(title, content, webhook=self.webhook,
                             keyword=self.keyword, dedupe_key=self.dedupe_key)
