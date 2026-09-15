#!/usr/bin/env python3
"""统一抓取 MLF 与 LPR，并可构建、推送宏观信号。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fetch_common import setup_logging, to_iso_now
from fetch_lpr import fetch_lpr_latest
from fetch_mlf_tavily import fetch_mlf_monthly_net

_SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = str(_SKILL_DIR.parent / "output" / _SKILL_DIR.name / "monetary_indicators_latest.json")


def build_payload(requested_month: str | None = None) -> dict:
    today = datetime.now()
    requested_display = requested_month or "上月（默认）"
    with ThreadPoolExecutor(max_workers=2) as executor:
        lpr_future = executor.submit(fetch_lpr_latest)
        mlf_future = executor.submit(fetch_mlf_monthly_net, requested_month)
        lpr, mlf = lpr_future.result(), mlf_future.result()
    actual_mlf_month = mlf.get("actual_month", requested_month or "unknown")
    mlf_type = "prev" if mlf.get("requested_month") != actual_mlf_month else "same"
    return {
        "as_of_date": today.strftime("%Y-%m-%d"),
        "requested_month": requested_display,
        "actual_fetched_month": {"mlf": actual_mlf_month},
        "data_month_type": {"mlf": mlf_type},
        "publish_days": {
            "mlf": "每月2-3日发布（脚本自动降级未发布月份）",
            "lpr": "每月20日（直接API获取最新值）",
        },
        "mlf": mlf,
        "lpr": lpr,
        "fetched_at": to_iso_now(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 MLF/LPR 最新指标")
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument("--month", default="", help="目标月份（YYYY-MM），默认查上月")
    parser.add_argument("--upload", action="store_true", help="抓取后构建并推送 macro_signal.json")
    args = parser.parse_args()
    setup_logging()
    payload = build_payload(args.month or None)
    print(f"[数据可用性] 请求月份: {payload['requested_month']}")
    mlf_msg = "（请求月份数据）" if payload["data_month_type"]["mlf"] == "same" else "（上月数据，因发布日未到）"
    print(f"[数据可用性] MLF实际获取: {payload['actual_fetched_month']['mlf']} {mlf_msg}")
    print(f"[数据可用性] LPR: {payload['publish_days']['lpr']}")
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.upload:
        return
    from build_macro_signal import build_signal
    from upload_signal import DEFAULT_URL, UploadError, load_env_file, upload_signal
    signal = build_signal(payload)
    if not signal["details"]:
        print("[upload] 可用指标不足，无法构建信号，跳过推送")
        sys.exit(1)
    signal_path = out_path.parent / "macro_signal.json"
    signal_path.write_text(json.dumps(signal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    load_env_file()
    token = os.environ.get("MACRO_SIGNAL_UPLOAD_TOKEN", "")
    url = os.environ.get("MACRO_SIGNAL_UPLOAD_URL", "") or DEFAULT_URL
    if not token:
        print("[upload] --upload 需要配置 MACRO_SIGNAL_UPLOAD_TOKEN")
        sys.exit(1)
    try:
        upload_signal(url, token, "monetary-policy-skill", "macro_signal.json", signal)
    except UploadError as exc:
        print(f"[upload] 推送失败: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()