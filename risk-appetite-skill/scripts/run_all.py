#!/usr/bin/env python3
"""
风险偏好判断 Skill - 统一数据获取入口
基于成交额/换手率（活跃度）和融资融券余额两个维度判断市场风险偏好
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 确保本地 scripts 目录可导入
_SCRIPT_DIR = Path(__file__).resolve().parent
for _p in [str(_SCRIPT_DIR)]:
    if _p in sys.path:
        sys.path.remove(_p)
sys.path.insert(0, str(_SCRIPT_DIR))

from fetch_common import setup_logging, LOGGER, to_iso_now
from fetch_margin import fetch_margin_ohlc, fetch_margin_history
from fetch_volume import fetch_market_volume, fetch_turnover_rate, fetch_history


def fetch_all(days: int = 5) -> dict[str, Any]:
    """
    获取所有风险偏好相关数据

    参数:
        days: 计算均值的历史天数（默认5日）

    返回:
        包含成交额、换手率、融资融券数据的综合字典
    """
    LOGGER.info("开始获取风险偏好数据，区间=%d日", days)

    result: dict[str, Any] = {
        "fetched_at": to_iso_now(),
        "period_days": days,
        "volume": None,
        "turnover": None,
        "margin": None,
        "history": {},
        "status": "failed",
    }

    try:
        # 1. 成交额数据
        LOGGER.info("获取两市成交额...")
        result["volume"] = fetch_market_volume(days)

        # 2. 换手率数据
        LOGGER.info("获取换手率...")
        result["turnover"] = fetch_turnover_rate(days=days)

        # 3. 融资融券数据
        LOGGER.info("获取融资融券余额...")
        result["margin"] = fetch_margin_ohlc()

        # 4. 历史数据（用于环比计算和趋势判断）
        LOGGER.info("获取历史数据用于趋势分析...")
        result["history"] = {
            "volume": fetch_history(days * 2),
            "margin": fetch_margin_history(days * 2),
        }

        result["status"] = "ok"
        LOGGER.info("数据获取完成")

    except Exception as exc:
        LOGGER.warning("数据获取过程出错: %s", exc)
        result["error"] = str(exc)

    return result


def _calc_consecutive_inflow_score(margin_history: list[dict[str, Any]]) -> tuple[int, str]:
    """
    计算连续净流入加分

    规则：
    - 融资余额连续5个交易日净流入：+5分
    - 连续3个交易日净流入：+2分
    """
    if len(margin_history) < 5:
        return 0, ""

    consecutive_positive = 0
    max_consecutive = 0

    for i in range(len(margin_history) - 1):
        current_rzye = margin_history[i].get("rzye", 0) or 0
        prev_rzye = margin_history[i + 1].get("rzye", 0) or 0

        if prev_rzye > 0 and current_rzye > prev_rzye:
            consecutive_positive += 1
            max_consecutive = max(max_consecutive, consecutive_positive)
        else:
            consecutive_positive = 0

    if max_consecutive >= 5:
        return 5, f"连续{max_consecutive}日净流入"
    elif max_consecutive >= 3:
        return 2, f"连续{max_consecutive}日净流入"

    return 0, ""


def _calc_consecutive_outflow_score(margin_history: list[dict[str, Any]]) -> tuple[int, str]:
    """
    计算连续净流出减分

    规则：
    - 融资余额连续3个交易日净流出且呈加速趋势：-5分
    - 连续2个交易日净流出：-2分
    """
    if len(margin_history) < 3:
        return 0, ""

    consecutive_negative = 0
    accelerating = False
    prev_change = 0

    for i in range(len(margin_history) - 1):
        current_rzye = margin_history[i].get("rzye", 0) or 0
        prev_rzye = margin_history[i + 1].get("rzye", 0) or 0

        if prev_rzye > 0 and current_rzye < prev_rzye:
            change = (current_rzye - prev_rzye) / prev_rzye * 100
            if i > 0 and change < prev_change < 0:
                accelerating = True
            prev_change = change
            consecutive_negative += 1
        else:
            consecutive_negative = 0
            prev_change = 0
            accelerating = False

    if consecutive_negative >= 3 and accelerating:
        return -5, f"连续{consecutive_negative}日净流出加速"
    elif consecutive_negative >= 2:
        return -2, f"连续{consecutive_negative}日净流出"

    return 0, ""


def _calc_short_interest_anomaly_score(margin_history: list[dict[str, Any]]) -> tuple[int, str]:
    """
    计算融券余额异常跳升扣分

    规则：
    - 融券余额单日环比翻倍（>100%）：扣3分
    - 融券余额单日环比增幅超50%：扣2分
    """
    if len(margin_history) < 2:
        return 0, ""

    for i in range(min(3, len(margin_history) - 1)):
        current_rqye = margin_history[i].get("rqye", 0) or 0
        prev_rqye = margin_history[i + 1].get("rqye", 0) or 0

        if prev_rqye > 0 and current_rqye > prev_rqye:
            change_pct = (current_rqye - prev_rqye) / prev_rqye * 100
            if change_pct > 100:
                return -3, f"融券余额异常跳升{change_pct:.0f}%"
            elif change_pct > 50:
                return -2, f"融券余额大幅增加{change_pct:.0f}%"

    return 0, ""


def calculate_score(data: dict[str, Any]) -> dict[str, Any]:
    """
    基于获取的数据计算风险偏好评分

    评分框架（来自提示词.md）：
    - 活跃度维度（50%）：成交额(25%) + 换手率(25%)
    - 融资融券维度（50%）：融资余额环比变化

    辅助加减分：
    - 融资余额连续5个交易日净流入：+5分
    - 融资余额连续3个交易日净流出且呈加速趋势：-5分
    - 融券余额出现异常跳升（单日环比翻倍等）：扣3-5分

    返回：
        包含评分结果的字典
    """
    result = {
        "turnover_score": None,
        "volume_score": None,
        "activity_score": None,
        "margin_score": None,
        "total_score": None,
        "conclusion": None,
        "suggestion": None,
        "bonus": {},
        "raw_data": {},
    }

    try:
        # 提取当前数据
        volume_data = data.get("volume", {})
        turnover_data = data.get("turnover", {})
        margin_data = data.get("margin", {})
        history = data.get("history", {})
        margin_history = history.get("margin", [])

        total_amount = volume_data.get("total_amount_yi") or 0
        turnover_rate = turnover_data.get("turnover_rate") or 0
        rzdf = margin_data.get("rzdf") or 0  # 融资余额环比 %

        # ========== 成交额得分 ==========
        if total_amount > 25000:
            volume_score = 90
        elif total_amount > 20000:
            volume_score = 80
        elif total_amount > 18000:
            volume_score = 70
        elif total_amount > 13000:
            volume_score = 60
        elif total_amount > 8000:
            volume_score = 50
        elif total_amount > 5000:
            volume_score = 30
        elif total_amount > 0:
            volume_score = 10
        else:
            volume_score = 0

        # ========== 换手率得分 ==========
        if turnover_rate > 2.5:
            turnover_score = 90
        elif turnover_rate > 2.0:
            turnover_score = 80
        elif turnover_rate > 1.5:
            turnover_score = 70
        elif turnover_rate > 1.2:
            turnover_score = 60
        elif turnover_rate > 0.7:
            turnover_score = 50
        elif turnover_rate > 0.4:
            turnover_score = 30
        else:
            turnover_score = 10

        # ========== 活跃度维度得分 ==========
        activity_score = volume_score * 0.5 + turnover_score * 0.5

        # ========== 融资余额环比得分 ==========
        if rzdf > 2.5:
            margin_score = 90
        elif rzdf > 1.0:
            margin_score = 70
        elif rzdf > 0:
            margin_score = 55
        elif rzdf > -1.0:
            margin_score = 45
        elif rzdf > -2.5:
            margin_score = 30
        else:
            margin_score = 10

        # ========== 辅助加减分 ==========
        bonus_total = 0
        bonus_details: dict[str, Any] = {}

        # 连续净流入加分
        inflow_bonus, inflow_reason = _calc_consecutive_inflow_score(margin_history)
        if inflow_bonus != 0:
            bonus_total += inflow_bonus
            bonus_details["inflow"] = {"score": inflow_bonus, "reason": inflow_reason}

        # 连续净流出减分
        outflow_bonus, outflow_reason = _calc_consecutive_outflow_score(margin_history)
        if outflow_bonus != 0:
            bonus_total += outflow_bonus
            bonus_details["outflow"] = {"score": outflow_bonus, "reason": outflow_reason}

        # 融券异常扣分
        short_bonus, short_reason = _calc_short_interest_anomaly_score(margin_history)
        if short_bonus != 0:
            bonus_total += short_bonus
            bonus_details["short_interest"] = {"score": short_bonus, "reason": short_reason}

        LOGGER.info("辅助加减分: %s (合计: %+d)", bonus_details, bonus_total)

        # ========== 综合得分 ==========
        total_score = activity_score * 0.5 + margin_score * 0.5 + bonus_total
        total_score = max(0, min(100, total_score))  # 限制在 0-100

        # ========== 结论判定 ==========
        if total_score >= 80:
            conclusion = "极度亢奋"
            suggestion = "警惕短期过热风险，不宜追高，注意仓位管理"
        elif total_score >= 60:
            conclusion = "偏热/乐观"
            suggestion = "趋势向好，可参与但保持警惕"
        elif total_score >= 40:
            conclusion = "中性"
            suggestion = "多空均衡，正常观察即可"
        elif total_score >= 20:
            conclusion = "偏冷/谨慎"
            suggestion = "情绪低迷，可能是逐步低吸的机会"
        else:
            conclusion = "极度恐慌"
            suggestion = "市场恐慌，通常是中长期左侧布局窗口"

        result.update({
            "turnover_score": round(turnover_score, 1),
            "volume_score": round(volume_score, 1),
            "activity_score": round(activity_score, 1),
            "margin_score": round(margin_score, 1),
            "total_score": round(total_score, 1),
            "conclusion": conclusion,
            "suggestion": suggestion,
            "bonus": bonus_details,
            "bonus_total": bonus_total,
            "raw_data": {
                "total_amount_yi": total_amount,
                "turnover_rate": turnover_rate,
                "rzdf": rzdf,
            },
        })

    except Exception as exc:
        LOGGER.warning("评分计算失败: %s", exc)
        result["error"] = str(exc)

    return result


def format_report(data: dict[str, Any], score: dict[str, Any]) -> str:
    """生成格式化报告"""
    if data.get("status") != "ok":
        return f"数据获取失败: {data.get('error', '未知错误')}"

    volume = data.get("volume", {})
    turnover = data.get("turnover", {})
    margin = data.get("margin", {})
    bonus = score.get("bonus", {})
    bonus_total = score.get("bonus_total", 0)

    # 格式化加减分说明
    bonus_str = ""
    if bonus:
        bonus_parts = []
        for key, val in bonus.items():
            bonus_parts.append(f"{val['reason']}({val['score']:+d}分)")
        bonus_str = "，".join(bonus_parts)

    report = f"""# 风险偏好分析报告

## 核心结论
**{score['conclusion']}**（综合评分: {score['total_score']}分）
> {score['suggestion']}

## 核心指标

| 指标 | 当前值 | 环比/变化 | 信号 | 得分 |
|------|--------|---------|------|------|
| 成交额 | {volume.get('total_amount_yi', 'N/A')}亿元 | - | {get_signal_emoji(score.get('volume_score', 0))} | {score.get('volume_score', 'N/A')} |
| 换手率 | {turnover.get('turnover_rate', 'N/A')}% | - | {get_signal_emoji(score.get('turnover_score', 0))} | {score.get('turnover_score', 'N/A')} |
| 融资余额 | {margin.get('rzye', 'N/A')}亿元 | 环比 {margin.get('rzdf', 0):+.2f}% | {get_signal_emoji(score.get('margin_score', 0))} | {score.get('margin_score', 'N/A')} |

## 评分明细

| 维度 | 得分 | 权重 | 加权得分 |
|------|------|------|---------|
| 活跃度维度 | {score.get('activity_score', 'N/A')}分 | 50% | {round(score.get('activity_score', 0) * 0.5, 1)}分 |
| 融资融券维度 | {score.get('margin_score', 'N/A')}分 | 50% | {round(score.get('margin_score', 0) * 0.5, 1)}分 |
| 辅助加减分 | {bonus_total:+d}分 | - | {bonus_str} |
| **综合评分** | | | **{score.get('total_score', 'N/A')}分** |

## 数据来源
- 成交额/换手率：沪深交易所官方 API（fetch_volume_exchange.py）
- 融资融券：akshare macro_china_market_margin_sh/sz（中证数据）
- 数据时间：{data.get('fetched_at', 'N/A')}

---
*本报告由 risk-appetite-skill 自动生成*
"""
    return report


def get_signal_emoji(score: float | None) -> str:
    """根据得分返回信号 emoji"""
    if score is None:
        return "⚪"
    if score >= 80:
        return "🔥"
    if score >= 60:
        return "🟡"
    if score >= 40:
        return "⚪"
    if score >= 20:
        return "🔵"
    return "❄️"


def main() -> None:
    parser = argparse.ArgumentParser(description="风险偏好判断 - 统一数据获取")
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径")
    parser.add_argument("--report", type=str, default="", help="输出文本报告路径")
    parser.add_argument("--days", type=int, default=5, help="评估区间天数（默认5日）")
    args = parser.parse_args()

    setup_logging()

    # 获取数据
    all_data = fetch_all(days=args.days)

    # 计算评分
    score_result = calculate_score(all_data)

    # 合并结果
    result = {
        "data": all_data,
        "score": score_result,
    }

    # 输出 JSON
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(rendered + "\n")
        LOGGER.info("已写入 JSON: %s", args.output)

    # 输出文本报告
    if args.report:
        report_text = format_report(all_data, score_result)
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report_text)
        LOGGER.info("已写入报告: %s", args.report)


if __name__ == "__main__":
    main()
