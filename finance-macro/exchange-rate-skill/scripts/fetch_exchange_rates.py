#!/usr/bin/env python3
"""
汇率数据获取脚本 - exchange-rate-skill
数据源:
- 美元指数: FRED (DTWEXBGS) - 名义广义美元指数，2006年1月=100
- 美元兑人民币: FRED (DEXCHUS)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from fredapi import Fred

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_common import (
    get_logger,
    load_env_file,
    setup_logging,
    today_str,
)

logger = get_logger(__name__)

# 数据源配置
FRED_DOLLAR_INDEX_CODE = "DTWEXBGS"  # FRED 美元指数（广义贸易加权，2006年1月=100）
FRED_USD_CNY_CODE = "DEXCHUS"  # FRED 美元兑人民币

# CSV 文件列名映射
COLUMN_MAPPING = {
    "dollar_index": "美元指数",
    "usd_cny": "美元人民币",
}


def get_fred_service() -> Fred:
    """获取 FRED 服务实例"""
    load_env_file()
    fred_api_key = os.environ.get("FRED_API_KEY")
    if not fred_api_key:
        raise ValueError(
            "FRED_API_KEY 未设置。请选择以下方式之一：\n"
            "  1. 设置环境变量: export FRED_API_KEY=your_key\n"
            "  2. 在项目根目录创建 .env 文件，内容: FRED_API_KEY=your_key\n"
            "  3. 从 https://fred.stlouisfed.org/docs/api/api_key.html 申请 API Key"
        )
    return Fred(api_key=fred_api_key)


def fetch_dollar_index_from_fred(fred: Fred, start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.Series:
    """从 FRED 获取 DTWEXBGS 美元指数

    Args:
        fred: FRED 服务实例
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        pd.Series，index 为日期，value 为指数值
    """
    try:
        logger.info(f"获取 dollar_index ({FRED_DOLLAR_INDEX_CODE})...")
        series = fred.get_series(
            FRED_DOLLAR_INDEX_CODE,
            observation_start=start_date,
            observation_end=end_date,
        )
        if series is not None and not series.empty:
            series.name = "dollar_index"
            logger.info(f"成功获取 dollar_index，共 {len(series)} 条记录")
            return series
        else:
            logger.warning("dollar_index 数据为空")
            return pd.Series(dtype="float64")
    except Exception as e:
        logger.error(f"获取 dollar_index 失败: {e}")
        return pd.Series(dtype="float64")


def fetch_exchange_rates(
    start_date: str | None = None,
    end_date: str | None = None,
    days: int = 30,
) -> dict[str, pd.Series]:
    """获取汇率数据（美元指数 + 美元兑人民币）

    Args:
        start_date: 起始日期 (YYYY-MM-DD)，默认取最近 days 天
        end_date: 结束日期 (YYYY-MM-DD)，默认今天
        days: 如果没有指定 start_date，则取最近多少天的数据

    Returns:
        包含美元指数和美元兑人民币的字典
    """
    load_env_file()

    # 默认日期范围
    if end_date is None:
        end_date = pd.Timestamp.now().normalize()
    else:
        end_date = pd.Timestamp(end_date)

    if start_date is None:
        start_date = end_date - pd.Timedelta(days=days)
    else:
        start_date = pd.Timestamp(start_date)

    logger.info(f"获取汇率数据: {start_date.date()} 至 {end_date.date()}")

    result = {}

    # 获取 FRED 服务（美元指数和美元兑人民币都从 FRED 获取）
    fred_api_key = os.environ.get("FRED_API_KEY")
    if not fred_api_key:
        logger.warning("未设置 FRED_API_KEY，无法获取汇率数据")
    else:
        fred = Fred(api_key=fred_api_key)

        # 1. 美元指数 - FRED DTWEXBGS
        dollar_index_series = fetch_dollar_index_from_fred(fred, start_date, end_date)
        if not dollar_index_series.empty:
            result["dollar_index"] = dollar_index_series

        # 2. 美元兑人民币 - FRED DEXCHUS
        try:
            logger.info(f"获取 usd_cny ({FRED_USD_CNY_CODE})...")
            series = fred.get_series(
                FRED_USD_CNY_CODE,
                observation_start=start_date,
                observation_end=end_date,
            )
            if series is not None and not series.empty:
                result["usd_cny"] = series
                logger.info(f"成功获取 usd_cny，共 {len(series)} 条记录")
            else:
                logger.warning("usd_cny 数据为空")
        except Exception as e:
            logger.error(f"获取 usd_cny 失败: {e}")

    return result


def save_exchange_rates_to_csv(data: dict[str, pd.Series], csv_path: Path | None = None) -> Path:
    """保存汇率数据到 CSV

    Args:
        data: 汇率数据字典
        csv_path: CSV 文件路径，默认保存到项目根目录

    Returns:
        CSV 文件路径
    """
    if csv_path is None:
        csv_path = Path(__file__).resolve().parent.parent / "exchange_rates.csv"

    # 构建 DataFrame
    df_data = {}
    for name, series in data.items():
        if not series.empty:
            col_name = COLUMN_MAPPING.get(name, name)
            df_data[col_name] = series

    if not df_data:
        logger.warning("没有数据可保存")
        return csv_path

    df = pd.DataFrame(df_data)
    df.index.name = "date"

    # 确保目录存在
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # 追加模式：先读取现有数据，再合并
    if csv_path.exists():
        existing = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        combined = pd.concat([existing, df])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()
        combined.to_csv(csv_path)
        logger.info(f"追加数据到 {csv_path}，总计 {len(combined)} 条记录")
    else:
        df.to_csv(csv_path)
        logger.info(f"保存汇率数据到 {csv_path}，共 {len(df)} 条记录")

    return csv_path


def fetch_and_save(start_date: str | None = None, end_date: str | None = None, days: int = 30) -> Path:
    """获取汇率数据并保存到 CSV

    Args:
        start_date: 起始日期
        end_date: 结束日期
        days: 默认回溯天数

    Returns:
        CSV 文件路径
    """
    data = fetch_exchange_rates(start_date, end_date, days)
    return save_exchange_rates_to_csv(data)


def get_latest_exchange_rates() -> dict[str, float | None]:
    """获取最新的汇率数据

    Returns:
        包含最新汇率的字典
    """
    data = fetch_exchange_rates(days=7)
    result = {}
    for name, series in data.items():
        if not series.empty:
            last_valid = series.last_valid_index()
            if last_valid is not None:
                result[name] = float(series[last_valid])
            else:
                result[name] = None
        else:
            result[name] = None
    return result


if __name__ == "__main__":
    setup_logging(verbose=True)
    logger.info("=" * 50)
    logger.info("开始获取汇率数据")
    logger.info("=" * 50)

    try:
        csv_path = fetch_and_save(days=90)
        logger.info(f"数据已保存到: {csv_path}")

        # 验证最新数据
        latest = get_latest_exchange_rates()
        logger.info("最新汇率数据:")
        for name, value in latest.items():
            logger.info(f"  {name}: {value}")

    except Exception as e:
        logger.error(f"获取汇率数据失败: {e}")
        sys.exit(1)
