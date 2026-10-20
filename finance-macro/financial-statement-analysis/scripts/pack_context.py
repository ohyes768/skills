"""按阶段提供限量上下文包、分页游标与读取台账。"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from pathlib import Path

from artifacts import read_json

DEFAULT_MAX_CHARS = 12000
STAGES = ("locate", "map", "analyze", "review")
_ITEM_MARGIN = 120
_BLOCK_BUDGET = DEFAULT_MAX_CHARS - 600


def _encode_cursor(index: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"i": index}).encode()).decode()


def _decode_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return int(json.loads(base64.urlsafe_b64decode(cursor.encode()))["i"])
    except (ValueError, KeyError) as exc:
        raise ValueError(f"invalid cursor: {cursor!r}") from exc


def parse_pages(spec: str) -> list[int] | None:
    """解析「1,3,5-7」形式的页码；空白返回 None（不筛选）。"""
    if not spec.strip():
        return None
    pages: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        start_text, sep, end_text = part.partition("-")
        try:
            start = int(start_text)
            end = int(end_text) if sep else start
        except ValueError as exc:
            raise ValueError(f"invalid page spec: {part!r} in {spec!r}") from exc
        if start < 1 or end < start:
            raise ValueError(f"invalid page range: {part!r} in {spec!r}")
        pages.update(range(start, end + 1))
    return sorted(pages)


def _document_page_count(run_dir: Path) -> int:
    document_path = run_dir / "document.json"
    if document_path.exists():
        count = read_json(document_path).get("page_count")
        if isinstance(count, int) and count > 0:
            return count
    manifest_path = run_dir / "extraction_manifest.json"
    if manifest_path.exists():
        count = read_json(manifest_path).get("page_count")
        if isinstance(count, int) and count > 0:
            return count
    raise ValueError("page bounds unknown: document.json or extraction_manifest.json with page_count required")


def _sorted_evidences(run_dir: Path, section_ids: list[str] | None, pages: list[int] | None):
    manifest = read_json(run_dir / "extraction_manifest.json")
    evidences = manifest.get("evidences", [])
    if section_ids:
        allowed = set(section_ids)
        evidences = [e for e in evidences if e.get("section_id") in allowed]
    if pages:
        allowed_pages = set(pages)
        evidences = [e for e in evidences if allowed_pages & set(e.get("pdf_pages", []))]
    return sorted(evidences, key=lambda e: e["evidence_id"])


def _split_text_blocks(evidence: dict, text: str) -> list[dict]:
    blocks = []
    current_lines: list[str] = []
    used = 0

    def flush():
        nonlocal current_lines, used
        if current_lines:
            blocks.append(_text_block(evidence, "".join(current_lines)))
            current_lines, used = [], 0

    for line in text.splitlines(keepends=True):
        if len(line) > _BLOCK_BUDGET:
            flush()
            for i in range(0, len(line), _BLOCK_BUDGET):
                blocks.append(_text_block(evidence, line[i : i + _BLOCK_BUDGET]))
            continue
        if used + len(line) > _BLOCK_BUDGET:
            flush()
        current_lines.append(line)
        used += len(line)
    flush()
    return blocks


def _text_block(evidence: dict, text: str) -> dict:
    return {
        "evidence_id": evidence["evidence_id"],
        "kind": "text",
        "pdf_pages": evidence["pdf_pages"],
        "text": text,
    }


def _split_table_blocks(evidence: dict, table: dict) -> list[dict]:
    headers = table["headers"]
    rows = table["rows"]
    header_len = len(json.dumps({"headers": headers, "rows": [[]]}, ensure_ascii=False))
    blocks = []
    start = 0
    while start < len(rows):
        used = header_len
        end = start
        while end < len(rows):
            row_len = len(json.dumps(rows[end], ensure_ascii=False)) + 1
            if used + row_len > _BLOCK_BUDGET and end > start:
                break
            used += row_len
            end += 1
        blocks.append(
            {
                "evidence_id": evidence["evidence_id"],
                "kind": "table",
                "pdf_pages": evidence["pdf_pages"],
                "headers": headers,
                "rows": rows[start:end],
                "row_range": [start, end],
                "total_rows": len(rows),
            }
        )
        start = end
    return blocks


def _build_blocks(run_dir: Path, section_ids, pages) -> tuple[list[dict], list[str]]:
    blocks: list[dict] = []
    evidence_ids: list[str] = []
    for evidence in _sorted_evidences(run_dir, section_ids, pages):
        evidence_ids.append(evidence["evidence_id"])
        path = run_dir / evidence["file"]
        if evidence["kind"] == "table":
            table = read_json(path)
            blocks.extend(_split_table_blocks(evidence, table))
        elif evidence["kind"] == "image_crop":
            blocks.append({
                "evidence_id": evidence["evidence_id"],
                "kind": "image_crop",
                "pdf_pages": evidence["pdf_pages"],
                "file": str(path.resolve()),
                "requires_visual_review": True,
                "issues": evidence.get("issues", []),
            })
        else:
            text = path.read_text(encoding="utf-8")
            blocks.extend(_split_text_blocks(evidence, text))
    return blocks, evidence_ids


def _locate_items(run_dir: Path, section_ids, pages) -> tuple[list[dict], list[str]]:
    sections_doc = read_json(run_dir / "sections.json")
    items: list[dict] = []
    evidence_ids: list[str] = []
    for section in sections_doc.get("sections", []):
        if section_ids and section["section_id"] not in set(section_ids):
            continue
        items.append({**section, "kind": "section_index"})
    evidences = (
        _sorted_evidences(run_dir, section_ids, pages)
        if (run_dir / "extraction_manifest.json").exists() else []
    )
    for evidence in evidences:
        evidence_ids.append(evidence["evidence_id"])
        items.append(
            {
                "kind": "evidence_index",
                "evidence_id": evidence["evidence_id"],
                "section_id": evidence.get("section_id"),
                "type": evidence["kind"],
                "pdf_pages": evidence["pdf_pages"],
                "method": evidence["method"],
                "complete": evidence["complete"],
                "issues": evidence["issues"],
            }
        )
    return items, evidence_ids


def _measure(packet: dict) -> int:
    probe = dict(packet, character_count=0)
    n = len(json.dumps(probe, ensure_ascii=False))
    for _ in range(4):
        actual = len(json.dumps(dict(packet, character_count=n), ensure_ascii=False))
        if actual == n:
            break
        n = actual
    return n


def _usage_history(run_dir: Path) -> tuple[int, set[str], int]:
    path = run_dir / "context_usage.jsonl"
    if not path.exists():
        return 0, set(), 0
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return sum(line["character_count"] for line in lines), {
        line["packet_sha256"] for line in lines
    }, len(lines)


def build_packet(
    run_dir: Path,
    *,
    stage: str,
    request_id: str,
    section_ids: list[str] | None = None,
    pages: list[int] | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
    cursor: str | None = None,
) -> dict:
    if stage not in STAGES:
        raise ValueError(f"unknown stage: {stage}")
    run_dir = Path(run_dir)
    if pages:
        page_count = _document_page_count(run_dir)
        bad = [page for page in pages if not 1 <= page <= page_count]
        if bad:
            raise ValueError(f"pages out of range 1..{page_count}: {bad}")
    start = _decode_cursor(cursor)

    if stage == "locate":
        items, evidence_ids = _locate_items(run_dir, section_ids, pages)
        blocks: list[dict] = []
    else:
        blocks, evidence_ids = _build_blocks(run_dir, section_ids, pages)
        items = blocks[start : start]

    candidate_blocks = [] if stage == "locate" else blocks[start:]
    budget = max_chars - _ITEM_MARGIN
    packed: list[dict] = []
    used = 0
    consumed = 0
    for block in candidate_blocks:
        block_len = len(json.dumps(block, ensure_ascii=False)) + 1
        if packed and used + block_len > budget:
            break
        if not packed and block_len > budget:
            raise ValueError(
                f"single block exceeds budget ({block_len} > {budget}); "
                "block splitting produced an oversized chunk"
            )
        packed.append(block)
        used += block_len
        consumed += 1

    next_index = start + consumed
    next_cursor = None
    if stage != "locate" and next_index < len(blocks):
        next_cursor = _encode_cursor(next_index)

    packet = {
        "stage": stage,
        "request_id": request_id,
        "items": packed if stage != "locate" else items,
        "character_count": 0,
        "next_cursor": next_cursor,
    }
    packet["character_count"] = _measure(packet)
    packet_text = json.dumps(packet, ensure_ascii=False)
    sha_source = json.dumps(
        {
            "stage": stage,
            "items": packet["items"],
            "character_count": packet["character_count"],
            "next_cursor": next_cursor,
        },
        ensure_ascii=False,
    )
    packet_sha = hashlib.sha256(sha_source.encode("utf-8")).hexdigest()

    prev_total, prev_shas, prev_lines = _usage_history(run_dir)
    all_shas = prev_shas | {packet_sha}
    summary = {
        "total_delivered_chars": prev_total + packet["character_count"],
        "unique_packets": len(all_shas),
        "repeat_packets": prev_lines + 1 - len(all_shas),
    }
    record = {
        "request_id": request_id,
        "stage": stage,
        "packet_sha256": packet_sha,
        "evidence_ids": evidence_ids,
        "character_count": packet["character_count"],
        "byte_count": len(packet_text.encode("utf-8")),
        "cursor": cursor,
        "estimated_input_tokens": None,
        "tokenizer": None,
        "usage_summary": summary,
    }
    with open(run_dir / "context_usage.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return {"packet": packet, "usage_summary": summary, "packet_sha256": packet_sha}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成限量上下文包并记录读取台账")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--stage", required=True, choices=STAGES)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--sections", default="", help="逗号分隔的 section_id 列表")
    parser.add_argument("--pages", default="")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS)
    parser.add_argument("--cursor", default=None)
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    section_ids = [s.strip() for s in args.sections.split(",") if s.strip()] or None
    pages = parse_pages(args.pages)

    try:
        result = build_packet(
            run_dir,
            stage=args.stage,
            request_id=args.request_id,
            section_ids=section_ids,
            pages=pages,
            max_chars=args.max_chars,
            cursor=args.cursor,
        )
    except (ValueError, FileNotFoundError) as exc:
        print(f"pack_context failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print(json.dumps(result["packet"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
