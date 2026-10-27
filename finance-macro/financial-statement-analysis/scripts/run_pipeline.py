"""统一阶段入口：prepare/compute/report/review，持久修复预算与质量状态。

新入口只做确定性编排：不调用模型、不修改校验规则、不重置预算。
run_state.json 是诊断状态，不是安全权威；受保护模式的最终校验由宿主控制。
退出码：0 阶段成功；1 致命合同/维护错误；2 未通过（status=repair_needed 需修复重跑，partial 可交付但不完整）。
quality_status：verified（报告通过）/ partial（预算内可修复）/ maintenance_required。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from artifacts import evidence_selected, read_json, write_json

STATE_SCHEMA_VERSION = 1
MAX_REPAIRS = 2
EXAMPLE_LIMIT = 5
MAX_FEEDBACK_CHARS = 4000
BUDGET_POLICY = ("Do not delete or edit run_state.json to reset the repair budget; "
                 "when the budget is exhausted, deliver conclusions as "
                 "quality_status=maintenance_required/partial instead of bypassing validation.")
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
    """全部校验错误单轮给全（字符限额内），修复不应被反馈窗口拖成多轮。"""
    items = [f"{key}: {item}" for key in _ISSUE_KEYS for item in validation.get(key, [])]
    rendered, _ = _limited(items, "report_validation.json")
    return rendered


def _render_issue(issue) -> str:
    if not isinstance(issue, dict):
        return str(issue)
    parts = [f"{key}={issue[key]}" for key in
             ("anchor", "statement_index", "row_label", "paragraph_index", "input_index")
             if issue.get(key) is not None]
    text = issue.get("error", str(issue))
    return f"[{' '.join(parts)}] {text}" if parts else text


def _limited(issues: list[dict], detail_file: str | None = None) -> tuple[list[str], int]:
    """按字符限额反馈全部问题；只有超限时才截断并指向落盘文件。"""
    rendered: list[str] = []
    used = 0
    for issue in issues:
        text = _render_issue(issue)
        if rendered and used + len(text) > MAX_FEEDBACK_CHARS:
            rendered.append(f"...and {len(issues) - len(rendered)} more; "
                            f"full list in {detail_file or 'the detailed validation file'}")
            break
        rendered.append(text)
        used += len(text)
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
    inspect_pdf(run_dir)
    document = read_json(run_dir / "document.json")
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
        "next_action": "pick key sections; run run_pipeline.py evidence for extraction and context",
        "quality_status": "partial",
    }
    return result, 0


def _structured_dates(document: dict) -> list[str]:
    """从 document.period 推导结构化拉取需要的三个报告期末。"""
    from fact_selection import prior_year

    period = document.get("period") or {}
    end = period.get("end")
    if not end:
        return []
    dates = {end, prior_year(end)}
    start = period.get("start")
    if start:
        from datetime import date, timedelta

        dates.add((date.fromisoformat(start) - timedelta(days=1)).isoformat())
    return sorted(dates)


def _structured_note(doc: dict) -> str | None:
    """留档仍有缺失项时生成分类回退说明；齐全返回 None。"""
    failures = doc.get("fetch_failures") or {}
    if not failures:
        return None
    no_data = sorted(k for k, v in failures.items() if v.get("reason") == "no_data")
    failed = sorted(k for k, v in failures.items() if v.get("reason") == "fetch_failed")
    parts = []
    if no_data:
        parts.append("no data (report may be undisclosed yet, or the issuer is a "
                     f"bank/insurer not covered by the general-enterprise tables): "
                     f"{', '.join(no_data)}")
    if failed:
        parts.append(f"request failed: {', '.join(failed)}")
    return ("structured fetch incomplete: " + "; ".join(parts)
            + "; fell back to PDF-only (archived parts are reused; "
              "the next run retries only the missing parts)")


def _load_or_fetch_structured(run_dir: Path) -> tuple[dict | None, str | None]:
    """加载（必要时拉取）结构化数据；不完整时返回 (None, 回退说明) 并留档已拉部分。"""
    from fetch_structured import FetchStructuredError, fetch_structured

    struct_path = run_dir / "structured_financials.json"
    if struct_path.exists():
        try:
            candidate = read_json(struct_path)
        except (OSError, ValueError) as exc:
            return None, f"structured data unreadable ({exc}); fell back to PDF-only"
        if _structured_note(candidate) is None:
            return candidate, None
        # 留档不完整（缺项留待披露）：继续走增量拉取，仅补缺失项
    document = read_json(run_dir / "document.json")
    code = document.get("stock_code")
    dates = _structured_dates(document)
    if not code or not dates:
        return None, "document lacks stock_code or period; fell back to PDF-only"
    try:
        doc = fetch_structured(code, dates, run_dir)
    except (FetchStructuredError, OSError, ValueError) as exc:
        return None, f"structured fetch failed ({exc}); fell back to PDF-only"
    note = _structured_note(doc)
    if note:
        return None, note
    return doc, None


def cmd_compute(run_dir: Path, *, spec_path: Path | None = None,
                pdf_only: bool = False) -> tuple[dict, int]:
    import build_financials
    from calculate_metrics import calculate_metrics as compute_metrics
    from financial_schema import validate_financials

    run_dir = Path(run_dir)
    if spec_path is not None:
        from build_fact_inputs_verified import build_inputs

        try:
            inputs = build_inputs(run_dir, read_json(Path(spec_path)))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return ({"status": "repair_needed", "stage": "compute",
                     "quality_status": "partial", "terminal": False,
                     "issues": [str(exc)], "next_action": "fix spec.json from source evidence"}, 2)
        write_json(run_dir / "fact_inputs.json", inputs)
    state = _load_state(run_dir)
    remaining, blocked = _budget(state, run_dir, "compute", "fact_inputs.json")
    if blocked:
        state["quality_status"] = "maintenance_required"
        _save_state(run_dir, state)
        return ({"status": "failed", "stage": "compute", "artifacts": {},
                 "issues": [blocked], "remaining_repairs": 0, "policy": BUDGET_POLICY,
                 "quality_status": "maintenance_required"}, 2)
    inputs_path = run_dir / "fact_inputs.json"
    has_inputs = inputs_path.exists()
    if not has_inputs and pdf_only:
        return ({"status": "failed", "stage": "compute", "artifacts": {},
                 "issues": ["fact_inputs.json missing; write compact fact inputs first"],
                 "remaining_repairs": remaining, "quality_status": "partial"}, 1)
    structured_note: str | None = None
    structured_doc: dict | None = None
    if not pdf_only:
        structured_doc, structured_note = _load_or_fetch_structured(run_dir)
    if structured_doc is not None:
        sample_inputs = read_json(inputs_path) if has_inputs else None
        financials, mapping = build_financials.build_financials_structured(
            run_dir, structured_doc, sample_inputs)
        write_json(run_dir / "structured_check.json", mapping.get("structured_check", {}))
    else:
        if not has_inputs:
            note = f"; {structured_note}" if structured_note else ""
            message = (f"fact_inputs.json missing and structured source unavailable{note}"
                       "; write compact fact inputs first")
            return ({"status": "failed", "stage": "compute", "artifacts": {},
                     "issues": [message],
                     "remaining_repairs": remaining, "quality_status": "partial"}, 1)
        financials, mapping = build_financials.build_financials(run_dir, read_json(inputs_path))
    if structured_note:
        mapping.setdefault("warnings", []).append(
            {"input_index": -1, "error": structured_note, "field": "structured",
             "severity": "warning"})
    write_json(run_dir / "mapping_validation.json", mapping)
    if financials is None:
        errors, total = _limited(mapping["issues"], "mapping_validation.json")
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
        "next_action": ("write a report spec and run report --spec <spec> "
                        "--independent-review; complete semantic review first"),
    }
    from pack_context import build_packet
    result["context"] = build_packet(run_dir, stage="analyze", request_id="compute-analysis")
    return result, (0 if not issues else 2)


def cmd_report(run_dir: Path, *, include_report: bool = False,
               independent_review: bool = False,
               spec_path: Path | None = None) -> tuple[dict, int]:
    import render_report
    import validate_report

    run_dir = Path(run_dir)
    if spec_path is not None:
        from report_inputs_builder import build_report_inputs

        try:
            spec_inputs = build_report_inputs(run_dir, read_json(Path(spec_path)))
        except (OSError, ValueError, KeyError, TypeError, render_report.RenderIssue) as exc:
            return ({"status": "repair_needed", "stage": "report", "terminal": False,
                     "quality_status": "partial",
                     "issues": [f"report spec construction failed: {exc}"],
                     "next_action": "fix the report spec against financials/metrics facts"}, 2)
        write_json(run_dir / "report_inputs.json", spec_inputs)
    if independent_review:
        from verify_report_inputs import verify_inputs

        try:
            preflight = verify_inputs(run_dir, read_json(run_dir / "report_inputs.json"))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            state = _load_state(run_dir)
            state.update(stage="report", quality_status="maintenance_required")
            _save_state(run_dir, state)
            return ({"status": "failed", "stage": "report", "terminal": False,
                     "quality_status": "maintenance_required", "issues": [str(exc)]}, 1)
        if preflight:
            errors, total = _limited(preflight, "report_preflight.json")
            write_json(run_dir / "report_preflight.json", {"issues": preflight})
            state = _load_state(run_dir)
            state.update(stage="report", quality_status="partial")
            _save_state(run_dir, state)
            return ({"status": "repair_needed", "stage": "report", "terminal": False,
                     "quality_status": "partial", "issues": errors,
                     "error_counts": {"preflight": total},
                     "next_action": "fix report_inputs.json before final report"}, 2)
    state = _load_state(run_dir)
    remaining, blocked = _budget(state, run_dir, "report", "report_inputs.json")
    if blocked:
        state["quality_status"] = "maintenance_required"
        _save_state(run_dir, state)
        return ({"status": "failed", "stage": "report", "artifacts": {},
                 "issues": [blocked], "remaining_repairs": 0, "policy": BUDGET_POLICY,
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
        errors, total = _limited(issues, "render_issues.json")
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
    independent = None
    if validation["passed"] and independent_review:
        from verify_report_independent import verify_run

        try:
            independent = verify_run(run_dir)
        except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
            independent = {"passed": False, "issues": [f"independent review unavailable: {exc}"]}
        write_json(run_dir / "independent_review.json", independent)
        if not independent["passed"]:
            state["quality_status"] = "partial"
            _save_state(run_dir, state)
            errors, total = _limited(independent["issues"], "independent_review.json")
            return ({"status": "repair_needed", "stage": "report", "terminal": False,
                     "quality_status": "partial", "issues": errors,
                     "error_counts": {"independent_review": total},
                     "remaining_repairs": remaining,
                     "artifacts": {"independent_review": str(run_dir / "independent_review.json")},
                     "next_action": "fix inputs using independent_review.json; rerun report"}, 2)
    if validation["passed"]:
        state["quality_status"] = "verified"
        _save_state(run_dir, state)
        result = {"status": "ok", "stage": "report",
                 "artifacts": {"analysis_md": str(run_dir / "analysis.md"),
                               "report_claims_json": str(run_dir / "report_claims.json"),
                               "report_validation": str(run_dir / "report_validation.json")},
                 "issues": [], "remaining_repairs": remaining,
                 "quality_status": "verified",
                 "terminal": True, "next_action": None}
        if independent is not None:
            result["independent_review"] = {
                key: independent[key] for key in ("passed", "checks", "not_applicable")}
        if include_report:
            result["report_markdown"] = markdown
        return result, 0
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


def cmd_evidence(run_dir: Path, *, section_ids: list[str] | None = None,
                 pages: list[int] | None = None, request_id: str = "evidence",
                 cursor: str | None = None) -> tuple[dict, int]:
    """One tool call for extraction plus first packet; continuation never re-extracts."""
    from extract_sections import extract_sections
    from pack_context import build_packet

    if not section_ids and not pages:
        raise ValueError("evidence requires explicit sections or pages")
    if cursor is None:
        extract_sections(run_dir, section_ids=section_ids, pages=pages)
    manifest = read_json(run_dir / "extraction_manifest.json")
    selected = [ev for ev in manifest["evidences"]
                if evidence_selected(ev, section_ids, pages)]
    if not selected:
        return ({"stage": "evidence", "status": "failed", "quality_status": "partial",
                 "terminal": False, "issues": ["no evidence matched the requested sections/pages"],
                 "incomplete_evidence_ids": []}, 1)
    incomplete = [ev["evidence_id"] for ev in selected if not ev["complete"]]
    context = build_packet(run_dir, stage="map", request_id=request_id,
                           section_ids=section_ids, pages=pages, cursor=cursor)
    result = {"stage": "evidence", "status": "partial" if incomplete else "ok",
              "quality_status": "partial", "terminal": False, "context": context,
              "issues": [issue for ev in selected for issue in ev.get("issues", [])],
              "incomplete_evidence_ids": incomplete,
              "next_action": ("continue cursor if present; otherwise assemble spec.json with "
                              "all required facts, then compute --spec; complex mappings may "
                              "use direct fact_inputs.json")}
    return result, (2 if incomplete else 0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="财报分析统一阶段入口")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="下载、索引并返回章节定位包")
    prepare.add_argument("--url", required=True)
    prepare.add_argument("--run-dir", required=True)

    compute = subparsers.add_parser("compute", help="fact_inputs.json → financials + metrics")
    compute.add_argument("--run-dir", required=True)
    compute.add_argument("--pdf-only", action="store_true",
                         help="跳过东财 F10 结构化数据，强制纯 PDF 全量抽取模式")
    compute.add_argument("--spec", help="spec → verified fact inputs → compute in one call")

    report = subparsers.add_parser("report", help="report_inputs.json → analysis + claims + 校验")
    report.add_argument("--run-dir", required=True)
    report.add_argument("--spec", help="声明式 report spec → report_inputs.json → 同次执行 report")
    report.add_argument("--independent-review", action="store_true",
                        help="预检、渲染、机器校验、独立复核全部通过后才交付")
    report.add_argument("--include-report", action="store_true",
                        help="调用方要求完整正文时，同次返回已校验的报告，免去额外读取")

    review = subparsers.add_parser("review", help="只读当前状态与修复余量")
    review.add_argument("--run-dir", required=True)

    evidence = subparsers.add_parser("evidence", help="增量提取并直接返回首个证据包")
    evidence.add_argument("--run-dir", required=True)
    evidence.add_argument("--sections", default="")
    evidence.add_argument("--pages", default="")
    evidence.add_argument("--request-id", default="evidence")
    evidence.add_argument("--cursor")

    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    if args.command == "prepare":
        result, code = cmd_prepare(args.url, run_dir)
    elif args.command == "compute":
        result, code = cmd_compute(run_dir, spec_path=Path(args.spec) if args.spec else None,
                                   pdf_only=args.pdf_only)
    elif args.command == "report":
        result, code = cmd_report(run_dir, include_report=args.include_report,
                                  independent_review=args.independent_review,
                                  spec_path=Path(args.spec) if args.spec else None)
    elif args.command == "evidence":
        from pack_context import parse_pages
        result, code = cmd_evidence(
            run_dir, section_ids=[s.strip() for s in args.sections.split(",") if s.strip()] or None,
            pages=parse_pages(args.pages), request_id=args.request_id, cursor=args.cursor)
    else:
        result, code = cmd_review(run_dir)
    print(json.dumps(result, ensure_ascii=False, default=str))
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
