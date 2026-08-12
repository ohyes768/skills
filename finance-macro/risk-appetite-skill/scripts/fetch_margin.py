#!/usr/bin/env python3
"""
抓取融资融券余额数据（沪市+深市合计）
数据来源：akshare macro_china_market_margin_sh / macro_china_market_margin_sz
融资融券数据于每日(T日)09:45左右更新前一交易日(T-1日)数据
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# 确保本地 scripts 目录可导入
_SCRIPT_DIR = Path(__file__).resolve().parent
for _p in [str(_SCRIPT_DIR)]:
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(_SCRIPT_DIR))

import akshare as ak

from fetch_common import (
    LOGGER,
    read_cache,
    setup_logging,
    to_float,
    to_iso_now,
    write_cache,
)


def fetch_margin_ohlc(force: bool = False) -> dict[str, Any]:
    """
    抓取沪深两市融资融券余额数据

    返回结构：
    {
        "date": "YYYY-MM-DD",           # 数据日期
        "rzye": 1234567.89,             # 融资余额合计（亿元）
        "rqye": 123456.78,              # 融券余额合计（亿元）
        "rzje": 1234567.89,             # 融资买入额
        "rqje": 123456.78,              # 融券卖出额
        "rzdf": 123.45,                 # 融资余额环比变化率 %
        "rqdf": 12.34,                  # 融券余额环比变化率 %
        "source": "akshare",
        "fetched_at": "ISO时间"
    }
    """
    today = datetime.now().strftime("%Y-%m-%d")

    # 尝试读取缓存（当日缓存）
    if not force:
        cached = read_cache("margin", today)
        if cached:
            LOGGER.info("使用缓存: margin/%s", today)
            return cached

    result: dict[str, Any] = {
        "date": None,
        "rzye": None,
        "rqye": None,
        "rzje": None,
        "rqje": None,
        "rzdf": None,
        "rqdf": None,
        "source": "akshare",
        "fetched_at": to_iso_now(),
        "status": "failed",
    }

    try:
        # 沪市融资融券
        df_sh = ak.macro_china_market_margin_sh()
        df_sh.columns = [c.strip() for c in df_sh.columns]
        LOGGER.debug("沪市列名: %s", list(df_sh.columns))

        # 深市融资融券
        df_sz = ak.macro_china_market_margin_sz()
        df_sz.columns = [c.strip() for c in df_sz.columns]
        LOGGER.debug("深市列名: %s", list(df_sz.columns))

        # 验证数据非空
        if df_sh.empty or df_sz.empty:
            LOGGER.warning("融资融券数据为空")
            return result

        # 根据列名获取数据（更健壮）
        # 沪市列名：['日期', '融资余额', '融资买入额', '融券余额', '融券卖出额', '融资净买入', '融券净卖出']
        col_map_sh = _detect_margin_columns(df_sh.columns.tolist())
        col_map_sz = _detect_margin_columns(df_sz.columns.tolist())

        if not col_map_sh or not col_map_sz:
            LOGGER.warning("无法识别融资融券列名")
            return result

        # 取最新一行（数据升序，取最后一条为最近）
        latest_sh = df_sh.iloc[-1]
        latest_sz = df_sz.iloc[-1]

        # 提取数据（单位：万元 -> 亿元）
        rzye_sh = to_float(latest_sh[col_map_sh["rzye"]]) / 100000000
        rzje_sh = to_float(latest_sh[col_map_sh["rzje"]]) / 100000000
        rqye_sh = to_float(latest_sh[col_map_sh["rqye"]]) / 100000000
        rqje_sh = to_float(latest_sh[col_map_sh["rqje"]]) / 100000000

        rzye_sz = to_float(latest_sz[col_map_sz["rzye"]]) / 100000000
        rzje_sz = to_float(latest_sz[col_map_sz["rzje"]]) / 100000000
        rqye_sz = to_float(latest_sz[col_map_sz["rqye"]]) / 100000000
        rqje_sz = to_float(latest_sz[col_map_sz["rqje"]]) / 100000000

        # 合计（亿元）
        rzye = rzye_sh + rzye_sz
        rqye = rqye_sh + rqye_sz
        rzje = rzje_sh + rzje_sz
        rqje = rqje_sh + rqje_sz

        # 计算环比（数据升序，前一条是倒数第二）
        prev_sh = df_sh.iloc[-2] if len(df_sh) > 1 else None
        prev_sz = df_sz.iloc[-2] if len(df_sz) > 1 else None

        rzdf = None
        rqdf = None
        if prev_sh is not None and prev_sz is not None:
            prev_rzye_sh = to_float(prev_sh[col_map_sh["rzye"]]) / 100000000
            prev_rzye_sz = to_float(prev_sz[col_map_sz["rzye"]]) / 100000000
            prev_rqye_sh = to_float(prev_sh[col_map_sh["rqye"]]) / 100000000
            prev_rqye_sz = to_float(prev_sz[col_map_sz["rqye"]]) / 100000000

            prev_rzye = prev_rzye_sh + prev_rzye_sz
            prev_rqye = prev_rqye_sh + prev_rqye_sz

            if prev_rzye > 0:
                rzdf = (rzye - prev_rzye) / prev_rzye * 100
            if prev_rqye > 0:
                rqdf = (rqye - prev_rqye) / prev_rqye * 100

        # 数据日期
        date_col = col_map_sh.get("date", df_sh.columns[0])
        date_str = str(latest_sh[date_col])[:10] if len(df_sh) > 0 else today

        result.update({
            "date": date_str,
            "rzye": round(rzye, 2),
            "rqye": round(rqye, 2),
            "rzje": round(rzje, 2),
            "rqje": round(rqje, 2),
            "rzdf": round(rzdf, 2) if rzdf is not None else None,
            "rqdf": round(rqdf, 2) if rqdf is not None else None,
            "status": "ok",
        })

        # 写入缓存
        write_cache("margin", date_str, result)
        LOGGER.info("融资融券数据获取成功: 融资余额=%.2f亿, 环比=%.2f%%", rzye, rzdf or 0)

    except Exception as exc:
        LOGGER.warning("融资融券数据获取失败: %s", exc)
        result["error"] = str(exc)

    return result


def _detect_margin_columns(columns: list[str]) -> dict[str, str] | None:
    """检测融资融券数据的列名映射"""
    # 常见的列名模式
    patterns = {
        "date": ["日期", "date", "日期列"],
        "rzye": ["融资余额", "融资余额(元)", "余额"],
        "rzje": ["融资买入额", "买入额", "融资买入"],
        "rqye": ["融券余额", "融券余额(元)"],
        "rqje": ["融券卖出额", "融券卖出"],
        "rzjmre": ["融资净买入", "净买入"],
        "rqjmre": ["融券净卖出", "净卖出"],
    }

    col_map: dict[str, str] = {}
    for target, keywords in patterns.items():
        for col in columns:
            for kw in keywords:
                if kw in col:
                    col_map[target] = col
                    break

    # 至少需要日期和融资余额
    if "date" not in col_map or "rzye" not in col_map:
        return None

    return col_map


def fetch_margin_history(days: int = 20) -> list[dict[str, Any]]:
    """获取最近N个交易日的融资融券数据（用于计算趋势）"""
    results = []

    try:
        df_sh = ak.macro_china_market_margin_sh()
        df_sh.columns = [c.strip() for c in df_sh.columns]
        df_sz = ak.macro_china_market_margin_sz()
        df_sz.columns = [c.strip() for c in df_sz.columns]

        col_map_sh = _detect_margin_columns(df_sh.columns.tolist())
        col_map_sz = _detect_margin_columns(df_sz.columns.tolist())

        if not col_map_sh or not col_map_sz:
            LOGGER.warning("无法识别历史数据列名")
            return results

        # 合并沪市深市（数据升序，取最后N条为最近）
        for i in range(min(days, len(df_sh))):
            row_sh = df_sh.iloc[-(i + 1)]
            row_sz = df_sz.iloc[-(i + 1)] if i < len(df_sz) else row_sh

            date_str = str(row_sh[col_map_sh["date"]])[:10]

            rzye_sh = to_float(row_sh[col_map_sh["rzye"]]) / 100000000
            rzye_sz = to_float(row_sz[col_map_sz["rzye"]]) / 100000000
            rqye_sh = to_float(row_sh[col_map_sh["rqye"]]) / 100000000
            rqye_sz = to_float(row_sz[col_map_sz["rqye"]]) / 100000000

            results.append({
                "date": date_str,
                "rzye": round(rzye_sh + rzye_sz, 2),
                "rqye": round(rqye_sh + rqye_sz, 2),
            })

    except Exception as exc:
        LOGGER.warning("融资融券历史数据获取失败: %s", exc)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取融资融券余额数据")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    parser.add_argument("--force", action="store_true", help="强制刷新缓存")
    parser.add_argument("--history", type=int, default=0, help="获取历史数据天数")
    args = parser.parse_args()

    setup_logging()

    if args.history > 0:
        data = fetch_margin_history(args.history)
    else:
        data = fetch_margin_ohlc(force=args.force)

    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        LOGGER.info("已写入 %s", args.output)


if __name__ == "__main__":
    main()
