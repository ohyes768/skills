#!/usr/bin/env python3
"""Fetch a read-only CSI300 snapshot and print a concise Chinese brief."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
from runpy import run_path
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

dingtalk = run_path(str(Path(__file__).with_name("dingtalk_push.py")))

DEFAULT_BASE_URL = "https://web.duomi77.cn:9443/api/index-trends"
MODELS = {"trailing_10y_weekly": "近10年周线通道",
          "since_inception_weekly": "上市以来周线通道"}
REGIONS = {"below_channel": "下方", "lower": "低位", "middle": "中部",
           "upper": "高位", "above_channel": "上方"}
REASONS = {"model_not_ready": "模型尚未就绪", "no_daily_data": "暂无日行情",
           "invalid_channel": "通道计算异常"}


def number(value, precision=2):
    """Reject booleans, numeric strings and nonfinite values; keep real zero."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return f"{value:.{precision}f}" if math.isfinite(value) else None
    except OverflowError:
        return None


def mapping(value):
    return value if isinstance(value, dict) else {}


def date_label(value, missing):
    return f"截至{value}" if isinstance(value, str) and value else missing


def summarize(data):
    """Preserve independent market/valuation dates and quality warnings."""
    market = []
    if data.get("available") is True:
        market.append("沪深300" + date_label(data.get("price_as_of"), "（行情日期未提供）"))
        close = number(data.get("close"))
        market.append(f"收于{close}点" if close is not None else "收盘价暂无数据")
        model = MODELS.get(data.get("model_kind"), "周线通道（模型未确认）")
        region = REGIONS.get(data.get("region"))
        market.append(f"位于{model}{region}" if region else f"采用{model}，区域未确认")
        position = number(data.get("position_pct"), 1)
        market.append(f"通道位置{position}%" if position is not None else "通道位置暂无数据")
        rails = [number(data.get(key)) for key in ("lower", "mid", "upper")]
        market.append("下轨/中轨/上轨为" + "/".join(rails) + "点"
                      if all(item is not None for item in rails) else "轨道数据不完整")
    else:
        reason = REASONS.get(data.get("reason"), "数据尚未就绪或状态未确认")
        market.append(f"沪深300周线通道暂不可用（{reason}）")
    state = mapping(data.get("data_status")).get("state")
    if state != "ok":
        warning = {"stale": "行情滞后，以上为缓存值",
                   "error": "行情更新失败，以上为缓存值",
                   "empty": "行情暂无数据"}.get(state, "行情状态未确认")
        market.append(warning)

    valuation = mapping(data.get("valuation"))
    state = valuation.get("state")
    if state in ("disabled", "empty"):
        text = "估值未启用" if state == "disabled" else "估值暂无数据"
    else:
        pe = number(valuation.get("pe_ttm"))
        percentile = number(valuation.get("percentile_pct"), 1)
        if state == "error" and pe is None and percentile is None:
            text = "估值更新失败，估值暂不可用"
        else:
            pieces = ["估值" + date_label(valuation.get("as_of"), "日期未提供")]
            if state != "ok":
                pieces.append({"stale": "估值滞后", "error": "估值更新失败，以下为缓存值"}
                              .get(state, "估值状态未确认"))
            if state == "stale" and valuation.get("target_date"):
                pieces.append(f"目标日期{valuation['target_date']}")
            pieces.append(f"PE-TTM为{pe}倍" if pe is not None else "PE-TTM暂无数据")
            pieces.append(f"近10年分位{percentile}%" if percentile is not None else "PE分位暂无数据")
            text = "，".join(pieces)
    return "，".join(market) + "。" + text + "。"


def tls_context(insecure=False, ca_file=None):
    """Default strict verification; `--insecure` is opt-in, `--ca-file` pins a CA."""
    if insecure:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        return context
    return ssl.create_default_context(cafile=str(ca_file)) if ca_file else ssl.create_default_context()


def fetch(base_url, model, timeout, context=None):
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        raise ValueError("invalid API base URL")
    url = base_url.rstrip("/") + "/indices/000300/status?" + urlencode({"model": model})
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "csi300-brief/1.0"})
    with urlopen(request, timeout=timeout, context=context) as response:
        data = json.loads(response.read())
    if not isinstance(data, dict) or not isinstance(data.get("available"), bool):
        raise ValueError("invalid snapshot")
    return data


def push_title(data):
    """Title carries the robot keyword so the message never fails `310000`."""
    date = data.get("price_as_of")
    if not isinstance(date, str) or not date:
        date = datetime.now().strftime("%Y-%m-%d")
    return f"沪深300 ETF 简况 · {date}"


def push(text, title, *, env_file=None, keyword=None, timeout=10, dry_run=False):
    """Return the shared sender's result; delivery failures are classified, not raised."""
    path = Path(env_file) if env_file else None
    keyword = dingtalk["resolve_keyword"](keyword, path)
    if not dingtalk["keyword_present"](title, text, keyword):
        return dingtalk["result"](dingtalk["KEYWORD_MISSING"],
                                  errmsg=f"标题或正文未包含关键词「{keyword}」，未发送")
    try:
        webhook = dingtalk["resolve_webhook"](None, path)
    except ValueError as exc:
        return dingtalk["result"](dingtalk["NOT_CONFIGURED"], errmsg=str(exc))
    if dry_run:
        return dict(dingtalk["result"](dingtalk["DRY_RUN"], errmsg="未发送"), title=title)
    return dingtalk["send"](webhook, title, text, timeout=timeout)


def positive_timeout(value):
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("超时必须为正数") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("超时必须为正数")
    return timeout


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="API前缀，不包含/indices路径")
    parser.add_argument("--model", choices=tuple(MODELS), default="trailing_10y_weekly")
    parser.add_argument("--timeout", type=positive_timeout, default=20, help="请求超时秒数（默认20）")
    parser.add_argument("--push", action="store_true", help="生成后推送到钉钉群机器人")
    parser.add_argument("--title", help="钉钉标题，默认「沪深300 ETF 简况 · 价格日期」")
    parser.add_argument("--env-file", type=Path, help=".env 路径，默认本 skill 目录下的 .env")
    parser.add_argument("--keyword", help="机器人关键词，默认读 DINGTALK_KEYWORD")
    parser.add_argument("--push-timeout", type=positive_timeout, default=10, help="推送超时秒数（默认10）")
    parser.add_argument("--dry-run", action="store_true", help="配合 --push 只校验配置与关键词，不发送")
    parser.add_argument("--insecure", action="store_true",
                        help="跳过 TLS 证书校验（仅在本机明确接受该风险时使用，默认严格校验）")
    parser.add_argument("--ca-file", type=Path, help="把自签证书或内网 CA 指定为信任根，替代 --insecure")
    args = parser.parse_args(argv)
    try:
        context = tls_context(args.insecure, args.ca_file)
    except (OSError, ssl.SSLError):
        print("沪深300数据暂时获取失败（证书文件无法读取或无效）。")
        return 1
    try:
        data = fetch(args.base_url, args.model, args.timeout, context)
    except HTTPError as exc:
        reason = f"接口HTTP {exc.code}"
    except (URLError, OSError):
        reason = "网络、超时或TLS连接异常"
    except (ValueError, UnicodeError):
        reason = "接口地址或响应格式无效"
    else:
        text = summarize(data)
        print(text)
        if not args.push:
            return 0
        outcome = push(text, args.title or push_title(data), env_file=args.env_file,
                       keyword=args.keyword, timeout=args.push_timeout, dry_run=args.dry_run)
        print(json.dumps(outcome, ensure_ascii=False), file=sys.stderr)
        return dingtalk["EXIT_CODES"][outcome["status"]]
    print(f"沪深300数据暂时获取失败（{reason}）。")
    return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
