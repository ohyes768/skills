"""Skill-only stopping point and fewer deterministic tool round trips."""

import json

import pytest
import run_pipeline
from fixtures import build_synthetic_pdfs
from test_build_financials import fact_input, prepare_build_run
from test_render_report import prepare_render_run, revenue_inputs, write_json_file


def rendered(run_dir):
    prepare_render_run(run_dir)
    write_json_file(run_dir / "report_inputs.json", revenue_inputs())
    write_json_file(run_dir / "source.json", {"requested_url": "https://example.com/report.pdf"})
    assert run_pipeline.cmd_report(run_dir)[1] == 0


def test_report_success_is_last_tool_step(run_dir):
    rendered(run_dir)
    result, code = run_pipeline.cmd_report(run_dir)
    assert code == 0
    assert result["terminal"] is True
    assert result["next_action"] is None
    assert "report_markdown" not in result
    assert not (run_dir / "completion.json").exists()


def test_requested_report_body_matches_validated_file(run_dir):
    rendered(run_dir)
    result, code = run_pipeline.cmd_report(run_dir, include_report=True)
    assert code == 0
    assert result["terminal"] is True
    assert result["report_markdown"] == (run_dir / "analysis.md").read_text(encoding="utf-8")


def test_cli_can_deliver_report_without_another_tool_read(run_dir, capsys):
    rendered(run_dir)
    assert run_pipeline.main(["report", "--run-dir", str(run_dir), "--include-report"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["report_markdown"] == (run_dir / "analysis.md").read_text(encoding="utf-8")


def test_failed_report_does_not_signal_completion_or_deliver_body(run_dir):
    rendered(run_dir)
    write_json_file(run_dir / "report_inputs.json",
                    revenue_inputs(bindings={"rev": {"fact_id": "missing"}}))
    result, code = run_pipeline.cmd_report(run_dir, include_report=True)
    assert code == 2
    assert result.get("terminal") is not True
    assert "report_markdown" not in result


def test_evidence_extracts_and_returns_first_packet_then_only_reads_cursor(run_dir, monkeypatch):
    import extract_sections
    import inspect_pdf

    pdf, _pages = build_synthetic_pdfs.build_annual_report()
    (run_dir / "source.pdf").write_bytes(pdf)
    inspect_pdf.inspect_pdf(run_dir)
    result, code = run_pipeline.cmd_evidence(
        run_dir, section_ids=["s-consolidated-income-statement"], request_id="map-first")
    assert code in (0, 2)
    assert result["context"]["packet"]["items"]
    assert (run_dir / "context_usage.jsonl").exists()
    monkeypatch.setattr(extract_sections, "extract_sections",
                        lambda *a, **k: pytest.fail("cursor must not re-extract"))
    import pack_context
    result, _code = run_pipeline.cmd_evidence(
        run_dir, section_ids=["s-consolidated-income-statement"],
        request_id="map-next", cursor=pack_context._encode_cursor(1))
    assert "context" in result


def test_compute_returns_bounded_analysis_without_raw_evidence(run_dir):
    prepare_build_run(run_dir)
    write_json_file(run_dir / "fact_inputs.json", {"schema_version": 1, "facts": [fact_input()]})
    result, code = run_pipeline.cmd_compute(run_dir)
    assert code in (0, 2)
    packet = result["context"]["packet"]
    assert packet["character_count"] <= 12000
    assert any(item["kind"] == "fact" for item in packet["items"])
    assert all(item["kind"] in {"fact", "metric", "check"} for item in packet["items"])
    assert json.loads((run_dir / "context_usage.jsonl").read_text().splitlines()[0])["stage"] == "analyze"
