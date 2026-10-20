"""run_pipeline：阶段编排、有限修复预算、幂等与质量状态回归。"""

import json
from pathlib import Path

import run_pipeline
from test_build_financials import fact_input, prepare_build_run, write_json_file
from test_render_report import prepare_render_run, revenue_inputs


def fact_inputs_file(run_dir: Path, facts: list[dict]) -> None:
    write_json_file(run_dir / "fact_inputs.json", {"schema_version": 1, "facts": facts})


def run(command: str, run_dir: Path, **kwargs) -> tuple[dict, int]:
    if command == "prepare":
        return run_pipeline.cmd_prepare(kwargs["url"], run_dir)
    if command == "compute":
        return run_pipeline.cmd_compute(run_dir)
    if command == "report":
        return run_pipeline.cmd_report(run_dir)
    return run_pipeline.cmd_review(run_dir)


def test_compute_builds_metrics_and_reports_unresolved(run_dir):
    prepare_build_run(run_dir)
    fact_inputs_file(run_dir, [
        fact_input(),
        fact_input(metric="net_profit_group", raw_label="净利润",
                   raw_value="123,456,789.00",
                   evidence={"evidence_id": "ev-0001", "locator": {"row": 4, "col": 1}}),
    ])
    result, code = run("compute", run_dir)
    assert (run_dir / "financials.json").exists()
    assert (run_dir / "metrics.json").exists()
    assert result["metric_counts"]["computed"] >= 1
    assert result["remaining_repairs"] == run_pipeline.MAX_REPAIRS
    assert code in (0, 2)


def test_compute_reports_mapping_repairs(run_dir):
    prepare_build_run(run_dir)
    fact_inputs_file(run_dir, [fact_input(raw_value="1.00")])
    result, code = run("compute", run_dir)
    assert code == 2
    assert result["status"] == "repair_needed"
    assert result["error_counts"]["mapping_issues"] >= 1
    assert not (run_dir / "financials.json").exists()
    assert not (run_dir / "metrics.json").exists()


def test_compute_missing_inputs_is_fatal(run_dir):
    prepare_build_run(run_dir)
    result, code = run("compute", run_dir)
    assert code == 1
    assert "fact_inputs.json missing" in result["issues"][0]


def test_report_passes_to_verified(run_dir):
    prepare_render_run(run_dir)
    write_json_file(run_dir / "report_inputs.json", revenue_inputs())
    result, code = run("report", run_dir)
    assert code == 0
    assert result["quality_status"] == "verified"
    assert (run_dir / "analysis.md").exists()
    assert (run_dir / "report_claims.json").exists()
    review, review_code = run("review", run_dir)
    assert review_code == 0
    assert review["quality_status"] == "verified"
    assert review["report_validation"]["passed"] is True


def test_report_repair_budget_exhausts(run_dir):
    """初检 + 最多两次修复：连续三次不同输入失败后，第四次提交被拒。"""
    prepare_render_run(run_dir)
    variants = [
        revenue_inputs(bindings={"rev": {"fact_id": "f-0001"},
                                 "yoy": {"metric_id": "revenue_yoo"}}),
        revenue_inputs(bindings={"rev": {"fact_id": "f-0042"},
                                 "yoy": {"metric_id": "revenue_yoy"}}),
        revenue_inputs(bindings={"rev": {"fact_id": "f-0043"},
                                 "yoy": {"metric_id": "revenue_yoy"}}),
        revenue_inputs(bindings={"rev": {"fact_id": "f-0044"},
                                 "yoy": {"metric_id": "revenue_yoy"}}),
    ]
    for index, inputs in enumerate(variants):
        write_json_file(run_dir / "report_inputs.json", inputs)
        result, code = run("report", run_dir)
        if index < 3:
            assert code == 2
            assert result["quality_status"] == "partial"
        else:
            assert code == 2
            assert result["quality_status"] == "maintenance_required"
            assert result["remaining_repairs"] == 0
            assert "budget exhausted" in result["issues"][0]
            assert "run_state.json" in result["policy"]


def test_identical_input_rerun_does_not_consume_budget(run_dir):
    prepare_render_run(run_dir)
    write_json_file(run_dir / "report_inputs.json",
                    revenue_inputs(bindings={"rev": {"fact_id": "f-0001"},
                                             "yoy": {"metric_id": "revenue_yoo"}}))
    for _ in range(3):
        result, code = run("report", run_dir)
        assert code == 2
        assert "budget exhausted" not in result["issues"][0]
    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["repairs"]["report"]["count"] == 1


def test_review_reflects_partial_state(run_dir):
    prepare_render_run(run_dir)
    write_json_file(run_dir / "report_inputs.json", revenue_inputs())
    run("report", run_dir)
    write_json_file(run_dir / "analysis.md", "# 篡改\n\n收入 99 亿元\n")
    result, _code = run("review", run_dir)
    assert result["stage"] == "report"
    assert result["artifacts"]["report_validation.json"]
    assert result["remaining_repairs"] == run_pipeline.MAX_REPAIRS


def test_prepare_rejects_skill_source_dir():
    skill_root = Path(__file__).parent.parent
    result, code = run("prepare", skill_root, url="https://example.com/a.pdf")
    assert code == 1
    assert "must not be the skill source directory" in result["issues"][0]


def test_prepare_invokes_fetch_and_inspect(run_dir, monkeypatch):
    from fetch_pdf import FetchError

    def fake_fetch(url, output_dir, **kwargs):
        write_json_file(Path(output_dir) / "source.json",
                        {"schema_version": 1, "requested_url": url, "sha256": "x"})
        return {"reused": False, "requested_url": url}

    def fake_inspect(target: Path) -> dict:
        real_meta = {"company_name": "测试公司", "stock_code": "300000",
                     "report_type": "semi_annual", "currency": "CNY",
                     "audit_status": "unaudited", "page_count": 10,
                     "period": {"start": "2026-01-01", "end": "2026-06-30"}}
        write_json_file(target / "document.json", {"schema_version": 1, **real_meta})
        write_json_file(target / "sections.json", {
            "schema_version": 1,
            "sections": [{"section_id": "s-1", "title": "合并资产负债表", "start_page": 3,
                          "end_page": 4, "priority": 30, "verified": True}],
        })
        return real_meta

    monkeypatch.setattr("fetch_pdf.fetch_pdf", fake_fetch)
    monkeypatch.setattr("inspect_pdf.inspect_pdf", fake_inspect)

    result, code = run("prepare", run_dir, url="https://example.com/a.pdf")
    assert code == 0
    assert result["status"] == "ok"
    assert result["document"]["company_name"] == "测试公司"
    assert result["sections"][0]["section_id"] == "s-1"
    assert result["artifacts"]["source_reused"] is False
    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["stage"] == "prepare"

    monkeypatch.setattr("fetch_pdf.fetch_pdf",
                        lambda url, output_dir, **k: (_ for _ in ()).throw(
                            FetchError("HTTP 404")))
    result, code = run("prepare", run_dir, url="https://example.com/broken.pdf")
    assert code == 1
    assert "fetch failed" in result["issues"][0]


def test_state_survives_restart(run_dir):
    """持久预算：直接重读 run_state.json（等价新进程）后预算不重置。"""
    prepare_render_run(run_dir)
    write_json_file(run_dir / "report_inputs.json",
                    revenue_inputs(bindings={"rev": {"fact_id": "f-0001"},
                                             "yoy": {"metric_id": "revenue_yoo"}}))
    run("report", run_dir)
    fresh_state = run_pipeline._load_state(run_dir)
    assert fresh_state["repairs"]["report"]["count"] == 1
    write_json_file(run_dir / "report_inputs.json",
                    revenue_inputs(bindings={"rev": {"fact_id": "f-0002"},
                                             "yoy": {"metric_id": "revenue_yoo"}}))
    _, code = run("report", run_dir)
    assert code == 2
    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    assert state["repairs"]["report"]["count"] == 2


def test_compute_feedback_lists_all_issues(run_dir):
    """16 个映射错误必须一轮全部反馈，而不是每轮只给 5 条导致修复轮数爆炸。"""
    prepare_build_run(run_dir)
    facts = [
        fact_input(metric=f"made_up_{i}", raw_label=f"未知科目{i}")
        for i in range(16)
    ]
    fact_inputs_file(run_dir, facts)
    result, code = run("compute", run_dir)
    assert code == 2
    assert result["error_counts"]["mapping_issues"] == 16
    assert len(result["issues"]) == 16
    assert "[input_index=15]" in result["issues"][-1]
