#!/usr/bin/env python3
"""杭州 PM2.5 实测与未来五天趋势。Python 3.10+，无需第三方依赖。"""

import argparse
import json
import sys
from pathlib import Path

from providers import fetch_snapshot, local_time
from report import build_report, render_markdown


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        choices=range(1, 6),
        default=5,
        help="含今天的自然日数量，默认5",
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument(
        "--output-dir", type=Path, help="同时写入 report.json 和 report.md"
    )
    parser.add_argument(
        "--save-input", type=Path, help="保存本次原始响应快照，供离线回放"
    )
    parser.add_argument("--input", type=Path, help="离线读取快照，不访问网络")
    parser.add_argument("--now", help="仅供离线回放的报告时间，必须包含时区偏移")
    args = parser.parse_args(argv)
    if args.now and not args.input:
        parser.error("--now 仅可与 --input 一起用于离线回放")
    try:
        now = local_time(args.now) if args.now else None
        snapshot = (
            json.loads(args.input.read_text(encoding="utf-8-sig"))
            if args.input
            else fetch_snapshot(args.days)
        )
        report = build_report(snapshot, now=now, days=args.days)
        markdown = render_markdown(report)
        serialized = (
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
        if args.save_input:
            args.save_input.parent.mkdir(parents=True, exist_ok=True)
            args.save_input.write_text(
                json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False)
                + "\n",
                encoding="utf-8",
            )
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            (args.output_dir / "report.json").write_text(serialized, encoding="utf-8")
            (args.output_dir / "report.md").write_text(markdown, encoding="utf-8")
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.stdout.write(serialized if args.format == "json" else markdown)
    return 1 if report["status"] == "unavailable" else 0


if __name__ == "__main__":
    raise SystemExit(main())
