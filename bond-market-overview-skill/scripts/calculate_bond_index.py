#!/usr/bin/env python3
"""
债市宏观友好度指数计算脚本 - bond-market-overview-skill
直接读取各skill已有的真实数据文件，计算债市宏观友好度指数
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Skill数据目录（统一使用Claude skills安装路径）
SKILLS_BASE = Path("C:/Users/Administrator/.claude/skills")


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    for enc in ["utf-8", "utf-8-sig", "gbk"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            pass
    return None


def extract_score(data: dict | None, default: float = 50.0) -> float:
    if data is None:
        return default
    if "score" in data:
        return float(data["score"])
    if "data" in data and isinstance(data["data"], dict):
        if "score" in data["data"]:
            return float(data["data"]["score"])
    for key in ["composite_score", "total_score", "综合评分", "得分"]:
        if key in data:
            return float(data[key])
    return default


def extract_conclusion(data: dict | None, default: str = "未知") -> str:
    if data is None:
        return default
    for key in ["conclusion", "定性", "结论", "status", "综合结论"]:
        if key in data:
            return str(data[key])
    if "data" in data and isinstance(data["data"], dict):
        for key in ["conclusion", "定性", "结论", "status", "综合结论"]:
            if key in data["data"]:
                return str(data["data"][key])
    return default


# ─── 各维度得分提取 ────────────────────────────────────────────

def get_monetary_policy_score() -> tuple[float, str]:
    """货币政策：读LPR + DR007"""
    lpr_path = SKILLS_BASE / "monetary-policy-skill" / "data" / "2026-04" / "lpr.json"
    dr_path = SKILLS_BASE / "monetary-policy-skill" / "data" / "2026-04" / "dr007.json"

    lpr_data = load_json(lpr_path)
    dr_data = load_json(dr_path)

    # LPR 1Y: 3.0% → 中性偏低（宽松）；>3.1偏紧，<2.9极松
    lpr_1y = 0.0
    conclusion = "未知"
    if lpr_data:
        lpr_1y = lpr_data.get("lpr_1y", 0.0)
        conclusion = f"LPR_1Y={lpr_1y}%"

    # DR007: 1.34% → 资金面宽松
    dr007 = 0.0
    if dr_data:
        dr007 = dr_data.get("value", 0.0)

    # 评分逻辑：LPR和DR007都处于历史低位，货币政策偏宽松
    # 基准线约2.0%，当前3.0%LPR → 评分约65（宽松区间）
    if lpr_1y > 0:
        # LPR 1Y历史区间约2.8-4.0，当前3.0属于偏低宽松
        score = max(40, min(85, 82 - (lpr_1y - 2.8) * 40))
    else:
        score = 50.0

    return score, conclusion


def get_money_supply_score() -> tuple[float, str]:
    """信用扩张：读M1/M2 + 社融"""
    path = SKILLS_BASE / "money-supply-skill" / "data" / "money_supply_latest.json"
    data = load_json(path)

    if data is None:
        return 50.0, "数据缺失"

    m1_m2_latest = data.get("m1_m2", {}).get("latest", data.get("m1_m2", {}))
    m1_yoy = m1_m2_latest.get("m1_yoy", 0.0)
    m2_yoy = m1_m2_latest.get("m2_yoy", 0.0)
    spread = m1_m2_latest.get("m1_m2_spread", 0.0)  # 负值表示活化不足

    sf = data.get("social_financing", {})
    sf_yoy = sf.get("balance_yoy_pct", 0.0)

    # 评分逻辑：
    # M1-M2剪刀差负值大→信用收缩→对债市利好（所以这里高分=信用收缩，不是扩张）
    # 但按照映射规则，score高分=经济好信用扩张，分低=信用收缩
    # M1-M2差-3.4% → 实体经济偏冷
    if spread < -3.0:
        # 严重负剪刀差 → 信用收缩 → score给40（偏冷）
        score = max(20, 50 + spread * 5)
    elif spread < -1.5:
        score = max(30, 50 + spread * 8)
    else:
        score = min(70, 50 + spread * 10)

    conclusion = f"M1 YoY={m1_yoy}% M2 YoY={m2_yoy}% 剪刀差={spread}% 社融存比YoY={sf_yoy}%"
    return score, conclusion


def get_entity_economy_score() -> tuple[float, str]:
    """经济运行：读用电量 + 中长期贷款"""
    elec_path = SKILLS_BASE / "entity-economy-skill" / "data" / "2026-03" / "electricity.json"
    credit_path = SKILLS_BASE / "entity-economy-skill" / "data" / "2026-03" / "pbc_credit.json"

    elec_data = load_json(elec_path)
    credit_data = load_json(credit_path)

    # 用电增速：3.5% → 偏冷（正常约5-7%）
    elec_yoy = 0.0
    if elec_data:
        elec_yoy = elec_data.get("yoy_percent", 0.0)

    # 中长期贷款：123.8万亿
    credit_yoy = 0.0
    if credit_data:
        # 计算同比需要历史数据，暂用绝对值判断
        pass

    # 评分：3.5%用电增速明显偏低，实体经济偏冷
    if elec_yoy > 7:
        score = 80  # 过热
    elif elec_yoy > 5:
        score = 65  # 偏热
    elif elec_yoy > 3:
        score = 40  # 偏冷
    elif elec_yoy > 1:
        score = 30  # 偏冷
    else:
        score = 20  # 过冷

    conclusion = f"用电YoY={elec_yoy}%"
    return float(score), conclusion


def get_inflation_score() -> tuple[float, str]:
    """通胀：读CPI + PPI"""
    cpi_path = SKILLS_BASE / "inflation-skill" / "data" / "2026-03" / "cpi.json"
    ppi_path = SKILLS_BASE / "inflation-skill" / "data" / "2026-03" / "ppi.json"

    cpi_data = load_json(cpi_path)
    ppi_data = load_json(ppi_path)

    cpi_yoy = 0.0
    ppi_yoy = 0.0
    if cpi_data:
        cpi_yoy = cpi_data.get("cpi_national_yoy", 0.0)
    if ppi_data:
        ppi_yoy = ppi_data.get("ppi_yoy", 0.0)

    # 评分逻辑：低通胀/通缩对债市利好（100-D映射后高分）
    # CPI 1.0% + PPI 0.5% → 极度温和，接近通缩
    # CPI历史区间约-1%到5%，当前1%属于低通胀区间
    if cpi_yoy > 3.5:
        score = 75  # 偏高
    elif cpi_yoy > 2.0:
        score = 60  # 温和
    elif cpi_yoy > 1.0:
        score = 45  # 低通胀
    elif cpi_yoy > 0.0:
        score = 25  # 接近通缩
    else:
        score = 10  # 通缩

    conclusion = f"CPI YoY={cpi_yoy}% PPI={ppi_yoy}%"
    return float(score), conclusion


def get_risk_appetite_score() -> tuple[float, str]:
    """风险偏好：读两市成交额 + 换手率 + 融资余额"""
    path = SKILLS_BASE / "risk-appetite-skill" / "risk_data.json"
    data = load_json(path)

    if data is None:
        return 50.0, "数据缺失"

    score_data = data.get("score", {})
    if not score_data:
        return 50.0, "数据缺失"

    total_score = score_data.get("total_score", 50.0)
    conclusion = score_data.get("conclusion", "未知")

    return float(total_score), f"total_score={total_score} conclusion={conclusion}"


def get_exchange_rate_score() -> tuple[float, str]:
    """外部汇率：读北向资金 + 汇率数据"""
    path = SKILLS_BASE / "exchange-rate-skill" / "exchange_rate_data.json"
    data = load_json(path)

    if data is None:
        return 50.0, "数据缺失"

    fund_flow = data.get("data", {}).get("fund_flow", {})
    north_cum = fund_flow.get("north_cumulative", {})

    # 北向30日净流出-2194亿 → 外资外流 → 对债市中性偏负（但外资配债比例低）
    cum_30d = north_cum.get("cum_30d", 0.0)

    if cum_30d > 500:
        score = 70  # 外资大幅净流入
    elif cum_30d > 100:
        score = 60  # 外资小幅净流入
    elif cum_30d > -500:
        score = 50  # 基本平衡
    elif cum_30d > -1500:
        score = 35  # 外资净流出
    else:
        score = 20  # 外资大幅净流出

    conclusion = f"北向30日净流出={cum_30d}亿"
    return float(score), conclusion


# ─── 核心计算 ──────────────────────────────────────────────────

def calculate_bond_index(
    monetary: float,
    credit: float,
    economy: float,
    inflation: float,
    risk: float,
    exchange: float,
) -> dict:
    """计算债市宏观友好度指数"""
    # 正向映射
    monetary_friendly = monetary
    exchange_friendly = exchange
    # 反向映射
    credit_friendly = 100 - credit
    economy_friendly = 100 - economy
    inflation_friendly = 100 - inflation
    risk_friendly = 100 - risk

    weights = {
        "monetary": 0.25,
        "economy": 0.20,
        "inflation": 0.20,
        "credit": 0.15,
        "risk": 0.15,
        "exchange": 0.05,
    }

    total = (
        monetary_friendly * weights["monetary"]
        + economy_friendly * weights["economy"]
        + inflation_friendly * weights["inflation"]
        + credit_friendly * weights["credit"]
        + risk_friendly * weights["risk"]
        + exchange_friendly * weights["exchange"]
    )

    contributions = {
        "monetary": monetary_friendly * weights["monetary"],
        "economy": economy_friendly * weights["economy"],
        "inflation": inflation_friendly * weights["inflation"],
        "credit": credit_friendly * weights["credit"],
        "risk": risk_friendly * weights["risk"],
        "exchange": exchange_friendly * weights["exchange"],
    }

    return {
        "scores": {
            "monetary": monetary,
            "credit": credit,
            "economy": economy,
            "inflation": inflation,
            "risk": risk,
            "exchange": exchange,
        },
        "friendly_scores": {
            "monetary": round(monetary_friendly, 2),
            "credit": round(credit_friendly, 2),
            "economy": round(economy_friendly, 2),
            "inflation": round(inflation_friendly, 2),
            "risk": round(risk_friendly, 2),
            "exchange": round(exchange_friendly, 2),
        },
        "weights": weights,
        "contributions": {k: round(v, 2) for k, v in contributions.items()},
        "total_index": round(total, 2),
        "conclusion": _get_conclusion(total),
    }


def _get_conclusion(index: float) -> str:
    if index >= 80:
        return "极度利好"
    elif index >= 65:
        return "利好"
    elif index >= 45:
        return "中性"
    elif index >= 30:
        return "利空"
    else:
        return "极度利空"


# ─── 主入口 ────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Bond Market Macro Friendliness Index Calculator")
    print("=" * 60)

    # 收集6个维度得分
    monetary, m_conclusion = get_monetary_policy_score()
    credit, c_conclusion = get_money_supply_score()
    economy, e_conclusion = get_entity_economy_score()
    inflation, i_conclusion = get_inflation_score()
    risk, r_conclusion = get_risk_appetite_score()
    exchange, x_conclusion = get_exchange_rate_score()

    print("\n--- Raw Scores ---")
    print(f"  monetary_policy : {monetary:.1f}  [{m_conclusion}]")
    print(f"  money_supply   : {credit:.1f}  [{c_conclusion}]")
    print(f"  entity_economy : {economy:.1f}  [{e_conclusion}]")
    print(f"  inflation      : {inflation:.1f}  [{i_conclusion}]")
    print(f"  risk_appetite  : {risk:.1f}  [{r_conclusion}]")
    print(f"  exchange_rate  : {exchange:.1f}  [{x_conclusion}]")

    # 计算
    result = calculate_bond_index(monetary, credit, economy, inflation, risk, exchange)

    print(f"\n--- Bond Index: {result['total_index']} ({result['conclusion']}) ---")
    print(f"  contributions: {result['contributions']}")

    # 保存到skill本地目录
    output_path = Path(__file__).resolve().parent.parent / "bond_index_data.json"
    result["fetched_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {output_path}")
    return result


if __name__ == "__main__":
    main()
