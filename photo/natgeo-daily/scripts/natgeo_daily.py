#!/usr/bin/env python3
"""国家地理每日精选：抓取 + 翻译 + 钉钉推送（task-web/skill 版）。

来源：stock-info-dingding/natgeo/natgeo_push.py（2026-11-07 迁入 skill）。
差异：data 目录改为 skill 内 data/；退出码语义化；httpx→requests；
调度由 task-web 负责，本脚本不自带 cron。

退出码：0=成功（sent 或 duplicate）；2=当日照片提取失败；3=钉钉推送被拒；
5=投递结果未知（可能已送达，禁止盲目重发）；4=其他异常。

2026-11-12 改造（重复推送根因修复）：
- 推送改走公共 dingtalk-push CLI（personal-tools/dingtalk-push）。此前本脚本
  内联 requests POST，遇到 errcode=-1「系统繁忙」会把同一份正文原样重发，而 -1
  是受理后的繁忙回执（消息其实已进群）→ 群里出现两条相同推送（2026-11-12
  "国家地理 · Electric Reef" 即此因）。CLI 用内容哈希做回执去重（同内容 →
  duplicate 跳过，不再有第二条），且把超时/5xx/响应不可解析归为 unknown、
  不自动重发。
- 摄影师提取新增兜底：独立图注（Caption__Credit）与主图 JSON（crdt），
  补上「署名不在 og:description 正文」时恒为 null 的缺陷。
"""
import importlib.util
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"
PAGE_URL = "https://www.nationalgeographic.com/photo-of-the-day/"
DINGTALK_KEYWORD = "国家地理"

# 推送状态（与公共 dingtalk-push CLI 的 status 对齐）
PUSH_SENT = "sent"
PUSH_DUPLICATE = "duplicate"
PUSH_UNKNOWN = "unknown"
PUSH_FAILED = "failed"


def load_skill_env() -> None:
    """加载 skill 目录 .env（不覆盖已有环境变量）；webhook 等机密只进 .env/调度环境，不进代码。"""
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))


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


# 摄影师署名：首字母大写的姓名（最多 3 词），部分带资质后缀如 "Endia Beal, MoCP"
_NAME = r"[A-ZÀ-Ý][\w'’\.\-]*"
_CREDIT = rf"{_NAME}(?:\s+{_NAME}){{0,2}}(?:,\s*[A-Z][A-Za-z0-9&\.]{{1,8}})?"
# NatGeo 描述里署名的两种写法
_BY_PATTERNS = (r"[Pp]hotograph(?:ed)? by\s+", r"photographer\s+")
# 独立图注里的署名（NatGeo 常把署名放在正文之外）：
#   <span aria-label="..." class="RichText Caption__Credit">Manu San Félix, ...</span>
_CAPTION_CREDIT_RE = re.compile(r'class="[^"]*Caption__Credit[^"]*"[^>]*>([^<]{1,160})<')
# 主图 JSON 里的署名字段（"altText" 与 "crdt" 相邻，属同一张主图对象）
_JSON_CREDIT_RE = re.compile(r'"altText":"[^"]{0,400}","crdt":"([^"]{1,160})"')
# 资质后缀（MoCP 之类）；机构名（National Geographic Pristine Seas）不算
_CREDENTIAL_RE = re.compile(r"^[A-Z][A-Za-z0-9&\.]{1,8}$")


def normalize_credit(raw: str) -> Optional[str]:
    """署名归一：'姓名, 机构' → '姓名'；短资质后缀（MoCP）保留。

    NatGeo 图注给的是 "Manu San Félix, National Geographic Pristine Seas"，
    后半段是机构不是摄影师；"Endia Beal, MoCP" 的 MoCP 是资质，要留。
    """
    text = " ".join(str(raw or "").split()).strip(" .,;:")
    if not text:
        return None
    parts = [p.strip() for p in text.split(",")]
    name = parts[0]
    if not re.fullmatch(rf"{_NAME}(?:\s+{_NAME}){{0,2}}", name):
        return None
    if len(parts) > 1 and _CREDENTIAL_RE.fullmatch(parts[1]):
        return f"{name}, {parts[1]}"
    return name


def extract_photographer_from_description(description: str) -> Optional[str]:
    """从 OG 描述里取摄影师。

    NatGeo 的描述有两种写法：
      1) 结尾署名 "Photograph by Emre Çaylak"
      2) 正文内嵌 "photographer Emre Çaylak says ..."
    只认首字母大写的词组，避免把 "the photographer notes ..." 之类的普通短语误当成人名。
    """
    text = description or ""
    for prefix in _BY_PATTERNS:
        m = re.search(rf"{prefix}({_CREDIT})", text)
        if m:
            return normalize_credit(m.group(1))
    return None


def extract_photographer_from_html(html: str) -> Optional[str]:
    """从页面 HTML 兜底取摄影师署名（署名不在 og:description 正文时的场景）。

    2026-11-12：当日照片（Electric Reef）的署名只出现在图注与主图 JSON 里，
    og:description 里没有 → 推送内容缺「摄影师」一行。
    """
    for pattern in (_CAPTION_CREDIT_RE, _JSON_CREDIT_RE):
        m = pattern.search(html or "")
        if not m:
            continue
        name = normalize_credit(m.group(1))
        if name:
            return name
    return None


def extract_og_tag(html: str, property_name: str) -> Optional[str]:
    m = re.search(
        rf'<meta[^>]+property=["\']{re.escape(property_name)}["\'][^>]+content=["\']([^"\']+)["\']',
        html,
    ) or re.search(
        rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(property_name)}["\']',
        html,
    )
    return m.group(1) if m else None


def fetch_page(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


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
        # 正文内嵌署名优先，图注/主图 JSON 兜底
        photographer=(extract_photographer_from_description(description or "")
                     or extract_photographer_from_html(html)),
    )
    return photo


def _load_dingtalk_push():
    """加载正本 dingtalk_push.py（skills 仓库 personal-tools/dingtalk-push），不持有副本。"""
    configured = os.environ.get("DINGTALK_PUSH_SKILL_DIR")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser() / "scripts" / "dingtalk_push.py")
    for parent in Path(__file__).resolve().parents:
        for relative in ("personal-tools/dingtalk-push/scripts/dingtalk_push.py",
                         "skills/personal-tools/dingtalk-push/scripts/dingtalk_push.py"):
            candidates.append(parent / relative)
    home = Path.home()
    for root in (home / ".hermes" / "skills", home / ".codex" / "skills",
                 home / ".agents" / "skills"):
        candidates.append(root / "personal-tools" / "dingtalk-push" / "scripts" / "dingtalk_push.py")
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location("dingtalk_push_canonical", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise ImportError(
        "未找到正本 dingtalk_push.py（skills 仓库 personal-tools/dingtalk-push/scripts/）；"
        "安装 dingtalk-push skill，或把 DINGTALK_PUSH_SKILL_DIR 指向其包目录")


def push_to_dingtalk(message: str) -> str:
    """经公共 dingtalk-push CLI 投递一条 markdown；返回状态 sent/duplicate/failed/unknown。

    去重与「结果未知不盲重」由 CLI 的回执负责：
    - 同一内容再推 → duplicate（跳过，不会出现第二条相同消息）
    - 超时/5xx/响应不可解析 → unknown（可能已送达，不自动重发）
    """
    webhook = os.environ.get("NATGEO_DINGTALK_WEBHOOK", "")
    if not webhook:
        print("钉钉推送失败: 未设置 NATGEO_DINGTALK_WEBHOOK（写入 skill 目录 .env 或调度环境后重试）")
        return PUSH_FAILED
    if os.environ.get("NATGEO_DINGTALK_SECRET", "").strip():
        print("钉钉推送失败: 公共 CLI 不支持加签；请把群机器人安全设置改为「自定义关键词」"
              "（关键词：国家地理），或在 skill .env 里清空 NATGEO_DINGTALK_SECRET")
        return PUSH_FAILED
    try:
        module = _load_dingtalk_push()
    except ImportError as exc:
        print(f"钉钉推送失败: {exc}", file=sys.stderr)
        return PUSH_FAILED
    try:
        result = module.send(DINGTALK_KEYWORD, message, webhook=webhook,
                              keyword=DINGTALK_KEYWORD)
    except Exception as exc:  # 推送异常统一降级为失败，不做盲目重发
        print(f"钉钉推送失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return PUSH_FAILED
    status = str(result.get("status") or PUSH_FAILED)
    if status == PUSH_SENT:
        print("钉钉推送: 已送达")
    elif status == PUSH_DUPLICATE:
        print("钉钉推送: 相同内容此前已发送，按回执跳过（不会再出现第二条）")
    elif status == PUSH_UNKNOWN:
        print("钉钉推送: 投递结果未知（可能已送达）——先核对群消息再决定是否重发，禁止盲目重发",
              file=sys.stderr)
    else:
        print(f"钉钉推送: 未送达 status={status} "
              f"{json.dumps(result, ensure_ascii=False)}", file=sys.stderr)
    return status


def _push_exit_code(status: str) -> int:
    """推送状态 → 退出码。duplicate 视为成功（此前已送达）；unknown 单列，禁止盲目重发。"""
    if status in (PUSH_SENT, PUSH_DUPLICATE):
        return 0
    if status == PUSH_UNKNOWN:
        return 5
    return 3


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
    load_skill_env()
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
        status = push_to_dingtalk(build_dingtalk_markdown(photo))
        code = _push_exit_code(status)
        if code == 5:
            print(">>> 钉钉投递结果未知（可能已送达）：先核对群消息再决定是否重发")
            return 5
        if code != 0:
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
