"""统一阶段入口：prepare/compute/report/review，持久修复预算与质量状态。

新入口只做确定性编排：不调用模型、不修改校验规则、不重置预算。
run_state.json 是诊断状态，不是安全权威；受保护模式的最终校验由宿主控制。
退出码：0 阶段成功；1 致命合同/维护错误；2 可保留但未通过或需修复。
quality_status：verified（报告通过）/ partial（预算内可修复）/ maintenance_required。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from artifacts import read_json, write_json

STATE_SCHEMA_VERSION = 1
MAX_REPAIRS = 2
EXAMPLE_LIMIT = 5
_ISSUE_KEYS = (
    "unknown_fact_ids", "unknown_metric_ids", "unknown_evidence_ids", "out_of_range_pages",
    "value_mismatches", "missing_evidence_claims", "body_mismatches", "unclaimed_numeric_lines",
    "invalid_support", "page_mismatches",
)


def _file_sha(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_state(run_dir: Path) -> dict:
    path = run_dir / "run_state.json"
    if not path.exists():
        return {"schema_version": STATE_SCHEMA_VERSION, "stage": None,
                "repairs": {}, "quality_status": None, "input_sha256": {}}
    state = read_json(path)
    state.setdefault("repairs", {})
    state.setdefault("input_sha256", {})
    return state


def _save_state(run_dir: Path, state: dict) -> None:
    write_json(run_dir / "run_state.json", state)


def _count_issues(validation: dict) -> dict:
    return {key: len(validation.get(key, [])) for key in _ISSUE_KEYS}


def _examples(validation: dict) -> list[str]:
    examples: list[str] = []
    for key in _ISSUE_KEYS:
        for item in validation.get(key, [])[:EXAMPLE_LIMIT]:
            examples.append(f"{key}: {item}")
    return examples[:EXAMPLE_LIMIT]


def _limited(issues: list[dict]) -> tuple[list[str], int]:
    """有限错误反馈：示例 + 总数，完整清单已在落盘文件中。"""
    rendered = [issue["error"] if isinstance(issue, dict) else str(issue)
                for issue in issues[:EXAMPLE_LIMIT]]
    return rendered, len(issues)


def _budget(state: dict, run_dir: Path, stage: str, inputs_name: str) -> tuple[int, str | None]:
    """返回剩余修复次数（初检不计入修复）；输入未变时幂等重放不消耗预算。"""
    input_sha = _file_sha(run_dir / inputs_name)
    last_sha = state["input_sha256"].get(stage)
    record = state["repairs"].setdefault(stage, {"count": 0})
    if input_sha is not None and input_sha != last_sha:
        if record["count"] >= MAX_REPAIRS + 1:
            return 0, (f"{stage} repair budget exhausted ({MAX_REPAIRS} repairs used); "
                       "start a new run directory or request maintenance")
        record["count"] += 1
        state["input_sha256"][stage] = input_sha
    remaining = MAX_REPAIRS - max(record["count"] - 1, 0)
    return remaining, None


def cmd_prepare(url: str, run_dir: Path) -> tuple[dict, int]:
    from fetch_pdf import FetchError, fetch_pdf
    from inspect_pdf import inspect_pdf

    run_dir = Path(run_dir)
    if run_dir.exists() and (run_dir / "scripts").exists():
        result = {"status": "failed", "stage": "prepare",
                  "artifacts": {}, "issues": ["run-dir must not be the skill source directory"]}
        return result, 1
    try:
        fetch = fetch_pdf(url, run_dir)
    except FetchError as exc:
        return ({"status": "failed", "stage": "prepare", "artifacts": {},
                 "issues": [f"fetch failed: {exc}"]}, 1)
    document = inspect_pdf(run_dir)
    sections = [
        {key: section[key] for key in ("section_id", "title", "start_page", "end_page",
                                       "priority", "verified")}
        for section in read_json(run_dir / "sections.json").get("sections", [])
    ]
    state = _load_state(run_dir)
    state["stage"] = "prepare"
    _save_state(run_dir, state)
    result = {
        "status": "ok", "stage": "prepare",
        "artifacts": {
            "document_json": str(run_dir / "document.json"),
            "sections_json": str(run_dir / "sections.json"),
            "source_reused": fetch.get("reused", False),
        },
        "issues": [],
        "document": {key: document.get(key) for key in
                     ("company_name", "stock_code", "report_type", "period",
                      "currency", "audit_status", "page_count")},
        "sections": sections,
        "next_action": ("pick key sections, run extract_sections.py, then pack_context.py "
                        "--stage map to read evidence"),
        "quality_status": "partial",
    }
    return result, 0


def cmd_compute(run_dir: Path) -> tuple[dict, int]:
    import build_financials
    from calculate_metrics import calculate_metrics as compute_metrics
    from financial_schema import validate_financials

    run_dir = Path(run_dir)
    state = _load_state(run_dir)
    remaining, blocked = _budget(state, run_dir, "compute", "fact_inputs.json")
    if blocked:
        state["quality_status"] = "maintenance_required"
        _save_state(run_dir, state)
        return ({"status": "failed", "stage": "compute", "artifacts": {},
                 "issues": [blocked], "remaining_repairs": 0,
                 "quality_status": "maintenance_required"}, 2)
    inputs_path = run_dir / "fact_inputs.json"
    if not inputs_path.exists():
        return ({"status": "failed", "stage": "compute", "artifacts": {},
                 "issues": ["fact_inputs.json missing; write compact fact inputs first"],
                 "remaining_repairs": remaining, "quality_status": "partial"}, 1)
    financials, mapping = build_financials.build_financials(run_dir, read_json(inputs_path))
    write_json(run_dir / "mapping_validation.json", mapping)
    if financials is None:
        errors, total = _limited(mapping["issues"])
        state["stage"] = "compute"
        state["quality_status"] = "partial"
        _save_state(run_dir, state)
        return ({"status": "repair_needed", "stage": "compute",
                 "artifacts": {"mapping_validation": str(run_dir / "mapping_validation.json")},
                 "issues": errors, "error_counts": {"mapping_issues": total},
                 "remaining_repairs": remaining, "quality_status": "partial",
                 "next_action": "fix fact_inputs.json per mapping_validation.json and rerun compute",
                 }, 2)
    write_json(run_dir / "financials.json", financials)
    contract_errors = validate_financials(financials)
    if contract_errors:
        return ({"status": "failed", "stage": "compute", "artifacts": {},
                 "issues": [f"contract violation: {e['fact_id']} {e['field']}: {e['error']}"
                            for e in contract_errors],
                 "remaining_repairs": remaining, "quality_status": "maintenance_required"}, 1)
    document = read_json(run_dir / "financials.json")
    metrics_doc = compute_metrics(document)
    write_json(run_dir / "metrics.json", metrics_doc)
    write_json(run_dir / "validation.json",
               {"schema_version": 1, "checks": metrics_doc["validation"]})
    state["stage"] = "compute"
    state["quality_status"] = "partial"
    _save_state(run_dir, state)
    computed = sum(1 for m in metrics_doc["metrics"] if m["status"] == "computed")
    unresolved = [m for m in metrics_doc["metrics"] if m["status"] != "computed"]
    checks = metrics_doc["validation"]
    problems = [c for c in checks if c["status"] not in ("passed", "not_applicable")]
    issues = [f"{c['check_id']}: {c['status']}" for c in problems]
    result = {
        "status": "ok" if not issues else "partial",
        "stage": "compute",
        "artifacts": {"metrics_json": str(run_dir / "metrics.json"),
                      "validation_json": str(run_dir / "validation.json")},
        "issues": issues,
        "metric_counts": {"computed": computed, "unresolved": len(unresolved)},
        "unresolved_examples": [
            {"metric_id": m["metric_id"], "status": m["status"], "reason": m["reason"]}
            for m in unresolved[:EXAMPLE_LIMIT]
        ],
        "remaining_repairs": remaining,
        "quality_status": "partial",
        "next_action": "write report_inputs.json with bindings into facts/metrics, then run report",
    }
    return result, (0 if not issues else 2)


def cmd_report(run_dir: Path) -> tuple[dict, int]:
    import render_report
    import validate_report

    run_dir = Path(run_dir)
    state = _load_state(run_dir)
    remaining, blocked = _budget(state, run_dir, "report", "report_inputs.json")
    if blocked:
        state["quality_status"] = "maintenance_required"
        _save_state(run_dir, state)
        return ({"status": "failed", "stage": "report", "artifacts": {},
                 "issues": [blocked], "remaining_repairs": 0,
                 "quality_status": "maintenance_required"}, 2)
    inputs_path = run_dir / "report_inputs.json"
    if not inputs_path.exists():
        return ({"status": "failed", "stage": "report", "artifacts": {},
                 "issues": ["report_inputs.json missing; write structured report inputs first"],
                 "remaining_repairs": remaining, "quality_status": "partial"}, 1)
    try:
        inputs = read_json(inputs_path)
        markdown, claims, issues = render_report.render_report(run_dir, inputs)
    except (OSError, ValueError) as exc:
        state["quality_status"] = "maintenance_required"
        _save_state(run_dir, state)
        return ({"status": "failed", "stage": "report", "artifacts": {},
                 "issues": [f"render failed: {exc}"],
                 "quality_status": "maintenance_required"}, 1)
    if issues:
        write_json(run_dir / "render_issues.json", {"schema_version": 1, "issues": issues})
        errors, total = _limited(issues)
        state["stage"] = "report"
        state["quality_status"] = "partial"
        _save_state(run_dir, state)
        return ({"status": "repair_needed", "stage": "report",
                 "artifacts": {"render_issues": str(run_dir / "render_issues.json")},
                 "issues": errors, "error_counts": {"render_issues": total},
                 "remaining_repairs": remaining, "quality_status": "partial",
                 "next_action": "fix report_inputs.json per render_issues.json and rerun report"}, 2)
    write_json(run_dir / "report_claims.json", {"schema_version": 1, "claims": claims})
    (run_dir / "analysis.md").write_text(markdown, encoding="utf-8", newline="\n")
    validation = validate_report.validate_report(run_dir)
    state["stage"] = "report"
    if validation["passed"]:
        state["quality_status"] = "verified"
        _save_state(run_dir, state)
        return ({"status": "ok", "stage": "report",
                 "artifacts": {"analysis_md": str(run_dir / "analysis.md"),
                               "report_claims_json": str(run_dir / "report_claims.json"),
                               "report_validation": str(run_dir / "report_validation.json")},
                 "issues": [], "remaining_repairs": remaining,
                 "quality_status": "verified",
                 "next_action": "semantic review by the agent; publishing belongs to the caller"}, 0)
    state["quality_status"] = "partial"
    _save_state(run_dir, state)
    errors, _total = _examples(validation), sum(_count_issues(validation).values())
    return ({"status": "repair_needed", "stage": "report",
             "artifacts": {"report_validation": str(run_dir / "report_validation.json")},
             "issues": errors, "error_counts": _count_issues(validation),
             "remaining_repairs": remaining, "quality_status": "partial",
             "next_action": ("fix report_inputs.json bindings; validate_report details are in "
                             "report_validation.json")}, 2)


def cmd_review(run_dir: Path) -> tuple[dict, int]:
    run_dir = Path(run_dir)
    state = _load_state(run_dir)
    quality = state.get("quality_status")
    artifacts: dict[str, str] = {}
    for name in ("document.json", "sections.json", "financials.json", "metrics.json",
                 "mapping_validation.json", "analysis.md", "report_claims.json",
                 "report_validation.json", "run_state.json"):
        path = run_dir / name
        if path.exists():
            artifacts[name] = str(path)
    validation_summary = None
    validation_path = run_dir / "report_validation.json"
    if validation_path.exists():
        validation = read_json(validation_path)
        validation_summary = {"passed": validation.get("passed"),
                              "error_counts": _count_issues(validation)}
    stage = state.get("stage")
    report_repairs = state["repairs"].get("report", {}).get("count", 0)
    if quality == "verified":
        status, code = "ok", 0
    elif quality == "maintenance_required":
        status, code = "failed", 1
    else:
        status, code = "partial", 2
    return ({"status": status, "stage": stage, "artifacts": artifacts, "issues": [],
             "quality_status": quality, "report_validation": validation_summary,
             "remaining_repairs": MAX_REPAIRS - max(report_repairs - 1, 0),
             "next_action": None if quality == "verified" else
             "resume the stage that last emitted repair_needed"}, code)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="财报分析统一阶段入口")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="下载、索引并返回章节定位包")
    prepare.add_argument("--url", required=True)
    prepare.add_argument("--run-dir", required=True)

    compute = subparsers.add_parser("compute", help="fact_inputs.json → financials + metrics")
    compute.add_argument("--run-dir", required=True)

    report = subparsers.add_parser("report", help="report_inputs.json → analysis + claims + 校验")
    report.add_argument("--run-dir", required=True)

    review = subparsers.add_parser("review", help="只读当前状态与修复余量")
    review.add_argument("--run-dir", required=True)

    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    if args.command == "prepare":
        result, code = cmd_prepare(args.url, run_dir)
    elif args.command == "compute":
        result, code = cmd_compute(run_dir)
    elif args.command == "report":
        result, code = cmd_report(run_dir)
    else:
        result, code = cmd_review(run_dir)
    print(json.dumps(result, ensure_ascii=False, default=str))
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
