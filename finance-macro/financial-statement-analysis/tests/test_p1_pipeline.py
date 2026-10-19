"""P1 回归：首次读取、增量证据身份与混合页传递。"""

import json

import extract_sections
import pack_context
import pytest
from test_extract_sections import prepare


def test_locate_before_any_extraction(run_dir):
    prepare(run_dir)
    assert not (run_dir / "extraction_manifest.json").exists()
    packet = pack_context.build_packet(run_dir, stage="locate", request_id="first")["packet"]
    assert any(item["kind"] == "section_index" for item in packet["items"])


def test_supplement_preserves_existing_evidence_and_ids(run_dir):
    pages = prepare(run_dir)
    first = extract_sections.extract_sections(
        run_dir, section_ids=["s-consolidated-balance-sheet"]
    )
    original = {e["evidence_id"]: (e, (run_dir / e["file"]).read_bytes())
                for e in first["evidences"]}
    second = extract_sections.extract_sections(run_dir, pages=[pages["合并利润表"]])
    after = {e["evidence_id"]: e for e in second["evidences"]}
    assert set(original) <= set(after)
    for evidence_id, (evidence, content) in original.items():
        assert after[evidence_id]["pdf_pages"] == evidence["pdf_pages"]
        assert (run_dir / evidence["file"]).read_bytes() == content
    third = extract_sections.extract_sections(run_dir, pages=[pages["合并利润表"]])
    assert third == second, "same-document supplement must be idempotent"


def test_new_document_cannot_rebind_existing_evidence(run_dir):
    prepare(run_dir)
    extract_sections.extract_sections(run_dir, pages=[9])
    manifest = (run_dir / "extraction_manifest.json").read_bytes()
    with open(run_dir / "source.pdf", "ab") as stream:
        stream.write(b"\n% new document version\n")
    with pytest.raises(ValueError, match="document|source|version"):
        extract_sections.extract_sections(run_dir, pages=[12])
    assert (run_dir / "extraction_manifest.json").read_bytes() == manifest


def test_mixed_page_pack_returns_image_reference_without_decoding(run_dir):
    pages = prepare(run_dir)
    extract_sections.extract_sections(run_dir, pages=[pages["_mixed_page"]])
    packet = pack_context.build_packet(run_dir, stage="map", request_id="mixed")["packet"]
    images = [item for item in packet["items"] if item["kind"] == "image_crop"]
    assert images and images[0]["requires_visual_review"] is True
    assert images[0]["file"].endswith(".png")
    assert "text" not in images[0]
    manifest = json.loads((run_dir / "extraction_manifest.json").read_text(encoding="utf-8"))
    assert any(not e["complete"] for e in manifest["evidences"] if e["kind"] == "image_crop")
