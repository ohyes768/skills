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
DEFAULT_OUTPUT_PATH = SKILL_ROOT / "macro_index_data.json"


@dataclass(frozen=True)
class DimensionConfig:
    folder: str
    title: str
    core: bool
    candidate_files: tuple[str, ...]


DIMENSIONS: dict[str, DimensionConfig] = {
    "monetary_policy": DimensionConfig(
        folder="monetary-policy-skill",
        title="货币政策",
        core=True,
        candidate_files=("macro_signal.json", "monetary_policy_data.json"),
    ),
    "money_supply": DimensionConfig(
        folder="money-supply-skill",
        title="信用扩张",
        core=True,
        candidate_files=("macro_signal.json", "money_supply_data.json", "data/money_supply_latest.json"),
    ),
    "entity_economy": DimensionConfig(
        folder="entity-economy-skill",
        title="经济运行",
        core=True,
        candidate_files=("macro_signal.json", "entity_economy_data.json"),
    ),
    "inflation": DimensionConfig(
        folder="inflation-skill",
        title="通胀环境",
        core=True,
        candidate_files=("macro_signal.json", "inflation_data.json", "data/2026-03/inflation.json"),
    ),
    "exchange_rate": DimensionConfig(
        folder="exchange-rate-skill",
        title="外部压力",
        core=True,
        candidate_files=("macro_signal.json", "exchange_rate_data.json"),
    ),
    "risk_appetite": DimensionConfig(
        folder="risk-appetite-skill",
        title="市场情绪",
        core=False,
        candidate_files=("macro_signal.json", "risk_data.json"),
    ),
}


MACRO_WEIGHTS = {
    "monetary_policy": 0.20,
    "money_supply": 0.20,
    "entity_economy": 0.25,
    "inflation": 0.15,
    "exchange_rate": 0.20,
}


def run_assessment(
    skills_root: Path = DEFAULT_SKILLS_ROOT,
    output_path: Path | None = None,
    today: date | None = None,
    max_age_days: int = 45,
) -> dict[str, Any]:
    today = today or datetime.now(UTC).date()
    signals = load_all_signals(skills_root=skills_root, today=today, max_age_days=max_age_days)
    data_quality = build_data_quality(signals)
    blocking = data_quality["blocking_errors"]

    if blocking:
        result = {
            "status": "unavailable",
            "summary": "本周判断不可用：关键数据缺失、过期或没有明确评分。",
            "data_quality": data_quality,
            "macro": {"score": None, "tone": "不可用", "weights": MACRO_WEIGHTS},
            "sentiment": build_sentiment(signals.get("risk_appetite")),
            "dimensions": signals,
            "macro_data_details": build_macro_data_details(signals),
            "generated_at": now_utc(),
        }
    else:
        macro = build_macro_view(signals)
        sentiment = build_sentiment(signals.get("risk_appetite"))
        result = {
            "status": "available",
            "summary": build_summary(macro, sentiment),
            "data_quality": data_quality,
            "macro": macro,
            "sentiment": sentiment,
            "dimensions": signals,
            "macro_data_details": build_macro_data_details(signals),
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
    skill_dir = skills_root / config.folder
    checked_paths = [str(skill_dir / candidate) for candidate in config.candidate_files]

    for candidate in config.candidate_files:
        path = skill_dir / candidate
        if not path.exists():
            continue

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return unavailable_signal(name, config, path, checked_paths, f"JSON无法读取：{exc}")

        signal = extract_signal(name, config, payload, path)
        signal["checked_paths"] = checked_paths
        add_freshness(signal, today=today, max_age_days=max_age_days)
        return signal

    return unavailable_signal(name, config, None, checked_paths, "未找到该维度的输出文件")


def unavailable_signal(
    name: str,
    config: DimensionConfig,
    path: Path | None,
    checked_paths: list[str],
    error: str,
) -> dict[str, Any]:
    return {
        "dimension": name,
        "title": config.title,
        "core": config.core,
        "status": "missing",
        "score": None,
        "conclusion": None,
        "data_date": None,
        "source_file": str(path) if path else None,
        "checked_paths": checked_paths,
        "errors": [error],
    }


def extract_signal(name: str, config: DimensionConfig, payload: dict[str, Any], path: Path) -> dict[str, Any]:
    score = find_score(payload)
    conclusion = find_first_text(payload, ("conclusion", "summary", "tone", "status", "suggestion"))
    data_date = find_first_text(payload, ("data_date", "as_of_date", "published_at", "month", "fetched_at"))
    errors = normalize_errors(payload.get("errors"))

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
        "details": extract_details(payload),
    }


def extract_details(payload: dict[str, Any]) -> dict[str, Any]:
    details = payload.get("details")
    if isinstance(details, dict):
        return details

    score_block = payload.get("score")
    if isinstance(score_block, dict):
        raw_data = score_block.get("raw_data")
        if isinstance(raw_data, dict):
            return raw_data

    data_block = payload.get("data")
    if isinstance(data_block, dict):
        return data_block

    return {}


def find_score(payload: dict[str, Any]) -> float | None:
    for key in ("score", "total_score", "composite_score"):
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return float(value)

    score_block = payload.get("score")
    if isinstance(score_block, dict):
        for key in ("total_score", "composite_score", "score"):
            value = score_block.get(key)
            if isinstance(value, (int, float)):
                return float(value)

    data_block = payload.get("data")
    if isinstance(data_block, dict):
        for key in ("score", "total_score", "composite_score"):
            value = data_block.get(key)
            if isinstance(value, (int, float)):
                return float(value)

    return None


def find_first_text(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value is not None:
            return str(value)

    for nested_key in ("score", "data"):
        nested = payload.get(nested_key)
        if isinstance(nested, dict):
            for key in keys:
                value = nested.get(key)
                if value is not None:
                    return str(value)

    return None


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
    missing = []
    stale = []
    invalid = []
    warnings = []
    blocking_errors = []

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


def build_macro_data_details(signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
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


def build_macro_view(signals: dict[str, dict[str, Any]]) -> dict[str, Any]:
    friendly_scores = {
        "monetary_policy": round(signals["monetary_policy"]["score"], 2),
        "money_supply": round(signals["money_supply"]["score"], 2),
        "entity_economy": round(smooth_score(signals["entity_economy"]["score"], ECONOMY_CURVE), 2),
        "inflation": round(smooth_score(signals["inflation"]["score"], INFLATION_CURVE), 2),
        "exchange_rate": round(signals["exchange_rate"]["score"], 2),
    }
    contributions = {
        name: round(friendly_scores[name] * weight, 2)
        for name, weight in MACRO_WEIGHTS.items()
    }
    score = round(sum(contributions.values()), 2)
    return {
        "score": score,
        "tone": macro_tone(score),
        "weights": MACRO_WEIGHTS,
        "friendly_scores": friendly_scores,
        "contributions": contributions,
    }


ECONOMY_CURVE = (
    (0, 10),
    (30, 35),
    (45, 72),
    (60, 92),
    (70, 88),
    (80, 58),
    (100, 20),
)

INFLATION_CURVE = (
    (0, 10),
    (30, 45),
    (45, 92),
    (55, 98),
    (65, 80),
    (75, 45),
    (100, 0),
)


def smooth_score(score: float, curve: tuple[tuple[float, float], ...]) -> float:
    if score <= curve[0][0]:
        return curve[0][1]
    if score >= curve[-1][0]:
        return curve[-1][1]

    for (left_x, left_y), (right_x, right_y) in zip(curve, curve[1:]):
        if left_x <= score <= right_x:
            ratio = (score - left_x) / (right_x - left_x)
            return left_y + ratio * (right_y - left_y)

    raise ValueError(f"Score cannot be mapped: {score}")


def macro_tone(score: float) -> str:
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
    if not signal or signal["score"] is None or signal["status"] != "ok":
        return {
            "available": False,
            "score": None,
            "temperature": "不可用",
            "message": "市场情绪数据不可用，不参与核心宏观判断。",
        }

    score = signal["score"]
    if score >= 85:
        temperature = "过热"
        message = "情绪过热，短期回撤风险较高。"
    elif score >= 70:
        temperature = "偏热"
        message = "情绪偏热，追高需要更谨慎。"
    elif score >= 45:
        temperature = "正常"
        message = "情绪处于正常区间。"
    elif score >= 25:
        temperature = "偏冷"
        message = "情绪偏冷，若宏观改善可能出现左侧机会。"
    else:
        temperature = "恐慌"
        message = "情绪恐慌，需区分系统性风险和错杀机会。"

    return {
        "available": True,
        "score": round(score, 2),
        "temperature": temperature,
        "message": message,
    }


def build_summary(macro: dict[str, Any], sentiment: dict[str, Any]) -> str:
    if not sentiment["available"]:
        return f"宏观底色：{macro['tone']}；短期情绪：不可用；综合判断：仅能判断中期宏观环境。"

    if macro["tone"] in {"明显利好", "偏利好"} and sentiment["temperature"] in {"偏热", "过热"}:
        return f"宏观底色：{macro['tone']}；短期情绪：{sentiment['temperature']}；综合判断：中期环境改善，但短期追高风险上升。"
    if macro["tone"] in {"明显利好", "偏利好"} and sentiment["temperature"] in {"偏冷", "恐慌"}:
        return f"宏观底色：{macro['tone']}；短期情绪：{sentiment['temperature']}；综合判断：中期环境改善，市场可能仍有左侧机会。"
    if macro["tone"] in {"偏不利", "明显不利"}:
        return f"宏观底色：{macro['tone']}；短期情绪：{sentiment['temperature']}；综合判断：宏观环境拖累更重要，不宜只看情绪修复。"
    return f"宏观底色：{macro['tone']}；短期情绪：{sentiment['temperature']}；综合判断：多空交织，等待更明确的宏观方向。"


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description="Calculate A-share macro assessment.")
    parser.add_argument("--skills-root", type=Path, default=DEFAULT_SKILLS_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--max-age-days", type=int, default=45)
    args = parser.parse_args()

    result = run_assessment(
        skills_root=args.skills_root,
        output_path=args.output,
        max_age_days=args.max_age_days,
    )

    print_macro_data_details(result["macro_data_details"])
    print()
    print("=== 总结 ===")
    print(f"状态：{result['status']}")
    if result["status"] == "available":
        print(f"核心宏观指数：{result['macro']['score']}（{result['macro']['tone']}）")
        print(f"短期情绪：{result['sentiment']['temperature']}")
        print(f"综合判断：{result['summary'].split('综合判断：')[-1]}")
    else:
        print(result["summary"])
        for error in result["data_quality"]["blocking_errors"]:
            print(f"- {error}")
    print(f"结果已保存：{args.output}")
    return 0 if result["status"] == "available" else 2


def print_macro_data_details(details: dict[str, Any]) -> None:
    print("=== 宏观数据明细 ===")
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


if __name__ == "__main__":
    raise SystemExit(main())
