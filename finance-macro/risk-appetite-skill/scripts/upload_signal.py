#!/usr/bin/env python3
"""
宏观信号上传脚本 - 推送 skill JSON 到 macro 后端

对接契约: personal-web/.trellis/spec/guides/macro-signal-upload.md
    POST https://<host>/api/macro/signal/upload
    Header X-Upload-Token, body {"skill", "file", "data"}

本脚本设计为 6 个 finance-macro 子 skill 通用：
    - risk-appetite-skill → risk_data.json（结构嵌套在 data.* 下）
    - 其余 5 个宏观信号 skill → macro_signal.json（conclusion/data_date/details）

配置来源（finance-macro/.env，由 fetch_common.load_env_file 加载）：
    MACRO_SIGNAL_UPLOAD_TOKEN   # 必填，缺失直接报错退出
    MACRO_SIGNAL_UPLOAD_URL     # 默认 https://web.duomi77.cn:9443/api/macro/signal/upload

用法示例：
    # 推送 risk_data.json（默认输入、默认 skill）
    uv run python scripts/upload_signal.py

    # 干跑：只做本地预检并打印 payload 摘要，不发送
    uv run python scripts/upload_signal.py --dry-run

    # 推送并验证月份列表出现新月份
    uv run python scripts/upload_signal.py --verify

    # 其他宏观 skill 复用（自动推断 file=macro_signal.json）
    uv run python scripts/upload_signal.py --skill inflation-skill --input ../inflation-skill/macro_signal.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from urllib3.exceptions import InsecureRequestWarning

# 确保本地 scripts 目录可导入
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from fetch_common import LOGGER, load_env_file, setup_logging

# ============ 契约常量（对齐后端 ALLOWED_SKILLS / ALLOWED_FILES）============

DEFAULT_URL = "https://web.duomi77.cn:9443/api/macro/signal/upload"
UPLOAD_TIMEOUT = 10  # 秒
MAX_RETRIES = 2      # 仅网络错误/5xx 重试，4xx 不重试（契约 7.6：不要无限重试）

# skill → 允许推送的 file（risk-appetite 与其他 5 个结构不同，不能混传）
MACRO_SKILLS = {
    "monetary-policy-skill", "money-supply-skill", "entity-economy-skill",
    "inflation-skill", "exchange-rate-skill",
}
RISK_SKILL = "risk-appetite-skill"
SKILL_FILE_MAP = {skill: "macro_signal.json" for skill in MACRO_SKILLS}
SKILL_FILE_MAP[RISK_SKILL] = "risk_data.json"


def ssl_verify_from_env() -> bool:
    """是否校验 TLS 证书（NAS 自签场景可设 MACRO_UPLOAD_SSL_VERIFY=0 跳过，仅限内网自建服务）"""
    return os.environ.get("MACRO_UPLOAD_SSL_VERIFY", "1").strip().lower() not in ("0", "false", "no")


# ============ 本地预检（fail-fast，避免无谓网络请求被后端 400/401 打回）============

def _date_only(value: Any) -> str | None:
    """取日期前 10 位（兼容 'YYYY-MM-DD' 与 ISO 时间戳，对齐后端行为）"""
    if not isinstance(value, str) or len(value) < 10:
        return None
    head = value[:10]
    try:
        datetime.strptime(head, "%Y-%m-%d")
        return head
    except ValueError:
        return None


def validate_payload(skill: str, file: str, data: Any) -> tuple[list[str], list[str]]:
    """
    按契约校验 payload，返回 (errors, warnings)。

    errors: 会阻止上传的结构问题（对应后端 400 或后端读到空指标）
    warnings: 不阻止上传，但值得提醒（如数据日期过旧）
    """
    errors: list[str] = []
    warnings: list[str] = []

    # --- 白名单 / 配对（对应后端 400）---
    if skill not in SKILL_FILE_MAP:
        errors.append(f"非法 skill: {skill}（白名单: {sorted(SKILL_FILE_MAP)}）")
        return errors, warnings
    if file not in ("macro_signal.json", "risk_data.json"):
        errors.append(f"非法 file: {file}（仅允许 macro_signal.json / risk_data.json）")
        return errors, warnings
    if SKILL_FILE_MAP[skill] != file:
        errors.append(
            f"skill 与 file 不匹配: {skill} 只能推送 {SKILL_FILE_MAP[skill]}，收到 {file}"
        )
        return errors, warnings
    if not isinstance(data, dict):
        errors.append("data 必须是 JSON 对象（dict），不能是 list/string/null")
        return errors, warnings

    # --- 结构最小集（对齐后端转换逻辑，缺 key 后端不报错但读到空指标）---
    dates: list[str] = []

    if file == "risk_data.json":
        # 后端 _convert_risk_appetite: score.conclusion + data.{volume,turnover,margin}.*
        score = data.get("score")
        if not (isinstance(score, dict) and isinstance(score.get("conclusion"), str) and score.get("conclusion")):
            errors.append("缺少 score.conclusion（定性结论，后端展示用）")

        inner = data.get("data")
        if not isinstance(inner, dict):
            errors.append("缺少 data 字段（risk_data.json 的指标嵌套在 data.* 下）")
            return errors, warnings

        required = [
            ("volume", "total_amount_yi", "两市成交额(亿元)"),
            ("turnover", "turnover_rate", "换手率(%)"),
            ("margin", "rzye", "融资余额(亿元)"),
        ]
        for sub_key, field, label in required:
            block = inner.get(sub_key)
            if not isinstance(block, dict) or not block:
                errors.append(f"缺少 data.{sub_key}（{label}）")
                continue
            value = block.get(field)
            if value is None or isinstance(value, str):
                errors.append(f"data.{sub_key}.{field} 缺失或非数值（{label}）")
            d = _date_only(block.get("date"))
            if d is None:
                errors.append(f"data.{sub_key}.date 缺失或格式非法（后端靠它判断数据月份）")
            else:
                dates.append(d)

    else:  # macro_signal.json
        # 后端 _convert_dimension_from_macro_signal: conclusion + data_date + details 数值
        if not (isinstance(data.get("conclusion"), str) and data.get("conclusion")):
            errors.append("缺少 conclusion（定性结论）")

        d = _date_only(data.get("data_date"))
        if d is None:
            errors.append("data_date 缺失或格式非法（需 YYYY-MM-DD 或 ISO 时间戳）")
        else:
            dates.append(d)

        details = data.get("details")
        if not isinstance(details, dict) or not details:
            errors.append("缺少 details（指标字典）")
        else:
            numeric = [k for k, v in details.items() if isinstance(v, (int, float))]
            dropped = len(details) - len(numeric)
            if not numeric:
                errors.append("details 中没有任何数值型指标（字符串/None 会被后端丢弃）")
            elif dropped:
                warnings.append(f"details 中有 {dropped} 个非数值 key 将被后端丢弃")

    # --- 新鲜度（契约 7.2：data_date 必须真实，过旧会让前端读到旧月份）---
    for d in dates:
        age = datetime.now() - datetime.strptime(d, "%Y-%m-%d")
        if age > timedelta(days=10):
            warnings.append(f"数据日期 {d} 距今已 {age.days} 天，确认是否要推送旧数据")

    return errors, warnings


# ============ 上传 / 验证 ============

def upload_signal(
    url: str,
    token: str,
    skill: str,
    file: str,
    data: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any] | None:
    """
    推送 JSON 到 macro 后端。成功返回响应 dict，失败抛 UploadError。

    重试策略：仅网络错误 / 5xx 重试（退避 2s、4s），4xx 不重试。
    """
    errors, warns = validate_payload(skill, file, data)
    for w in warns:
        LOGGER.warning("预检警告: %s", w)
    if errors:
        for e in errors:
            LOGGER.error("预检失败: %s", e)
        raise UploadError(f"payload 预检未通过（{len(errors)} 个错误）", status=None)

    payload = {"skill": skill, "file": file, "data": data}

    if dry_run:
        LOGGER.info("[dry-run] 预检通过，不发送。payload: skill=%s file=%s bytes=%s",
                    skill, file, len(json.dumps(payload, ensure_ascii=False)))
        return None

    headers = {"X-Upload-Token": token, "Content-Type": "application/json"}
    body = json.dumps(payload, ensure_ascii=False)
    ssl_verify = ssl_verify_from_env()
    if not ssl_verify:
        warnings.filterwarnings("ignore", category=InsecureRequestWarning)
        LOGGER.info("MACRO_UPLOAD_SSL_VERIFY=0，跳过证书校验（自签内网场景）")

    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 2):  # 1 次首发 + 2 次重试
        try:
            resp = requests.post(url, headers=headers, data=body.encode("utf-8"),
                                 timeout=UPLOAD_TIMEOUT, verify=ssl_verify)
        except requests.RequestException as exc:
            last_exc = exc
            LOGGER.warning("网络错误(第 %d/%d 次): %s", attempt, MAX_RETRIES + 1, exc)
            if attempt <= MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            raise UploadError(f"网络错误，已重试 {MAX_RETRIES} 次仍失败: {exc}", status=None)

        # HTTP 有响应 → 按状态码处理（4xx 不重试）
        if resp.status_code == 200:
            result = resp.json()
            LOGGER.info("上传成功: skill=%s file=%s bytes=%s path=%s",
                        result.get("skill"), result.get("file"),
                        result.get("bytes"), result.get("path"))
            return result

        detail = _safe_detail(resp)
        if resp.status_code == 401:
            # 契约 7.6: 401 → 检查 token 配置
            hint = "upload token 未配置（服务端 MACRO_SIGNAL_UPLOAD_TOKEN）" if "未配置" in detail \
                else "token 错误，检查 MACRO_SIGNAL_UPLOAD_TOKEN"
            raise UploadError(f"401 Unauthorized: {detail}（{hint}）", status=401)
        if resp.status_code == 400:
            raise UploadError(f"400 Bad Request: {detail}（检查 skill/file 白名单与 data 结构）", status=400)
        if resp.status_code == 422:
            raise UploadError(f"422 Unprocessable Entity: {detail}（请求体 JSON 解析失败）", status=422)
        if resp.status_code >= 500:
            LOGGER.warning("服务端 %d(第 %d/%d 次): %s",
                           resp.status_code, attempt, MAX_RETRIES + 1, detail)
            if attempt <= MAX_RETRIES:
                time.sleep(2 ** attempt)
                continue
            raise UploadError(f"服务端错误 {resp.status_code}: {detail}", status=resp.status_code)
        raise UploadError(f"意外状态码 {resp.status_code}: {detail}", status=resp.status_code)

    raise UploadError(f"上传失败: {last_exc}", status=None)


def verify_months(url: str, data_dates: list[str]) -> bool:
    """
    推送后验（契约 6）：GET /api/macro/months，确认数据月份已出现。

    data_dates: payload 中出现的 'YYYY-MM-DD' 列表（任一月份出现即算通过）。
    """
    months_url = urljoin(url, "../months")  # .../signal/upload → .../months
    expect = {d[:7] for d in data_dates}
    try:
        resp = requests.get(months_url, timeout=UPLOAD_TIMEOUT, verify=ssl_verify_from_env())
        resp.raise_for_status()
        months = set(resp.json().get("months", []))
    except requests.RequestException as exc:
        LOGGER.warning("月份验证请求失败(不影响上传结果): %s", exc)
        return False

    hit = expect & months
    if hit:
        LOGGER.info("验证通过: 月份 %s 已出现在 GET /months（缓存已清，立即生效）", sorted(hit))
        return True
    LOGGER.warning("验证未通过: 期望月份 %s 未出现在 /months 返回 %s 中", sorted(expect), sorted(months))
    return False


def _safe_detail(resp: requests.Response) -> str:
    """安全提取 FastAPI 错误 detail，避免二次异常"""
    try:
        detail = resp.json().get("detail", "")
        return str(detail) if detail else resp.text[:200]
    except ValueError:
        return resp.text[:200]


class UploadError(Exception):
    """上传失败（携带 HTTP 状态码，便于上游区分处理）"""

    def __init__(self, message: str, status: int | None):
        super().__init__(message)
        self.status = status


# ============ CLI ============

def main() -> int:
    parser = argparse.ArgumentParser(description="推送宏观信号 JSON 到 macro 后端")
    parser.add_argument("--input", type=str, default="",
                        help="输入 JSON 路径（默认: <skill根>/<推断的file>）")
    parser.add_argument("--skill", type=str, default=RISK_SKILL,
                        help=f"skill 名（默认 {RISK_SKILL}，白名单见 SKILL_FILE_MAP）")
    parser.add_argument("--file", type=str, default="",
                        help="推送的 file 名（默认按 skill 推断）")
    parser.add_argument("--url", type=str, default="",
                        help="上传地址（默认 env MACRO_SIGNAL_UPLOAD_URL 或内置生产地址）")
    parser.add_argument("--verify", action="store_true",
                        help="推送成功后调用 GET /months 验证月份出现")
    parser.add_argument("--dry-run", action="store_true",
                        help="只做本地预检并打印 payload 摘要，不发送")
    args = parser.parse_args()

    setup_logging()

    skill = args.skill
    file = args.file or SKILL_FILE_MAP.get(skill, "")
    skill_root = _SCRIPT_DIR.parent
    # 与 run_all.py 统一输出目录对齐，旧位置作回退
    candidates = [
        skill_root.parent / "output" / skill_root.name / file,  # finance-macro/output/<skill>/<file>
        skill_root / file,                                       # <skill根>/<file>（旧位置）
    ]
    if args.input:
        input_path = Path(args.input)
    else:
        input_path = next((p for p in candidates if p.exists()), candidates[0])

    # 配置：.env 优先于内置默认（token 必须来自 env，不硬编码）
    load_env_file()
    token = os.environ.get("MACRO_SIGNAL_UPLOAD_TOKEN", "")
    url = args.url or os.environ.get("MACRO_SIGNAL_UPLOAD_URL", "") or DEFAULT_URL

    if not token:
        LOGGER.error("缺少 MACRO_SIGNAL_UPLOAD_TOKEN（配置在 finance-macro/.env 或环境变量）")
        return 1

    if not input_path.exists():
        LOGGER.error("输入文件不存在: %s", input_path)
        return 1

    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    try:
        upload_signal(url, token, skill, file, data, dry_run=args.dry_run)
    except UploadError as exc:
        LOGGER.error("上传失败: %s", exc)
        return 1

    if args.verify and not args.dry_run:
        # 汇总 payload 中的数据日期用于验证
        dates: list[str] = []
        if file == "risk_data.json":
            inner = data.get("data") or {}
            for sub in ("volume", "turnover", "margin"):
                d = _date_only((inner.get(sub) or {}).get("date"))
                if d:
                    dates.append(d)
        else:
            d = _date_only(data.get("data_date"))
            if d:
                dates.append(d)
        if dates:
            verify_months(url, dates)

    return 0


if __name__ == "__main__":
    sys.exit(main())
