"""Public references must cover runtime identifiers without source-code browsing."""

import ast
import re
from decimal import Decimal
from pathlib import Path

from calculate_metrics import _RED_FLAG_THRESHOLDS, calculate_metrics
from render_report import _CLAIM_TYPES

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


def test_entrypoint_routes_to_both_contracts():
    entry = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    for name in ("metric-catalog.md", "independent-review-contract.md"):
        assert f"references/{name}" in entry
        assert name in (REFS / "report-inputs-example.md").read_text(encoding="utf-8")
