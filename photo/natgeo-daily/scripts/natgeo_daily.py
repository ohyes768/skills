#!/usr/bin/env python3
"""国家地理每日精选：抓取 + 翻译 + 钉钉推送（task-web/skill 版）。

来源：stock-info-dingding/natgeo/natgeo_push.py（2026-11-07 迁入 skill）。
差异：data 目录改为 skill 内 data/；退出码语义化；httpx→requests；
无按日去重（与原版一致）。调度由 task-web 负责，本脚本不自带 cron。

退出码：0=成功；2=当日照片提取失败；3=钉钉推送失败；4=其他异常。
"""
import base64
import hashlib
import hmac
import json
import os
import re
import sys
import time
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
PAGE_URL = "https://www.nationalgeographic.com/photo-of-the-day/"
DINGTALK_KEYWORD = "国家地理"
DEFAULT_WEBHOOK = os.environ.get(
    "NATGEO_DINGTALK_WEBHOOK",
    "https://oapi.dingtalk.com/robot/send?access_token=b9053bb9dae6c8f2c74d8f70cab2ef663f224751ab0b7bac281b2d370f521063",
)


def translate_to_chinese(text: str, api_key: Optional[str] = None) -> Optional[str]:
    """DeepSeek 翻译；无 key 返回 None（Hermes 会话内可由模型自行翻译）。"""
    key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        print("警告: 未设置 DEEPSEEK_API_KEY，跳过脚本内翻译")
        return None
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": "你是专业翻译，把英文摄影说明译成优美的中文，保留原文的意境。"},
            {"role": "user", "content": text},
        ],
        "temperature": 0.3,
    }
    try:
        resp = requests.post(
            DEEPSEEK_API_URL,
            headers={"Authorization": f"Bearer {key}"},
            json=payload, timeout=30,
        )
        resp.raise_for_status()
        return str(resp.json()["choices"][0]["message"]["content"]).strip()
    except Exception as e:
        print(f"警告: DeepSeek 翻译失败: {e}")
        return None


@dataclass
class PhotoItem:
    title: str = ""
    description: str = ""
    translated_description: Optional[str] = None
    image_url: str = ""
    page_url: str = ""
    date: str = ""
    photographer: Optional[str] = None


def get_sign(secret: str) -> tuple[str, str]:
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    hmac_code = hmac.new(secret.encode(), string_to_sign.encode(), hashlib.sha256).digest()
    return timestamp, urllib.parse.quote_plus(base64.b64encode(hmac_code))


def fetch_page(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_og_tag(html: str, property_name: str) -> Optional[str]:
    m = re.search(
        rf'<meta[^>]+property=["\']{re.escape(property_name)}["\'][^>]+content=["\']([^"\']+)["\']',
        html,
    ) or re.search(
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(property_name)}["\']',
        html,
    )
    return m.group(1) if m else None


def extract_photographer_from_description(description: str) -> Optional[str]:
    m = re.search(r"[Pp]hotograph by\s+(.+)", description or "")
    return m.group(1).strip() if m else None


def extract_from_page(html: str, page_url: str) -> Optional[PhotoItem]:
    title = extract_og_tag(html, "og:title")
    description = extract_og_tag(html, "og:description")
    image_url = extract_og_tag(html, "og:image")
    if not title or not image_url:
        return None
    photo = PhotoItem(
        title=title.strip(),
        description=(description or "").strip(),
        image_url=image_url,
        page_url=page_url,
        date=page_url.rstrip("/").split("/")[-1] if page_url.rstrip("/").split("/")[-1].count("-") == 2 else "",
        photographer=extract_photographer_from_description(description or ""),
    )
    return photo


def push_to_dingtalk(message: str) -> bool:
    webhook = DEFAULT_WEBHOOK
    secret = os.environ.get("NATGEO_DINGTALK_SECRET", "")
    if secret:
        ts, sign = get_sign(secret)
        webhook = f"{webhook}&timestamp={ts}&sign={sign}"
    resp = requests.post(
        webhook,
        json={"msgtype": "markdown", "markdown": {"title": DINGTALK_KEYWORD, "text": message}},
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    ok = resp.status_code == 200
    print(f"钉钉推送: HTTP {resp.status_code} {resp.text[:120]}")
    return ok


def build_dingtalk_markdown(photo: PhotoItem) -> str:
    lines = [f"### {DINGTALK_KEYWORD} · {photo.title}"]
    if photo.date:
        lines.append(f"**日期**: {photo.date}")
    if photo.photographer:
        lines.append(f"**摄影师**: {photo.photographer}")
    if photo.translated_description:
        lines.append(f"\n{photo.translated_description}")
    lines.append(f"\n{photo.description}")
    if photo.page_url:
        lines.append(f"\n[查看原图]({photo.page_url})")
    lines.append(f"\n![photo]({photo.image_url})")
    return "\n".join(lines)


def main() -> int:
    print(">>> 国家地理每日精选")
    data_dir = Path(__file__).resolve().parent.parent / "data"
    output_file = data_dir / f"natgeo_photo_{datetime.now().strftime('%Y%m%d')}.json"
    try:
        html = fetch_page(PAGE_URL)
        page_url = extract_og_tag(html, "og:url") or PAGE_URL
        photo = extract_from_page(html, page_url)
        if not photo:
            print(">>> 提取数据失败：当日照片 OG 标签缺失")
            return 2
        print(f">>> 标题: {photo.title} | 摄影师: {photo.photographer}")
        photo.translated_description = translate_to_chinese(photo.description)
        data_dir.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(asdict(photo), ensure_ascii=False, indent=2), encoding="utf-8")
        print(f">>> 数据已保存: {output_file}")
        if not push_to_dingtalk(build_dingtalk_markdown(photo)):
            print(">>> 钉钉推送失败")
            return 3
        print(">>> 完成!")
        return 0
    except Exception as e:
        print(f">>> 错误: {e}")
        import traceback
        traceback.print_exc()
        return 4


if __name__ == "__main__":
    sys.exit(main())
