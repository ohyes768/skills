#!/usr/bin/env python3
"""
北向资金数据爬虫 - exchange-rate-skill
从东方财富获取北向资金7日/30日累计及日频明细数据

数据来源:
- RPT_MUTUAL_NETINFLOW_STATISTICS: 7日/30日/历史累计
- RPT_MUTUAL_NETINFLOW_DETAILS: 日频明细

Usage:
    uv run python scripts/fetch_north_flow.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_common import build_session, get_logger, setup_logging, to_iso_now

logger = get_logger(__name__)

EM_API_BASE = "https://datacenter-web.eastmoney.com/securities/api/data/v1/get"
EM_REFERER = "https://data.eastmoney.com/hsgt/hsgtV2.html"


def fetch_north_cumulative(session: requests.Session) -> dict[str, Any]:
    """获取北向资金当日/7日/30日/历史累计成交总额

    Returns:
        {
            "date": "2026-05-12",
            "cum_today_yi": 61870.16,    # 当日成交总额（万元）
            "cum_7d_yi": 373179.80,      # 7日累计成交总额（万元）
            "cum_30d_yi": 1070403.06,    # 30日累计成交总额（万元）
            "cum_history_yi": 5380787.51,  # 历史累计成交总额（万元）
            "fetched_at": "2026-05-12T...",
        }
    """
    params = {
        "reportName": "RPT_MUTUAL_NETINFLOW_STATISTICS",
        "columns": (
            "DIRECTION_TYPE,TOTAL_INFLOW_SH,TOTAL_INFLOW_SZ,"
            "TOTAL_INFLOW_BOTH,TIME_TYPE,HISTORY_TOTAL_INFLOW"
        ),
        "filter": '(DIRECTION_TYPE,=,"2")',
        "client": "WEB",
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "Referer": EM_REFERER,
        "Accept": "application/json",
    }

    try:
        resp = session.get(EM_API_BASE, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"请求失败: {e}")
        return {}

    if not data.get("success"):
        logger.error(f"API返回失败: {data.get('message', 'unknown')}")
        return {}

    records = data.get("result", {}).get("data", [])
    if not records:
        logger.error("未找到北向资金累计数据")
        return {}

    result = {
        "fetched_at": to_iso_now(),
        "cum_today_yi": None,
        "cum_7d_yi": None,
        "cum_30d_yi": None,
        "cum_history_yi": None,
    }

    for rec in records:
        tt = str(rec.get("TIME_TYPE", ""))
        if tt == "1":
            result["cum_today_yi"] = rec.get("TOTAL_INFLOW_BOTH")
        elif tt == "2":
            result["cum_7d_yi"] = rec.get("TOTAL_INFLOW_BOTH")
        elif tt == "3":
            result["cum_30d_yi"] = rec.get("TOTAL_INFLOW_BOTH")
        elif tt == "4":
            result["cum_history_yi"] = rec.get("HISTORY_TOTAL_INFLOW")

    logger.info(
        "北向资金累计数据: 7日=%.2f亿, 30日=%.2f亿, 历史=%.2f亿",
        (result.get("cum_7d_yi") or 0) / 10000,
        (result.get("cum_30d_yi") or 0) / 10000,
        (result.get("cum_history_yi") or 0) / 10000,
    )

    return result


def fetch_north_daily(session: requests.Session, days: int = 30) -> pd.DataFrame:
    """获取北向资金近N日日频明细

    Args:
        session: HTTP会话
        days: 回溯天数

    Returns:
        DataFrame, columns: date(index), 北向净流入, 北向涨幅
        单位: 亿元
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "Referer": EM_REFERER,
        "Accept": "application/json",
    }

    all_records: list[dict] = []
    page = 1

    while len([r for r in all_records if r["TIME_TYPE"] == "1"]) < days:
        params = {
            "reportName": "RPT_MUTUAL_NETINFLOW_DETAILS",
            "columns": (
                "DIRECTION_TYPE,TRADE_DATE,NET_INFLOW_SH,"
                "NET_INFLOW_SZ,NET_INFLOW_BOTH,TIME_TYPE"
            ),
            "filter": '(DIRECTION_TYPE,=,"2")',
            "pageSize": "100",
            "pageNumber": str(page),
            "sortTypes": "-1",
            "sortColumns": "TRADE_DATE",
            "client": "WEB",
        }

        try:
            resp = session.get(EM_API_BASE, params=params, headers=headers, timeout=20)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            logger.error(f"请求失败: {e}")
            return pd.DataFrame()

        if not data.get("success"):
            logger.error(f"API返回失败: {data.get('message', 'unknown')}")
            return pd.DataFrame()

        records = data.get("result", {}).get("data", [])
        if not records:
            break

        all_records.extend(records)
        page += 1

        # 安全限制：最多拉10页
        if page > 10:
            break

    # 筛选 TIME_TYPE=1（当日），并按日期去重（只保留最新days个）
    daily_records = []
    seen_dates = set()
    for rec in all_records:
        if str(rec.get("TIME_TYPE")) != "1":
            continue
        trade_date = rec.get("TRADE_DATE", "")
        if not trade_date or trade_date in seen_dates:
            continue
        seen_dates.add(trade_date)

        # 单位从万元转为亿元
        net_sh = (rec.get("NET_INFLOW_SH") or 0) / 10000
        net_sz = (rec.get("NET_INFLOW_SZ") or 0) / 10000
        net_both = (rec.get("NET_INFLOW_BOTH") or 0) / 10000

        daily_records.append({
            "date": pd.to_datetime(trade_date).date(),
            "沪股通净流入": net_sh,
            "深股通净流入": net_sz,
            "北向净流入": net_both,
        })

    if not daily_records:
        return pd.DataFrame()

    df = pd.DataFrame(daily_records)
    df = df.set_index("date").sort_index()
    df.index = pd.to_datetime(df.index)

    # 计算日环比涨幅
    df["北向涨幅"] = df["北向净流入"].pct_change() * 100

    logger.info("获取到 %d 条北向资金日频数据", len(df))
    return df


def fetch_north_deal_amt(session: requests.Session, days: int = 30) -> pd.DataFrame:
    """获取北向资金近N日成交总额（日频）

    数据来源: RPT_MUTUAL_DEALAMT 接口的 NF_DEAL_AMT 字段
    - NF_DEAL_AMT = 沪股通成交额 + 深股通成交额（北向合计）
    - 单位: 万元

    Args:
        session: HTTP会话
        days: 回溯天数

    Returns:
        DataFrame, columns: date(index), 北向成交总额, 沪股通成交额, 深股通成交额
        单位: 亿元
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "Referer": "https://data.eastmoney.com/hsgtV2/hsgtDetail/scgk.html",
        "Accept": "application/json",
    }

    params = {
        "reportName": "RPT_MUTUAL_DEALAMT",
        "columns": "TRADE_DATE,NF_DEAL_AMT,SSC_DEAL_AMT,ST_DEAL_AMT",
        "pageSize": str(days),
        "pageNumber": "1",
        "sortTypes": "-1",
        "sortColumns": "TRADE_DATE",
        "client": "WEB",
    }

    try:
        resp = session.get(EM_API_BASE, params=params, headers=headers, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"请求失败: {e}")
        return pd.DataFrame()

    if not data.get("success"):
        logger.error(f"API返回失败: {data.get('message', 'unknown')}")
        return pd.DataFrame()

    records = data.get("result", {}).get("data", [])
    if not records:
        logger.error("未找到北向资金成交总额数据")
        return pd.DataFrame()

    daily_records = []
    for rec in records:
        trade_date = rec.get("TRADE_DATE", "")
        if not trade_date:
            continue

        # 单位从万元转为亿元
        nf_deal = (rec.get("NF_DEAL_AMT") or 0) / 10000
        ssc_deal = (rec.get("SSC_DEAL_AMT") or 0) / 10000
        st_deal = (rec.get("ST_DEAL_AMT") or 0) / 10000

        daily_records.append({
            "date": pd.to_datetime(trade_date).date(),
            "北向成交总额": nf_deal,
            "沪股通成交额": ssc_deal,
            "深股通成交额": st_deal,
        })

    if not daily_records:
        return pd.DataFrame()

    df = pd.DataFrame(daily_records)
    df = df.set_index("date").sort_index()
    df.index = pd.to_datetime(df.index)

    logger.info("获取到 %d 条北向资金成交总额数据", len(df))
    return df


def save_north_flow_to_csv(
    north_df: pd.DataFrame,
    csv_path: Path | None = None,
) -> Path:
    """保存北向资金数据到 CSV

    Args:
        north_df: 北向资金 DataFrame（支持净流入或成交总额格式）
        csv_path: CSV 文件路径

    Returns:
        CSV 文件路径
    """
    if csv_path is None:
        csv_path = Path(__file__).resolve().parent.parent / "fund_flow.csv"

    if north_df.empty:
        logger.warning("没有数据可保存")
        return csv_path

    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # 读取已有数据（保留南向等历史数据）
    existing_df = pd.DataFrame()
    try:
        existing_df = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        existing_df.index = pd.to_datetime(existing_df.index)
        logger.info(f"读取已有历史数据: {len(existing_df)} 行")
    except FileNotFoundError:
        logger.info("CSV文件不存在，将创建新文件")
    except Exception as e:
        logger.warning(f"读取已有CSV失败，将创建新文件: {e}")

    # 构建新数据
    new_df = pd.DataFrame(north_df, index=north_df.index)

    # 合并：已有数据 + 新数据，同日覆盖
    if not existing_df.empty:
        combined = existing_df.copy()
        for col in new_df.columns:
            combined[col] = new_df[col]
        fund_flow_df = combined.sort_index()
    else:
        fund_flow_df = new_df

    # 保存
    fund_flow_df.to_csv(csv_path)
    logger.info(f"北向资金数据已保存到 {csv_path}，共 {len(fund_flow_df)} 条记录")

    return csv_path


def _build_session() -> requests.Session:
    """构建 HTTP 会话（本地版本，不依赖 fetch_common 的 bug）"""
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
    })
    adapter = requests.adapters.HTTPAdapter(max_retries=3)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def main() -> None:
    """主入口"""
    setup_logging(verbose=True)
    logger.info("=" * 50)
    logger.info("开始获取北向资金数据")
    logger.info("=" * 50)

    session = _build_session()

    # 获取累计数据
    cum_data = fetch_north_cumulative(session)
    if not cum_data:
        logger.error("获取累计数据失败")
        sys.exit(1)

    # 获取日频数据
    daily_df = fetch_north_daily(session, days=30)
    if daily_df.empty:
        logger.error("获取日频数据失败")
        sys.exit(1)

    # 保存到 CSV
    csv_path = save_north_flow_to_csv(daily_df)

    # 设置最新日期
    latest_date = daily_df.index.max().strftime("%Y-%m-%d") if not daily_df.empty else "N/A"
    cum_data["date"] = latest_date

    # 输出结果
    latest_date = daily_df.index.max().strftime("%Y-%m-%d") if not daily_df.empty else "N/A"
    print()
    print("=" * 50)
    print("北向资金数据获取成功")
    print("=" * 50)
    print(f"  日期: {latest_date}")
    print(
        f"  7日累计: {((cum_data.get('cum_7d_yi') or 0) / 10000):.2f} 亿元"
    )
    print(
        f"  30日累计: {((cum_data.get('cum_30d_yi') or 0) / 10000):.2f} 亿元"
    )
    print(
        f"  历史累计: {((cum_data.get('cum_history_yi') or 0) / 10000):.2f} 亿元"
    )
    print(f"  日频明细: {len(daily_df)} 条已保存到 {csv_path}")
    print()

    # 显示最近5日数据
    print("最近5日北向资金明细:")
    print(daily_df.tail(5).to_string())


if __name__ == "__main__":
    main()
