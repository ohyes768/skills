"""每日财报阅读（选股推荐）。

数据流：
    emappdata.eastmoney.com（人气榜代码）
    + ak.stock_zh_a_spot()（新浪全 A 股行情）
    + qt.gtimg.cn（腾讯总市值）
    + sw_industry_mapping.csv（本地行业映射）
    → 4 条硬规则过滤 → 行业轮换 + 30 天去重 → Markdown → DingTalkPusher。

设计文档：.trellis/tasks/08-20-daily-stock-pick/design.md
"""
from __future__ import annotations

import json
import logging
import os
import random
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from dingtalk_push import DingTalkPusher

# 自动加载 .env（与 a_stock_push.py 同款做法）
_dotenv_path = Path(__file__).resolve().parent / ".env"
if _dotenv_path.exists():
    with open(_dotenv_path, encoding="utf-8") as f:
        for _line in f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _key, _value = _line.split("=", 1)
                os.environ.setdefault(_key.strip(), _value.strip())

LOGGER = logging.getLogger(__name__)

HISTORY_VERSION = 1
HISTORY_PATH = Path(__file__).resolve().parent / "data" / "daily_pick_history.json"
SW_INDUSTRY_CSV = Path(__file__).resolve().parent / "sw_industry_mapping.csv"
EMAPP_HOT_URL = "https://emappdata.eastmoney.com/stockrank/getAllCurrentList"
TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
EM_APPOINT_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
LISTING_AGE_DAYS_FOR_KNOWN = 730  # CSV 收录视为已上市 2 年
REPORT_WINDOW_DAYS = 180          # 财报查询/展示窗口
ANNUAL_WINDOW_DAYS = 800          # 年报行业学习查询窗口（年报多在 1-4 月披露，需覆盖两期）


# ======================
# 配置 / DTO
# ======================


@dataclass(frozen=True)
class PickConfig:
    """选股阈值配置。"""

    min_total_mv_wan: float = 300_000.0  # 30 亿元 = 300,000 万元
    min_amount_wan: float = 3_000.0      # 3000 万元
    min_listing_days: int = 365
    cooldown_days: int = 30
    industry_rotation_window_days: int = 14
    pct_warn_threshold: float = 5.0      # 单日涨跌幅 ±5% 提示风险


@dataclass(frozen=True)
class Candidate:
    """过滤后的候选股票。"""

    code: str
    name: str
    market: str
    total_mv_wan: float
    amount_wan: float
    pct_chg: float
    listing_date: date
    industry: str = ""


@dataclass(frozen=True)
class PickRecord:
    """每日推荐的历史记录。"""

    date: str
    code: str
    name: str
    industry: str
    latest_report_url: str = ""


@dataclass(frozen=True)
class History:
    """历史推荐记录集合（不可变）。"""

    records: tuple[PickRecord, ...] = ()

    @classmethod
    def load(cls, path: Path) -> History:
        if not path.exists():
            LOGGER.warning("历史文件不存在: %s，按空历史运行", path)
            return cls()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            records_raw = raw.get("records", [])
            records = tuple(
                PickRecord(
                    date=str(r["date"]),
                    code=str(r["code"]),
                    name=str(r["name"]),
                    industry=str(r.get("industry", "")),
                    latest_report_url=str(r.get("latest_report_url", "")),
                )
                for r in records_raw
            )
            return cls(records=records)
        except (json.JSONDecodeError, KeyError, OSError) as exc:
            LOGGER.warning("历史文件损坏: %s (%s)，按空历史运行", path, exc)
            return cls()

    def save(self, path: Path) -> None:
        payload = {"version": HISTORY_VERSION, "records": [r.__dict__ for r in self.records]}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def append(self, record: PickRecord) -> History:
        return History(records=self.records + (record,))

    def is_in_cooldown(self, code: str, today: date, cooldown_days: int) -> bool:
        for r in self.records:
            if r.code != code:
                continue
            try:
                rd = date.fromisoformat(r.date)
            except ValueError:
                continue
            if (today - rd).days < cooldown_days:
                return True
        return False

    def industry_freq(self, today: date, window_days: int) -> dict[str, int]:
        freq: dict[str, int] = {}
        for r in self.records:
            if not r.industry:
                continue
            try:
                rd = date.fromisoformat(r.date)
            except ValueError:
                continue
            if (today - rd).days < window_days:
                freq[r.industry] = freq.get(r.industry, 0) + 1
        return freq


# ======================
# 过滤 + 轮换
# ======================


def is_st_name(name: str) -> bool:
    """判断名称是否为 ST / *ST / 退市股。

    启发式：中文 ST 标记的 "ST" 后面必跟空格/中文/符号或字符串边界；
    英文词 "Stellantis" 等的 "ST" 后面必跟英文字母。
    """
    if "退" in name:
        return True
    upper = name.upper()
    idx = 0
    while True:
        idx = upper.find("ST", idx)
        if idx == -1:
            return False
        after = upper[idx + 2] if idx + 2 < len(upper) else ""
        if not after.isalpha():
            return True
        idx += 2


def filter_candidates(
    candidates: Iterable[Candidate], cfg: PickConfig, today: date
) -> list[Candidate]:
    """应用 4 条硬规则：非 ST、上市 ≥ 365 天、市值 ≥ 30 亿、成交额 ≥ 3000 万。"""
    result: list[Candidate] = []
    for c in candidates:
        if is_st_name(c.name):
            continue
        if (today - c.listing_date).days < cfg.min_listing_days:
            continue
        if c.total_mv_wan < cfg.min_total_mv_wan:
            continue
        if c.amount_wan < cfg.min_amount_wan:
            continue
        result.append(c)
    return result


def rotate_pick(
    candidates: Iterable[Candidate],
    history: History,
    today: date,
    cfg: PickConfig,
    rng: random.Random,
) -> Candidate | None:
    """行业轮换抽样。"""
    pool = [
        c
        for c in candidates
        if not history.is_in_cooldown(c.code, today, cfg.cooldown_days)
    ]
    if not pool:
        return None

    freq = history.industry_freq(today, cfg.industry_rotation_window_days)

    # 优先"最近窗口内未推荐过"的行业
    fresh = [c for c in pool if freq.get(c.industry, 0) == 0]
    if fresh:
        return rng.choice(fresh)

    # 兜底：取频次最低的行业
    min_freq = min(freq.get(c.industry, 0) for c in pool)
    low_freq_pool = [c for c in pool if freq.get(c.industry, 0) == min_freq]
    return rng.choice(low_freq_pool) if low_freq_pool else None


# ======================
# Markdown 渲染
# ======================


def build_markdown(
    pick: Candidate | None,
    today: date,
    freq: dict[str, int] | None = None,
    report_urls: list[str] | None = None,
    cfg: PickConfig | None = None,
    next_report: str = "",
) -> str:
    cfg = cfg or PickConfig()
    if pick is None:
        return f"# 每日财报阅读 {today.isoformat()}\n\n今日无可推荐。\n"

    warn = " ⚠️" if abs(pick.pct_chg) >= cfg.pct_warn_threshold else ""
    mv_yi = pick.total_mv_wan / 10_000.0
    amount_qian_wan = pick.amount_wan / 1_000.0  # 万元 → 千万元
    # report_urls 元素格式："YYYY-MM-DD 公告标题 URL"（fetch_report_urls 生成）
    report_lines: list[str] = []
    for report_url in report_urls or []:
        parts = report_url.split(" ", 2)
        if len(parts) == 3:
            report_lines.append(f"- [{parts[1]}（{parts[0]}披露）]({parts[2]})")
    report_section = (
        "**近 180 天财报**：\n\n" + "\n".join(report_lines)
        if report_lines
        else "**近 180 天财报**：（暂无披露计划）"
    )
    next_report_section = f"**下期财报**：{next_report}\n\n" if next_report else ""
    freq_summary = (
        ", ".join(f"{k}: {v}" for k, v in (freq or {}).items()) or "（无历史）"
    )

    return (
        f"# 每日财报阅读 {today.isoformat()}\n\n"
        f"## {pick.name}（{pick.code}）\n\n"
        f"| 项目 | 数据 |\n"
        f"|------|------|\n"
        f"| 市场 | {pick.market} |\n"
        f"| 总市值 | {mv_yi:.2f} 亿元 |\n"
        f"| 当日成交额 | {amount_qian_wan:.2f} 千万元 |\n"
        f"| 涨跌幅 | {pick.pct_chg:+.2f}%{warn} |\n"
        f"| 所属行业 | {pick.industry or '（未识别）'} |\n"
        f"| 上市日期 | {pick.listing_date.isoformat()} |\n\n"
        f"{report_section}\n\n"
        f"{next_report_section}"
        f"---\n"
        f"历史 {cfg.industry_rotation_window_days} 天行业频次：{freq_summary}\n"
    )


# ======================
# 数据源层
# ======================


def _determine_market(code: str) -> str:
    if code.startswith("60"):
        return "上海-主板"
    if code.startswith("68"):
        return "上海-科创板"
    if code.startswith("00"):
        return "深圳-主板"
    if code.startswith("30"):
        return "深圳-创业板"
    if code.startswith(("8", "4", "92", "93")):
        return "北交所"
    return ""


_INDUSTRY_CACHE: tuple[dict[str, str], set[str]] | None = None


def _load_industry_csv() -> tuple[dict[str, str], set[str]]:
    """加载 sw_industry_mapping.csv，返回 ({code6: 二级行业}, {code6})。"""
    global _INDUSTRY_CACHE
    if _INDUSTRY_CACHE is not None:
        return _INDUSTRY_CACHE
    df = pd.read_csv(SW_INDUSTRY_CSV, dtype=str)
    code6 = df["股票代码"].str.extract(r"(\d{6})")[0]
    industry = df["二级行业"].fillna("")
    code_set = set(code6)
    _INDUSTRY_CACHE = (dict(zip(code6, industry)), code_set)
    return _INDUSTRY_CACHE


def fetch_hot_codes() -> list[str]:
    """emappdata.eastmoney.com 拿人气榜 Top 100 代码（带 SH/SZ/BJ 前缀）。"""
    payload = {
        "appId": "appId01",
        "globalId": "786e4c21-70dc-435a-93bb-38",
        "marketType": "",
        "pageNo": 1,
        "pageSize": 100,
    }
    r = requests.post(EMAPP_HOT_URL, json=payload, timeout=15)
    r.raise_for_status()
    data = r.json().get("data", [])
    return [str(item["sc"]) for item in data]


def fetch_spot_all() -> pd.DataFrame:
    """akshare 新浪源全 A 股实时行情（含 code6 / amount_wan / pct_chg 派生列）。"""
    import akshare as ak  # type: ignore[import-untyped]

    df = ak.stock_zh_a_spot()
    if df is None or df.empty:
        return df  # type: ignore[no-any-return]
    df = df.copy()
    df["code6"] = df["代码"].astype(str).str.extract(r"(\d{6})")
    df = df.copy()
    df["code6"] = df["代码"].astype(str).str.extract(r"(\d{6})")
    df["amount_wan"] = pd.to_numeric(df["成交额"], errors="coerce") / 10_000.0
    df["pct_chg"] = pd.to_numeric(df["涨跌幅"], errors="coerce")
    return df  # type: ignore[no-any-return]


def fetch_market_cap_via_tencent(codes: list[str]) -> dict[str, float]:
    """腾讯 qt.gtimg.cn 批量拿总市值（亿元），返回 {code6: total_cap_yi}。

    注：第 45 字段为总市值（亿元）。
    """
    if not codes:
        return {}
    tencent_codes = [
        f'{"sh" if c[0] in ("6", "9") else "sz"}{c}' for c in codes
    ]
    url = TENCENT_QUOTE_URL + ",".join(tencent_codes)
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    r.raise_for_status()
    cap_map: dict[str, float] = {}
    for line in r.text.split("\n"):
        if '="' not in line:
            continue
        prefix, body = line.split('="', 1)
        code_raw = prefix.strip().split("_")[-1].lower()
        code6 = code_raw[2:]  # 去掉 sh/sz/bj 前缀
        fields = body.rstrip('";').split("~")
        if len(fields) > 45:
            try:
                cap_map[code6] = float(fields[45])
            except ValueError:
                continue
    return cap_map


def fetch_industry_for_code(code6: str) -> str:
    """从本地 sw_industry_mapping.csv 查二级行业。"""
    industry_map, _ = _load_industry_csv()
    return industry_map.get(code6, "")


def is_in_csv(code6: str) -> bool:
    """判断 code6 是否在 sw_industry_mapping.csv 中（用于次新启发式）。"""
    _, code_set = _load_industry_csv()
    return code6 in code_set


def parse_spot_row(
    row: pd.Series,
    *,
    total_mv_yi: float,
    industry: str,
    is_listed: bool,
    today: date,
) -> Candidate | None:
    """行情行 → Candidate。

    参数：
        total_mv_yi：总市值（亿元），从腾讯接口注入
        industry：二级行业，从 CSV 注入
        is_listed：是否在 CSV 中（True=老票，False=次新）
    """
    try:
        code6 = str(row.get("code6") or "")
        if len(code6) != 6:
            return None
        name = str(row["名称"])
        market = _determine_market(code6)
        amount_wan = float(row.get("amount_wan", 0) or 0)
        pct_chg = float(row.get("pct_chg", 0) or 0)
        total_mv_wan = total_mv_yi * 10_000.0  # 亿 → 万元
        listing_date = (
            today - timedelta(days=LISTING_AGE_DAYS_FOR_KNOWN)
            if is_listed
            else today
        )
        return Candidate(
            code=code6,
            name=name,
            market=market,
            total_mv_wan=total_mv_wan,
            amount_wan=amount_wan,
            pct_chg=pct_chg,
            listing_date=listing_date,
            industry=industry,
        )
    except (KeyError, ValueError, TypeError) as exc:
        LOGGER.debug("parse_spot_row 跳过: %s (%s)", row.get("code6"), exc)
        return None


def fetch_real_listing_date(code: str) -> date | None:
    """新浪 stock_ipo_info 拿真实上市日期。失败返回 None（用启发式兜底）。"""
    import akshare as ak

    try:
        df = ak.stock_ipo_info(stock=code)
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("拉 %s 上市日期失败: %s", code, exc)
        return None
    if df is None or df.empty:
        return None
    for _, row in df.iterrows():
        item = str(row.iloc[0])
        if "上市日期" in item:
            try:
                return datetime.strptime(str(row.iloc[1])[:10], "%Y-%m-%d").date()  # noqa: DTZ007
            except ValueError:
                return None
    return None


def fetch_report_urls(code: str) -> list[str]:
    """巨潮资讯近 180 天定期报告链接列表（通常 1~2 份）。

    四类（年报/半年报/一季报/三季报）全查，窗口内正式公告全部收集，
    按披露日期倒序；排除摘要/更正/英文版等非正式公告。
    """
    import akshare as ak

    end = date.today()  # noqa: DTZ011
    start = end - timedelta(days=REPORT_WINDOW_DAYS)
    results: list[tuple[str, str, str]] = []  # (date, title, url)
    for category in ("年报", "半年报", "一季报", "三季报"):
        try:
            df = ak.stock_zh_a_disclosure_report_cninfo(
                symbol=code,
                market="沪深京",
                category=category,
                start_date=start.strftime("%Y%m%d"),
                end_date=end.strftime("%Y%m%d"),
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.debug("拉 %s %s 失败: %s", code, category, exc)
            continue
        if df is None or df.empty:
            continue
        formal = df[~df["公告标题"].astype(str).str.contains("摘要|更正|补充|英文", na=False)]
        for _, row in formal.iterrows():
            announce_time = str(row["公告时间"])[:10]
            # 用静态 PDF 直链替代 detail 页（SPA 需 JS 渲染，钉钉内置浏览器打不开）
            announcement_id = _extract_announcement_id(str(row["公告链接"]))
            pdf_url = (
                f"http://static.cninfo.com.cn/finalpage/{announce_time}/{announcement_id}.PDF"
                if announcement_id
                else str(row["公告链接"])
            )
            results.append((announce_time, str(row["公告标题"]), pdf_url))
    results.sort(key=lambda x: x[0], reverse=True)
    return [f"{d} {t} {u}" for d, t, u in results]


def fetch_latest_annual_report(code: str) -> tuple[str, str, str, str] | None:
    """近 ANNUAL_WINDOW_DAYS 天年报类正式公告取最新一份。

    返回 (披露日, 标题, PDF直链, 报告期)；查不到或解析失败返回 None。
    与 fetch_report_urls 的 180 天窗口相互独立：随机交易日大多在最新年报披露窗口之外。
    """
    import akshare as ak

    end = date.today()  # noqa: DTZ011
    start = end - timedelta(days=ANNUAL_WINDOW_DAYS)
    try:
        df = ak.stock_zh_a_disclosure_report_cninfo(
            symbol=code,
            market="沪深京",
            category="年报",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("年报公告拉取失败 %s: %s", code, exc)
        return None
    if df is None or df.empty:
        LOGGER.warning("行业学习：年报公告窗口内为空 %s", code)
        return None
    formal = df[~df["公告标题"].astype(str).str.contains("摘要|更正|补充|英文", na=False)]
    if formal.empty:
        LOGGER.warning("行业学习：年报公告窗口内无正式公告 %s", code)
        return None
    formal = formal.sort_values("公告时间", ascending=False)
    row = formal.iloc[0]
    announce_time = str(row["公告时间"])[:10]
    title = str(row["公告标题"])
    announcement_id = _extract_announcement_id(str(row["公告链接"]))
    pdf_url = (
        f"http://static.cninfo.com.cn/finalpage/{announce_time}/{announcement_id}.PDF"
        if announcement_id
        else str(row["公告链接"])
    )
    period_token = parse_report_period(title)
    if not period_token:
        LOGGER.error("行业学习：年报报告期解析失败 %s %r", code, title[:80])
        return None
    return announce_time, title, pdf_url, period_token


def _extract_announcement_id(detail_url: str) -> str:
    """从巨潮 detail URL 提取 announcementId 参数值。"""
    import urllib.parse

    try:
        query = urllib.parse.urlparse(detail_url).query
        params = urllib.parse.parse_qs(query)
        return str(params.get("announcementId", [""])[0])
    except ValueError:
        return ""


def fetch_next_report(code: str, today: date) -> str:
    """东财 datacenter 预约披露：返回下期定期报告描述，无则空串。

    只取预约日 ≥ today 的最新报告期一条（预约日已过的不展示）。
    """
    params = {
        "sortColumns": "REPORT_DATE",
        "sortTypes": "-1",
        "pageSize": "10",
        "pageNumber": "1",
        "reportName": "RPT_PUBLIC_BS_APPOIN",
        "columns": "ALL",
        "filter": f'(SECURITY_CODE="{code}")',
    }
    try:
        r = requests.get(EM_APPOINT_URL, params=params, timeout=15)
        r.raise_for_status()
        rows = (r.json().get("result") or {}).get("data") or []
    except Exception as exc:  # noqa: BLE001
        LOGGER.debug("拉 %s 预约披露失败: %s", code, exc)
        return ""
    for row in rows:
        raw = str(row.get("APPOINT_PUBLISH_DATE") or row.get("FIRST_APPOINT_DATE") or "")[:10]
        if not raw:
            continue
        try:
            appoint_date = date.fromisoformat(raw)
        except ValueError:
            continue
        if appoint_date >= today:
            type_name = str(row.get("REPORT_TYPE_NAME") or "").strip()
            return f"{type_name}（预约 {raw} 披露）"
    return ""


# ======================
# Hermes 财报分析链路
# ======================


def parse_report_period(title: str, fallback: str = "") -> str:
    """从公告标题解析报告期代号：2026h1 / 2025fy / 2026q1 / 2025q3。

    季度支持省略“第”、阿拉伯数字及标题内空白；解析失败返回 fallback。
    F10 分析入口不传 fallback，避免把公告日期作为报告期。
    """
    match = re.search(r"(\d{4})\s*年(.+?)报告", title)
    if not match:
        return fallback
    year, kind = match.group(1), re.sub(r"\s+", "", match.group(2))
    if "半年度" in kind:
        return f"{year}h1"
    if re.match(r"第?[一1]季度", kind):
        return f"{year}q1"
    if re.match(r"第?[三3]季度", kind):
        return f"{year}q3"
    if "年度" in kind:
        return f"{year}fy"
    return fallback


def _today_report_entry(history: History, today: date) -> str:
    """当日推荐记录的最新财报条目（"YYYY-MM-DD 标题 URL"），无则空串。"""
    if history.records and history.records[-1].date == today.isoformat():
        return history.records[-1].latest_report_url
    return ""


# ======================
# 编排
# ======================


def build_candidates(
    hot_codes: list[str],
    cfg: PickConfig,
    today: date,
) -> list[Candidate]:
    """人气榜代码 → 过滤后候选池。"""
    if not hot_codes:
        return []

    target_codes = {code[2:] for code in hot_codes if len(code) >= 8}
    spot = fetch_spot_all()
    if spot is None or spot.empty:
        return []
    if "code6" not in spot.columns:
        return []
    spot_filtered = spot[spot["code6"].isin(target_codes)]
    if spot_filtered.empty:
        return []

    cap_map = fetch_market_cap_via_tencent(
        [str(c) for c in spot_filtered["code6"].tolist()]
    )
    raw: list[Candidate] = []
    for _, row in spot_filtered.iterrows():
        code6 = str(row["code6"])
        cand = parse_spot_row(
            row,
            total_mv_yi=cap_map.get(code6, 0.0),
            industry=fetch_industry_for_code(code6),
            is_listed=is_in_csv(code6),
            today=today,
        )
        if cand is not None:
            raw.append(cand)
    return filter_candidates(raw, cfg, today)


def run_pipeline(
    today: date,
    cfg: PickConfig,
    history: History,
    rng: random.Random,
    *,
    hot_codes: list[str] | None = None,
    spot_df: pd.DataFrame | None = None,
    cap_map: dict[str, float] | None = None,
    report_urls: list[str] | None = None,
    real_listing_date: date | None = None,
    next_report: str | None = None,
) -> tuple[Candidate | None, str, History]:
    """主流程：候选池 → 轮换 → 渲染 → 持久化。

    hot_codes / spot_df / cap_map 为可选注入点，单元测试可绕过真实网络。
    """
    freq = history.industry_freq(today, cfg.industry_rotation_window_days)

    try:
        if hot_codes is None:
            hot_codes = fetch_hot_codes()
        if spot_df is None and hot_codes:
            spot_df = fetch_spot_all()
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("拉取数据失败: %s", exc)
        return None, build_markdown(None, today, freq, cfg=cfg), history

    candidates: list[Candidate] = []
    if spot_df is not None and not spot_df.empty and "code6" in spot_df.columns:
        target_codes = {code[2:] for code in (hot_codes or []) if len(code) >= 8}
        spot_filtered = spot_df[spot_df["code6"].isin(target_codes)]
        if not spot_filtered.empty:
            if cap_map is None:
                cap_map = fetch_market_cap_via_tencent(
                    [str(c) for c in spot_filtered["code6"].tolist()]
                )
            for _, row in spot_filtered.iterrows():
                code6 = str(row["code6"])
                cand = parse_spot_row(
                    row,
                    total_mv_yi=cap_map.get(code6, 0.0),
                    industry=fetch_industry_for_code(code6),
                    is_listed=is_in_csv(code6),
                    today=today,
                )
                if cand is not None:
                    candidates.append(cand)
    candidates = filter_candidates(candidates, cfg, today)

    pick = rotate_pick(candidates, history, today, cfg, rng)
    if pick is None:
        return None, build_markdown(None, today, freq, cfg=cfg), history

    # 选中后拉真实上市日期（1 次请求）；失败保持启发式日期
    real_date = (
        real_listing_date if real_listing_date is not None else fetch_real_listing_date(pick.code)
    )
    if real_date is not None:
        pick = Candidate(
            code=pick.code,
            name=pick.name,
            market=pick.market,
            total_mv_wan=pick.total_mv_wan,
            amount_wan=pick.amount_wan,
            pct_chg=pick.pct_chg,
            listing_date=real_date,
            industry=pick.industry,
        )

    if report_urls is None:
        report_urls = fetch_report_urls(pick.code)
    if next_report is None:
        next_report = fetch_next_report(pick.code, today)
    # 展示频次把本次推荐的行业也算进去（选股用的 freq 不含本次，勿复用）
    freq_with_pick = {**freq, pick.industry: freq.get(pick.industry, 0) + 1} if pick.industry else freq
    md = build_markdown(pick, today, freq_with_pick, report_urls, cfg, next_report)
    new_record = PickRecord(
        date=today.isoformat(),
        code=pick.code,
        name=pick.name,
        industry=pick.industry,
        latest_report_url=report_urls[0] if report_urls else "",
    )
    return pick, md, history.append(new_record)


def main() -> int:
    push_mode = os.environ.get("PUSH_MODE", "0")
    is_dry_run = push_mode != "1"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    print(
        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始每日财报阅读..."  # noqa: DTZ005
    )
    print(f"推送模式: {'测试模式（仅打印）' if is_dry_run else '正式推送'}")

    cfg = PickConfig()
    history = History.load(HISTORY_PATH)
    rng = random.SystemRandom()
    today = date.today()  # noqa: DTZ011

    # 当日已推送守卫（skill 化后手动触发频率上升，防同日重复推送）：
    # DAILY_PICK_ONCE_DAILY=1 且历史里今日已有推送记录 → 跳过推送，
    # 仅输出当日已推标的信息；dry-run 测试模式不拦。
    if (
        os.environ.get("DAILY_PICK_ONCE_DAILY") == "1"
        and _today_report_entry(history, today)
    ):
        _prev = history.records[-1]
        print(
            f"  - 今日已推送 {_prev.name}（{_prev.code}），"
            "DAILY_PICK_ONCE_DAILY=1 生效，跳过本次推送（不重复推送）"
        )
        return 0

    pick, content, new_history = run_pipeline(today, cfg, history, rng)

    if is_dry_run:
        print("  - [测试模式] 消息内容:")
        print(content)
        return 0

    print("  - 推送钉钉中...")
    try:
        webhook = os.environ.get("DAILY_PICK_WEBHOOK")
        pusher = DingTalkPusher(webhook=webhook, keyword="财报")
        # 机器人关键词为「财报」，标题必须包含
        title = (
            f"【财报阅读】{pick.name}（{pick.code}）"
            if pick is not None
            else "【财报阅读】今日无可推荐"
        )
        ok = pusher.push_markdown(title=title, content=content)
        print(f"  - {'推送成功' if ok else '推送失败'}")
        if ok and pick is not None:
            # 深度分析由 daily-pick-brief skill 编排：agent 读历史 JSON 后
            # 直接执行 financial-statement-analysis / annual-report-industry-learning，
            # 脚本只负责选股与主推送，不再经 hermes_client 提交 Runs API。
            new_history.save(HISTORY_PATH)
        return 0 if ok else 1
    except Exception as exc:  # noqa: BLE001
        print(f"钉钉推送异常: {exc}")
        return 1


if __name__ == "__main__":
    # 辅助入口：daily_pick.py --latest-annual <code>
    # 输出最新年报公告「披露日 标题 PDF直链 报告期」（skill 编排用，一行四段）
    if len(sys.argv) > 1 and sys.argv[1] == "--latest-annual":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        _annual = fetch_latest_annual_report(sys.argv[2])
        if _annual is None:
            print("NO_ANNUAL_REPORT")
            sys.exit(1)
        print(" ".join(_annual))
        sys.exit(0)
    sys.exit(main())