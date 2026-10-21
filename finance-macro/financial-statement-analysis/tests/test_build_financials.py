"""build_financials：紧凑事实输入构造标准合同的映射、维度与证据定位回归。"""

import json
from pathlib import Path

import build_financials
from financial_schema import metric_aliases, validate_financials


def write_json_file(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_build_run(run_dir: Path, document_period: dict | None = None) -> None:
    write_json_file(run_dir / "document.json", {
        "schema_version": 1,
        "company_name": "测试公司",
        "stock_code": "300000",
        "currency": "CNY",
        "page_count": 20,
        "period": document_period or {
            "kind": "duration", "start": "2026-01-01", "end": "2026-06-30",
            "frequency": "half_year", "aggregation": "cumulative",
        },
    })
    write_json_file(run_dir / "source.json", {
        "schema_version": 1, "requested_url": "https://example.com/a.pdf",
        "sha256": "abc123", "size_bytes": 10,
    })
    write_json_file(run_dir / "extraction_manifest.json", {
        "schema_version": 1,
        "document_sha256": "abc123",
        "page_count": 20,
        "evidences": [
            {"evidence_id": "ev-0001", "section_id": "s-1", "pdf_pages": [5],
             "kind": "table", "file": "excerpts/ev-0001.table.json",
             "method": "pdfplumber_table", "complete": True, "issues": []},
            {"evidence_id": "ev-0002", "section_id": "s-1", "pdf_pages": [6],
             "kind": "text", "file": "excerpts/ev-0002.txt",
             "method": "pymupdf_text", "complete": True, "issues": []},
            {"evidence_id": "ev-0003", "section_id": "s-1", "pdf_pages": [7],
             "kind": "image_crop", "file": "excerpts/ev-0003.png",
             "method": "image_crop", "complete": False, "issues": ["pending visual review"]},
        ],
    })
    write_json_file(run_dir / "excerpts" / "ev-0001.table.json", {
        "headers": ["项目", "本期", "上期"],
        "rows": [
            ["营业收入", "1,234,567,890.12", "987,654,321.00"],
            ["营业成本", "800,000,000.00", "700,000,000.00"],
            ["货币资金", "500,000,000.00", "450,000,000.00"],
            ["资产总计", "2,000,000,000.00", "1,800,000,000.00"],
            ["净利润", "123,456,789.00", "110,000,000.00"],
        ],
        "pages": [5],
    })
    (run_dir / "excerpts").mkdir(exist_ok=True)
    (run_dir / "excerpts" / "ev-0002.txt").write_text(
        "[p.6] 归属于母公司股东的净利润 123,456,789.00 元\n", encoding="utf-8"
    )


def fact_input(**overrides) -> dict:
    fact = {
        "metric": "revenue",
        "raw_label": "营业收入",
        "raw_value": "1,234,567,890.12",
        "raw_unit": "元",
        "period_ref": "current",
        "evidence": {"evidence_id": "ev-0001", "locator": {"row": 0, "col": 1}},
    }
    fact.update(overrides)
    return fact


def load_financials(run_dir: Path) -> dict:
    return json.loads((run_dir / "financials.json").read_text(encoding="utf-8"))


def load_validation(run_dir: Path) -> dict:
    return json.loads((run_dir / "mapping_validation.json").read_text(encoding="utf-8"))


def test_alias_and_contract_fields_are_program_supplied(run_dir):
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [fact_input(metric="cost_of_revenue",
                                                       raw_label="营业成本",
                                                       raw_value="800,000,000.00",
                                                       evidence={"evidence_id": "ev-0001",
                                                                 "locator": {"row": 1, "col": 1}})]}
    financials, validation = build_financials.build_financials(run_dir, inputs)
    assert financials is not None
    assert validation["issues"] == []
    fact = financials["facts"][0]
    assert fact["metric"] == "cost_of_sales"
    assert fact["attribution"] == "group"
    assert fact["unit"] == "元"
    assert fact["currency"] == "CNY"
    assert fact["fact_id"] == "f-0001"
    assert fact["raw_value"] == "800,000,000.00"
    assert validate_financials(financials) == []


def test_period_refs_resolve_from_document(run_dir):
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [
        fact_input(),
        fact_input(metric="monetary_funds", raw_label="货币资金",
                   raw_value="500,000,000.00", period_ref="closing",
                   evidence={"evidence_id": "ev-0001", "locator": {"row": 2, "col": 1}}),
    ]}
    financials, _ = build_financials.build_financials(run_dir, inputs)
    current = financials["facts"][0]["period"]
    assert current == {"kind": "duration", "start": "2026-01-01", "end": "2026-06-30",
                       "frequency": "half_year", "aggregation": "cumulative"}
    closing = financials["facts"][1]["period"]
    assert closing == {"kind": "instant", "start": None, "end": "2026-06-30",
                       "frequency": "half_year", "aggregation": "instant"}
    assert validate_financials(financials) == []


def test_prior_period_and_opening_balance_dates(run_dir):
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [
        fact_input(period_ref="prior"),
        fact_input(metric="total_assets", raw_label="资产总计", raw_value="2,000,000,000.00",
                   period_ref="opening",
                   evidence={"evidence_id": "ev-0001", "locator": {"row": 3, "col": 1}}),
    ]}
    financials, _ = build_financials.build_financials(run_dir, inputs)
    prior = financials["facts"][0]["period"]
    assert (prior["start"], prior["end"]) == ("2025-01-01", "2025-06-30")
    opening = financials["facts"][1]["period"]
    assert opening["kind"] == "instant"
    assert opening["end"] == "2025-12-31"


def test_undisclosed_value_gets_program_missing_reason(run_dir):
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [
        fact_input(raw_value="—", evidence=None),
    ]}
    financials, validation = build_financials.build_financials(run_dir, inputs)
    assert financials is not None
    assert validation["issues"] == []
    fact = financials["facts"][0]
    assert fact["value"] is None
    assert fact["missing_reason"] == "not disclosed in source"
    assert fact["evidence_ids"] == []
    assert validate_financials(financials) == []


def test_table_cell_mismatch_blocks_output(run_dir):
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [
        fact_input(raw_value="999,999,999.00"),
    ]}
    financials, validation = build_financials.build_financials(run_dir, inputs)
    assert financials is None
    assert not (run_dir / "financials.json").exists()
    assert "cell mismatch" in validation["issues"][0]["error"]


def test_locator_out_of_range_reports_position(run_dir):
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [
        fact_input(evidence={"evidence_id": "ev-0001", "locator": {"row": 9, "col": 1}}),
    ]}
    financials, validation = build_financials.build_financials(run_dir, inputs)
    assert financials is None
    assert "out of range" in validation["issues"][0]["error"]


def test_text_evidence_label_must_occur(run_dir):
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [
        fact_input(metric="net_profit_owners", raw_label="归属于母公司股东的净利润",
                   raw_value="123,456,789.00", period_ref="current",
                   evidence={"evidence_id": "ev-0002"}),
    ]}
    financials, validation = build_financials.build_financials(run_dir, inputs)
    assert financials is not None
    assert financials["facts"][0]["attribution"] == "owners"
    assert validation["issues"] == []

    bad = {"schema_version": 1, "facts": [
        fact_input(metric="net_profit_owners", raw_label="扣除非经常性损益",
                   raw_value="123,456,789.00", period_ref="current",
                   evidence={"evidence_id": "ev-0002"}),
    ]}
    financials, validation = build_financials.build_financials(run_dir, bad)
    assert financials is None
    assert "not found in text evidence" in validation["issues"][0]["error"]


def test_monetary_funds_and_cash_equivalents_stay_distinct(run_dir):
    aliases = metric_aliases()
    assert "货币资金" in aliases["monetary_funds"]
    assert "货币资金" not in aliases["cash_equivalents"]
    assert "现金及现金等价物余额" not in aliases["monetary_funds"]


def test_unverifiable_evidence_downgrades_review_status(run_dir):
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [
        fact_input(evidence={"evidence_id": "ev-0003"}),
    ]}
    financials, validation = build_financials.build_financials(run_dir, inputs)
    assert financials is not None
    assert financials["facts"][0]["review_status"] == "ambiguous"
    assert validation["issues"] == []
    assert validation["warnings"], "downgrade must be visible as a warning"


def test_unmapped_label_blocks_with_position(run_dir):
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [
        fact_input(metric="something_made_up", raw_label="其他综合收益的税后净额"),
    ]}
    financials, validation = build_financials.build_financials(run_dir, inputs)
    assert financials is None
    assert validation["issues"][0]["input_index"] == 0
    assert "unmapped metric label" in validation["issues"][0]["error"]


def test_wrong_period_ref_for_kind_rejected(run_dir):
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [
        fact_input(period_ref="opening"),
    ]}
    financials, validation = build_financials.build_financials(run_dir, inputs)
    assert financials is None
    assert "period_ref" in validation["issues"][0]["field"]


def test_missing_document_period_requires_clarification(run_dir):
    prepare_build_run(run_dir, document_period=None)
    document = json.loads((run_dir / "document.json").read_text(encoding="utf-8"))
    document.pop("period")
    (run_dir / "document.json").write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    inputs = {"schema_version": 1, "facts": [fact_input()]}
    financials, validation = build_financials.build_financials(run_dir, inputs)
    assert financials is None
    assert "clarify" in validation["issues"][0]["error"]


def test_cli_writes_artifacts_and_exit_codes(run_dir, capsys):
    prepare_build_run(run_dir)
    write_json_file(run_dir / "fact_inputs.json",
                    {"schema_version": 1, "facts": [fact_input()]})
    assert build_financials.main(["--run-dir", str(run_dir)]) == 0
    assert load_financials(run_dir)["facts"][0]["metric"] == "revenue"
    out = capsys.readouterr().out
    assert len([line for line in out.splitlines() if line.strip()]) == 1

    write_json_file(run_dir / "fact_inputs.json",
                    {"schema_version": 1, "facts": [fact_input(raw_value="1.00")]})
    try:
        build_financials.main(["--run-dir", str(run_dir)])
        raised = False
    except SystemExit as exc:
        raised = exc.code == 2
    assert raised, "cell mismatch must exit 2 (repairable)"


def test_document_period_frequency_passes_through(run_dir):
    """document.json 的 period.frequency 已由 inspect_pdf 产合同值，构造原样透传。"""
    prepare_build_run(run_dir, document_period={
        "kind": "duration", "start": "2026-01-01", "end": "2026-06-30",
        "frequency": "half_year", "aggregation": "cumulative",
    })
    inputs = {"schema_version": 1, "facts": [fact_input()]}
    financials, validation = build_financials.build_financials(run_dir, inputs)
    assert financials is not None, validation["issues"]
    assert financials["facts"][0]["period"]["frequency"] == "half_year"
    assert validate_financials(financials) == []
