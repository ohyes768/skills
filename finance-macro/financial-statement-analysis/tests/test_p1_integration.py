"""Fresh offline pipeline, including supplementation after a report is written."""

import json

import calculate_metrics
import extract_sections
import fetch_pdf
import httpx
import inspect_pdf
import pack_context
import validate_report
from fixtures import build_synthetic_pdfs


def test_fresh_pdf_to_validated_report_and_supplement(run_dir, make_fact, monkeypatch):
    # Keep both amount columns inside the physical page in this generated fixture.
    monkeypatch.setattr(build_synthetic_pdfs, "PAGE_WIDTH", 842)
    pdf, pages = build_synthetic_pdfs.build_annual_report()
    with httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=pdf))) as client:
        monkeypatch.setattr(fetch_pdf, "_cli_client", client)
        assert fetch_pdf.main(["--url", "https://example.com/annual.pdf",
                               "--output-dir", str(run_dir)]) == 0
    assert inspect_pdf.main(["--run-dir", str(run_dir)]) == 0
    packet = pack_context.build_packet(run_dir, stage="locate", request_id="first")["packet"]
    assert any(item["kind"] == "section_index" for item in packet["items"])
    manifest = extract_sections.extract_sections(run_dir, section_ids=["s-consolidated-income-statement"])
    evidence = next(e for e in manifest["evidences"] if e["kind"] == "table")
    mapped = pack_context.build_packet(run_dir, stage="map", request_id="map-first")["packet"]
    assert any(item.get("evidence_id") == evidence["evidence_id"] for item in mapped["items"])
    table = json.loads((run_dir / evidence["file"]).read_text(encoding="utf-8"))
    row = next(row for row in table["rows"] if "营业总收入" in row[0])
    facts = [make_fact("f-current", "revenue", row[1].replace(",", ""),
                       evidence_ids=[evidence["evidence_id"]]),
             make_fact("f-prior", "revenue", row[2].replace(",", ""),
                       start="2023-01-01", end="2023-12-31",
                       evidence_ids=[evidence["evidence_id"]])]
    financials = {"schema_version": 1, "document_sha256": manifest["document_sha256"],
                  "facts": facts}
    (run_dir / "financials.json").write_text(json.dumps(financials), encoding="utf-8")
    # Revenue is sufficient for YoY; unrelated missing metrics stay unavailable.
    assert calculate_metrics.main(["--run-dir", str(run_dir)]) == 0
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    yoy = next(m for m in metrics["metrics"] if m["metric_id"] == "revenue_yoy")
    assert yoy["status"] == "computed" and yoy["value"] == "0.2"
    assert next(m for m in metrics["metrics"] if m["metric_id"] == "net_margin_group")["value"] is None
    text = f"营业收入同比增长 20%（PDF 第 {pages['合并利润表']} 页）"
    (run_dir / "analysis.md").write_text("# 分析\n## 核心结论\n" + text, encoding="utf-8")
    claims = {"schema_version": 1, "claims": [{
        "claim_id": "c-1", "report_anchor": "## 核心结论", "text": text,
        "claim_type": "calculation", "metric_ids": ["revenue_yoy"],
        "fact_ids": [], "evidence_ids": [], "source_pages": evidence["pdf_pages"]}]}
    (run_dir / "report_claims.json").write_text(json.dumps(claims), encoding="utf-8")
    assert validate_report.main(["--run-dir", str(run_dir)]) == 0
    original = (run_dir / evidence["file"]).read_bytes()
    extract_sections.extract_sections(run_dir, section_ids=["s-mdna"])
    assert (run_dir / evidence["file"]).read_bytes() == original
    remapped = pack_context.build_packet(run_dir, stage="map", request_id="map-supplement")["packet"]
    assert any(item.get("evidence_id") == evidence["evidence_id"] for item in remapped["items"])
    assert validate_report.main(["--run-dir", str(run_dir)]) == 0
