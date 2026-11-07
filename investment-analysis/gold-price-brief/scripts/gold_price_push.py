"""
黄金走势播报（task-web 统一调度版）

Canonical source: skills/investment-analysis/gold-price-brief。
迁移自 stock-info-dingding/gold_price_push.py（2026-11-07）；旧入口在 Hermes
调度切换完成前保留兼容，两处不得各自独立演进。

AI 分析已从本脚本剥离，改由 Hermes skill（gold-price-brief）完成：
  - fetch: 取黄金数据，JSON 输出 stdout（供 agent/Hermes 读取）
  - push:  读 数据JSON + 分析markdown → 组装钉钉消息推送（PUSH_MODE=1 生效）
  - 无参数: 兼容旧用法（fetch + DeepSeek 分析 + push 一条龙；已弃用，仅为回滚保留）

定时触发统一由 task-web 管理（hermes_trigger → Runs API → gold-price-brief skill）。
"""

import sys
import os
import json
import argparse
from datetime import datetime
from pathlib import Path

# 自动加载 .env 文件
_dotenv_path = Path(__file__).resolve().parents[1] / ".env"
if _dotenv_path.exists():
    with open(_dotenv_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold import get_merged_gold_data, GoldAnalyzer, DingTalkPusher
from gold.formatter import build_gold_markdown

FETCH_NOTE = "供 gold-price-brief skill / 调试使用"


def cmd_fetch() -> int:
    """取黄金数据，JSON 输出 stdout。失败退出码 1（不再吞错返回 0）。"""
    try:
        gold_data = get_merged_gold_data()
    except Exception as e:
        print(f"获取数据失败: {e}", file=sys.stderr)
        return 1
    print(json.dumps(gold_data, ensure_ascii=False, default=str))
    return 0


def cmd_push(json_file: str, analysis_file: str) -> int:
    """读 数据JSON + 分析markdown，组装并推送钉钉（PUSH_MODE=1 才真发）。"""
    push_mode = os.environ.get("PUSH_MODE", "0") == "1"
    try:
        gold_data = json.loads(Path(json_file).read_text(encoding="utf-8"))
        analysis = Path(analysis_file).read_text(encoding="utf-8").strip()
    except Exception as e:
        print(f"输入读取失败: {e}", file=sys.stderr)
        return 1
    if not analysis:
        print("分析文本为空，拒绝推送", file=sys.stderr)
        return 1

    markdown_content = build_gold_markdown(gold_data, analysis)
    if not push_mode:
        print(markdown_content)
        print("[测试模式] 未实际推送，PUSH_MODE=1 开启", file=sys.stderr)
        return 0

    try:
        pusher = DingTalkPusher(
            webhook=os.environ.get("GOLD_DINGTALK_WEBHOOK"),
            secret=os.environ.get("GOLD_DINGTALK_SECRET", ""),
        )
        success = pusher.push_markdown(title="黄金走势研判", content=markdown_content)
    except Exception as e:
        print(f"钉钉推送失败: {e}", file=sys.stderr)
        return 1
    if success:
        print("推送成功!")
        return 0
    print("推送失败!", file=sys.stderr)
    return 1


def legacy_run() -> None:
    """旧一条龙（fetch + DeepSeek 分析 + push）。已弃用，保留供回滚。"""
    push_mode = os.environ.get("PUSH_MODE", "0")
    is_dry_run = push_mode != "1"
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始黄金分析推送...（旧模式）")
    try:
        gold_data = get_merged_gold_data()
        print(f"  - 当前金价: {gold_data['gold_price']} 元/克")
    except Exception as e:
        print(f"获取数据失败: {e}")
        return
    try:
        analysis = GoldAnalyzer().analyze(gold_data)
        print("  - AI 分析完成")
    except Exception as e:
        print(f"AI 分析失败: {e}")
        return
    markdown_content = build_gold_markdown(gold_data, analysis)
    if is_dry_run:
        print(markdown_content)
        return
    try:
        pusher = DingTalkPusher(
            webhook=os.environ.get("GOLD_DINGTALK_WEBHOOK"),
            secret=os.environ.get("GOLD_DINGTALK_SECRET", ""),
        )
        print("推送成功!" if pusher.push_markdown(title="黄金走势研判", content=markdown_content) else "推送失败!")
    except Exception as e:
        print(f"钉钉推送失败: {e}")


def main():
    parser = argparse.ArgumentParser(description="黄金走势播报（fetch/push 子命令）")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("fetch", help="取黄金数据，JSON 输出 stdout")
    p_push = sub.add_parser("push", help="读 数据JSON+分析markdown 推送钉钉（PUSH_MODE=1 生效）")
    p_push.add_argument("json_file")
    p_push.add_argument("analysis_file")
    args = parser.parse_args()

    if args.cmd == "fetch":
        sys.exit(cmd_fetch())
    if args.cmd == "push":
        sys.exit(cmd_push(args.json_file, args.analysis_file))
    legacy_run()


if __name__ == "__main__":
    main()
