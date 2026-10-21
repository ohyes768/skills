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


def test_inspect_frequency_semi_annual_is_normalized(run_dir):
    """回归（b1a13cc 曾修复后被覆盖）：semi_annual 必须归一化为合同值 half_year。"""
    prepare_build_run(run_dir, document_period={
        "kind": "duration", "start": "2026-01-01", "end": "2026-06-30",
        "frequency": "semi_annual", "aggregation": "cumulative",
    })
    inputs = {"schema_version": 1, "facts": [fact_input()]}
    financials, validation = build_financials.build_financials(run_dir, inputs)
    assert financials is not None, validation["issues"]
    assert financials["facts"][0]["period"]["frequency"] == "half_year"
    assert validate_financials(financials) == []


def structured_doc() -> dict:
    def row(**kv):
        return [kv]

    return {
        "schema_version": 1, "source": "structured_eastmoney",
        "security_code": "300000", "secucode": "300000.SZ",
        "report_dates": ["2026-06-30", "2025-06-30", "2025-12-31"],
        "reports": {
            "2026-06-30": {
                "balance": row(TOTAL_ASSETS="1366525227.25", MONETARYFUNDS="123625294.67",
                               ACCOUNTS_RECE="288607514.94"),
                "income": row(TOTAL_OPERATE_INCOME="230730296.15", OPERATE_COST="158078681.91",
                              PARENT_NETPROFIT="-77252801.33"),
                "cashflow": row(NETCASH_OPERATE="-57969741.72", END_CCE="105663595.93",
                                CONSTRUCT_LONG_ASSET="10575340.49"),
            },
            "2025-06-30": {
                "balance": row(TOTAL_ASSETS="1400000000.00", MONETARYFUNDS="150000000.00",
                               ACCOUNTS_RECE="250000000.00"),
                "income": row(TOTAL_OPERATE_INCOME="319200000.00", OPERATE_COST="230000000.00",
                              PARENT_NETPROFIT="-46860200.00"),
                "cashflow": row(NETCASH_OPERATE="-20000000.00", END_CCE="154376097.57",
                                CONSTRUCT_LONG_ASSET="30000000.00"),
            },
            "2025-12-31": {
                "balance": row(TOTAL_ASSETS="1397677219.66", MONETARYFUNDS="140000000.00",
                               ACCOUNTS_RECE="260000000.00"),
                "income": row(TOTAL_OPERATE_INCOME="600000000.00", OPERATE_COST="470000000.00",
                              PARENT_NETPROFIT="0.00"),
                "cashflow": row(NETCASH_OPERATE="10000000.00", END_CCE="140000000.00",
                                CONSTRUCT_LONG_ASSET="50000000.00"),
            },
        },
    }


def test_structured_branch_generates_dual_period_facts(run_dir):
    prepare_build_run(run_dir)
    financials, validation = build_financials.build_financials_structured(
        run_dir, structured_doc())
    assert financials is not None, validation["issues"]
    by_metric = {}
    for fact in financials["facts"]:
        by_metric.setdefault((fact["metric"], fact["period"]["end"]), fact)
    revenue_cur = by_metric[("revenue", "2026-06-30")]
    revenue_prior = by_metric[("revenue", "2025-06-30")]
    cash_opening = by_metric[("cash_equivalents", "2025-12-31")]
    assert revenue_cur["value"] == "230730296.15"
    assert revenue_cur["source"] == "structured"
    assert revenue_cur["evidence_ids"] == []
    assert revenue_prior["value"] == "319200000.00"
    assert cash_opening["period"]["kind"] == "instant"
    assert cash_opening["period"]["end"] == "2025-12-31"
    assert validate_financials(financials) == []
    assert validation["warnings"], "unsupported metrics must surface as warnings"


def test_structured_missing_date_blocks(run_dir):
    prepare_build_run(run_dir)
    doc = structured_doc()
    doc["reports"].pop("2025-06-30")
    financials, validation = build_financials.build_financials_structured(run_dir, doc)
    assert financials is None
    assert any("not fetched" in i["error"] for i in validation["issues"])


def test_structured_null_value_becomes_missing_fact(run_dir):
    prepare_build_run(run_dir)
    doc = structured_doc()
    doc["reports"]["2026-06-30"]["income"][0]["RESEARCH_EXPENSE"] = None
    doc["reports"]["2025-06-30"]["income"][0]["RESEARCH_EXPENSE"] = None
    financials, _ = build_financials.build_financials_structured(run_dir, doc)
    r_and_d = [f for f in financials["facts"] if f["metric"] == "r_and_d_expense"]
    assert r_and_d and all(f["value"] is None for f in r_and_d)
    assert all(f["missing_reason"] == "not disclosed in structured source" for f in r_and_d)


def test_structured_missing_field_warns_and_skips(run_dir):
    prepare_build_run(run_dir)
    doc = structured_doc()
    for date in doc["reports"]:
        doc["reports"][date]["balance"][0].pop("GOODWILL", None)
    financials, validation = build_financials.build_financials_structured(run_dir, doc)
    assert financials is not None
    assert not [f for f in financials["facts"] if f["metric"] == "goodwill"]
    assert any("field missing" in w["error"] and "goodwill" in w["error"]
               for w in validation["warnings"])


def _override_income_cell(run_dir: Path, row: int, value: str) -> None:
    path = run_dir / "excerpts" / "ev-0001.table.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["rows"][row][1] = value
    write_json_file(path, data)


def test_sample_check_verified_when_twin_matches(run_dir):
    """抽查数与结构化值一致：双源并存、check 记 verified、值由 pick_usable 去重。"""
    prepare_build_run(run_dir)
    _override_income_cell(run_dir, 0, "230,730,296.15")
    inputs = {"schema_version": 1, "facts": [
        fact_input(raw_value="230,730,296.15"),
    ]}
    financials, validation = build_financials.build_financials_structured(
        run_dir, structured_doc(), inputs)
    assert financials is not None, validation["issues"]
    check = validation["structured_check"]
    revenue = next(s for s in check["samples"] if s["metric"] == "revenue"
                   and s["period_end"] == "2026-06-30")
    assert revenue["status"] == "verified"
    assert check["verified"] >= 1
    assert check["conflicts"] == 0
    rev_facts = [f for f in financials["facts"] if f["metric"] == "revenue"
                 and f["period"]["end"] == "2026-06-30"]
    assert {f["source"] for f in rev_facts} == {"structured", "extracted"}
    assert validate_financials(financials) == []


def test_sample_check_conflict_marks_fact(run_dir):
    """抽查数与结构化值不一致：structured fact 转 conflict，check 记 conflicts。"""
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [
        fact_input(metric="cost_of_sales", raw_label="营业成本",
                   raw_value="800,000,000.00",
                   evidence={"evidence_id": "ev-0001", "locator": {"row": 1, "col": 1}}),
    ]}
    financials, validation = build_financials.build_financials_structured(
        run_dir, structured_doc(), inputs)
    assert financials is not None, "conflict is recorded, not fatal"
    check = validation["structured_check"]
    cost = next(s for s in check["samples"] if s["metric"] == "cost_of_sales"
                and s["period_end"] == "2026-06-30")
    assert cost["status"] == "conflict"
    assert check["conflicts"] >= 1
    conflicted = [f for f in financials["facts"]
                  if f["metric"] == "cost_of_sales" and f["source"] == "structured"]
    assert conflicted and conflicted[0]["review_status"] == "conflict"
    assert any("mismatch" in i["error"] for i in validation["issues"])


def test_unchecked_without_sample_inputs(run_dir):
    prepare_build_run(run_dir)
    _, validation = build_financials.build_financials_structured(run_dir, structured_doc())
    check = validation["structured_check"]
    assert check["unchecked"] == check["verified"] + check["conflicts"] + check["unchecked"]
    assert check["verified"] == 0 and check["conflicts"] == 0
    assert all(s["status"] == "unchecked" for s in check["samples"])


def test_presence_scan_counts_found_and_not_found(run_dir):
    """全量数值存在性：值在证据文本中出现计 found，否则 not_found（不阻塞）。"""
    prepare_build_run(run_dir)
    doc = structured_doc()
    # 把本期营收值写入证据文本（ev-0002 任一行），使其可被存在性命中。
    txt = run_dir / "excerpts" / "ev-0002.txt"
    txt.write_text(txt.read_text(encoding="utf-8") + "\n[p.55] 230,730,296.15\n",
                   encoding="utf-8")
    financials, validation = build_financials.build_financials_structured(run_dir, doc)
    assert financials is not None
    presence = validation["structured_check"]["presence"]
    assert presence["found"] >= 1, "revenue current value exists in evidence text"
    assert presence["not_found"] >= 1, "values not in extracted pages stay not_found"
    assert presence["found"] + presence["not_found"] + presence["no_value"] == len(financials["facts"])


def test_recommended_sample_metrics_warning(run_dir):
    """抽查单未覆盖建议科目时给 warning 提示，不阻塞。"""
    prepare_build_run(run_dir)
    inputs = {"schema_version": 1, "facts": [fact_input()]}
    financials, validation = build_financials.build_financials_structured(
        run_dir, structured_doc(), inputs)
    assert financials is not None
    reco_warnings = [w for w in validation["warnings"]
                     if "sample sheet does not cover" in w["error"]]
    assert reco_warnings, "missing recommended samples must be surfaced"
    assert "net_profit_owners" in reco_warnings[0]["error"]
