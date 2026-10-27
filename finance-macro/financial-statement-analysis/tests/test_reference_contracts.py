"""Public references must cover runtime identifiers without source-code browsing."""

import ast
import json
import re
from decimal import Decimal
from pathlib import Path

from calculate_metrics import _RED_FLAG_THRESHOLDS, calculate_metrics
from financial_schema import METRIC_CONTRACTS
from render_report import _CLAIM_TYPES, _PLACEHOLDER_RE, _check_static_text

ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "references"


def test_metric_catalog_matches_emitted_ids():
    emitted = {m["metric_id"] for m in calculate_metrics({"facts": []})["metrics"]}
    catalog = (REFS / "metric-catalog.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| `([a-z_]+)` \|", catalog, re.MULTILINE))
    assert documented == emitted


def test_review_contract_covers_all_check_labels():
    tree = ast.parse((ROOT / "scripts/verify_report_independent.py").read_text(encoding="utf-8"))
    emitted = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            emitted.update(re.findall(r"\b[A-E]\d+\b", node.value))
    contract = (REFS / "independent-review-contract.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| (\w\d+) \|", contract, re.MULTILINE))
    assert emitted == documented


def test_red_flag_table_matches_thresholds_and_ids():
    contract = (REFS / "artifact-contracts.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `([a-z_]+)` \| [^|]+ \| ([^|]+) \|", contract, re.MULTILINE)
    emitted = {f["flag_id"] for f in calculate_metrics({"facts": []})["red_flags"]}
    assert {flag_id for flag_id, _ in rows} == emitted
    documented = {}
    for _, cell in rows:
        match = re.fullmatch(r"\s*`([a-z_]+)` = ([\d.]+)\s*", cell)
        if match:
            documented[match.group(1)] = Decimal(match.group(2))
    assert documented == _RED_FLAG_THRESHOLDS


def test_claim_types_documented():
    contract = (REFS / "artifact-contracts.md").read_text(encoding="utf-8")
    match = re.search(r"`claim_type` \(([a-z_ /]+)\)", contract)
    assert match and set(match.group(1).split(" / ")) == _CLAIM_TYPES


def test_fact_metric_lists_match_schema():
    text = (REFS / "fact-inputs-example.md").read_text(encoding="utf-8")
    section = text.split("## 指标与期间类型", 1)[1]
    documented = {}
    for kind in ("duration", "instant"):
        block = re.search(rf"^{kind}（[^）]*）：(.*?)(?:\n\n|\Z)", section, re.MULTILINE | re.DOTALL)
        documented[kind] = set(re.findall(r"`([a-z_]+)`", block.group(1)))
    expected = {kind: {m for m, c in METRIC_CONTRACTS.items() if c["period_kind"] == kind}
                for kind in ("duration", "instant")}
    assert documented == expected


def test_report_skeleton_uses_known_metrics_and_clean_static_text():
    skeleton = json.loads((REFS / "report-spec-skeleton.json").read_text(encoding="utf-8"))
    emitted = {m["metric_id"] for m in calculate_metrics({"facts": []})["metrics"]}
    used = set(re.findall(r'"metric_id": "([a-z_]+)"', json.dumps(skeleton)))
    assert used <= emitted
    for section in skeleton["sections"]:
        for statement in section.get("statements", []):
            _check_static_text(_PLACEHOLDER_RE.sub("X", statement["template"]), {})
        for paragraph in section.get("paragraphs", []):
            _check_static_text(paragraph, {}, strict=True)
        for row in (section.get("table") or {}).get("rows", []):
            for cell in row["cells"]:
                if isinstance(cell, str):
                    _check_static_text(cell, {})


def test_entrypoint_routes_to_both_contracts():
    entry = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    for name in ("metric-catalog.md", "independent-review-contract.md"):
        assert f"references/{name}" in entry
        assert name in (REFS / "report-inputs-example.md").read_text(encoding="utf-8")
