"""从 SPDR 官方历史文件读取 GLD 实物持仓（吨）。"""
from io import BytesIO
import logging
import math

import pandas as pd
import requests

LOGGER = logging.getLogger(__name__)
ARCHIVE_URL = "https://api.spdrgoldshares.com/api/v1/historical-archive?product=gld&exchange=NYSE&lang=en"


def parse_gld_archive(content: bytes, days: int = 20) -> list:
    """显式选择GLD数据表与吨数字段，禁止用总资产推算实物持仓。"""
    if days <= 0:
        raise ValueError("days必须为正数")
    frame = pd.read_excel(BytesIO(content), sheet_name="US GLD Historical Archive")
    if not {"Date", "Tonnes of Gold"}.issubset(frame.columns):
        raise ValueError("官方GLD文件缺少日期或吨数字段")
    records = {}
    for raw_date, raw_tonnes in frame[["Date", "Tonnes of Gold"]].itertuples(index=False, name=None):
        try:
            observed = pd.to_datetime(raw_date, errors="coerce")
            tonnes = float(str(raw_tonnes).replace(",", ""))
            if pd.isna(observed) or not math.isfinite(tonnes) or tonnes <= 0:
                continue
            day = observed.strftime("%Y-%m-%d")
            records[day] = {"Date": day, "gold_tonnes": round(tonnes, 2)}
        except (ValueError, TypeError):
            continue
    if not records:
        raise ValueError("官方GLD文件没有有效持仓")
    return sorted(records.values(), key=lambda r: r["Date"], reverse=True)[:days]


def get_gld_holdings_history(days: int = 20) -> list:
    try:
        response = requests.get(ARCHIVE_URL, timeout=(5, 20))
        response.raise_for_status()
        return parse_gld_archive(response.content, days)
    except Exception as exc:
        # 此项为可选因子；文件格式改变、下载失败都不能恢复旧的错误估算。
        LOGGER.warning("官方GLD持仓暂缺（%s）", type(exc).__name__)
        return []
