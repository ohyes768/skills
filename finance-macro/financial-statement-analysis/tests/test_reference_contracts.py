"""Public references must cover runtime identifiers without source-code browsing."""

import ast
import re
from pathlib import Path

from calculate_metrics import calculate_metrics

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


def test_entrypoint_routes_to_both_contracts():
    entry = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    for name in ("metric-catalog.md", "independent-review-contract.md"):
        assert f"references/{name}" in entry
        assert name in (REFS / "report-inputs-example.md").read_text(encoding="utf-8")
