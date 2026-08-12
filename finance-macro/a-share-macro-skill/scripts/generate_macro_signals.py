#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable


SKILLS_ROOT = Path(__file__).resolve().parents[2]

DIMENSIONS = (
    "monetary_policy",
    "money_supply",
    "entity_economy",
    "inflation",
    "exchange_rate",
)

FOLDERS = {
    "monetary_policy": "monetary-policy-skill",
    "money_supply": "money-supply-skill",
    "entity_economy": "entity-economy-skill",
    "inflation": "inflation-skill",
    "exchange_rate": "exchange-rate-skill",
}


def generate_all(skills_root: Path = SKILLS_ROOT) -> dict[str, Any]:
    builders: dict[str, Callable[[Path], dict[str, Any]]] = {
        "monetary_policy": build_monetary_policy_signal,
        "money_supply": build_money_supply_signal,
        "entity_economy": build_entity_economy_signal,
        "inflation": build_inflation_signal,
        "exchange_rate": build_exchange_rate_signal,
    }
    generated: list[str] = []
    failed: list[str] = []
    signals: dict[str, dict[str, Any]] = {}

    for dimension, builder in builders.items():
        skill_dir = skills_root / FOLDERS[dimension]
        try:
            signal = builder(skill_dir)
            validate_signal(signal)
            write_signal(skill_dir, signal)
            generated.append(dimension)
            signals[dimension] = signal
        except Exception as exc:
            failed.append(dimension)
            error_signal = make_error_signal(dimension, str(exc))
            write_signal(skill_dir, error_signal)
            signals[dimension] = error_signal

    return {"generated": generated, "failed": failed, "signals": signals}


def build_monetary_policy_signal(skill_dir: Path) -> dict[str, Any]:
    data_dir = skill_dir / "data"
    dr007 = read_latest_json(data_dir, "dr007.json")
    lpr = read_latest_json(data_dir, "lpr.json")
    mlf = read_latest_json(data_dir, "mlf.json", required=False) or {}

    dr007_value = number(dr007.get("value"))
    lpr_1y = number(lpr.get("lpr_1y"))
    prev_lpr_1y = number(lpr.get("prev_lpr_1y"))
    if dr007_value is None or lpr_1y is None:
        raise ValueError("DR007或LPR数据不足")

    score = 50.0
    score += clamp((2.2 - dr007_value) * 20, -20, 25)
    if prev_lpr_1y is not None:
        score += clamp((prev_lpr_1y - lpr_1y) * 120, -12, 18)

    mlf_net = number(mlf.get("net_injection_billion_yuan") or mlf.get("net_injection_yi"))
    if mlf_net is not None:
        score += clamp(mlf_net / 50, -10, 10)

    score = clamp(score, 0, 100)
    conclusion = "偏宽松" if score >= 65 else "偏紧" if score < 45 else "中性"
    return make_signal("monetary_policy", score, conclusion, date_from(dr007, lpr, mlf), {"dr007": dr007_value, "lpr_1y": lpr_1y})


def build_money_supply_signal(skill_dir: Path) -> dict[str, Any]:
    payload = read_json(skill_dir / "data" / "money_supply_latest.json")
    latest = payload.get("m1_m2", {}).get("latest", {})
    social = payload.get("social_financing", {})
    m2_yoy = number(latest.get("m2_yoy"))
    m1_yoy = number(latest.get("m1_yoy"))
    spread = number(latest.get("m1_m2_spread") or latest.get("m2_m1_spread"))
    social_yoy = number(social.get("balance_yoy_pct"))
    monthly_yoy = number(social.get("monthly_new_yoy_pct"))

    if m2_yoy is None or m1_yoy is None:
        raise ValueError("M1/M2数据不足")

    score = 50.0
    score += clamp((m2_yoy - 7.5) * 5, -15, 18)
    score += clamp((m1_yoy - 4.0) * 4, -12, 16)
    if spread is not None:
        score += clamp((spread + 4.0) * 3, -12, 12)
    if social_yoy is not None:
        score += clamp((social_yoy - 7.0) * 5, -10, 15)
    if monthly_yoy is not None:
        score += clamp(monthly_yoy / 4, -12, 12)

    score = clamp(score, 0, 100)
    conclusion = "信用扩张" if score >= 65 else "信用偏弱" if score < 45 else "信用中性"
    return make_signal("money_supply", score, conclusion, payload.get("as_of_date") or payload.get("fetched_at"), {"m2_yoy": m2_yoy, "m1_yoy": m1_yoy, "social_yoy": social_yoy})


def build_entity_economy_signal(skill_dir: Path) -> dict[str, Any]:
    data_dir = skill_dir / "data"
    electricity = read_latest_json(data_dir, "electricity.json")
    railway = read_latest_json(data_dir, "railway_freight.json", required=False) or {}

    electricity_yoy = number(electricity.get("yoy_percent"))
    railway_yoy = number(railway.get("yoy_percent"))
    if electricity_yoy is None:
        raise ValueError("用电量数据不足")

    score = 50.0 + clamp((electricity_yoy - 3.0) * 6, -18, 24)
    if railway_yoy is not None:
        score += clamp((railway_yoy - 1.0) * 4, -12, 16)

    score = clamp(score, 0, 100)
    conclusion = "温和修复" if score >= 60 else "经济偏弱" if score < 45 else "平稳"
    return make_signal("entity_economy", score, conclusion, date_from(electricity, railway), {"electricity_yoy": electricity_yoy, "railway_yoy": railway_yoy})


def build_inflation_signal(skill_dir: Path) -> dict[str, Any]:
    data_dir = skill_dir / "data"
    latest_path = data_dir / "inflation_latest.json"
    payload = read_json(latest_path) if latest_path.exists() else read_latest_json(data_dir, "inflation.json")
    cpi = payload.get("cpi", {})
    ppi = payload.get("ppi", {})
    core = payload.get("core_cpi", {})
    cpi_yoy = number(cpi.get("cpi_national_yoy"))
    ppi_yoy = number(ppi.get("ppi_yoy"))
    core_yoy = number(core.get("core_cpi_yoy"))
    if cpi_yoy is None or ppi_yoy is None:
        raise ValueError("CPI或PPI数据不足")

    inflation_level = cpi_yoy * 0.5 + (core_yoy if core_yoy is not None else cpi_yoy) * 0.3 + ppi_yoy * 0.2
    score = 100 - abs(inflation_level - 1.8) * 18
    if inflation_level < 0:
        score -= 20
    if inflation_level > 4:
        score -= 25
    score = clamp(score, 0, 100)
    conclusion = "温和" if score >= 70 else "偏低" if inflation_level < 1 else "偏高"
    data_date = (
        core.get("published_at")
        or cpi.get("published_at")
        or ppi.get("published_at")
        or payload.get("fetched_at")
        or payload.get("month")
    )
    return make_signal("inflation", score, conclusion, data_date, {"cpi_yoy": cpi_yoy, "ppi_yoy": ppi_yoy, "core_cpi_yoy": core_yoy})


def build_exchange_rate_signal(skill_dir: Path) -> dict[str, Any]:
    payload = read_json(skill_dir / "exchange_rate_data.json")
    data = payload.get("data", {})
    errors = [str(item) for item in payload.get("errors", []) if item]
    exchange = data.get("exchange_rates", {})
    flow = data.get("fund_flow", {}).get("north_cumulative", {})
    ted = data.get("ted_spread", {})

    dollar_index = number(nested_value(exchange, "dollar_index", "value"))
    usd_cny = number(nested_value(exchange, "usd_cny", "value"))
    turnover_change = number(flow.get("turnover_7d_change_pct"))
    ted_spread = number(ted.get("ted_spread"))

    score = 50.0
    observed = 0
    if dollar_index is not None:
        score += clamp((103 - dollar_index) * 3, -18, 18)
        observed += 1
    if usd_cny is not None:
        score += clamp((7.25 - usd_cny) * 30, -15, 15)
        observed += 1
    if turnover_change is not None:
        score += clamp(turnover_change / 2, -10, 10)
        observed += 1
    if ted_spread is not None:
        score += clamp((0.25 - ted_spread) * 40, -12, 12)
        observed += 1

    if observed < 2:
        raise ValueError("外部压力有效指标不足")

    score = clamp(score, 0, 100)
    conclusion = "外部压力缓和" if score >= 65 else "外部承压" if score < 45 else "外部中性"
    signal = make_signal("exchange_rate", score, conclusion, payload.get("fetched_at"), {"dollar_index": dollar_index, "usd_cny": usd_cny, "ted_spread": ted_spread})
    signal["errors"] = errors
    return signal


def read_latest_json(base_dir: Path, filename: str, required: bool = True) -> dict[str, Any]:
    paths = sorted(base_dir.rglob(filename), key=lambda path: path.stat().st_mtime, reverse=True)
    if not paths:
        if required:
            raise ValueError(f"未找到{filename}")
        return {}
    return read_json(paths[0])


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def make_signal(dimension: str, score: float, conclusion: str, data_date: str | None, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "score": round(float(score), 2),
        "conclusion": conclusion,
        "data_date": normalize_date(data_date),
        "errors": [],
        "details": details,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def make_error_signal(dimension: str, message: str) -> dict[str, Any]:
    return {
        "dimension": dimension,
        "score": None,
        "conclusion": None,
        "data_date": None,
        "errors": [message],
        "details": {},
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def validate_signal(signal: dict[str, Any]) -> None:
    score = signal.get("score")
    if not isinstance(score, (int, float)) or not 0 <= score <= 100:
        raise ValueError("生成的评分无效")
    if not signal.get("data_date"):
        raise ValueError("生成结果缺少数据日期")


def write_signal(skill_dir: Path, signal: dict[str, Any]) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "macro_signal.json").write_text(json.dumps(signal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def date_from(*payloads: dict[str, Any]) -> str | None:
    for payload in payloads:
        for key in ("data_date", "published_at", "month", "as_of_date", "fetched_at"):
            if payload.get(key):
                return normalize_date(str(payload[key]))
    return None


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    if len(text) >= 10 and text[4:5] == "-":
        return text[:10]
    if len(text) >= 7 and text[4:5] == "-":
        return text[:7]
    return text


def nested_value(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate standard macro_signal.json files.")
    parser.add_argument("--skills-root", type=Path, default=SKILLS_ROOT)
    args = parser.parse_args()
    result = generate_all(args.skills_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
