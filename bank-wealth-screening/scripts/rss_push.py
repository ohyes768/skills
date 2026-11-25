#!/usr/bin/env python3
"""把 bank-wealth-screening 的筛选/净值结果推送到 RSS 中转服务。

实际投递委托给公共包 rss-relay-publish 的 scripts/rss_publish.py：
- 定位顺序：环境变量 RSS_RELAY_SKILL_DIR > 本仓库 skills/knowledge/rss-relay-publish
- 回执（查重）由公共层 SQLite 管理，本脚本不做 HTTP

用法：
  # 直接推 Markdown 报告
  python rss_push.py --file report.md --title "杭行代销在售 2026-11-25" \
      --channel bank-wealth --source bank-wealth-screening --dedupe-key "hzbank-onsale:2026-11-25"

  # 从 on_sale_hzbank.py / on_sale_cmb.py 的 JSON 输出渲染 Markdown 表格后推送
  python rss_push.py --json hzbank_onsale.json --title "..." --channel bank-wealth \
      --source bank-wealth-screening --dedupe-key "hzbank-onsale:2026-11-25"

  # 预览（不发送）
  ... --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_CHANNEL = "bank-wealth"
DEFAULT_SOURCE = "bank-wealth-screening"
MAX_TABLE_ROWS = 200


def locate_relay_cli() -> Path:
    env = os.environ.get("RSS_RELAY_SKILL_DIR")
    candidates = []
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve()
    for base in [*here.parents]:  # .../skills/bank-wealth-screening/scripts -> .../skills
        candidates.append(base / "knowledge" / "rss-relay-publish" / "scripts" / "rss_publish.py")
    for c in candidates:
        if c.is_file():
            return c
    raise SystemExit(
        "找不到 rss-relay-publish 公共包：请设置 RSS_RELAY_SKILL_DIR 指向该 skill 目录。"
        "找不到依赖时明确失败，不回退本地 POST。"
    )


def json_to_markdown(data) -> str:
    """把 on_sale 脚本的 JSON 输出（list[dict] 或 {"products": [...]}）渲染成 Markdown。"""
    if isinstance(data, dict):
        for key in ("products", "items", "data", "list"):
            if isinstance(data.get(key), list):
                meta = {k: v for k, v in data.items() if k != key and not isinstance(v, (list, dict))}
                rows = data[key]
                break
        else:
            raise SystemExit("JSON 中未找到产品列表字段（products/items/data/list）")
    elif isinstance(data, list):
        meta, rows = {}, data
    else:
        raise SystemExit("不支持的 JSON 结构")

    if not rows:
        return "> 无在售产品\n"

    lines = []
    for k, v in meta.items():
        lines.append(f"- {k}: {v}")
    if meta:
        lines.append("")

    keys: list[str] = []
    for r in rows[:50]:
        for k in r.keys():
            if k not in keys:
                keys.append(k)
    def cell(v) -> str:
        s = "" if v is None else str(v)
        return s.replace("|", "\\|").replace("\n", " ")
    lines.append("| " + " | ".join(keys) + " |")
    lines.append("|" + "---|" * len(keys))
    for r in rows[:MAX_TABLE_ROWS]:
        lines.append("| " + " | ".join(cell(r.get(k)) for k in keys) + " |")
    if len(rows) > MAX_TABLE_ROWS:
        lines.append("")
        lines.append(f"> 仅展示前 {MAX_TABLE_ROWS} 条，共 {len(rows)} 条")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="已生成的 Markdown 文件路径；- 表示 stdin")
    src.add_argument("--json", help="on_sale 脚本的 JSON 输出文件，自动渲染为 Markdown 表格")
    ap.add_argument("--title", required=True)
    ap.add_argument("--channel", default=DEFAULT_CHANNEL)
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--dedupe-key", required=True,
                    help="稳定唯一键，例如 hzbank-onsale:2026-11-25 或 cmb-onsale:2026-11-25")
    ap.add_argument("--url", help="可选原文链接")
    ap.add_argument("--dry-run", action="store_true", help="仅预览，不发送")
    ap.add_argument("--base-url", help="覆盖 RSS_RELAY_BASE_URL")
    ap.add_argument("--ca-file", help="自签证书 CA")
    ap.add_argument("--insecure", action="store_true", help="跳过 TLS 校验（仅显式要求时）")
    args = ap.parse_args()

    if args.file:
        if args.file == "-":
            content = sys.stdin.read()
        else:
            content = Path(args.file).read_text(encoding="utf-8")
    else:
        content = json_to_markdown(json.loads(Path(args.json).read_text(encoding="utf-8")))

    cli = locate_relay_cli()
    cmd = [
        sys.executable, str(cli), "publish",
        "--file", "-", "--title", args.title,
        "--channel", args.channel, "--source", args.source,
        "--dedupe-key", args.dedupe_key,
    ]
    if args.url:
        cmd += ["--url", args.url]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.base_url:
        cmd += ["--base-url", args.base_url]
    if args.ca_file:
        cmd += ["--ca-file", args.ca_file]
    if args.insecure:
        cmd.append("--insecure")

    proc = subprocess.run(cmd, input=content.encode("utf-8"))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
