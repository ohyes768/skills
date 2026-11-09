"""Draft/result contract validation, finalize and check CLI.

Offline, stdlib only. Reads nothing from evidence origins, never touches the
network, and never invents prices: all derived values come from valuation_math.
Errors raise ValueError; the CLI maps any failure to exit=2 on stderr with an
empty stdout.
"""
from __future__ import annotations

import argparse
import copy
import itertools
import json
import os
import re
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from valuation_math import NUMBER, decimal_value, evaluate, level_metrics, round_price

FORMULA_VERSION = "1"

SCHEMA_VERSION = "1.0.0"
STATUSES = ("ready", "insufficient_data", "blocked", "not_applicable")
KINDS = ("official", "data_platform", "research", "media", "upstream", "input")
VERIFICATIONS = ("read", "reused", "unverified")
METHODS = ("pe_multiple", "pb_multiple", "equity_cashflow_pv")
LEVELS = ("heavy_position", "add_position", "reduce_position", "full_exit")
SCENARIOS = ("bear", "base", "bull")
DRAFT_KEYS = ("code", "name", "as_of", "currency", "status", "summary", "confidence",
              "risks", "invalidation_conditions", "data_gaps", "evidence", "analysis",
              "valuation")
STOCK_KEYS = ("code", "name", "as_of", "currency")
ANALYSIS_KEYS = ("business", "normalization", "dividend", "valuation", "risk")
EVIDENCE_KEYS = ("id", "title", "kind", "origin", "locator", "period", "published_at",
                 "accessed_at", "verification")
METRIC_KEYS = ("ttm_eps", "common_bvps", "annual_dps", "dps_basis", "period",
               "share_basis", "evidence_ids")
VALUATION_KEYS = ("primary_method", "anchor", "scenarios", "decisions", "metric_inputs",
                  "sensitivity")
DERIVED_KEYS = ("formula_version", "calculated", "scenario_values", "sensitivity_values",
                "level_metrics")
RESULT_KEYS = ("schema_version", "skill_version", "code", "name", "currency", "as_of",
               "status", "levels", "valuation", "evidence", "data_gaps", "confidence",
               "risks", "invalidation_conditions", "summary", "analysis", "report_md")
CONFIDENCE_LEVELS = ("high", "medium", "low", "unavailable")
DPS_BASES = ("ttm_ordinary", "forward_ordinary", "none")
DATE_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
CODE_RE = re.compile(r"[0-9]{6}\Z")
SCHEME_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*):")
DRIVE_RE = re.compile(r"[A-Za-z]:[\\/]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
VERSION_RE = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}\Z")
QUANTUM = Decimal("0.0001")


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _text(value, label):
    _require(isinstance(value, str) and value.strip(), f"{label}: non-empty text required")
    return value


def _chinese_text(value, label):
    _text(value, label)
    _require(isinstance(value, str) and CJK_RE.search(value), f"{label}: 中文说明必填")
    return value


def _strict_date(value, label):
    _require(isinstance(value, str) and DATE_RE.fullmatch(value),
             f"{label}: date must be strict YYYY-MM-DD")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label}: not a real calendar date") from exc


def _number_or_null(value, label):
    if value is None:
        return None
    return decimal_value(value, label)


def _string_list(value, label):
    _require(isinstance(value, list), f"{label}: expected an array of strings")
    for item in value:
        _text(item, label)
    return value


def _exact_keys(value, keys, label):
    _require(isinstance(value, dict) and set(value) == set(keys),
             f"{label}: expected exactly {sorted(keys)}, got {sorted(value) if isinstance(value, dict) else type(value).__name__}")


def _id_refs(value, known, label):
    _require(isinstance(value, list) and value and all(isinstance(i, str) and i for i in value),
             f"{label}: non-empty evidence_ids required")
    unknown = [i for i in value if i not in known]
    _require(not unknown, f"{label}: unknown evidence ids {unknown}")
    return value


def read_skill_version(skill_path):
    """Read metadata.version from the SKILL.md frontmatter; never hardcode it."""
    try:
        text = Path(skill_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"SKILL.md unreadable: {exc}") from exc
    match = re.match(r"---\r?\n(.*?)\r?\n---", text, re.DOTALL)
    _require(match, "SKILL.md: YAML frontmatter block required")
    version = re.search(
        r"(?m)^metadata:[ \t]*\r?\n[ \t]+version:[ \t]*[\"']?([0-9][0-9A-Za-z._-]*)[\"']?[ \t]*\r?$",
        match.group(1))
    _require(version, "SKILL.md: metadata.version required in frontmatter")
    _require(VERSION_RE.fullmatch(version.group(1)),
             f"SKILL.md: unsupported version format {version.group(1)!r}")
    return version.group(1)


def _validate_stock(stock):
    _require(isinstance(stock, dict), "stock: expected object")
    _exact_keys(stock, STOCK_KEYS, "stock")
    _require(isinstance(stock["code"], str) and CODE_RE.fullmatch(stock["code"]),
             "stock.code: six ASCII digits required")
    _text(stock["name"], "stock.name")
    _strict_date(stock["as_of"], "stock.as_of")
    _require(stock["currency"] == "CNY", "stock.currency: only CNY is supported")
    return stock


def _check_origin(origin):
    """Validate where evidence came from without touching the network or disk.

    Allowed: inline chat material, http(s) URLs, absolute Windows/UNC/local paths.
    Everything else (unknown schemes, bare "https://", relative paths with a
    colon) is rejected so fabricated URLs and executable protocols cannot enter.
    """
    _text(origin, "evidence.origin")
    if origin.startswith("inline:"):
        _require(len(origin) > len("inline:"), "evidence.origin: inline:<date>:<描述> required")
        return
    scheme = SCHEME_RE.match(origin)
    if scheme and not DRIVE_RE.match(origin):
        # A scheme longer than one letter (https:, file:) is a protocol; a
        # single-letter scheme is a Windows drive like F:/ and stays a path.
        if len(scheme.group(1)) > 1:
            _require(scheme.group(1).lower() in ("http", "https"),
                     f"evidence.origin: protocol {scheme.group(1)} prohibited")
            _require(origin.rstrip() != f"{scheme.group(1)}://",
                     "evidence.origin: URL must point somewhere")
        else:
            _require(origin[0:1] in ("/", "\\"),
                     "evidence.origin: relative path with colon is ambiguous")
    elif not DRIVE_RE.match(origin) and origin[0:1] not in ("/", "\\"):
        _require(not scheme, "evidence.origin: relative path with colon is ambiguous")


def _validate_evidence(draft, as_of):
    evidence = draft["evidence"]
    _require(isinstance(evidence, list), "evidence: expected array")
    ids = set()
    for index, item in enumerate(evidence):
        label = f"evidence[{index}]"
        _exact_keys(item, EVIDENCE_KEYS, label)
        _text(item["id"], f"{label}.id")
        _require(item["id"] not in ids, f"{label}.id: duplicate id {item['id']}")
        ids.add(item["id"])
        _text(item["title"], f"{label}.title")
        _require(item["kind"] in KINDS, f"{label}.kind: unsupported")
        _check_origin(item["origin"])
        _text(item["locator"], f"{label}.locator")
        _text(item["period"], f"{label}.period")
        for field in ("published_at", "accessed_at"):
            if item[field] is not None:
                _strict_date(item[field], f"{label}.{field}")
        if item["published_at"] is not None:
            _require(_strict_date(item["published_at"], f"{label}.published_at") <= as_of,
                     f"{label}.published_at: disclosure must not be later than as_of")
        _require(item["verification"] in VERIFICATIONS, f"{label}.verification: unsupported")
    return ids


def _model_entry(entry, label, primary_method, known_ids, keys=("model", "rationale", "evidence_ids")):
    _exact_keys(entry, keys, label)
    _chinese_text(entry["rationale"], f"{label}.rationale")
    _id_refs(entry["evidence_ids"], known_ids, f"{label}.evidence_ids")
    model = entry["model"]
    _require(isinstance(model, dict) and model.get("method") == primary_method,
             f"{label}.model: must use primary_method {primary_method}")
    return model


def _fingerprint(node):
    """Order-independent structural fingerprint; numeric strings compare by value
    and a model without margin is treated as margin 0."""
    if isinstance(node, bool):
        return ("bool", node)
    if isinstance(node, (int, Decimal)):
        return ("num", decimal_value(node, "model parameter"))
    if isinstance(node, str):
        if NUMBER.fullmatch(node):
            return ("num", decimal_value(node, "model parameter"))
        return ("str", node)
    if isinstance(node, list):
        return ("list", tuple(_fingerprint(item) for item in node))
    if isinstance(node, dict):
        fields = {key: _fingerprint(value) for key, value in node.items()}
        if "method" in fields and "margin" not in fields:
            fields["margin"] = ("num", Decimal(0))
        return ("dict", frozenset(fields.items()))
    raise ValueError("model: unsupported value type")


def _validate_valuation(valuation, evidence_ids):
    _require(isinstance(valuation, dict), "valuation: ready requires the model object")
    _exact_keys(valuation, VALUATION_KEYS, "valuation")
    primary = valuation["primary_method"]
    _require(primary in METHODS, "valuation.primary_method: unsupported")
    _chinese_text(valuation["anchor"], "valuation.anchor")

    _exact_keys(valuation["scenarios"], SCENARIOS, "valuation.scenarios")
    scenario_models = {key: _model_entry(valuation["scenarios"][key],
                                         f"scenarios.{key}", primary, evidence_ids)
                       for key in SCENARIOS}
    _exact_keys(valuation["decisions"], LEVELS, "valuation.decisions")
    decision_models = {key: _model_entry(valuation["decisions"][key],
                                         f"decisions.{key}", primary, evidence_ids)
                       for key in LEVELS}
    shared_field = {"pe_multiple": "eps", "pb_multiple": "bvps"}.get(primary)
    if shared_field:
        shared = {_fingerprint(decision_models[key][shared_field]) for key in LEVELS}
        _require(len(shared) == 1,
                 f"decisions: all four points must share one {shared_field}")
    _exact_keys(valuation["metric_inputs"], METRIC_KEYS, "valuation.metric_inputs")
    metrics = valuation["metric_inputs"]
    for field in ("ttm_eps", "common_bvps"):
        _number_or_null(metrics[field], f"metric_inputs.{field}")
    dps = _number_or_null(metrics["annual_dps"], "metric_inputs.annual_dps")
    if dps is not None:
        _require(dps >= 0, "metric_inputs.annual_dps: must be nonnegative")
        _require(metrics["dps_basis"] in DPS_BASES[:2],
                 "metric_inputs.dps_basis: DPS present, basis cannot be none")
    else:
        _require(metrics["dps_basis"] in DPS_BASES, "metric_inputs.dps_basis: unsupported")
    _text(metrics["period"], "metric_inputs.period")
    _text(metrics["share_basis"], "metric_inputs.share_basis")
    metric_values_present = any(metrics[f] is not None for f in ("ttm_eps", "common_bvps", "annual_dps"))
    if metric_values_present:
        _id_refs(metrics["evidence_ids"], evidence_ids, "metric_inputs.evidence_ids")
    else:
        _require(isinstance(metrics["evidence_ids"], list),
                 "metric_inputs.evidence_ids: expected array")

    sensitivity = valuation["sensitivity"]
    _require(isinstance(sensitivity, list) and 2 <= len(sensitivity) <= 8,
             "valuation.sensitivity: expected 2..8 items")
    for index, item in enumerate(sensitivity):
        label = f"sensitivity[{index}]"
        _exact_keys(item, ("label", "base_level", "model", "rationale", "evidence_ids"), label)
        _text(item["label"], f"{label}.label")
        _require(item["base_level"] in LEVELS, f"{label}.base_level: unknown decision level")
        model = _model_entry(item, label, primary, evidence_ids,
                             keys=("label", "base_level", "model", "rationale", "evidence_ids"))
        _require(_fingerprint(model) != _fingerprint(decision_models[item["base_level"]]),
                 f"{label}.model: must change at least one parameter versus its base level")
    return scenario_models, decision_models, metrics


def _validate_draft(draft, stock):
    _require(isinstance(draft, dict), "draft: expected object")
    _exact_keys(draft, DRAFT_KEYS, "draft")
    for field in STOCK_KEYS:
        _require(draft[field] == stock[field],
                 f"draft.{field}: must match stock.json exactly")
    status = draft["status"]
    _require(status in STATUSES, "draft.status: unsupported status")
    _chinese_text(draft["summary"], "draft.summary")
    _exact_keys(draft["confidence"], ("level", "reason"), "draft.confidence")
    _require(draft["confidence"]["level"] in CONFIDENCE_LEVELS,
             "draft.confidence.level: unsupported")
    _chinese_text(draft["confidence"]["reason"], "draft.confidence.reason")
    _string_list(draft["risks"], "draft.risks")
    _require(isinstance(draft["invalidation_conditions"], list),
             "draft.invalidation_conditions: expected array")
    for item in draft["invalidation_conditions"]:
        _text(item, "draft.invalidation_conditions item")
    _string_list(draft["data_gaps"], "draft.data_gaps")
    _exact_keys(draft["analysis"], ANALYSIS_KEYS, "draft.analysis")
    for key in ANALYSIS_KEYS:
        _chinese_text(draft["analysis"][key], f"analysis.{key}")
    as_of = _strict_date(stock["as_of"], "stock.as_of")
    evidence_ids = _validate_evidence(draft, as_of)
    if status == "ready":
        usable = [item for item in draft["evidence"] if item["verification"] in ("read", "reused")]
        _require(usable, "ready: at least one read/reused evidence item is required")
        _validate_valuation(draft["valuation"], evidence_ids)
    else:
        _require(draft["valuation"] is None,
                 f"valuation: {status} requires null valuation")
        _require(draft["risks"] or draft["data_gaps"],
                 f"{status}: risks or data_gaps must explain the state")


def _compute_ready(draft):
    valuation = draft["valuation"]
    metrics = valuation["metric_inputs"]
    scenario_values = {}
    scenario_exact = {}
    for key in SCENARIOS:
        exact = evaluate(valuation["scenarios"][key]["model"])
        scenario_exact[key] = exact
        scenario_values[key] = {"exact_price": str(exact), "price": round_price(exact)}
    _require(scenario_exact["bear"] <= scenario_exact["base"] <= scenario_exact["bull"],
             "scenarios: unrounded values must satisfy bear<=base<=bull")

    calculated = {}
    rounded_prices = {}
    for key in LEVELS:
        exact = evaluate(valuation["decisions"][key]["model"])
        price = round_price(exact)
        calculated[key] = {"exact_price": str(exact), "price": price}
        rounded_prices[key] = price
    for lower, higher in itertools.pairwise(LEVELS):
        _require(rounded_prices[lower] < rounded_prices[higher],
                 f"decisions: rounded {lower} price must be strictly below {higher}")

    levels = {}
    level_metrics_out = {}
    for key in LEVELS:
        ratios = level_metrics(rounded_prices[key], metrics["ttm_eps"],
                               metrics["common_bvps"], metrics["annual_dps"])
        levels[key] = {"price": rounded_prices[key], "pe": ratios["pe"], "pb": ratios["pb"]}
        level_metrics_out[key] = {"dividend_yield_pct": ratios["dividend_yield_pct"]}

    sensitivity_values = []
    for item in valuation["sensitivity"]:
        exact = evaluate(item["model"])
        base_exact = Decimal(calculated[item["base_level"]]["exact_price"])
        delta = ((exact - base_exact) / base_exact * 100).quantize(QUANTUM)
        sensitivity_values.append({"label": item["label"], "base_level": item["base_level"],
                                   "exact_price": str(exact), "price": round_price(exact),
                                   "delta_pct": delta})

    derived = {"formula_version": FORMULA_VERSION, "calculated": calculated,
               "scenario_values": scenario_values, "sensitivity_values": sensitivity_values,
               "level_metrics": level_metrics_out}
    audit = copy.deepcopy(valuation)
    for entry in list(audit["scenarios"].values()) + list(audit["decisions"].values()) + audit["sensitivity"]:
        entry["model"].setdefault("margin", "0")
    return dict(sorted({**audit, **derived}.items())), levels


def render_report(result):
    lines = [f"# 四挡位估值报告：{result['name']}（{result['code']}）", "",
             f"- 截止日期（as_of）：{result['as_of']}；币种：{result['currency']}；状态：{result['status']}",
             f"- 信心（{result['confidence']['level']}）：{result['confidence']['reason']}", "",
             "## 摘要", "", result["summary"], ""]
    valuation = result["valuation"]
    if result["status"] == "ready":
        lines += ["## 四挡位观察线（PE 采用 TTM 口径，非正常化口径）", "",
                  "| 挡位 | 价格 | PE(TTM) | PB | 股息率(%) |", "|---|---|---|---|---|"]
        for key in LEVELS:
            level = result["levels"][key]
            yield_pct = valuation["level_metrics"][key]["dividend_yield_pct"]
            pe = "-" if level["pe"] is None else format(level["pe"], ".4f")
            pb = "-" if level["pb"] is None else format(level["pb"], ".4f")
            pct = "-" if yield_pct is None else format(yield_pct, ".4f")
            lines.append(f"| {key} | {format(level['price'], '.2f')} | {pe} | {pb} | {pct} |")
        lines += ["", "### 估值锚", "", valuation["anchor"], "",
                  "### 情景价值（未舍入见 exact_price）", "",
                  "| 情景 | 价格 |", "|---|---|"]
        for key in SCENARIOS:
            lines.append(f"| {key} | {format(valuation['scenario_values'][key]['price'], '.2f')} |")
        lines += ["", "### 敏感性", "", "| 标签 | 基准挡位 | 价格 | 相对基准(%) |", "|---|---|---|---|"]
        for item in valuation["sensitivity_values"]:
            lines.append(f"| {item['label']} | {item['base_level']} | "
                         f"{format(item['price'], '.2f')} | {format(item['delta_pct'], '.4f')} |")
        lines += ["", "### 各挡位参数理由", ""]
        for key in LEVELS:
            entry = valuation["decisions"][key]
            lines.append(f"- {key}：{entry['rationale']}")
    else:
        lines += ["## 四挡位观察线", "", "状态非 ready，不输出任何四点价格、比率或参考价。", ""]
    lines += ["", "## 分析", ""]
    for key in ANALYSIS_KEYS:
        lines += [f"### {key}", "", result["analysis"][key], ""]
    lines += ["## 证据", ""]
    for item in result["evidence"]:
        lines.append(f"- {item['id']}（{item['kind']}，{item['verification']}）：{item['title']}；"
                     f"来源 {item['origin']}；定位 {item['locator']}；期间 {item['period']}；"
                     f"披露 {item['published_at'] or '未记录'}；访问 {item['accessed_at'] or '未记录'}")
    if not result["evidence"]:
        lines.append("-（无）")
    for title, field in (("风险", "risks"), ("数据缺口", "data_gaps"),
                         ("失效条件", "invalidation_conditions")):
        lines += ["", f"## {title}", ""]
        lines += [f"- {item}" for item in result[field]] or ["-（无）"]
    lines += ["", "## 免责声明", "",
              ("本报告由脚本按固定合同生成：脚本通过不证明证据真实、参数合理或结果正确，"
               "所有价格为有条件观察线而非交易指令，不构成个性化投资建议，不构成损失下限。")]
    return "\n".join(lines)


def finalize(draft, stock, skill_path):
    """Validate draft against stock, recompute everything, return the 17-field result."""
    _validate_stock(stock)
    skill_version = read_skill_version(skill_path)
    _validate_draft(draft, stock)
    status = draft["status"]
    if status == "ready":
        valuation, levels = _compute_ready(draft)
    else:
        valuation = None
        levels = {key: {"price": None, "pe": None, "pb": None} for key in LEVELS}
    result = {
        "schema_version": SCHEMA_VERSION,
        "skill_version": skill_version,
        "code": draft["code"],
        "name": draft["name"],
        "currency": draft["currency"],
        "as_of": draft["as_of"],
        "status": status,
        "levels": levels,
        "valuation": valuation,
        "evidence": draft["evidence"],
        "data_gaps": draft["data_gaps"],
        "confidence": draft["confidence"],
        "risks": draft["risks"],
        "invalidation_conditions": draft["invalidation_conditions"],
        "summary": draft["summary"],
        "analysis": draft["analysis"],
        "report_md": "",
    }
    result["report_md"] = render_report(result)
    _require(set(result) == set(RESULT_KEYS), "internal: result key set drifted")
    return result


def check(result, stock, skill_path):
    """Recompute every derived field from the audit parameters and deep-compare."""
    _validate_stock(stock)
    read_skill_version(skill_path)
    _require(isinstance(result, dict), "result: expected object")
    _exact_keys(result, RESULT_KEYS, "result")
    _require(result["schema_version"] == SCHEMA_VERSION, "result.schema_version: mismatch")
    status = result["status"]
    _require(status in STATUSES, "result.status: unsupported")
    draft = {key: result[key] for key in DRAFT_KEYS if key in result}
    _require(set(draft) == set(DRAFT_KEYS), "result: missing audit fields for replay")
    valuation = result["valuation"]
    if status == "ready":
        _require(isinstance(valuation, dict), "result.valuation: ready requires object")
        _exact_keys(valuation, VALUATION_KEYS + DERIVED_KEYS, "result.valuation")
        _require(valuation["formula_version"] == FORMULA_VERSION, "result.valuation.formula_version: mismatch")
        draft["valuation"] = {key: copy.deepcopy(valuation[key]) for key in VALUATION_KEYS}
    else:
        _require(valuation is None, "result.valuation: non-ready requires null")
        draft["valuation"] = None
    recomputed = finalize(draft, stock, skill_path=skill_path)
    _deep_compare(recomputed, result, "$")
    return {"status": "ok", "code": stock["code"], "as_of": stock["as_of"]}


def _deep_compare(expected, actual, path):
    if isinstance(expected, bool) or isinstance(actual, bool):
        _require(type(expected) is type(actual) and expected == actual,
                 f"{path}: value differs")
        return
    if isinstance(expected, (int, Decimal)) and isinstance(actual, (int, Decimal)):
        _require(Decimal(expected) == Decimal(actual), f"{path}: numeric value differs")
        return
    _require(type(expected) is type(actual), f"{path}: type differs")
    if isinstance(expected, dict):
        _require(set(expected) == set(actual), f"{path}: key set differs")
        for key in expected:
            _deep_compare(expected[key], actual[key], f"{path}.{key}")
        return
    if isinstance(expected, list):
        _require(len(expected) == len(actual), f"{path}: length differs")
        for index, (left, right) in enumerate(zip(expected, actual)):
            _deep_compare(left, right, f"{path}[{index}]")
        return
    _require(expected == actual, f"{path}: value differs")


def dumps(obj) -> str:
    """Serialize with Decimal as exact JSON numbers; no NaN/Infinity/bool keys."""
    out: list[str] = []
    _write_json(obj, out)
    return "".join(out)


def _write_json(node, out):
    if node is None:
        out.append("null")
    elif node is True:
        out.append("true")
    elif node is False:
        out.append("false")
    elif isinstance(node, Decimal):
        if not node.is_finite():
            raise ValueError("dumps: non-finite Decimal cannot be JSON")
        out.append(str(node))
    elif isinstance(node, int):
        out.append(str(node))
    elif isinstance(node, str):
        out.append(json.dumps(node, ensure_ascii=False))
    elif isinstance(node, list):
        out.append("[")
        for index, item in enumerate(node):
            if index:
                out.append(",")
            _write_json(item, out)
        out.append("]")
    elif isinstance(node, dict):
        out.append("{")
        for index, (key, value) in enumerate(node.items()):
            _require(isinstance(key, str), "dumps: object keys must be strings")
            if index:
                out.append(",")
            out.append(json.dumps(key, ensure_ascii=False))
            out.append(":")
            _write_json(value, out)
        out.append("}")
    else:
        raise ValueError(f"dumps: unsupported type {type(node).__name__}")


def load_json(path):
    """Strict loader: no duplicate keys, no NaN/Infinity, floats stay Decimal."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc

    def pairs(items):
        keys = [key for key, _ in items]
        duplicates = {key for key in keys if keys.count(key) > 1}
        if duplicates:
            raise ValueError(f"duplicate JSON key(s): {sorted(duplicates)}")
        return dict(items)

    def constant(name):
        raise ValueError(f"non-finite JSON constant not allowed: {name}")

    return json.loads(text, parse_float=lambda value: decimal_value(value, "json number"),
                      parse_constant=constant, object_pairs_hook=pairs)


def save_atomic(path, text):
    """Write text to path atomically; on any failure keep the old file intact."""
    path = Path(path)
    handle_fd, temp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".valuation-save-",
                                            suffix=".tmp")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _same_file(left, right):
    try:
        return os.path.samefile(left, right)
    except OSError:
        return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="validate_result.py",
        description="Offline four-level valuation finalize/check tool (stdlib only).")
    subparsers = parser.add_subparsers(dest="command", required=True)
    finalize_parser = subparsers.add_parser("finalize", help="validate draft and write result")
    finalize_parser.add_argument("--input", required=True, help="draft.json path")
    finalize_parser.add_argument("--stock", required=True, help="stock.json path")
    finalize_parser.add_argument("--output", required=True, help="result.json path")
    check_parser = subparsers.add_parser("check", help="recompute and verify a result file")
    check_parser.add_argument("--input", required=True, help="result.json path")
    check_parser.add_argument("--stock", required=True, help="stock.json path")
    args = parser.parse_args(argv)
    try:
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", newline="")
        skill_path = Path(__file__).resolve().parent.parent / "SKILL.md"
        stock = load_json(args.stock)
        if args.command == "finalize":
            for guarded in (args.input, args.stock):
                if _same_file(args.output, guarded):
                    raise ValueError("output must not overwrite the draft or stock file")
            draft = load_json(args.input)
            result = finalize(draft, stock, skill_path=skill_path)
            text = dumps(result) + "\n"
            save_atomic(args.output, text)
            sys.stdout.write(text)
        else:
            result = load_json(args.input)
            receipt = check(result, stock, skill_path=skill_path)
            sys.stdout.write(dumps(receipt) + "\n")
        return 0
    except Exception as exc:  # noqa: BLE001 - CLI contract: every failure exits 2
        sys.stderr.write(f"error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
