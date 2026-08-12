#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_PATH = SKILL_ROOT / "bond_index_data.json"


@dataclass(frozen=True)
class DimensionConfig:
    folder: str
    title: str
    core: bool


DIMENSIONS: dict[str, DimensionConfig] = {
    "monetary_policy": DimensionConfig("monetary-policy-skill", "货币政策", True),
    "money_supply": DimensionConfig("money-supply-skill", "信用扩张", True),
    "entity_economy": DimensionConfig("entity-economy-skill", "经济运行", True),
    "inflation": DimensionConfig("inflation-skill", "通胀环境", True),
    "exchange_rate": DimensionConfig("exchange-rate-skill", "外部压力", True),
    "risk_appetite": DimensionConfig("risk-appetite-skill", "市场情绪", False),
}


BOND_WEIGHTS = {
    "monetary_policy": 0.25,
    "entity_economy": 0.22,
    "inflation": 0.22,
    "money_supply": 0.16,
    "exchange_rate": 0.15,
}


def run_assessment(
    skills_root: Path = DEFAULT_SKILLS_ROOT,
    output_path: Path | None = None,
    today: date | None = None,
    max_age_days: int = 45,
) -> dict[str, Any]:
    today = today or datetime.now(UTC).date()
    signals = load_all_signals(skills_root, today, max_age_days)
    data_quality = build_data_quality(signals)

    if data_quality["blocking_errors"]:
        result = {
            "status": "unavailable",
            "summary": "本周债市判断不可用：关键数据缺失、过期或没有明确评分。",
            "data_quality": data_quality,
            "bond": {"score": None, "tone": "不可用", "weights": BOND_WEIGHTS},
            "sentiment": build_sentiment(signals.get("risk_appetite")),
            "dimensions": signals,
            "bond_data_details": build_bond_data_details(signals),
            "generated_at": now_utc(),
        }
    else:
        bond = build_bond_view(signals)
        sentiment = build_sentiment(signals.get("risk_appetite"))
        result = {
            "status": "available",
            "summary": build_summary(bond, sentiment),
            "data_quality": data_quality,
            "bond": bond,
            "sentiment": sentiment,
            "dimensions": signals,
            "bond_data_details": build_bond_data_details(signals),
            "generated_at": now_utc(),
        }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def load_all_signals(skills_root: Path, today: date, max_age_days: int) -> dict[str, dict[str, Any]]:
    return {
        name: load_signal(name, config, skills_root, today, max_age_days)
        for name, config in DIMENSIONS.items()
    }


def load_signal(
    name: str,
    config: DimensionConfig,
    skills_root: Path,
    today: date,
    max_age_days: int,
) -> dict[str, Any]:
    path = skills_root / config.folder / "macro_signal.json"
    if not path.exists() and name == "risk_appetite":
        path = skills_root / config.folder / "risk_data.json"
    if not path.exists():
        return unavailable_signal(name, config, None, "未找到该维度的统一输出文件")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return unavailable_signal(name, config, path, f"JSON无法读取：{exc}")

    signal = extract_signal(name, config, payload, path)
    add_freshness(signal, today, max_age_days)
    return signal


def unavailable_signal(name: str, config: DimensionConfig, path: Path | None, error: str) -> dict[str, Any]:
    return {
        "dimension": name,
        "title": config.title,
        "core": config.core,
        "status": "missing",
        "score": None,
        "conclusion": None,
        "data_date": None,
        "source_file": str(path) if path else None,
        "errors": [error],
        "details": {},
    }


def extract_signal(name: str, config: DimensionConfig, payload: dict[str, Any], path: Path) -> dict[str, Any]:
    score = find_score(payload)
    conclusion = find_first_text(payload, ("conclusion", "summary", "tone", "status", "suggestion"))
    data_date = find_first_text(payload, ("data_date", "as_of_date", "published_at", "month", "fetched_at"))
    errors = normalize_errors(payload.get("errors"))
    details = extract_details(payload)

    status = "ok"
    if score is None:
        status = "invalid"
        errors.append("没有明确的0-100评分")
    elif not 0 <= score <= 100:
        status = "invalid"
        errors.append(f"评分超出0-100范围：{score}")

    return {
        "dimension": name,
        "title": config.title,
        "core": config.core,
        "status": status,
        "score": score,
        "conclusion": conclusion,
        "data_date": data_date,
        "source_file": str(path),
        "errors": errors,
        "details": details,
    }


def find_score(payload: dict[str, Any]) -> float | None:
    value = payload.get("score")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        for key in ("total_score", "composite_score", "score"):
            if isinstance(value.get(key), (int, float)):
                return float(value[key])
    for key in ("total_score", "composite_score"):
        if isinstance(payload.get(key), (int, float)):
            return float(payload[key])
    return None


def find_first_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        if payload.get(key) is not None:
            return str(payload[key])
    for nested_key in ("score", "data"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                if nested.get(key) is not None:
                    return str(nested[key])
    return None


def extract_details(payload: dict[str, Any]) -> dict[str, Any]:
    details = payload.get("details")
    if isinstance(details, dict):
        return details
    score = payload.get("score")
    if isinstance(score, dict) and isinstance(score.get("raw_data"), dict):
        return score["raw_data"]
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return {}


def normalize_errors(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]


def add_freshness(signal: dict[str, Any], today: date, max_age_days: int) -> None:
    parsed = parse_signal_date(signal.get("data_date"))
    signal["age_days"] = None
    signal["freshness"] = "unknown"
    if parsed is None:
        signal["status"] = "invalid"
        signal["errors"].append("没有可识别的数据日期")
        return
    age_days = (today - parsed).days
    signal["age_days"] = age_days
    if age_days < 0:
        signal["freshness"] = "future"
        signal["status"] = "invalid"
        signal["errors"].append(f"数据日期晚于当前日期：{signal['data_date']}")
    elif age_days > max_age_days:
        signal["freshness"] = "stale"
        signal["status"] = "stale"
        signal["errors"].append(f"数据已过期：{age_days}天")
    else:
        signal["freshness"] = "fresh"


def parse_signal_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    if len(text) >= 10:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            pass
    if len(text) >= 7:
        try:
            return date.fromisoformat(text[:7] + "-01")
        except ValueError:
            return None
    return None


def build_data_quality(signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    missing, stale, invalid, warnings, blocking_errors = [], [], [], [], []
    for name, signal in signals.items():
        status = signal["status"]
        if status == "missing":
            missing.append(name)
        elif status == "stale":
            stale.append(name)
        elif status == "invalid":
            invalid.append(name)
        if signal["errors"]:
            line = f"{signal['title']}：{'; '.join(signal['errors'])}"
            if signal["core"]:
                blocking_errors.append(line)
            else:
                warnings.append(line)
    return {
        "ready": not blocking_errors,
        "missing_dimensions": missing,
        "stale_dimensions": stale,
        "invalid_dimensions": invalid,
        "blocking_errors": blocking_errors,
        "warnings": warnings,
    }


def build_bond_view(signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    friendly_scores = {
        "monetary_policy": round(signals["monetary_policy"]["score"], 2),
        "entity_economy": round(100 - signals["entity_economy"]["score"], 2),
        "inflation": round(100 - signals["inflation"]["score"], 2),
        "money_supply": round(100 - signals["money_supply"]["score"], 2),
        "exchange_rate": round(signals["exchange_rate"]["score"], 2),
    }
    contributions = {
        name: round(friendly_scores[name] * weight, 2)
        for name, weight in BOND_WEIGHTS.items()
    }
    score = round(sum(contributions.values()), 2)
    return {
        "score": score,
        "tone": bond_tone(score),
        "weights": BOND_WEIGHTS,
        "friendly_scores": friendly_scores,
        "contributions": contributions,
    }


def bond_tone(score: float) -> str:
    if score >= 80:
        return "明显利好"
    if score >= 65:
        return "偏利好"
    if score >= 45:
        return "中性"
    if score >= 30:
        return "偏不利"
    return "明显不利"


def build_sentiment(signal: dict[str, Any] | None) -> dict[str, Any]:
    if not signal or signal.get("score") is None or signal.get("status") != "ok":
        return {"available": False, "score": None, "temperature": "不可用", "message": "市场情绪不可用。"}
    score = signal["score"]
    if score >= 85:
        temperature = "过热"
        message = "风险偏好过热，对债市偏不利。"
    elif score >= 70:
        temperature = "偏热"
        message = "风险偏好偏热，债市短期容易承压。"
    elif score >= 45:
        temperature = "正常"
        message = "风险偏好正常。"
    elif score >= 25:
        temperature = "偏冷"
        message = "风险偏好偏冷，避险需求可能支撑债市。"
    else:
        temperature = "恐慌"
        message = "风险偏好恐慌，债市可能受避险需求支撑，但也要防流动性冲击。"
    return {"available": True, "score": round(score, 2), "temperature": temperature, "message": message}


def build_summary(bond: dict[str, Any], sentiment: dict[str, Any]) -> str:
    if not sentiment["available"]:
        return f"债市底色：{bond['tone']}；短期情绪：不可用；综合判断：仅能判断中期债市环境。"
    if bond["tone"] in {"明显利好", "偏利好"} and sentiment["temperature"] in {"偏冷", "恐慌"}:
        return f"债市底色：{bond['tone']}；短期情绪：{sentiment['temperature']}；综合判断：宏观和避险情绪共同支撑债市。"
    if bond["tone"] in {"明显利好", "偏利好"} and sentiment["temperature"] in {"偏热", "过热"}:
        return f"债市底色：{bond['tone']}；短期情绪：{sentiment['temperature']}；综合判断：中期环境偏有利，但短期风险偏好对债市形成压制。"
    if bond["tone"] in {"偏不利", "明显不利"}:
        return f"债市底色：{bond['tone']}；短期情绪：{sentiment['temperature']}；综合判断：宏观环境对债市不友好，久期和杠杆都应谨慎。"
    return f"债市底色：{bond['tone']}；短期情绪：{sentiment['temperature']}；综合判断：多空交织，票息和中性久期更合适。"


def build_bond_data_details(signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    details = {}
    for name, config in DIMENSIONS.items():
        signal = signals.get(name, {})
        details[config.title] = {
            "维度": name,
            "是否核心宏观": config.core,
            "状态": signal.get("status"),
            "评分": signal.get("score"),
            "结论": signal.get("conclusion"),
            "数据日期": signal.get("data_date"),
            "新鲜度": signal.get("freshness"),
            "距今天数": signal.get("age_days"),
            "指标明细": signal.get("details") or {},
            "错误信息": signal.get("errors") or [],
            "来源文件": signal.get("source_file"),
        }
    return details


def print_bond_data_details(details: dict[str, Any]) -> None:
    print("=== 债市宏观数据明细 ===")
    for title, item in details.items():
        print(f"\n【{title}】")
        print(f"状态：{item.get('状态')}；评分：{item.get('评分')}；结论：{item.get('结论')}；数据日期：{item.get('数据日期')}")
        indicators = item.get("指标明细") or {}
        if indicators:
            for key, value in indicators.items():
                print(f"- {key}: {value}")
        else:
            print("- 暂无指标明细")
        errors = item.get("错误信息") or []
        if errors:
            print(f"错误：{'; '.join(errors)}")


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate bond-market macro assessment.")
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--max-age-days", type=int, default=45)
    args = parser.parse_args()

    result = run_assessment(args.skills_root, args.output, max_age_days=args.max_age_days)
    print_bond_data_details(result["bond_data_details"])
    print()
    print("=== 总结 ===")
    print(f"状态：{result['status']}")
    if result["status"] == "available":
        print(f"债市核心指数：{result['bond']['score']}（{result['bond']['tone']}）")
        print(f"短期情绪：{result['sentiment']['temperature']}")
        print(f"综合判断：{result['summary'].split('综合判断：')[-1]}")
    else:
        print(result["summary"])
        for error in result["data_quality"]["blocking_errors"]:
            print(f"- {error}")
    print(f"结果已保存：{args.output}")
    return 0 if result["status"] == "available" else 2


if __name__ == "__main__":
    raise SystemExit(main())
