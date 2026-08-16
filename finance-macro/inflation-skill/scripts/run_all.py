#!/usr/bin/env python3
"""
统一抓取 CPI、PPI 和核心CPI数据，输出 JSON 文件。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from fetch_common import now as _now, setup_logging
from fetch_cpi import fetch_cpi
from fetch_ppi import fetch_ppi
from fetch_core_cpi_tavily import fetch_core_cpi

# 统一输出目录：finance-macro/output/<skill 目录名>
_SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = str(_SKILL_DIR.parent / "output" / _SKILL_DIR.name / "inflation_latest.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 CPI、PPI 和核心CPI")
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        help="指定月份 YYYY-MM（默认查已发布的最新月份）",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"输出 JSON 文件路径（默认 {DEFAULT_OUTPUT}）",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="抓取后构建 macro_signal.json 并推送到线上 macro 后端（token 从 finance-macro/.env 读取）",
    )
    args = parser.parse_args()

    setup_logging()

    target_month = args.month  # 由各抓取函数内部处理降级

    print("=== CPI 抓取 ===")
    cpi = fetch_cpi(target_month)
    print(json.dumps(cpi, ensure_ascii=False, indent=2))

    print("\n=== PPI 抓取 ===")
    ppi = fetch_ppi(target_month)
    print(json.dumps(ppi, ensure_ascii=False, indent=2))

    # 核心CPI使用CPI/PPI中实际获取的月份
    actual_for_core = cpi.get("month") or ppi.get("month")
    core_cpi: dict = {}
    if actual_for_core:
        print(f"\n=== 核心CPI 抓取 ({actual_for_core}) ===")
        core_cpi = fetch_core_cpi(actual_for_core)
        print(json.dumps(core_cpi, ensure_ascii=False, indent=2))

    combined = {
        "month": actual_for_core,
        "fetched_at": _now(),
        "cpi": cpi,
        "ppi": ppi,
        "core_cpi": core_cpi,
    }

    out_path = Path(args.output)
    if actual_for_core:
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n已写入 {out_path}")

    # 构建契约结构并推送到线上 macro 后端（模式对齐 exchange-rate-skill）
    if args.upload:
        import os
        import sys as _sys

        _script_dir = Path(__file__).resolve().parent
        if str(_script_dir) not in _sys.path:
            _sys.path.insert(0, str(_script_dir))

        from build_macro_signal import build_signal
        from upload_signal import DEFAULT_URL, UploadError, load_env_file, upload_signal

        signal = build_signal(combined)
        if not signal["details"] or not signal["data_date"]:
            print("[upload] 可用指标不足，无法构建 macro_signal.json，跳过推送")
            _sys.exit(1)

        # 落盘一份 macro_signal.json，便于单独重推（upload_signal.py 默认输入）
        signal_path = out_path.parent / "macro_signal.json"
        signal_path.write_text(json.dumps(signal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[upload] macro_signal.json 已保存到: {signal_path}")

        load_env_file()
        token = os.environ.get("MACRO_SIGNAL_UPLOAD_TOKEN", "")
        url = os.environ.get("MACRO_SIGNAL_UPLOAD_URL", "") or DEFAULT_URL
        if not token:
            print("[upload] --upload 需要配置 MACRO_SIGNAL_UPLOAD_TOKEN（finance-macro/.env）")
            _sys.exit(1)
        try:
            upload_signal(url, token, "inflation-skill", "macro_signal.json", signal)
        except UploadError as exc:
            print(f"[upload] 推送失败: {exc}")
            _sys.exit(1)


if __name__ == "__main__":
    main()
