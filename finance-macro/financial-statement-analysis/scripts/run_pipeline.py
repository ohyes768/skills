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

from artifacts import read_json, write_json

STATE_SCHEMA_VERSION = 1
MAX_REPAIRS = 2
EXAMPLE_LIMIT = 5
MAX_FEEDBACK_CHARS = 4000
BUDGET_POLICY = ("Do not delete or edit run_state.json to reset the repair budget; "
                 "when the budget is exhausted, deliver conclusions as "
                 "quality_status=maintenance_required/partial instead of bypassing validation.")
from validate_report import _ISSUE_KEYS


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
                       "request maintenance; do not reset the budget")
        record["count"] += 1
        state["input_sha256"][stage] = input_sha
    remaining = MAX_REPAIRS - max(record["count"] - 1, 0)
    return remaining, None


def _period(end: str) -> dict:
    from datetime import date
    parsed = date.fromisoformat(end)
    if (parsed.month, parsed.day) not in {(3, 31), (6, 30), (9, 30), (12, 31)}:
        raise ValueError("period must be a quarter-end report date (YYYY-MM-DD)")
    frequency = "annual" if parsed.month == 12 else "half_year" if parsed.month == 6 else "quarter"
    return {"kind": "duration", "start": f"{parsed.year}-01-01", "end": end,
            "frequency": frequency, "aggregation": "cumulative"}


def _dates(period: dict) -> list[str]:
    from datetime import date, timedelta

    from fact_selection import prior_year
    return sorted({period["end"], prior_year(period["end"]),
                   (date.fromisoformat(period["start"]) - timedelta(days=1)).isoformat()})


def _missing_reports(document: dict, archive: dict) -> list[str]:
    from datetime import date, timedelta

    from fact_selection import prior_year
    period = document["period"]
    current, prior = period["end"], prior_year(period["end"])
    opening = (date.fromisoformat(period["start"]) - timedelta(days=1)).isoformat()
    needed = {(current, kind) for kind in ("balance", "income", "cashflow")}
    needed.update({(prior, "income"), (prior, "cashflow"), (opening, "balance"),
                   (opening, "cashflow")})
    return [f"{day}/{kind}: F10 statement unavailable"
            for day, kind in sorted(needed)
            if not archive.get("reports", {}).get(day, {}).get(kind)]


def cmd_prepare(code: str, period_end: str, run_dir: Path, *,
                refresh: bool = False) -> tuple[dict, int]:
    from fetch_structured import FetchStructuredError, fetch_structured, secucode
    run_dir = Path(run_dir)
    try:
        normalized = secucode(code).split(".")[0]
        period = _period(period_end)
        if run_dir.resolve() == Path(__file__).resolve().parent.parent:
            raise ValueError("run-dir must not be the skill source directory")
        if (run_dir / "document.json").exists():
            previous = read_json(run_dir / "document.json")
            if (previous.get("source") != "structured_eastmoney"
                    or previous.get("stock_code") != normalized
                    or previous.get("period") != period):
                raise ValueError("run-dir is bound to a different source/security/period")
        elif any(run_dir.glob("*.json")):
            # A cached F10 archive is allowed, but an unbound old run is not adopted.
            other = [f.name for f in run_dir.glob("*.json")
                     if f.name != "structured_financials.json"]
            if other:
                raise ValueError("run-dir contains unbound artifacts")
        archive = fetch_structured(normalized, _dates(period), run_dir, refresh=refresh)
        current = archive.get("reports", {}).get(period_end, {})
        rows = [row for entries in current.values() for row in entries]
        if not rows:
            detail = "; ".join(f"{key}: {v['reason']}" for key, v in
                               archive.get("fetch_failures", {}).items())
            raise ValueError("no current-period F10 data retrieved; " + detail)
        company = next((r.get("SECURITY_NAME_ABBR") or r.get("SECURITY_NAME")
                        for r in rows if r.get("SECURITY_NAME_ABBR") or r.get("SECURITY_NAME")),
                       normalized)
        document = {"schema_version": 2, "source": "structured_eastmoney",
                    "company_name": company, "stock_code": normalized,
                    "period": period, "currency": "CNY", "scope": "consolidated"}
        write_json(run_dir / "document.json", document)
        state = _load_state(run_dir)
        state.update(stage="prepare", quality_status="partial")
        _save_state(run_dir, state)
        missing = _missing_reports(document, archive)
        return ({"status": "partial" if missing else "ok", "stage": "prepare",
                 "quality_status": "partial", "terminal": False, "issues": missing,
                 "document": document,
                 "artifacts": {"structured_financials": str(run_dir / "structured_financials.json")},
                 "next_action": "run compute; missing F10 values remain unavailable"},
                2 if missing else 0)
    except (OSError, ValueError, FetchStructuredError) as exc:
        return ({"status": "failed", "stage": "prepare", "terminal": False,
                 "quality_status": "partial", "issues": [str(exc)]}, 1)


def cmd_compute(run_dir: Path) -> tuple[dict, int]:
    from build_financials import build_financials_structured
    from calculate_metrics import calculate_metrics
    from pack_context import build_packet
    from source_provenance import source_errors
    run_dir = Path(run_dir)
    state = _load_state(run_dir)
    state.update(stage="compute", quality_status="partial")
    _save_state(run_dir, state)
    archive = read_json(run_dir / "structured_financials.json")
    financials, mapping = build_financials_structured(run_dir, archive)
    write_json(run_dir / "mapping_validation.json", mapping)
    if financials is None:
        state["quality_status"] = "maintenance_required"
        _save_state(run_dir, state)
        return ({"status": "failed", "stage": "compute", "terminal": False,
                 "quality_status": "maintenance_required", "issues": mapping["issues"]}, 1)
    errors = source_errors(run_dir, financials)
    if errors:
        state["quality_status"] = "maintenance_required"
        _save_state(run_dir, state)
        return ({"status": "failed", "stage": "compute", "terminal": False,
                 "quality_status": "maintenance_required", "issues": errors}, 1)
    write_json(run_dir / "financials.json", financials)
    metrics = calculate_metrics(financials)
    write_json(run_dir / "metrics.json", metrics)
    write_json(run_dir / "validation.json", {"schema_version": 1, "checks": metrics["validation"]})
    from analysis_pack import build_analysis_pack
    write_json(run_dir / "analysis_pack.json", build_analysis_pack(run_dir))
    state = _load_state(run_dir)
    state.update(stage="compute", quality_status="partial")
    _save_state(run_dir, state)
    problems = [f"{c['check_id']}: {c['status']}" for c in metrics["validation"]
                if c["status"] in {"failed", "conflict"}]
    missing = _missing_reports(read_json(run_dir / "document.json"), archive)
    context = build_packet(run_dir, stage="analyze", request_id="compute-analysis")
    return ({"status": "partial" if problems or missing else "ok", "stage": "compute",
             "quality_status": "partial", "terminal": False, "issues": problems + missing,
             "warnings": mapping.get("warnings", []),
             "metric_counts": {"computed": sum(m["status"] == "computed" for m in metrics["metrics"])},
             "packet": context["packet"],
             "usage_summary": context["usage_summary"],
             "packet_sha256": context["packet_sha256"],
             "context": context,
             "continuation": {
                 "cursor_field": "packet.next_cursor",
                 "pack_context_cursor_field": "packet.next_cursor",
                 "end_when": "null",
                 "invalid_cursor_status": "failed",
             },
             "next_action": "read packet.next_cursor until null, then author report_spec.json"},
            2 if problems or missing else 0)


def cmd_report(run_dir: Path, *, include_report: bool = False,
               independent_review: bool = False,
               spec_path: Path | None = None,
               build_spec: bool = False) -> tuple[dict, int]:
    import render_report
    import validate_report

    run_dir = Path(run_dir)
    from source_provenance import source_errors
    state = _load_state(run_dir)
    state.update(stage="report", quality_status="partial")
    _save_state(run_dir, state)
    errors = source_errors(run_dir)
    if not errors:
        errors = validate_report.calculation_errors(run_dir)
    if errors:
        state["quality_status"] = "maintenance_required"
        _save_state(run_dir, state)
        return ({"status": "failed", "stage": "report", "terminal": False,
                 "quality_status": "maintenance_required", "issues": errors}, 1)
    if spec_path is not None:
        spec_input = read_json(spec_path)
        from build_report_spec import _is_placeholder_paragraph
        if any(_is_placeholder_paragraph(p) for sec in spec_input.get("sections", [])
               for p in sec.get("paragraphs", [])):
            return ({"status": "repair_needed", "stage": "report", "terminal": False,
                     "quality_status": "partial", "issues": ["rewrite qualitative placeholder paragraphs"]}, 2)
    if build_spec and spec_path is None:
        from artifacts import read_json as _read_json
        from build_report_spec import build_spec as _build_spec

        try:
            skeleton = _read_json(
                Path(__file__).resolve().parent.parent / "references" / "report-spec-skeleton.json")
            generated, _notes = _build_spec(run_dir, skeleton)
            write_json(run_dir / "report_spec.json", generated)
            return ({"status": "repair_needed", "stage": "report", "terminal": False,
                     "quality_status": "partial", "issues": ["author the generated report_spec.json before final delivery"],
                     "paragraphs_todo": generated.get("_paragraphs_todo", []),
                     "next_action": "edit report_spec.json then run report --spec"}, 2)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return ({"status": "repair_needed", "stage": "report", "terminal": False,
                     "quality_status": "partial",
                     "issues": [f"report spec generation failed: {exc}"],
                     "next_action": "fix financials/metrics facts then rerun report"}, 2)
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
    if validation["passed"]:
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
        missing = _missing_reports(read_json(run_dir / "document.json"),
                                   read_json(run_dir / "structured_financials.json"))
        if missing:
            state["quality_status"] = "partial"
            _save_state(run_dir, state)
            return ({"status": "partial", "stage": "report", "terminal": True,
                     "quality_status": "partial", "issues": missing,
                     "artifacts": {"analysis_md": str(run_dir / "analysis.md")},
                     "next_action": None}, 2)
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
    for name in ("document.json", "structured_financials.json", "financials.json", "metrics.json",
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

    prepare = subparsers.add_parser("prepare", help="按股票代码与报告期拉取 F10 三表")
    prepare.add_argument("--code", required=True)
    prepare.add_argument("--period", required=True)
    prepare.add_argument("--refresh", action="store_true")
    prepare.add_argument("--run-dir", required=True)

    compute = subparsers.add_parser("compute", help="F10 archive → financials + metrics")
    compute.add_argument("--run-dir", required=True)

    report = subparsers.add_parser("report", help="report_inputs.json → analysis + claims + 校验")
    report.add_argument("--run-dir", required=True)
    report.add_argument("--spec", help="声明式 report spec → report_inputs.json → 同次执行 report")
    report.add_argument("--build-spec", action="store_true",
                        help="无 --spec 时用 references/report-spec-skeleton.json 自动生成 spec")
    report.add_argument("--independent-review", action="store_true",
                        help="预检、渲染、机器校验、独立复核全部通过后才交付")
    report.add_argument("--include-report", action="store_true",
                        help="调用方要求完整正文时，同次返回已校验的报告，免去额外读取")

    review = subparsers.add_parser("review", help="只读当前状态与修复余量")
    review.add_argument("--run-dir", required=True)

    args = parser.parse_args(argv)
    run_dir = Path(args.run_dir)
    try:
        if args.command == "prepare":
            result, code = cmd_prepare(args.code, args.period, run_dir, refresh=args.refresh)
        elif args.command == "compute":
            result, code = cmd_compute(run_dir)
        elif args.command == "report":
            result, code = cmd_report(run_dir, include_report=args.include_report,
                                      independent_review=args.independent_review,
                                      spec_path=Path(args.spec) if args.spec else None,
                                      build_spec=args.build_spec)
        else:
            result, code = cmd_review(run_dir)
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as exc:
        state = _load_state(run_dir)
        state.update(stage=args.command, quality_status="maintenance_required")
        _save_state(run_dir, state)
        result, code = ({"status": "failed", "stage": args.command, "terminal": False,
                         "quality_status": "maintenance_required", "issues": [str(exc)]}, 1)
    result.setdefault("terminal", False)
    print(json.dumps(result, ensure_ascii=False, default=str))
    sys.stdout.flush()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
