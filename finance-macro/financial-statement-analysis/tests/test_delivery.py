"""Explicit acceptance receipt and fewer deterministic tool round trips."""

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


def test_finish_requires_semantic_review(run_dir):
    rendered(run_dir)
    result, code = run_pipeline.cmd_finish(run_dir, semantic_reviewed=False)
    assert code != 0
    assert result["terminal"] is False
    assert not (run_dir / "completion.json").exists()


def test_finish_delivers_without_model_rewriting_report(run_dir):
    from completion import verify_completion

    rendered(run_dir)
    result, code = run_pipeline.cmd_finish(run_dir, semantic_reviewed=True)
    assert code == 0
    assert result["terminal"] is True
    assert result["next_action"] is None
    assert "analysis.md" not in result.get("output", "")
    body = verify_completion(run_dir, expected_url="https://example.com/report.pdf")
    assert body == (run_dir / "analysis.md").read_text(encoding="utf-8")
    with pytest.raises(ValueError, match="URL"):
        verify_completion(run_dir, expected_url="https://example.com/other.pdf")


@pytest.mark.parametrize("name", ["analysis.md", "financials.json", "report_inputs.json"])
def test_host_rejects_changed_artifact_after_finish(run_dir, name):
    from completion import verify_completion

    rendered(run_dir)
    assert run_pipeline.cmd_finish(run_dir, semantic_reviewed=True)[1] == 0
    with (run_dir / name).open("a", encoding="utf-8") as file:
        file.write(" \n")
    with pytest.raises(ValueError, match="changed"):
        verify_completion(run_dir)


def test_finish_revalidates_instead_of_trusting_verified_state(run_dir):
    rendered(run_dir)
    (run_dir / "analysis.md").write_text("# 篡改\n收入 99 亿元", encoding="utf-8")
    result, code = run_pipeline.cmd_finish(run_dir, semantic_reviewed=True)
    assert code == 2
    assert result["terminal"] is False
    assert not (run_dir / "completion.json").exists()


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
