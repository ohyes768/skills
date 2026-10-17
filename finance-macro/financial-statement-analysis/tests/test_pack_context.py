import json
from pathlib import Path

import pack_context


def write_json_file(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_pack_run(run_dir: Path, text_chars: int = 13000, table_rows: int = 60) -> None:
    write_json_file(
        run_dir / "sections.json",
        {
            "schema_version": 1,
            "sections": [
                {
                    "section_id": "s-1",
                    "title": "合并资产负债表",
                    "start_page": 9,
                    "end_page": 10,
                    "priority": 30,
                    "location_basis": "bookmark",
                    "verified": True,
                }
            ],
        },
    )
    write_json_file(
        run_dir / "extraction_manifest.json",
        {
            "schema_version": 1,
            "page_count": 17,
            "evidences": [
                {
                    "evidence_id": "ev-0001",
                    "section_id": "s-1",
                    "pdf_pages": [9, 10],
                    "kind": "text",
                    "file": "excerpts/ev-0001.txt",
                    "method": "pymupdf_text",
                    "complete": True,
                    "issues": [],
                },
                {
                    "evidence_id": "ev-0002",
                    "section_id": "s-1",
                    "pdf_pages": [9, 10],
                    "kind": "table",
                    "file": "excerpts/ev-0002.table.json",
                    "method": "pdfplumber_table",
                    "complete": True,
                    "issues": [],
                },
            ],
        },
    )
    lines = []
    remaining = text_chars
    line_no = 0
    while remaining > 0:
        line_no += 1
        line = f"[p.9] 科目说明第{line_no}行" + "现" * min(48, remaining)
        lines.append(line)
        remaining -= 50
    (run_dir / "excerpts").mkdir(exist_ok=True)
    (run_dir / "excerpts" / "ev-0001.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    write_json_file(
        run_dir / "excerpts" / "ev-0002.table.json",
        {
            "headers": ["项目", "期末余额", "期初余额"],
            "rows": [[f"科目{i}", f"{i},000.00", f"{i},001.00"] for i in range(table_rows)],
            "pages": [9, 10],
        },
    )


def fetch_all_packets(run_dir: Path, stage: str = "analyze", **kwargs) -> list[dict]:
    packets = []
    cursor = None
    for request_seq in range(1, 100):
        result = pack_context.build_packet(
            run_dir,
            stage=stage,
            request_id=f"{stage}-{request_seq:02d}",
            cursor=cursor,
            **kwargs,
        )
        packets.append(result["packet"])
        cursor = result["packet"]["next_cursor"]
        if cursor is None:
            break
    return packets


def test_packet_within_character_limit(run_dir):
    prepare_pack_run(run_dir)
    result = pack_context.build_packet(run_dir, stage="analyze", request_id="analyze-01")
    packet = result["packet"]
    assert packet["character_count"] <= 12000
    assert len(json.dumps(packet, ensure_ascii=False)) <= 12000 + 50


def test_paging_preserves_all_content(run_dir):
    prepare_pack_run(run_dir)
    packets = fetch_all_packets(run_dir)
    assert len(packets) > 1, "large evidence must paginate"

    texts = []
    for packet in packets:
        for item in packet["items"]:
            if item["kind"] == "text":
                texts.append(item["text"])
    original = (run_dir / "excerpts" / "ev-0001.txt").read_text(encoding="utf-8")
    assert "".join(texts) == original

    total_rows = 0
    seen_row_ranges = []
    for packet in packets:
        for item in packet["items"]:
            if item["kind"] == "table":
                total_rows += len(item["rows"])
                seen_row_ranges.extend(range(item["row_range"][0], item["row_range"][1]))
    table = json.loads(
        (run_dir / "excerpts" / "ev-0002.table.json").read_text(encoding="utf-8")
    )
    assert total_rows == len(table["rows"])
    assert sorted(seen_row_ranges) == list(range(len(table["rows"])))
    assert packets[-1]["next_cursor"] is None


def test_table_header_repeated_on_continuation(run_dir):
    prepare_pack_run(run_dir, text_chars=100, table_rows=400)
    packets = fetch_all_packets(run_dir)
    table_items = [
        item for packet in packets for item in packet["items"] if item["kind"] == "table"
    ]
    assert len(table_items) > 1
    headers = table_items[0]["headers"]
    assert headers == ["项目", "期末余额", "期初余额"]
    for item in table_items[1:]:
        assert item["headers"] == headers


def test_cursor_resume_no_overlap(run_dir):
    prepare_pack_run(run_dir)
    first = pack_context.build_packet(run_dir, stage="analyze", request_id="a-01")
    assert first["packet"]["next_cursor"] is not None
    second = pack_context.build_packet(
        run_dir, stage="analyze", request_id="a-02", cursor=first["packet"]["next_cursor"]
    )
    first_texts = [i.get("text", "") for i in first["packet"]["items"] if i["kind"] == "text"]
    second_texts = [i.get("text", "") for i in second["packet"]["items"] if i["kind"] == "text"]
    assert first_texts and second_texts
    overlap = set(first_texts) & set(second_texts)
    assert not overlap


def test_chinese_character_count_accurate(run_dir):
    prepare_pack_run(run_dir, text_chars=100, table_rows=2)
    result = pack_context.build_packet(run_dir, stage="analyze", request_id="a-01")
    packet = result["packet"]
    exact = len(json.dumps(packet, ensure_ascii=False))
    assert packet["character_count"] == exact


def test_usage_log_accumulates_repeats(run_dir):
    prepare_pack_run(run_dir, text_chars=100, table_rows=2)
    pack_context.build_packet(run_dir, stage="analyze", request_id="a-01")
    pack_context.build_packet(run_dir, stage="analyze", request_id="a-02")
    lines = (run_dir / "context_usage.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first, second = json.loads(lines[0]), json.loads(lines[1])
    assert first["packet_sha256"] == second["packet_sha256"]
    summary = second["usage_summary"]
    assert summary["total_delivered_chars"] == first["character_count"] + second["character_count"]
    assert summary["unique_packets"] == 1
    assert summary["repeat_packets"] == 1


def test_no_fabricated_token_numbers(run_dir):
    prepare_pack_run(run_dir, text_chars=100, table_rows=2)
    pack_context.build_packet(run_dir, stage="analyze", request_id="a-01")
    line = (run_dir / "context_usage.jsonl").read_text(encoding="utf-8").splitlines()[0]
    usage = json.loads(line)
    assert usage["estimated_input_tokens"] is None
    assert usage["tokenizer"] is None


def test_locate_stage_returns_index_without_full_text(run_dir):
    prepare_pack_run(run_dir)
    result = pack_context.build_packet(run_dir, stage="locate", request_id="locate-01")
    packet = result["packet"]
    texts = [item for item in packet["items"] if item["kind"] == "text_full"]
    assert not texts
    sections = [item for item in packet["items"] if item["kind"] == "section_index"]
    assert sections and sections[0]["section_id"] == "s-1"
    evidence_index = [item for item in packet["items"] if item["kind"] == "evidence_index"]
    assert evidence_index


def test_sections_filter(run_dir):
    prepare_pack_run(run_dir)
    write_json_file(
        run_dir / "extraction_manifest.json",
        json.loads((run_dir / "extraction_manifest.json").read_text(encoding="utf-8"))
        | {
            "evidences": [
                {
                    "evidence_id": "ev-0003",
                    "section_id": "s-2",
                    "pdf_pages": [12],
                    "kind": "text",
                    "file": "excerpts/ev-0003.txt",
                    "method": "pymupdf_text",
                    "complete": True,
                    "issues": [],
                }
            ]
        },
    )
    (run_dir / "excerpts" / "ev-0003.txt").write_text("[p.12] 其他章节内容\n", encoding="utf-8")
    result = pack_context.build_packet(
        run_dir, stage="analyze", request_id="a-01", section_ids=["s-1"]
    )
    covered = {item["evidence_id"] for item in result["packet"]["items"]}
    assert "ev-0003" not in covered


def test_cli_outputs_single_packet_line(run_dir, capsys):
    prepare_pack_run(run_dir, text_chars=100, table_rows=2)
    code = pack_context.main(
        ["--run-dir", str(run_dir), "--stage", "analyze", "--request-id", "analyze-01"]
    )
    assert code == 0
    out = capsys.readouterr().out
    lines = [line for line in out.splitlines() if line.strip()]
    assert len(lines) == 1
    packet = json.loads(lines[0])
    assert packet["stage"] == "analyze"
    assert (run_dir / "context_usage.jsonl").exists()
