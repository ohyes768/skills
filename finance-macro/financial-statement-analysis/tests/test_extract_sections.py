import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))

import extract_sections
import inspect_pdf
from build_synthetic_pdfs import build_annual_report


def prepare(run_dir: Path, **kwargs) -> dict:
    data, page_map = build_annual_report(**kwargs)
    (run_dir / "source.pdf").write_bytes(data)
    inspect_pdf.inspect_pdf(run_dir)
    return page_map


def by_kind(result: dict, kind: str) -> list[dict]:
    return [e for e in result["evidences"] if e["kind"] == kind]


def read_table(run_dir: Path, evidence: dict) -> dict:
    return json.loads((run_dir / evidence["file"]).read_text(encoding="utf-8"))


def test_section_text_and_merged_table(run_dir):
    pm = prepare(run_dir)
    result = extract_sections.extract_sections(
        run_dir, section_ids=["s-consolidated-balance-sheet"]
    )
    texts = by_kind(result, "text")
    tables = by_kind(result, "table")
    assert len(texts) == 2
    assert sorted(e["pdf_pages"] for e in texts) == [
        [pm["合并资产负债表"]],
        [pm["合并资产负债表"] + 1],
    ]
    assert len(tables) == 1
    table = read_table(run_dir, tables[0])
    assert table["headers"] == ["项目", "期末余额", "期初余额"]
    assert tables[0]["pdf_pages"] == [pm["合并资产负债表"], pm["合并资产负债表"] + 1]
    money_rows = [row for row in table["rows"] if row and row[0] == "货币资金"]
    assert money_rows and money_rows[0][1] == "150,000,000.00"
    total_rows = [row for row in table["rows"] if row and row[0] == "资产总计"]
    assert total_rows, "second page rows must be merged in"


def test_continued_header_mismatch_kept_separate(run_dir):
    prepare(run_dir, balance_continued_mismatch=True)
    result = extract_sections.extract_sections(
        run_dir, section_ids=["s-consolidated-balance-sheet"]
    )
    tables = by_kind(result, "table")
    assert len(tables) == 2
    mismatched = [e for e in tables if e["issues"]]
    assert mismatched, "mismatch must be recorded as an issue"


def test_parenthesized_negative_preserved(run_dir):
    prepare(run_dir)
    result = extract_sections.extract_sections(
        run_dir, section_ids=["s-consolidated-income-statement"]
    )
    tables = by_kind(result, "table")
    assert tables
    all_cells = [cell for table in tables for row in read_table(run_dir, table)["rows"] for cell in row]
    assert "(25,000,000.00)" in all_cells


def test_dash_preserved_as_missing(run_dir):
    prepare(run_dir)
    result = extract_sections.extract_sections(
        run_dir, section_ids=["s-consolidated-cash-flow"]
    )
    tables = by_kind(result, "table")
    assert tables
    all_cells = [cell for table in tables for row in read_table(run_dir, table)["rows"] for cell in row]
    assert "—" in all_cells
    assert "0" not in [c for c in all_cells if c.strip() == "0"]


def test_pages_selection(run_dir):
    pm = prepare(run_dir)
    start = pm["合并资产负债表"]
    result = extract_sections.extract_sections(run_dir, pages=[start, start + 1])
    covered = {page for e in result["evidences"] for page in e["pdf_pages"]}
    assert covered == {start, start + 1}


def test_image_table_without_ocr_is_incomplete(run_dir):
    pm = prepare(run_dir, income_as_image=True)
    result = extract_sections.extract_sections(
        run_dir, pages=[pm["合并利润表"]], ocr_runner=lambda path: None
    )
    start_page_texts = [e for e in by_kind(result, "text") if e["complete"] is False]
    assert start_page_texts, "image-only page text evidence must be incomplete"
    assert any("OCR" in issue or "ocr" in issue for e in start_page_texts for issue in e["issues"])


def test_ocr_runner_injected_recovers_text(run_dir):
    pm = prepare(run_dir, income_as_image=True)

    def fake_runner(image_path: Path) -> str:
        return "合并利润表\n营业总收入        1,200,000,000.00        1,000,000,000.00"

    result = extract_sections.extract_sections(
        run_dir,
        pages=[pm["合并利润表"]],
        ocr_runner=fake_runner,
    )
    ocr_texts = [e for e in by_kind(result, "text") if e["method"] == "ocr"]
    assert ocr_texts, "OCR evidence expected"
    assert ocr_texts[0]["complete"] is True
    content = (run_dir / ocr_texts[0]["file"]).read_text(encoding="utf-8")
    assert "营业总收入" in content


def test_mixed_page_image_crop_saved(run_dir):
    pm = prepare(run_dir)
    result = extract_sections.extract_sections(run_dir, pages=[pm["_mixed_page"]])
    crops = by_kind(result, "image_crop")
    assert crops
    assert (run_dir / crops[0]["file"]).exists()


def test_evidence_ids_stable_across_runs(run_dir):
    prepare(run_dir)
    first = extract_sections.extract_sections(run_dir, section_ids=["s-mdna"])
    second = extract_sections.extract_sections(run_dir, section_ids=["s-mdna"])
    ids1 = [e["evidence_id"] for e in first["evidences"]]
    ids2 = [e["evidence_id"] for e in second["evidences"]]
    assert ids1 == ids2
    assert ids1[0] == "ev-0001"


def test_pages_rerun_reuses_section_text_evidence(run_dir):
    pm = prepare(run_dir)
    start = pm["合并资产负债表"]
    first = extract_sections.extract_sections(
        run_dir, section_ids=["s-consolidated-balance-sheet"])
    section_text = {e["pdf_pages"][0]: e["evidence_id"] for e in by_kind(first, "text")}
    second = extract_sections.extract_sections(run_dir, pages=[start, start + 1, start + 2])
    texts = by_kind(second, "text")
    pages = [e["pdf_pages"][0] for e in texts]
    assert len(pages) == len(set(pages)), "one text evidence per page"
    for evidence in texts:
        page = evidence["pdf_pages"][0]
        if page in section_text:
            assert evidence["evidence_id"] == section_text[page]
            assert "s-consolidated-balance-sheet" in evidence["section_ids"]
    files = {p.name for p in (run_dir / "excerpts").glob("*.txt")}
    assert files == {Path(e["file"]).name for e in texts}


def test_pages_first_then_section_attaches_section(run_dir):
    pm = prepare(run_dir)
    start = pm["合并资产负债表"]
    first = extract_sections.extract_sections(run_dir, pages=[start])
    page_id = by_kind(first, "text")[0]["evidence_id"]
    second = extract_sections.extract_sections(
        run_dir, section_ids=["s-consolidated-balance-sheet"])
    reused = [e for e in by_kind(second, "text") if e["pdf_pages"] == [start]]
    assert [e["evidence_id"] for e in reused] == [page_id]
    assert reused[0]["section_id"] == "s-consolidated-balance-sheet"


def test_cli_exit_2_when_ocr_unavailable(run_dir, capsys, monkeypatch):
    prepare(run_dir, income_as_image=True)
    monkeypatch.setattr(extract_sections, "default_ocr_runner", lambda image_path: None)
    with pytest.raises(SystemExit) as exc_info:
        extract_sections.main(["--run-dir", str(run_dir), "--pages", "12"])
    assert exc_info.value.code == 2
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["status"] == "partial"
    assert payload["issues"], "unextracted pages must be listed in issues"


def test_extract_page_table_counts_and_returns_first_only():
    """同页多表：报告合格表格总数，但只提取第一张——计数供主循环产生告警。"""

    class FakePage:
        def extract_tables(self):
            return [
                [["项目", "期末余额"], ["货币资金", "150.00"], ["应收账款", "80.00"]],
                [["项目", "本期金额"], ["营业总收入", "230.73"], ["营业总成本", "190.00"]],
                [["单行表", "被忽略"]],
            ]

    class FakePdf:
        def __init__(self):
            self.pages = [FakePage()]

    rows, method, count = extract_sections._extract_page_table(FakePdf(), {"blocks": []}, 1)
    assert count == 2
    assert method == "pdfplumber_table"
    assert rows[0] == ["项目", "期末余额"], "only the first usable table is returned"
    assert ["营业总收入", "230.73"] not in rows, "second table must not leak into the first"


def test_multiple_table_warning_reaches_manifest(run_dir, monkeypatch):
    """主循环把同页多表计数转成 evidence issues，写入 manifest。"""
    prepare(run_dir)
    real = extract_sections._extract_page_table

    def fake(plumber_pdf, page_data, page_no):
        rows, method, count = real(plumber_pdf, page_data, page_no)
        return rows, method, max(count, 2)

    monkeypatch.setattr(extract_sections, "_extract_page_table", fake)
    result = extract_sections.extract_sections(
        run_dir, section_ids=["s-consolidated-balance-sheet"]
    )
    tables = by_kind(result, "table")
    assert tables, "table evidence must still be produced"
    assert any(
        "multiple tables" in issue for t in tables for issue in t["issues"]
    ), "multiple-tables warning must reach evidence issues"
