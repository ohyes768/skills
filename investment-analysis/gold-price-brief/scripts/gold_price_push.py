"""
黄金走势播报（task-web 统一调度版）

Canonical source: skills/investment-analysis/gold-price-brief。
迁移自 stock-info-dingding/gold_price_push.py（2026-11-07）；旧入口在 Hermes
调度切换完成前保留兼容，两处不得各自独立演进。

AI 分析已从本脚本剥离，改由 Hermes skill（gold-price-brief）完成：
  - fetch: 取黄金数据，JSON 输出 stdout（供 agent/Hermes 读取）
  - push:  读 数据JSON + 分析markdown → 经公共 dingtalk-push CLI 发送（PUSH_MODE=1 生效）
  - 无参数: 兼容旧用法（fetch + DeepSeek 分析 + push 一条龙；已弃用，仅为回滚保留）

定时触发统一由 task-web 管理（hermes_trigger → Runs API → gold-price-brief skill）。
本脚本不含任何钉钉 HTTP 发送；实际投递、回执去重与 unknown 处理由
personal-tools/dingtalk-push 的 dingtalk_send.py 统一负责。
"""

import sys
import os
import json
import argparse
import subprocess
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

# 添加本目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold import get_merged_gold_data, GoldAnalyzer
from gold.formatter import build_gold_markdown

FETCH_NOTE = "供 gold-price-brief skill / 调试使用"

TITLE = "黄金走势研判"
# 群机器人安全设置为「自定义关键词」：黄金 / 金价。标题恒含「黄金」，预检用其一即可。
KEYWORD = "黄金"
CLI_EXIT = {"failed": 2, "unknown": 3, "conflict": 4}


def locate_dingtalk_cli() -> Path:
    """定位公共 dingtalk-push CLI；找不到时报错，不回退内联 POST。"""
    configured = os.environ.get("DINGTALK_PUSH_SKILL_DIR")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser() / "scripts" / "dingtalk_send.py")
    for parent in Path(__file__).resolve().parents:
        for relative in ("dingtalk-push/scripts/dingtalk_send.py",
                         "personal-tools/dingtalk-push/scripts/dingtalk_send.py"):
            candidates.append(parent / relative)
    for root in (Path.home() / ".hermes" / "skills", Path.home() / ".codex" / "skills",
                 Path.home() / ".agents" / "skills"):
        candidates.append(root / "dingtalk-push" / "scripts" / "dingtalk_send.py")
    for path in candidates:
        if path.is_file():
            return path
    raise ValueError("未找到公共 dingtalk-push CLI；请安装 dingtalk-push skill 或设置 DINGTALK_PUSH_SKILL_DIR")


def send_via_dingtalk_cli(content: str) -> tuple[int, str]:
    """经公共 CLI 发送，返回 (退出码, 状态摘要)。sent/duplicate 视为成功。"""
    webhook = os.environ.get("GOLD_DINGTALK_WEBHOOK")
    if not webhook:
        print("GOLD_DINGTALK_WEBHOOK 未设置，无法推送（webhook 只放 .env 或调度环境，不入代码）", file=sys.stderr)
        return 1, "missing_webhook"
    try:
        cli = locate_dingtalk_cli()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1, "cli_not_found"
    args = [sys.executable, str(cli), "send", "--title", TITLE, "--file", "-",
            "--keyword", KEYWORD, "--webhook", webhook]
    # CLI 自身做有界 HTTP 与回执处理，不要在父进程用短超时强杀。
    proc = subprocess.run(args, input=content.encode("utf-8"), capture_output=True)
    try:
        data = json.loads(proc.stdout.decode("utf-8"))
    except (TypeError, ValueError):
        print("公共 CLI 未返回有效 JSON，请先人工核对群消息再重试；输出：\n"
              + proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace"),
              file=sys.stderr)
        return proc.returncode or 1, "invalid_cli_output"
    status = data.get("status")
    if status in ("sent", "duplicate"):
        print("推送成功!" if status == "sent" else "相同内容此前已发送，按回执跳过（退出码 0）。")
        return 0, status
    print(f"钉钉推送未确认：{json.dumps(data, ensure_ascii=False)}", file=sys.stderr)
    if proc.stderr:
        print(proc.stderr.decode("utf-8", "replace"), file=sys.stderr)
    return CLI_EXIT.get(status, proc.returncode or 1), status or "no_status"


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
    """读 数据JSON + 分析markdown，组装并经公共 CLI 推送钉钉（PUSH_MODE=1 才真发）。"""
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
    code, _ = send_via_dingtalk_cli(markdown_content)
    return code


def legacy_run() -> None:
    """旧一条龙（fetch + DeepSeek 分析 + push）。已弃用，保留供回滚；发送同样走公共 CLI。"""
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
    code, status = send_via_dingtalk_cli(markdown_content)
    print("推送成功!" if code == 0 else f"推送未确认（{status}，退出码 {code}）")


def main():
    parser = argparse.ArgumentParser(description="黄金走势播报（fetch/push 子命令）")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("fetch", help="取黄金数据，JSON 输出 stdout")
    p_push = sub.add_parser("push", help="读 数据JSON+分析markdown 经公共 CLI 推送钉钉（PUSH_MODE=1 生效）")
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
