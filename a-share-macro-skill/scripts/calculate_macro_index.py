#!/usr/bin/env python3
"""
宏观友好度指数计算脚本 - macro-overview-skill
根据6个专业Skill的数据计算A股宏观友好度指数
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

# Skill数据目录
SKILLS_BASE = Path(__file__).resolve().parent.parent

# 各Skill的JSON文件路径
SKILL_DATA_FILES = {
    "exchange_rate": SKILLS_BASE / "exchange-rate-skill" / "exchange_rate_data.json",
    "risk_appetite": SKILLS_BASE / "risk-appetite-skill" / "risk_data.json",
    "money_supply": SKILLS_BASE / "money-supply-skill" / "money_supply_data.json",
    "monetary_policy": SKILLS_BASE / "monetary-policy-skill" / "monetary_policy_data.json",
    "entity_economy": SKILLS_BASE / "entity-economy-skill" / "entity_economy_data.json",
    "inflation": SKILLS_BASE / "inflation-skill" / "inflation_data.json",
}


def load_skill_data() -> dict:
    """加载各Skill的JSON数据"""
    data = {}
    for key, path in SKILL_DATA_FILES.items():
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data[key] = json.load(f)
            except json.JSONDecodeError:
                data[key] = None
        else:
            data[key] = None
    return data


def extract_score(skill_data: dict | None, default: float = 50.0) -> float:
    """从Skill数据中提取评分，默认50（中性）"""
    if skill_data is None:
        return default

    # 尝试从不同格式提取评分
    # 格式1: {"score": xx}
    if "score" in skill_data:
        return float(skill_data["score"])

    # 格式2: {"data": {"score": xx}}
    if "data" in skill_data and isinstance(skill_data["data"], dict):
        if "score" in skill_data["data"]:
            return float(skill_data["data"]["score"])

    # 格式3: 顶层有综合评分字段
    for key in ["composite_score", "total_score", "综合评分", "得分"]:
        if key in skill_data:
            return float(skill_data[key])

    return default


def extract_conclusion(skill_data: dict | None, default: str = "未知") -> str:
    """从Skill数据中提取定性结论"""
    if skill_data is None:
        return default

    # 尝试从不同格式提取结论
    for key in ["conclusion", "定性", "结论", "status", "综合结论"]:
        if key in skill_data:
            return str(skill_data[key])

    if "data" in skill_data and isinstance(skill_data["data"], dict):
        for key in ["conclusion", "定性", "结论", "status", "综合结论"]:
            if key in skill_data["data"]:
                return str(skill_data["data"][key])

    return default


def calculate_economy_friendliness(C: float) -> float:
    """计算经济运行友好度（倒U型）"""
    if 40 <= C <= 70:
        return 80 + (C - 40) * 0.5
    elif 70 < C <= 80:
        return 70 - (C - 70) * 1.5
    elif C > 80:
        return max(40 - (C - 80) * 1.0, 20)
    else:  # C < 40
        return min(C * 0.8, 32)


def calculate_inflation_friendliness(D: float) -> float:
    """计算通胀友好度（倒U型）"""
    if 40 <= D <= 60:
        # 线性插值 90~100
        return 90 + (D - 40) * 0.5
    elif 60 < D <= 70:
        return 80 - (D - 60) * 2.0
    elif D > 70:
        return max(40 - (D - 70) * 1.5, 0)
    elif 30 <= D < 40:
        return 30 + (D - 30) * 3.0
    else:  # D < 30
        return max(D * 0.8, 0)


def calculate_risk_appetite_friendliness(E: float) -> float:
    """计算风险偏好友好度（倒U型）"""
    if 50 <= E <= 70:
        return 80 + (E - 50) * 1.0
    elif 70 < E <= 85:
        return max(70 - (E - 70) * 1.33, 50)
    elif E > 85:
        return max(30 - (E - 85) * 0.8, 0)
    elif 30 <= E < 50:
        return 40 + (E - 30) * 1.33
    elif 15 <= E < 30:
        return 20 + (E - 15) * 1.33
    else:  # E < 15
        return max(E * 1.33, 0)


def calculate_macro_index(
    monetary_policy_score: float,
    money_supply_score: float,
    entity_economy_score: float,
    inflation_score: float,
    risk_appetite_score: float,
    exchange_rate_score: float,
) -> dict:
    """计算宏观友好度指数

    Returns:
        包含各维度得分和综合指数的字典
    """
    # 线性映射
    monetary_friendly = monetary_policy_score  # A
    money_supply_friendly = money_supply_score  # B
    exchange_friendly = exchange_rate_score  # F

    # 倒U型映射
    economy_friendly = calculate_economy_friendliness(entity_economy_score)  # C
    inflation_friendly = calculate_inflation_friendliness(inflation_score)  # D
    risk_friendly = calculate_risk_appetite_friendliness(risk_appetite_score)  # E

    # 权重
    weights = {
        "monetary": 0.15,
        "money_supply": 0.15,
        "economy": 0.20,
        "inflation": 0.10,
        "risk": 0.20,
        "exchange": 0.20,
    }

    # 计算综合指数
    total = (
        monetary_friendly * weights["monetary"]
        + money_supply_friendly * weights["money_supply"]
        + economy_friendly * weights["economy"]
        + inflation_friendly * weights["inflation"]
        + risk_friendly * weights["risk"]
        + exchange_friendly * weights["exchange"]
    )

    # 贡献值
    contributions = {
        "monetary": monetary_friendly * weights["monetary"],
        "money_supply": money_supply_friendly * weights["money_supply"],
        "economy": economy_friendly * weights["economy"],
        "inflation": inflation_friendly * weights["inflation"],
        "risk": risk_friendly * weights["risk"],
        "exchange": exchange_friendly * weights["exchange"],
    }

    return {
        "scores": {
            "monetary_policy": monetary_policy_score,
            "money_supply": money_supply_score,
            "entity_economy": entity_economy_score,
            "inflation": inflation_score,
            "risk_appetite": risk_appetite_score,
            "exchange_rate": exchange_rate_score,
        },
        "friendly_scores": {
            "monetary_policy": round(monetary_friendly, 2),
            "money_supply": round(money_supply_friendly, 2),
            "economy": round(economy_friendly, 2),
            "inflation": round(inflation_friendly, 2),
            "risk_appetite": round(risk_friendly, 2),
            "exchange_rate": round(exchange_friendly, 2),
        },
        "weights": weights,
        "contributions": {k: round(v, 2) for k, v in contributions.items()},
        "total_index": round(total, 2),
        "conclusion": _get_conclusion(total),
    }


def _get_conclusion(index: float) -> str:
    """根据友好度指数返回定性结论"""
    if index >= 80:
        return "极度友好"
    elif index >= 65:
        return "友好"
    elif index >= 45:
        return "中性"
    elif index >= 30:
        return "不利"
    else:
        return "极度不利"


def main():
    """主入口：加载数据并计算宏观友好度指数"""
    print("=" * 60)
    print("A股宏观友好度指数计算")
    print("=" * 60)

    # 加载数据
    data = load_skill_data()

    # 提取评分
    scores = {
        "monetary_policy": extract_score(data.get("monetary_policy")),
        "money_supply": extract_score(data.get("money_supply")),
        "entity_economy": extract_score(data.get("entity_economy")),
        "inflation": extract_score(data.get("inflation")),
        "risk_appetite": extract_score(data.get("risk_appetite")),
        "exchange_rate": extract_score(data.get("exchange_rate")),
    }

    print("\n各Skill原始评分:")
    for key, value in scores.items():
        print(f"  {key}: {value}")

    # 计算
    result = calculate_macro_index(
        monetary_policy_score=scores["monetary_policy"],
        money_supply_score=scores["money_supply"],
        entity_economy_score=scores["entity_economy"],
        inflation_score=scores["inflation"],
        risk_appetite_score=scores["risk_appetite"],
        exchange_rate_score=scores["exchange_rate"],
    )

    print(f"\n宏观友好度指数: {result['total_index']} ({result['conclusion']})")

    # 保存结果
    output_path = SKILLS_BASE / "macro_index_data.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result["fetched_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_path}")

    return result


if __name__ == "__main__":
    main()