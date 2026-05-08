#!/usr/bin/env python3
"""
TED利差获取脚本 - exchange-rate-skill
计算公式: SOFR - DGS3MO（两个 FRED 利率指标的差值）
FRED代码: SOFR (担保隔夜融资利率), DGS3MO (3个月美债收益率)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from fredapi import Fred

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_common import get_logger, load_env_file, setup_logging

logger = get_logger(__name__)

# FRED 利率代码
FRED_CODES = {
    "sofr": "SOFR",     # 担保隔夜融资利率
    "us_3m": "DGS3MO",  # 3个月美债收益率
}


def fetch_ted_spread(
    start_date: str | None = None,
    end_date: str | None = None,
    days: int = 30,
) -> dict[str, pd.Series]:
    """获取 TED 利差数据（SOFR - 3个月美债收益率）

    Args:
        start_date: 起始日期 (YYYY-MM-DD)，默认取最近 days 天
        end_date: 结束日期 (YYYY-MM-DD)，默认今天
        days: 如果没有指定 start_date，则取最近多少天的数据

    Returns:
        包含 SOFR、3个月美债收益率、TED利差的字典
    """
    load_env_file()
    fred_api_key = os.environ.get("FRED_API_KEY")
    if not fred_api_key:
        raise ValueError(
            "FRED_API_KEY 未设置。请选择以下方式之一：\n"
            "  1. 设置环境变量: export FRED_API_KEY=your_key\n"
            "  2. 在项目根目录创建 .env 文件，内容: FRED_API_KEY=your_key\n"
            "  3. 从 https://fred.stlouisfed.org/docs/api/api_key.html 申请 API Key"
        )

    fred = Fred(api_key=fred_api_key)

    # 默认日期范围
    if end_date is None:
        end_date = pd.Timestamp.now().normalize()
    else:
        end_date = pd.Timestamp(end_date)

    if start_date is None:
        start_date = end_date - pd.Timedelta(days=days)
    else:
        start_date = pd.Timestamp(start_date)

    logger.info(f"获取TED利差数据: {start_date.date()} 至 {end_date.date()}")

    result = {}

    for name, code in FRED_CODES.items():
        try:
            logger.info(f"获取 {name} ({code})...")
            series = fred.get_series(
                code,
                observation_start=start_date,
                observation_end=end_date,
            )
            if series is not None and not series.empty:
                result[name] = series
                logger.info(f"成功获取 {name}，共 {len(series)} 条记录")
            else:
                logger.warning(f"{name} 数据为空")
                result[name] = pd.Series(dtype="float64")
        except Exception as e:
            logger.error(f"获取 {name} 失败: {e}")
            result[name] = pd.Series(dtype="float64")

    # 计算 TED 利差
    if "sofr" in result and "us_3m" in result:
        sofr = result["sofr"]
        us_3m = result["us_3m"]

        if not sofr.empty and not us_3m.empty:
            # 对齐索引
            sofr_aligned = sofr.reindex(us_3m.index, method="ffill")
            ted_spread = sofr_aligned - us_3m
            result["ted_spread"] = ted_spread
            logger.info(f"计算 TED 利差完成，共 {len(ted_spread)} 条记录")
        else:
            result["ted_spread"] = pd.Series(dtype="float64")
    else:
        result["ted_spread"] = pd.Series(dtype="float64")

    return result


def save_ted_spread_to_csv(data: dict[str, pd.Series], csv_path: Path | None = None) -> Path:
    """保存 TED 利差数据到 CSV

    Args:
        data: TED利差数据字典
        csv_path: CSV 文件路径，默认保存到项目根目录

    Returns:
        CSV 文件路径
    """
    if csv_path is None:
        csv_path = Path(__file__).resolve().parent.parent / "ted_spread.csv"

    # 构建 DataFrame
    df_data = {}
    for name, series in data.items():
        if not series.empty:
            col_name = {
                "sofr": "SOFR",
                "us_3m": "美债3m",
                "ted_spread": "TED利差",
            }.get(name, name)
            df_data[col_name] = series

    if not df_data:
        logger.warning("没有数据可保存")
        return csv_path

    df = pd.DataFrame(df_data)
    df.index.name = "date"

    # 确保目录存在
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # 追加模式
    if csv_path.exists():
        existing = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        combined = pd.concat([existing, df])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()
        combined.to_csv(csv_path)
        logger.info(f"追加数据到 {csv_path}，总计 {len(combined)} 条记录")
    else:
        df.to_csv(csv_path)
        logger.info(f"保存TED利差数据到 {csv_path}，共 {len(df)} 条记录")

    return csv_path


def fetch_and_save(start_date: str | None = None, end_date: str | None = None, days: int = 30) -> Path:
    """获取 TED 利差数据并保存到 CSV

    Args:
        start_date: 起始日期
        end_date: 结束日期
        days: 默认回溯天数

    Returns:
        CSV 文件路径
    """
    data = fetch_ted_spread(start_date, end_date, days)
    return save_ted_spread_to_csv(data)


def get_latest_ted_spread() -> dict[str, float | None]:
    """获取最新的 TED 利差数据

    Returns:
        包含最新 TED 利差的字典
    """
    data = fetch_ted_spread(days=7)
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
    logger.info("开始获取 TED 利差数据")
    logger.info("=" * 50)

    try:
        csv_path = fetch_and_save(days=90)
        logger.info(f"数据已保存到: {csv_path}")

        # 验证最新数据
        latest = get_latest_ted_spread()
        logger.info("最新 TED 利差数据:")
        for name, value in latest.items():
            if value is not None:
                logger.info(f"  {name}: {value:.4f}%")

    except Exception as e:
        logger.error(f"获取 TED 利差数据失败: {e}")
        sys.exit(1)
