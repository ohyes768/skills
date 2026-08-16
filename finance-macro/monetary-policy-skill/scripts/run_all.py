#!/usr/bin/env python3
"""
统一抓取 DR007、MLF、LPR，并输出 JSON。
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Literal

from fetch_common import setup_logging, to_iso_now
from fetch_dr007 import fetch_dr007_latest
from fetch_lpr import fetch_lpr_latest
from fetch_mlf_tavily import fetch_mlf_monthly_net

# 统一输出目录：finance-macro/output/<skill 目录名>
_SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = str(_SKILL_DIR.parent / "output" / _SKILL_DIR.name / "monetary_indicators_latest.json")


def build_payload(requested_month: str | None = None) -> dict:
    """构建数据载荷。

    各指标获取逻辑由各自脚本内部处理：
    - DR007：每日更新，直接查
    - MLF：每月2-3日发布，脚本内部自动降级未发布的月份
    - LPR：直接API获取最新值（每月20日发布）
    """
    today = datetime.now()
    requested_display = requested_month or "上月（默认）"

    with ThreadPoolExecutor(max_workers=3) as executor:
        f1 = executor.submit(fetch_dr007_latest)
        f2 = executor.submit(fetch_lpr_latest)
        f3 = executor.submit(fetch_mlf_monthly_net, requested_month)
        dr007, lpr, mlf = f1.result(), f2.result(), f3.result()

    # MLF 脚本内部已处理月份降级，从返回值中获取实际月份
    actual_mlf_month = mlf.get("actual_month", requested_month or "unknown")
    mlf_type = "prev" if mlf.get("requested_month") != actual_mlf_month else "same"

    return {
        "as_of_date": today.strftime("%Y-%m-%d"),
        "requested_month": requested_display,
        "actual_fetched_month": {
            "mlf": actual_mlf_month,
        },
        "data_month_type": {
            "mlf": mlf_type,
        },
        "publish_days": {
            "mlf": "每月2-3日发布（脚本自动降级未发布月份）",
            "lpr": "每月20日（直接API获取最新值）",
            "dr007": "每日更新",
        },
        "dr007": dr007,
        "mlf": mlf,
        "lpr": lpr,
        "fetched_at": to_iso_now(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 DR007/MLF/LPR 最新指标")
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"输出文件路径（默认 {DEFAULT_OUTPUT}）",
    )
    parser.add_argument(
        "--month",
        default="",
        help="目标月份（YYYY-MM），默认查上月",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="抓取后构建 macro_signal.json 并推送到线上 macro 后端（token 从 finance-macro/.env 读取）",
    )
    args = parser.parse_args()

    setup_logging()
    payload = build_payload(requested_month=(args.month or None))

    # 输出数据可用性提示
    print(f"[数据可用性] 请求月份: {payload['requested_month']}")
    mlf_type_msg = "（请求月份数据）" if payload["data_month_type"]["mlf"] == "same" else "（上月数据，因发布日未到）"
    print(f"[数据可用性] MLF实际获取: {payload['actual_fetched_month']['mlf']} {mlf_type_msg}")
    print(f"[数据可用性] LPR: {payload['publish_days']['lpr']}")
    print(f"[数据可用性] DR007: {payload['publish_days']['dr007']}")
    print()

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"\n输出文件: {out_path}")

    # 构建契约结构并推送到线上 macro 后端（模式对齐 exchange-rate-skill）
    if args.upload:
        import os

        from build_macro_signal import build_signal
        from upload_signal import DEFAULT_URL, UploadError, load_env_file, upload_signal

        signal = build_signal(payload)
        if not signal["details"] or not signal["data_date"]:
            print("[upload] 可用指标不足，无法构建 macro_signal.json，跳过推送")
            sys.exit(1)

        # 落盘一份 macro_signal.json，便于单独重推（upload_signal.py 默认输入）
        signal_path = out_path.parent / "macro_signal.json"
        signal_path.write_text(json.dumps(signal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[upload] macro_signal.json 已保存到: {signal_path}")

        load_env_file()
        token = os.environ.get("MACRO_SIGNAL_UPLOAD_TOKEN", "")
        url = os.environ.get("MACRO_SIGNAL_UPLOAD_URL", "") or DEFAULT_URL
        if not token:
            print("[upload] --upload 需要配置 MACRO_SIGNAL_UPLOAD_TOKEN（finance-macro/.env）")
            sys.exit(1)
        try:
            upload_signal(url, token, "monetary-policy-skill", "macro_signal.json", signal)
        except UploadError as exc:
            print(f"[upload] 推送失败: {exc}")
            sys.exit(1)


if __name__ == "__main__":
    main()
