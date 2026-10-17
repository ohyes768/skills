import json
from pathlib import Path

import pytest
import validate_report


def prepare_run(run_dir: Path, claims: list[dict], analysis_md: str = "# 分析\n\n正文。\n") -> None:
    (run_dir / "document.json").write_text(
        json.dumps({"schema_version": 1, "page_count": 17}, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "financials.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "document_sha256": "abc",
                "facts": [
                    {
                        "fact_id": "f-0001",
                        "metric": "revenue",
                        "value": "1200000000.00",
                        "evidence_ids": ["ev-0001"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "metrics.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metrics": [
                    {
                        "metric_id": "revenue_yoy",
                        "value": "0.2",
                        "status": "computed",
                        "formula": "(cur-prev)/prev",
                        "input_fact_ids": ["f-0001"],
                        "source_pages": [9],
                        "reason": None,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "extraction_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "page_count": 17,
                "evidences": [
                    {
                        "evidence_id": "ev-0001",
                        "section_id": "s-1",
                        "pdf_pages": [9],
                        "kind": "text",
                        "file": "excerpts/ev-0001.txt",
                        "method": "pymupdf_text",
                        "complete": True,
                        "issues": [],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "report_claims.json").write_text(
        json.dumps({"schema_version": 1, "claims": claims}, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "analysis.md").write_text(analysis_md, encoding="utf-8")


def make_claim(**overrides) -> dict:
    claim = {
        "claim_id": "c-001",
        "report_anchor": "# 分析",
        "text": "营业收入同比增长 20%",
        "fact_ids": ["f-0001"],
        "metric_ids": ["revenue_yoy"],
        "evidence_ids": ["ev-0001"],
        "source_pages": [9],
        "claim_type": "calculation",
    }
    claim.update(overrides)
    return claim


def load_result(run_dir: Path) -> dict:
    return json.loads((run_dir / "report_validation.json").read_text(encoding="utf-8"))


def test_valid_report_passes(run_dir):
    prepare_run(run_dir, [make_claim()])
    result = validate_report.validate_report(run_dir)
    assert result["passed"] is True
    assert result["unknown_fact_ids"] == []
    assert result["value_mismatches"] == []


def test_unknown_fact_id_detected(run_dir):
    prepare_run(run_dir, [make_claim(fact_ids=["f-9999"])])
    result = validate_report.validate_report(run_dir)
    assert result["unknown_fact_ids"] == ["f-9999"]
    assert result["passed"] is False


def test_unknown_metric_id_detected(run_dir):
    prepare_run(run_dir, [make_claim(metric_ids=["nope_metric"])])
    result = validate_report.validate_report(run_dir)
    assert result["unknown_metric_ids"] == ["nope_metric"]


def test_unknown_evidence_id_detected(run_dir):
    prepare_run(run_dir, [make_claim(evidence_ids=["ev-8888"])])
    result = validate_report.validate_report(run_dir)
    assert result["unknown_evidence_ids"] == ["ev-8888"]


def test_out_of_range_page_detected(run_dir):
    prepare_run(run_dir, [make_claim(source_pages=[99])])
    result = validate_report.validate_report(run_dir)
    assert {"claim_id": "c-001", "page": 99} in result["out_of_range_pages"]


def test_metric_value_mismatch_detected(run_dir):
    prepare_run(run_dir, [make_claim(text="营业收入同比增长 33%")])
    result = validate_report.validate_report(run_dir)
    assert result["value_mismatches"]
    assert result["value_mismatches"][0]["claim_id"] == "c-001"


def test_metric_value_percentage_forms_match(run_dir):
    prepare_run(run_dir, [make_claim(text="收入较上年增长 20.0%")])
    result = validate_report.validate_report(run_dir)
    assert result["value_mismatches"] == []


def test_fact_claim_without_evidence_flagged(run_dir):
    prepare_run(
        run_dir,
        [make_claim(claim_type="fact", fact_ids=[], metric_ids=[], evidence_ids=[], source_pages=[])],
    )
    result = validate_report.validate_report(run_dir)
    assert "c-001" in result["missing_evidence_claims"]


def test_illegal_claim_type_flagged(run_dir):
    prepare_run(run_dir, [make_claim(claim_type="rumor")])
    result = validate_report.validate_report(run_dir)
    assert "c-001" in result["missing_evidence_claims"]


def test_inference_requires_supporting_ids(run_dir):
    prepare_run(
        run_dir,
        [make_claim(claim_type="inference", text="风险信号：应收增速高于收入", fact_ids=[], metric_ids=[], evidence_ids=[])],
    )
    result = validate_report.validate_report(run_dir)
    assert "c-001" in result["missing_evidence_claims"]


def test_cli_exit_codes(run_dir, capsys):
    prepare_run(run_dir, [make_claim()])
    code = validate_report.main(["--run-dir", str(run_dir)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["status"] == "ok"

    prepare_run(run_dir, [make_claim(fact_ids=["f-9999"])])
    with pytest.raises(SystemExit) as exc_info:
        validate_report.main(["--run-dir", str(run_dir)])
    assert exc_info.value.code == 2


def test_cli_missing_artifacts_exit_1(run_dir):
    with pytest.raises(SystemExit) as exc_info:
        validate_report.main(["--run-dir", str(run_dir)])
    assert exc_info.value.code == 1
