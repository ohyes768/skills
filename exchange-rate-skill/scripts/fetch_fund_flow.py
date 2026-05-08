#!/usr/bin/env python3
"""
资金流向获取脚本 - exchange-rate-skill
从 AKShare 获取北向/南向资金流向数据
数据源: 东方财富，AKShare接口: ak.stock_market_fund_flow()
数据列: 7=北向净流入, 8=涨幅, 9=南向净流入, 10=涨幅
单位: 原始数据为元，代码转换为亿元
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import akshare as ak
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_common import get_logger, setup_logging

logger = get_logger(__name__)

# 默认数据起始日期（沪港通开通日）
DEFAULT_START_DATE = "2014-11-17"

# CSV 文件列名
COLUMN_MAPPING = {
    "north_net_flow": "北向净流入",
    "north_change": "北向涨幅",
    "south_net_flow": "南向净流入",
    "south_change": "南向涨幅",
}


def fetch_fund_flow(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, pd.DataFrame]:
    """获取北向/南向资金流向数据

    Args:
        start_date: 起始日期 (YYYY-MM-DD)，默认使用 DEFAULT_START_DATE
        end_date: 结束日期 (YYYY-MM-DD)，默认今天

    Returns:
        包含北向(north)和南向(south)资金流向的字典
    """
    logger.info(f"获取资金流向历史数据: {start_date or DEFAULT_START_DATE} 到 {end_date or '今天'}")

    try:
        # AKShare 接口：市场资金流向
        df = ak.stock_market_fund_flow()

        # 列索引说明：
        # 0=日期, 1=上证净流入, 2=上证涨幅, 3=深证净流入, 4=深证涨幅
        # 5=沪深港通净流入, 6=沪深港通涨幅
        # 7=北向净流入, 8=北向涨幅, 9=南向净流入, 10=南向涨幅
        # 11=中证全指, 12=中证全指涨幅, 13=上证50, 14=上证50涨幅
        if len(df.columns) >= 11:
            # 转换日期列
            date_col = df.columns[0]
            df["date"] = pd.to_datetime(df[date_col])
            df = df.set_index("date")

            # 筛选日期范围
            start_dt = pd.to_datetime(start_date) if start_date else pd.to_datetime(DEFAULT_START_DATE)
            end_dt = pd.to_datetime(end_date) if end_date else pd.Timestamp.now().normalize()

            df = df[(df.index >= start_dt) & (df.index <= end_dt)]

            result = {}

            # 北向资金数据（列索引：7=净流入, 8=涨幅）
            # 数据单位是元，需要转换为亿元（除以 1 亿）
            north_data = pd.DataFrame({
                "北向净流入": df.iloc[:, 7] / 1e8,  # 转换为亿元
                "北向涨幅": df.iloc[:, 8],
            })
            north_data.index = df.index
            result["north"] = north_data

            # 南向资金数据（列索引：9=净流入, 10=涨幅）
            south_data = pd.DataFrame({
                "南向净流入": df.iloc[:, 9] / 1e8,  # 转换为亿元
                "南向涨幅": df.iloc[:, 10],
            })
            south_data.index = df.index
            result["south"] = south_data

            logger.info(f"成功获取资金流向数据，北向 {len(result['north'])} 条，南向 {len(result['south'])} 条记录")
            return result
        else:
            logger.error(f"返回的列数不足: {len(df.columns)}，期望 >= 11")
            raise Exception(f"返回的列数不足: {len(df.columns)}")

    except Exception as e:
        logger.error(f"获取资金流向数据失败: {str(e)}")
        raise


def save_fund_flow_to_csv(data: dict[str, pd.DataFrame], csv_path: Path | None = None) -> Path:
    """保存资金流向数据到 CSV

    Args:
        data: 资金流向数据字典
        csv_path: CSV 文件路径，默认保存到项目根目录

    Returns:
        CSV 文件路径
    """
    if csv_path is None:
        csv_path = Path(__file__).resolve().parent.parent / "fund_flow.csv"

    if not data or all(df.empty for df in data.values()):
        logger.warning("没有数据可保存")
        return csv_path

    # 合并北向和南向数据
    fund_flow_list = []

    if "north" in data and not data["north"].empty:
        north_df = data["north"].copy()
        north_df.index.name = "date"
        fund_flow_list.append(north_df)

    if "south" in data and not data["south"].empty:
        south_df = data["south"].copy()
        south_df.index.name = "date"
        fund_flow_list.append(south_df)

    if not fund_flow_list:
        logger.warning("没有数据可保存")
        return csv_path

    # 按日期合并
    fund_flow_df = pd.concat(fund_flow_list, axis=1)

    # 确保目录存在
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # 追加模式
    if csv_path.exists():
        existing = pd.read_csv(csv_path, index_col=0, parse_dates=True)
        combined = pd.concat([existing, fund_flow_df])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined = combined.sort_index()
        combined.to_csv(csv_path)
        logger.info(f"追加数据到 {csv_path}，总计 {len(combined)} 条记录")
    else:
        fund_flow_df.to_csv(csv_path)
        logger.info(f"保存资金流向数据到 {csv_path}，共 {len(fund_flow_df)} 条记录")

    return csv_path


def fetch_and_save(start_date: str | None = None, end_date: str | None = None) -> Path:
    """获取资金流向数据并保存到 CSV

    Args:
        start_date: 起始日期
        end_date: 结束日期

    Returns:
        CSV 文件路径
    """
    data = fetch_fund_flow(start_date, end_date)
    return save_fund_flow_to_csv(data)


def get_latest_fund_flow() -> dict[str, dict[str, float | None]]:
    """获取最新的资金流向数据

    Returns:
        包含北向和南向最新数据的字典
    """
    end = pd.Timestamp.now().normalize()
    start = (end - pd.Timedelta(days=7)).normalize()

    data = fetch_fund_flow(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

    result = {}
    for direction, df in data.items():
        if not df.empty:
            last_idx = df.last_valid_index()
            if last_idx is not None:
                result[direction] = {
                    "net_flow": float(df.loc[last_idx, "北向净流入" if direction == "north" else "南向净流入"]) if f"{'北向' if direction == 'north' else '南向'}净流入" in df.columns else None,
                    "change": float(df.loc[last_idx, "北向涨幅" if direction == "north" else "南向涨幅"]) if f"{'北向' if direction == 'north' else '南向'}涨幅" in df.columns else None,
                    "date": last_idx.strftime("%Y-%m-%d"),
                }
            else:
                result[direction] = None
        else:
            result[direction] = None

    return result


def calculate_cumulative_flow(direction: str = "north", days: int = 30) -> dict[str, float | None]:
    """计算北向/南向资金的累计流入（7日和30日）

    Args:
        direction: 资金方向，"north" 或 "south"
        days: 计算多少天的累计

    Returns:
        包含 7日累计和30日累计的字典
    """
    end = pd.Timestamp.now().normalize()
    start = (end - pd.Timedelta(days=days + 10)).normalize()  # 多取10天确保有足够数据

    data = fetch_fund_flow(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

    if direction not in data or data[direction].empty:
        return {"cum_7d": None, "cum_30d": None}

    df = data[direction].sort_index(ascending=True).tail(days)

    net_col = "北向净流入" if direction == "north" else "南向净流入"
    if net_col not in df.columns:
        return {"cum_7d": None, "cum_30d": None}

    # 计算7日累计和30日累计
    cum_7d = df.tail(7)[net_col].sum()
    cum_30d = df.tail(30)[net_col].sum()

    # 处理 NaN 值
    cum_7d = float(cum_7d) if pd.notna(cum_7d) else None
    cum_30d = float(cum_30d) if pd.notna(cum_30d) else None

    return {
        "cum_7d": cum_7d,
        "cum_30d": cum_30d,
    }


def count_consecutive_days(df: pd.DataFrame, col: str, positive: bool = True, max_days: int = 30) -> int:
    """统计连续净流入/净流出天数

    Args:
        df: 资金流向 DataFrame
        col: 列名（北向净流入 或 南向净流入）
        positive: True=统计连续正流入天数，False=统计连续负流出天数
        max_days: 最多统计天数

    Returns:
        连续天数
    """
    if col not in df.columns:
        return 0

    # 按日期降序排列，取最近 max_days 天
    recent = df.sort_index(ascending=False).head(max_days).copy()

    count = 0
    for _, row in recent.iterrows():
        value = row[col]
        if pd.isna(value):
            break
        if positive and value > 0:
            count += 1
        elif not positive and value < 0:
            count += 1
        else:
            break

    return count


def get_single_day_extremes(df: pd.DataFrame, col: str) -> dict[str, float | None]:
    """获取单日最大流入和最大流出

    Args:
        df: 资金流向 DataFrame
        col: 列名（北向净流入 或 南向净流入）

    Returns:
        包含 max_inflow（最大流入） 和 max_outflow（最大流出） 的字典
    """
    if col not in df.columns:
        return {"max_inflow": None, "max_outflow": None}

    valid_data = df[col].dropna()
    if valid_data.empty:
        return {"max_inflow": None, "max_outflow": None}

    max_inflow = float(valid_data.max())
    max_outflow = float(valid_data.min())

    return {
        "max_inflow": max_inflow if max_inflow > 0 else None,
        "max_outflow": max_outflow if max_outflow < 0 else None,
    }


def calculate_flow_statistics(direction: str = "north", lookback_days: int = 30) -> dict:
    """计算北向/南向资金的完整统计指标

    Args:
        direction: 资金方向，"north" 或 "south"
        lookback_days: 回溯天数

    Returns:
        包含累计、连续天数、极值等全部统计指标的字典
    """
    end = pd.Timestamp.now().normalize()
    start = (end - pd.Timedelta(days=lookback_days + 10)).normalize()

    data = fetch_fund_flow(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))

    if direction not in data or data[direction].empty:
        return {
            "cum_7d": None,
            "cum_30d": None,
            "consecutive_positive_days": 0,
            "consecutive_negative_days": 0,
            "max_inflow": None,
            "max_outflow": None,
        }

    df = data[direction].sort_index(ascending=True).tail(lookback_days)
    net_col = "北向净流入" if direction == "north" else "南向净流入"

    if net_col not in df.columns:
        return {
            "cum_7d": None,
            "cum_30d": None,
            "consecutive_positive_days": 0,
            "consecutive_negative_days": 0,
            "max_inflow": None,
            "max_outflow": None,
        }

    # 累计值
    cum_7d = df.tail(7)[net_col].sum()
    cum_30d = df.tail(30)[net_col].sum()
    cum_7d = float(cum_7d) if pd.notna(cum_7d) else None
    cum_30d = float(cum_30d) if pd.notna(cum_30d) else None

    # 连续天数
    consecutive_positive = count_consecutive_days(df, net_col, positive=True, max_days=lookback_days)
    consecutive_negative = count_consecutive_days(df, net_col, positive=False, max_days=lookback_days)

    # 极值
    extremes = get_single_day_extremes(df, net_col)

    return {
        "cum_7d": cum_7d,
        "cum_30d": cum_30d,
        "consecutive_positive_days": consecutive_positive,
        "consecutive_negative_days": consecutive_negative,
        "max_inflow": extremes["max_inflow"],
        "max_outflow": extremes["max_outflow"],
    }


if __name__ == "__main__":
    setup_logging(verbose=True)
    logger.info("=" * 50)
    logger.info("开始获取资金流向数据")
    logger.info("=" * 50)

    try:
        csv_path = fetch_and_save()
        logger.info(f"数据已保存到: {csv_path}")

        # 验证最新数据
        latest = get_latest_fund_flow()
        logger.info("最新资金流向数据:")
        for direction, data in latest.items():
            if data:
                logger.info(f"  {direction}: 日期={data['date']}, 净流入={data['net_flow']:.2f}亿, 涨幅={data['change']:.2f}%")

        # 计算累计数据
        for direction in ["north", "south"]:
            cum = calculate_cumulative_flow(direction)
            dir_name = "北向" if direction == "north" else "南向"
            logger.info(f"{dir_name}资金累计: 7日={cum['cum_7d']:.2f}亿, 30日={cum['cum_30d']:.2f}亿")

    except Exception as e:
        logger.error(f"获取资金流向数据失败: {e}")
        sys.exit(1)
