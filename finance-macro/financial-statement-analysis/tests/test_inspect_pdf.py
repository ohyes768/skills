import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

import inspect_pdf
from build_synthetic_pdfs import build_annual_report


def prepare_run_dir(run_dir: Path, data: bytes) -> None:
    (run_dir / "source.pdf").write_bytes(data)
    (run_dir / "source.json").write_text(
        json.dumps({"sha256": "fixture", "requested_url": "https://example.com/x.pdf"}),
        encoding="utf-8",
    )


def read_pages(run_dir: Path) -> list[dict]:
    lines = (run_dir / "pages.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


@pytest.fixture()
def full_report(run_dir):
    data, page_map = build_annual_report()
    prepare_run_dir(run_dir, data)
    return run_dir, page_map


def test_bookmark_sections_located_with_verified(full_report):
    run_dir, pm = full_report
    result = inspect_pdf.inspect_pdf(run_dir)
    sections = {s["section_id"]: s for s in result["sections"]}

    balance = sections["s-consolidated-balance-sheet"]
    assert balance["start_page"] == pm["合并资产负债表"]
    assert balance["end_page"] == pm["合并资产负债表"] + 1
    assert balance["location_basis"] == "bookmark"
    assert balance["verified"] is True

    parent = sections["s-parent-balance-sheet"]
    assert parent["start_page"] == pm["母公司资产负债表"]
    assert parent["end_page"] == pm["母公司资产负债表"]
    assert parent["start_page"] > balance["end_page"]

    cash = sections["s-consolidated-cash-flow"]
    assert cash["start_page"] == pm["合并现金流量表"]
    assert cash["end_page"] == pm["审计报告"] - 1


def test_printed_page_offset_recorded(full_report):
    run_dir, pm = full_report
    inspect_pdf.inspect_pdf(run_dir)
    pages = read_pages(run_dir)
    assert len(pages) == pm["_page_count"]
    balance_page = pages[pm["合并资产负债表"] - 1]
    assert balance_page["pdf_page"] == pm["合并资产负债表"]
    assert balance_page["printed_page"] == pm["合并资产负债表"] - 1
    cover = pages[0]
    assert cover["pdf_page"] == 1
    assert cover["printed_page"] is None


def test_keyword_trap_does_not_create_section(full_report):
    run_dir, pm = full_report
    result = inspect_pdf.inspect_pdf(run_dir)
    mdna = next(
        s for s in result["sections"] if s["section_id"] == "s-mdna"
    )
    assert mdna["start_page"] == pm["管理层讨论与分析"]
    balance = next(
        s for s in result["sections"] if s["section_id"] == "s-consolidated-balance-sheet"
    )
    assert balance["start_page"] != pm["管理层讨论与分析"]


def test_toc_only_report_uses_printed_toc_with_verification(run_dir):
    data, pm = build_annual_report(with_bookmarks=False)
    prepare_run_dir(run_dir, data)
    result = inspect_pdf.inspect_pdf(run_dir)
    sections = {s["section_id"]: s for s in result["sections"]}

    summary = sections["s-summary-financials"]
    assert summary["location_basis"] == "printed_toc"
    assert summary["verified"] is True
    assert summary["start_page"] == pm["第三节 会计数据和财务指标摘要"]

    balance = sections["s-consolidated-balance-sheet"]
    assert balance["location_basis"] == "keyword_scan"
    assert balance["verified"] is False
    assert balance["start_page"] == pm["合并资产负债表"]


def test_no_bookmark_no_toc_falls_back_to_keyword_scan(run_dir):
    data, pm = build_annual_report(with_bookmarks=False, with_toc_page=False)
    prepare_run_dir(run_dir, data)
    result = inspect_pdf.inspect_pdf(run_dir)
    for section in result["sections"]:
        assert section["location_basis"] == "keyword_scan"
        assert section["verified"] is False
    sections = {s["section_id"]: s for s in result["sections"]}
    assert sections["s-consolidated-income-statement"]["start_page"] == pm["合并利润表"]


def test_document_metadata_extracted(full_report):
    run_dir, pm = full_report
    result = inspect_pdf.inspect_pdf(run_dir)
    doc = result["document"]
    assert doc["company_name"] == "贵州检测科技股份有限公司"
    assert doc["stock_code"] == "300001"
    assert doc["report_type"] == "annual"
    assert doc["period"] == {
        "kind": "duration",
        "start": "2024-01-01",
        "end": "2024-12-31",
        "frequency": "annual",
        "aggregation": "cumulative",
    }
    assert doc["audit_status"] == "audited"
    assert doc["is_full_text"] is True
    assert doc["page_count"] == pm["_page_count"]
    assert doc["metadata_conflicts"] == []
    assert doc["applicability"]["framework"] == "general"
    assert doc["applicability"]["audit_available"] is True


def test_period_frequency_uses_contract_values():
    """period.frequency 直接产事实合同值，下游不再归一化（semi_annual→half_year 等）。"""
    assert set(inspect_pdf._FREQUENCY_BY_TYPE) == set(inspect_pdf._PERIOD_END)
    assert inspect_pdf._FREQUENCY_BY_TYPE["semi_annual"] == "half_year"
    assert inspect_pdf._FREQUENCY_BY_TYPE["q1"] == "quarter"
    assert inspect_pdf._FREQUENCY_BY_TYPE["q3"] == "quarter"


def test_year_conflict_recorded(run_dir):
    data, _pm = build_annual_report(year_conflict=True)
    prepare_run_dir(run_dir, data)
    result = inspect_pdf.inspect_pdf(run_dir)
    conflicts = result["document"]["metadata_conflicts"]
    assert conflicts, "expected a conflict entry"
    entry = conflicts[0]
    assert entry["field"] == "report_period"
    assert any("2024" in value for value in entry["values"])
    assert any("2023" in value for value in entry["values"])
    assert 2 in entry["pages"]


def test_scanned_and_mixed_pages_classified(full_report):
    run_dir, pm = full_report
    inspect_pdf.inspect_pdf(run_dir)
    pages = read_pages(run_dir)
    scan = pages[pm["_scan_page"] - 1]
    assert scan["text_quality"] == "scanned"
    assert scan["scanned_region_ratio"] > 0.8
    mixed = pages[pm["_mixed_page"] - 1]
    assert mixed["text_quality"] == "native"
    assert 0 < mixed["scanned_region_ratio"] < 0.8


def test_stdout_contains_only_status_line(full_report, capsys):
    run_dir, _pm = full_report
    code = inspect_pdf.main(["--run-dir", str(run_dir)])
    assert code == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["status"] == "ok"
    assert "合并资产负债表" not in out


def test_missing_source_pdf_fails(run_dir):
    with pytest.raises(SystemExit) as exc_info:
        inspect_pdf.main(["--run-dir", str(run_dir)])
    assert exc_info.value.code == 1
