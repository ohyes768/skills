#!/usr/bin/env python3
"""
汇率与资金流向数据获取 - exchange-rate-skill
数据获取脚本：只负责抓取和格式化数据，评分由 SKILL.md 驱动

Usage:
    uv run python scripts/run_all.py [--days N] [--output FILE] [--report FILE]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_common import get_logger, setup_logging, now
from fetch_exchange_rates import fetch_exchange_rates, save_exchange_rates_to_csv
from fetch_north_flow import fetch_north_deal_amt, fetch_north_daily, save_north_flow_to_csv
from fetch_common import build_session
from fetch_ted_spread import fetch_ted_spread, save_ted_spread_to_csv

logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="汇率与资金流向数据获取")
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="回溯天数 (默认: 30)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="JSON 输出文件路径 (默认: {skill_dir}/exchange_rate_data.json)",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Markdown 报告输出路径 (默认: {skill_dir}/exchange_rate_report.md)",
    )
    return parser.parse_args()


def run_all(days: int = 30) -> dict:
    """运行所有数据获取脚本

    Args:
        days: 回溯天数

    Returns:
        包含所有原始数据的字典（评分由 SKILL.md 驱动）
    """
    results = {
        "fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "period_days": days,
        "data": {},
        "errors": [],
    }

    # 1. 获取汇率数据
    try:
        logger.info("获取汇率数据（美元指数 + 人民币）...")
        exchange_data = fetch_exchange_rates(days=days)
        csv_path = save_exchange_rates_to_csv(exchange_data)
        logger.info(f"汇率数据已保存到: {csv_path}")

        # 提取最新值
        latest = {}
        for name, series in exchange_data.items():
            if not series.empty:
                last_valid = series.last_valid_index()
                if last_valid is not None:
                    latest[name] = {
                        "value": round(float(series[last_valid]), 4),
                        "date": last_valid.strftime("%Y-%m-%d"),
                    }
        results["data"]["exchange_rates"] = latest

    except Exception as e:
        logger.error(f"获取汇率数据失败: {e}")
        results["errors"].append(f"exchange_rates: {str(e)}")

    # 2. 获取资金流向数据（北向/南向）
    try:
        logger.info("获取资金流向数据（北向/南向）...")

        session = build_session()

        # 2a. 获取北向资金日频成交总额（来自 RPT_MUTUAL_DEALAMT 的 NF_DEAL_AMT）
        deal_df = fetch_north_deal_amt(session, days=days)
        if deal_df.empty:
            raise ValueError("获取北向资金成交总额失败")

        # 提取当日成交总额
        last_idx = deal_df.index.max()
        turnover_today_yi = round(float(deal_df.loc[last_idx, "北向成交总额"]), 2)

        # 计算7日成交总额（近7个交易日）
        deal_7d = deal_df.head(7)
        turnover_7d_sum_yi = round(float(deal_7d["北向成交总额"].sum()), 2)
        turnover_7d_avg_yi = round(turnover_7d_sum_yi / 7, 2)

        # 计算上期7日成交总额（取更早的7个交易日）
        if len(deal_df) >= 14:
            prev_7d_sum_yi = round(float(deal_df.iloc[7:14]["北向成交总额"].sum()), 2)
        else:
            prev_7d_sum_yi = turnover_7d_sum_yi  # 数据不足时用本期代替

        # 环比变化
        if prev_7d_sum_yi > 0:
            turnover_7d_change_pct = round((turnover_7d_sum_yi - prev_7d_sum_yi) / prev_7d_sum_yi * 100, 2)
        else:
            turnover_7d_change_pct = 0.0

        # 2b. 合并成交总额和日频明细，统一写入 CSV
        combined_df = deal_df[["北向成交总额"]].copy()
        combined_df["北向净流入"] = 0  # 占位，日频明细中会有
        combined_df["沪股通净流入"] = 0
        combined_df["深股通净流入"] = 0

        # 获取日频明细补充净流入数据
        daily_df = fetch_north_daily(session, days=30)
        if not daily_df.empty:
            for col in ["北向净流入", "沪股通净流入", "深股通净流入"]:
                if col in daily_df.columns:
                    combined_df[col] = daily_df[col]

        save_north_flow_to_csv(combined_df)

        results["data"]["fund_flow"] = {
            "north": {
                "turnover_yi": turnover_today_yi,
                "date": last_idx.strftime("%Y-%m-%d"),
            },
            "south": {},  # 南向暂不处理
            "north_cumulative": {
                "turnover_7d_sum_yi": turnover_7d_sum_yi,
                "turnover_7d_avg_yi": turnover_7d_avg_yi,
                "turnover_7d_change_pct": turnover_7d_change_pct,
            },
            "south_cumulative": {},
        }

    except Exception as e:
        logger.error(f"获取资金流向数据失败: {e}")
        results["errors"].append(f"fund_flow: {str(e)}")

    # 3. 获取 TED 利差数据
    try:
        logger.info("获取 TED 利差数据...")
        ted_data = fetch_ted_spread(days=days)
        csv_path = save_ted_spread_to_csv(ted_data)
        logger.info(f"TED利差数据已保存到: {csv_path}")

        # 提取最新值
        latest = {}
        for name, series in ted_data.items():
            if not series.empty:
                last_valid = series.last_valid_index()
                if last_valid is not None:
                    latest[name] = {
                        "value": round(float(series[last_valid]), 4),
                        "date": last_valid.strftime("%Y-%m-%d"),
                    }

        # 重组 TED 数据结构
        if "sofr" in latest and "us_3m" in latest and "ted_spread" in latest:
            results["data"]["ted_spread"] = {
                "sofr": latest["sofr"]["value"],
                "us_3m": latest["us_3m"]["value"],
                "ted_spread": latest["ted_spread"]["value"],
            }

    except Exception as e:
        logger.error(f"获取 TED 利差数据失败: {e}")
        results["errors"].append(f"ted_spread: {str(e)}")

    return results


def save_results(results: dict, output_path: Path | None = None) -> Path:
    """保存 JSON 结果

    Args:
        results: 运行结果
        output_path: 输出路径

    Returns:
        输出文件路径
    """
    if output_path is None:
        output_path = Path(__file__).resolve().parent.parent / "exchange_rate_data.json"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    logger.info(f"数据已保存到: {output_path}")
    return output_path


def generate_report(results: dict, report_path: Path | None = None) -> Path:
    """生成文本报告（供 LLM 参考）

    Args:
        results: 运行结果
        report_path: 报告输出路径

    Returns:
        报告文件路径
    """
    if report_path is None:
        report_path = Path(__file__).resolve().parent.parent / "exchange_rate_report.md"

    # 读取原始数据用于报告
    data = results.get("data", {})

    lines = [
        "# 汇率与资金流向数据报告",
        "",
        f"生成时间: {results.get('fetched_at', now())}",
        "",
        "---",
        "",
    ]

    # 汇率数据
    exchange = data.get("exchange_rates", {})
    if exchange:
        lines.append("## 汇率数据")
        lines.append("")
        lines.append("| 指标 | 值 | 日期 |")
        lines.append("|------|-----|------|")
        if exchange.get("dollar_index"):
            di = exchange["dollar_index"]
            lines.append(f"| 美元指数 | {di['value']} | {di['date']} |")
        if exchange.get("usd_cny"):
            uc = exchange["usd_cny"]
            lines.append(f"| 美元兑人民币 | {uc['value']} | {uc['date']} |")
        lines.append("")

    # 资金流向
    fund_flow = data.get("fund_flow", {})
    if fund_flow:
        lines.append("## 资金流向")
        lines.append("")

        # 北向
        north = fund_flow.get("north", {})
        if north:
            lines.append("### 北向资金（沪深港通→A股）")
            lines.append(f"- 当日成交总额: {north.get('turnover_yi', 'N/A')} 亿元")
            lines.append("")

        # 南向
        south = fund_flow.get("south", {})
        if south:
            lines.append("### 南向资金（A股→沪深港通）")
            lines.append(f"- 当日成交总额: {south.get('turnover_yi', 'N/A')} 亿元")
            lines.append("")

        # 成交总额数据
        lines.append("### 北向资金成交总额")
        lines.append("")
        lines.append("| 7日累计成交额 | 7日日均成交额 | 环比变化 |")
        lines.append("|---------------|---------------|----------|")

        north_cum = fund_flow.get("north_cumulative", {})
        south_cum = fund_flow.get("south_cumulative", {})

        turnover_7d_sum = north_cum.get("turnover_7d_sum_yi")
        turnover_7d_avg = north_cum.get("turnover_7d_avg_yi")
        turnover_change = north_cum.get("turnover_7d_change_pct")

        def _fmt(v: float | None, suffix: str = "") -> str:
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return f"N/A{suffix}"
            return f"{v:.2f}{suffix}"

        def _pct(v: float | None) -> str:
            if v is None:
                return "N/A"
            return f"{v:+.2f}%"

        lines.append(f"| {_fmt(turnover_7d_sum, '亿')} | {_fmt(turnover_7d_avg, '亿')} | {_pct(turnover_change)} |")
        lines.append("")

    # TED 利差
    ted = data.get("ted_spread", {})
    if ted:
        lines.append("## TED 利差")
        lines.append("")
        lines.append("| 指标 | 值 |")
        lines.append("|------|-----|")
        lines.append(f"| SOFR | {ted.get('sofr', 'N/A')}% |")
        lines.append(f"| 美债3个月 | {ted.get('us_3m', 'N/A')}% |")
        lines.append(f"| TED利差 | {ted.get('ted_spread', 'N/A')}% |")
        lines.append("")

    # 错误信息
    errors = results.get("errors", [])
    if errors:
        lines.append("## 错误信息")
        lines.append("")
        for err in errors:
            lines.append(f"- {err}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("*数据由 exchange-rate-skill 自动获取，评分由 SKILL.md 评分框架驱动*")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"报告已保存到: {report_path}")
    return report_path


def main():
    """主入口"""
    args = parse_args()

    setup_logging(verbose=True)
    logger.info("=" * 60)
    logger.info("开始运行 exchange-rate-skill 数据获取")
    logger.info(f"回溯天数: {args.days}")
    logger.info("=" * 60)

    # 检查环境变量
    from fetch_common import load_env_file
    load_env_file()
    fred_key = os.environ.get("FRED_API_KEY")
    if not fred_key:
        logger.warning(
            "FRED_API_KEY 未设置。汇率和TED利差数据将无法获取。\n"
            "请选择以下方式之一解决：\n"
            "  1. 设置环境变量: export FRED_API_KEY=your_key\n"
            "  2. 在项目根目录创建 .env 文件，内容: FRED_API_KEY=your_key\n"
            "  3. 从 https://fred.stlouisfed.org/docs/api/api_key.html 申请 API Key\n"
            "提示: 北向/南向资金数据（AKShare）不需要 FRED_API_KEY"
        )

    try:
        # 数据获取
        results = run_all(days=args.days)

        # 确定输出路径
        skill_dir = Path(__file__).resolve().parent.parent
        output_path = Path(args.output) if args.output else skill_dir / "exchange_rate_data.json"
        report_path = Path(args.report) if args.report else skill_dir / "exchange_rate_report.md"

        # 保存结果
        save_results(results, output_path)
        generate_report(results, report_path)

        logger.info("=" * 60)
        logger.info("运行完成!")
        logger.info(f"数据文件: {output_path}")
        logger.info(f"报告文件: {report_path}")
        logger.info("=" * 60)

        # 输出错误汇总
        if results["errors"]:
            logger.warning("部分数据获取失败:")
            for err in results["errors"]:
                logger.warning(f"  - {err}")

    except Exception as e:
        logger.error(f"运行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()