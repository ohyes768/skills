#!/usr/bin/env python3
"""
抓取两市成交额和换手率数据

优先使用沪深交易所官方API（真实汇总数据）：
  - 上交所: https://www.sse.com.cn/market/stockdata/overview/day/
  - 深交所: https://www.szse.cn/market/overview/index.html

Fallback 使用 akshare（指数成交额估算，有10-20%误差）

换手率：使用上证指数换手率作为全市场参考
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

# 确保本地 scripts 目录可导入
_SCRIPT_DIR = Path(__file__).resolve().parent
for _p in [str(_SCRIPT_DIR)]:
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(_SCRIPT_DIR))

import pandas as pd

from fetch_common import (
    LOGGER,
    read_cache,
    setup_logging,
    to_float,
    to_iso_now,
    write_cache,
)


def _create_session_with_retry() -> requests.Session:
    """创建带重试机制的requests会话"""
    session = requests.Session()
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504], connect=3)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    return session


def fetch_turnover_rate_em(trade_date: str | None = None) -> dict[str, Any]:
    """
    通过东方财富API获取上证指数换手率（带重试机制）

    返回:
        {
            "date": "2026-05-12",
            "turnover_rate": 1.49,
            "volume": 718984002,
            "amount": 1465272590579.10,
            "amount_yi": 14652.73,
            "change_pct": 0.73,
            "source": "eastmoney",
            "fetched_at": "ISO时间"
        }
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y-%m-%d")

    result: dict[str, Any] = {
        "date": None,
        "turnover_rate": None,
        "volume": None,
        "amount": None,
        "amount_yi": None,
        "change_pct": None,
        "source": "eastmoney",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    try:
        session = _create_session_with_retry()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }

        url = 'https://push2his.eastmoney.com/api/qt/stock/kline/get'
        params = {
            'secid': '1.000001',  # 上证指数
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt': '101',  # 日K
            'fqt': '1',    # 前复权
            'beg': trade_date.replace('-', ''),
            'end': trade_date.replace('-', ''),
        }

        resp = session.get(url, params=params, headers=headers, timeout=20)
        data = resp.json()

        if not data.get('data') or not data['data'].get('klines'):
            LOGGER.warning("东方财富换手率API返回空数据")
            return result

        klines = data['data']['klines']
        if not klines:
            return result

        # 取最后一条K线
        latest = klines[-1]
        parts = latest.split(',')
        # 格式: 日期,开盘,收盘,最高,最低,成交量,成交额,涨跌幅,涨跌额,振幅,换手率
        result.update({
            "date": parts[0],
            "turnover_rate": round(float(parts[-1]), 2),
            "volume": int(float(parts[5])),
            "amount": float(parts[6]),
            "amount_yi": round(float(parts[6]) / 1e8, 2),
            "change_pct": round(float(parts[7]), 2),
            "status": "ok",
        })
        LOGGER.info("换手率获取成功(东方财富): %s 换手率=%s%%, 成交额=%.2f亿",
                    parts[0], parts[-1], result["amount_yi"] or 0)

    except Exception as exc:
        LOGGER.warning("东方财富换手率API失败: %s", exc)
        result["error"] = str(exc)

    return result


# stock_zh_a_hist 返回的列名
HIST_COLUMNS = [
    "日期", "股票代码", "开盘", "收盘", "最高", "最低",
    "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"
]


def _detect_hist_columns(columns: list[str]) -> dict[str, str]:
    """检测历史行情数据的列名映射"""
    col_map: dict[str, str] = {}
    for col in columns:
        col_lower = col.lower()
        if "日期" in col or "date" in col_lower:
            col_map["date"] = col
        elif "成交额" in col or "amount" in col_lower:
            col_map["amount"] = col
        elif "成交量" in col or "volume" in col_lower:
            col_map["volume"] = col
        elif "换手率" in col or "turnover" in col_lower:
            col_map["turnover"] = col
        elif "涨跌幅" in col or "change" in col_lower:
            col_map["change_pct"] = col
    return col_map


def fetch_turnover_rate(symbol: str = "000001", days: int = 5) -> dict[str, Any]:
    """
    获取换手率数据

    优先使用上交所官方API（加权平均换手率）
    Fallback 使用东方财富API（指数换手率）

    注意：所有数据源统一使用上一交易日（盘中时），
          以保持与成交额数据的一致性
    """
    from fetch_volume_exchange import get_trade_date
    trade_date = get_trade_date()

    # 尝试读取缓存（按交易日缓存）
    cached = read_cache("turnover", trade_date)
    if cached:
        LOGGER.info("使用缓存: turnover/%s", trade_date)
        return cached

    result: dict[str, Any] = {
        "date": None,
        "turnover_rate": None,
        "volume": None,
        "amount": None,
        "amount_yi": None,
        "change_pct": None,
        "source": "akshare",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    # 优先尝试上交所官方API
    try:
        from fetch_volume_exchange import fetch_sse_turnover
        sse_data = fetch_sse_turnover(trade_date)
        if sse_data.get("status") == "ok":
            result.update({
                "date": sse_data.get("date"),
                "turnover_rate": sse_data.get("turnover_rate"),
                "source": "exchange_official",
                "status": "ok",
            })
            write_cache("turnover", trade_date, result)
            LOGGER.info("换手率获取成功(官方API): %.4f%%", result["turnover_rate"])
            return result
    except Exception as exc:
        LOGGER.warning("上交所换手率API失败，切换到东方财富fallback: %s", exc)

    # Fallback: 使用东方财富API获取换手率
    try:
        em_data = fetch_turnover_rate_em(trade_date)
        if em_data.get("status") == "ok":
            result.update({
                "date": em_data.get("date"),
                "turnover_rate": em_data.get("turnover_rate"),
                "volume": em_data.get("volume"),
                "amount": em_data.get("amount"),
                "amount_yi": em_data.get("amount_yi"),
                "change_pct": em_data.get("change_pct"),
                "source": "eastmoney",
                "status": "ok",
            })
            write_cache("turnover", result["date"], result)
            LOGGER.info("换手率获取成功(东方财富): %s 换手率=%s%%",
                        result["date"], result["turnover_rate"])
            return result
    except Exception as exc:
        LOGGER.warning("东方财富换手率API失败: %s", exc)
        result["error"] = str(exc)

    return result


def fetch_market_volume(days: int = 5) -> dict[str, Any]:
    """
    获取沪深两市合计成交额

    优先使用沪深交易所官方API（真实汇总数据）
    Fallback 使用 akshare（指数成交额估算）
    返回两市合计成交额（亿元）
    """
    result: dict[str, Any] = {
        "date": None,
        "sh_amount_yi": None,
        "sz_amount_yi": None,
        "total_amount_yi": None,
        "source": "akshare",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    # 优先尝试交易所官方API
    try:
        from fetch_volume_exchange import fetch_both_exchanges
        exchange_data = fetch_both_exchanges()
        if exchange_data.get("status") in ("ok", "partial"):
            result.update({
                "date": exchange_data.get("date"),
                "sh_amount_yi": exchange_data.get("sh_amount_yi"),
                "sz_amount_yi": exchange_data.get("sz_amount_yi"),
                "total_amount_yi": exchange_data.get("total_amount_yi"),
                "source": "exchange_official",
                "status": "ok",
            })
            LOGGER.info("两市成交额获取成功(官方API): 沪市=%.2f亿, 深市=%.2f亿, 合计=%.2f亿",
                        result["sh_amount_yi"] or 0, result["sz_amount_yi"] or 0, result["total_amount_yi"] or 0)
            return result
    except Exception as exc:
        LOGGER.warning("交易所官方API失败，切换到akshare fallback: %s", exc)

    # Fallback: 使用akshare指数成交额估算
    try:
        end_date = datetime.now().strftime("%Y%m%d")
        start_date = (datetime.now() - timedelta(days=days + 10)).strftime("%Y%m%d")

        # 上证指数 (000001) -> 沪市
        df_sh = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date=start_date, end_date=end_date)
        # 深证成指 (399001) -> 深市
        df_sz = ak.stock_zh_a_hist(symbol="399001", period="daily", start_date=start_date, end_date=end_date)

        if df_sh.empty or df_sz.empty:
            LOGGER.warning("市场成交额数据为空")
            return result

        df_sh.columns = [c.strip() for c in df_sh.columns]
        df_sz.columns = [c.strip() for c in df_sz.columns]

        # 检测列名
        col_map_sh = _detect_hist_columns(df_sh.columns.tolist())
        col_map_sz = _detect_hist_columns(df_sz.columns.tolist())

        latest_sh = df_sh.iloc[0]
        latest_sz = df_sz.iloc[0]

        # 提取成交额
        sh_amount = to_float(latest_sh[col_map_sh.get("amount", df_sh.columns[7])])
        sz_amount = to_float(latest_sz[col_map_sz.get("amount", df_sz.columns[7])])

        if sh_amount and sz_amount:
            total = sh_amount + sz_amount
        elif sh_amount:
            total = sh_amount * 2  # 粗略估算
        elif sz_amount:
            total = sz_amount * 2
        else:
            total = None

        result.update({
            "date": str(latest_sh[col_map_sh.get("date", df_sh.columns[0])])[:10],
            "sh_amount_yi": round(sh_amount / 1e8, 2) if sh_amount else None,
            "sz_amount_yi": round(sz_amount / 1e8, 2) if sz_amount else None,
            "total_amount_yi": round(total / 1e8, 2) if total else None,
            "source": "akshare",
            "status": "ok",
        })

        LOGGER.info("两市成交额获取成功(akshare): 沪市=%.2f亿, 深市=%.2f亿, 合计=%.2f亿",
                    result["sh_amount_yi"] or 0, result["sz_amount_yi"] or 0, result["total_amount_yi"] or 0)

    except Exception as exc:
        LOGGER.warning("akshare成交额获取也失败了: %s", exc)
        result["error"] = str(exc)

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取两市成交额和换手率")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    parser.add_argument("--days", type=int, default=5, help="历史数据天数")
    args = parser.parse_args()

    setup_logging()

    volume_data = fetch_market_volume(args.days)
    turnover_data = fetch_turnover_rate(days=args.days)
    data = {
        "volume": volume_data,
        "turnover": turnover_data,
    }

    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()
