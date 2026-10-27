"""按章节或页面提取文字、表格与图片证据，处理跨页表拼接与 OCR 降级。"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pdfplumber
import pymupdf
from artifacts import emit_status, evidence_sections, read_json, write_json

SEPARATOR_RE = re.compile(r"\s{2,}")


def _text_key(evidence: dict, payload: bytes) -> tuple:
    return (tuple(evidence["pdf_pages"]), evidence["method"], hashlib.sha256(payload).hexdigest())


def _read_pages_index(run_dir: Path) -> list[dict]:
    with open(run_dir / "pages.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _normalize_rows(rows: list[list[str]]) -> list[list[str]]:
    width = max(len(r) for r in rows)
    return [r + [""] * (width - len(r)) for r in rows]


def _extract_page_table(
    plumber_pdf: pdfplumber.PDF, page_data: dict, page_no: int
) -> tuple[list[list[str]] | None, str | None, int]:
    """返回 (首个合格表格, 方法, 该页合格表格总数)；同页多表只提取第一张。"""
    try:
        raw_tables = plumber_pdf.pages[page_no - 1].extract_tables()
    except Exception:  # noqa: BLE001 - pdfplumber 对个别页面可能抛任意解析异常
        raw_tables = []
    usable_tables = 0
    rows = method = None
    for raw in raw_tables or []:
        cleaned = [[(cell or "").strip() for cell in row] for row in raw]
        cleaned = [r for r in cleaned if any(r)]
        if len(cleaned) >= 2:
            usable_tables += 1
            if rows is None:
                rows, method = _normalize_rows(cleaned), "pdfplumber_table"

    if rows is not None:
        return rows, method, usable_tables

    candidate = []
    for block in page_data["blocks"]:
        cells = [c for c in SEPARATOR_RE.split(block["text"].strip()) if c]
        if len(cells) >= 2:
            candidate.append(cells)
    if len(candidate) >= 2:
        return _normalize_rows(candidate), "text_lines", 1
    return None, None, 0


def _detect_tesseract() -> str | None:
    exe = shutil.which("tesseract")
    if not exe:
        return None
    try:
        result = subprocess.run(  # noqa: PLW1510 - returncode 手动判定
            [exe, "--list-langs"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if "chi_sim" not in (result.stdout or ""):
        return None
    return exe


def default_ocr_runner(image_path: Path) -> str | None:
    exe = _detect_tesseract()
    if exe is None:
        return None
    try:
        result = subprocess.run(  # noqa: PLW1510 - returncode 手动判定
            [exe, str(image_path), "stdout", "-l", "chi_sim"],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _render_png(
    doc: pymupdf.Document, page_no: int, out_path: Path, clip: pymupdf.Rect | None = None
) -> None:
    pix = doc[page_no - 1].get_pixmap(dpi=200, clip=clip)
    pix.save(str(out_path))


def _parse_pages_spec(spec: str) -> list[int]:
    result: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            result.extend(range(int(start_s), int(end_s) + 1))
        elif part:
            result.append(int(part))
    return result


def extract_sections(
    run_dir: Path,
    section_ids: list[str] | None = None,
    pages: list[int] | None = None,
    ocr_runner=None,
) -> dict:
    run_dir = Path(run_dir)
    sections_doc = read_json(run_dir / "sections.json")
    document = read_json(run_dir / "document.json")
    pages_index = _read_pages_index(run_dir)
    section_map = {s["section_id"]: s for s in sections_doc["sections"]}

    targets: list[tuple[int, str | None]] = []
    for sid in section_ids or []:
        sec = section_map[sid]
        targets.extend((p, sid) for p in range(sec["start_page"], sec["end_page"] + 1))
    selected = {p for p, _ in targets}
    for p in pages or []:
        if p not in selected:
            targets.append((p, None))
    targets = sorted(set(targets), key=lambda t: (t[0], t[1] or ""))

    excerpts = run_dir / "excerpts"
    excerpts.mkdir(exist_ok=True)
    digest = hashlib.sha256()
    with open(run_dir / "source.pdf", "rb") as source:
        for chunk in iter(lambda: source.read(65536), b""):
            digest.update(chunk)
    source_sha = digest.hexdigest()
    manifest_path = run_dir / "extraction_manifest.json"
    previous = read_json(manifest_path) if manifest_path.exists() else {}
    existing = previous.get("evidences", [])
    if existing and previous.get("document_sha256") != source_sha:
        raise ValueError("document version changed or legacy source is unbound; use a new run directory")
    highest_id = max((int(e["evidence_id"].removeprefix("ev-")) for e in existing), default=0)
    counter = itertools.count(highest_id + 1)
    evidences: list[dict] = []

    if ocr_runner is None:
        ocr_runner = default_ocr_runner

    with pymupdf.open(filename=str(run_dir / "source.pdf")) as doc:
        pdf_path = str(run_dir / "source.pdf")
        for page_no, sid in targets:
            page_data = pages_index[page_no - 1]
            issues: list[str] = []
            complete = True
            method = "pymupdf_text"
            texts = [b["text"] for b in page_data["blocks"]]
            char_count = sum(len(t) for t in texts)

            if char_count < 5:
                tmp_png = excerpts / f"tmp-ocr-{page_no}.png"
                _render_png(doc, page_no, tmp_png)
                ocr_text = ocr_runner(tmp_png)
                tmp_png.unlink(missing_ok=True)
                if ocr_text:
                    method = "ocr"
                    texts = [line.strip() for line in ocr_text.splitlines() if line.strip()]
                else:
                    complete = False
                    issues.append(
                        f"page {page_no}: text layer damaged or missing; OCR unavailable; page not extracted"
                    )
            elif page_data["text_quality"] == "poor_text":
                issues.append(f"page {page_no}: poor text quality")

            ev_id = f"ev-{next(counter):04d}"
            txt_path = excerpts / f"{ev_id}.txt"
            with open(txt_path, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(f"[p.{page_no}] {line}\n" for line in texts)
            evidences.append(
                {
                    "evidence_id": ev_id,
                    "section_id": sid,
                    "pdf_pages": [page_no],
                    "kind": "text",
                    "file": f"excerpts/{txt_path.name}",
                    "method": method,
                    "complete": complete,
                    "issues": issues,
                }
            )

            if 0.05 < page_data["scanned_region_ratio"] < 0.8:
                for info in doc[page_no - 1].get_image_info():
                    ev_id = f"ev-{next(counter):04d}"
                    png_path = excerpts / f"{ev_id}.png"
                    _render_png(doc, page_no, png_path, clip=pymupdf.Rect(info["bbox"]))
                    evidences.append(
                        {
                            "evidence_id": ev_id,
                            "section_id": sid,
                            "pdf_pages": [page_no],
                            "kind": "image_crop",
                            "file": f"excerpts/{png_path.name}",
                            "method": "image_crop",
                            "complete": False,
                            "issues": [
                                f"page {page_no}: image region saved; OCR not attempted on crop"
                            ],
                        }
                    )

        section_groups: dict[str, list[int]] = {}
        section_order: list[str] = []
        for page_no, sid in targets:
            if sid is None:
                continue
            if sid not in section_groups:
                section_groups[sid] = []
                section_order.append(sid)
            section_groups[sid].append(page_no)

        with pdfplumber.open(pdf_path) as plumber_pdf:
            for sid in section_order:
                merged: list[dict] = []
                for page_no in section_groups[sid]:
                    page_data = pages_index[page_no - 1]
                    rows, method, table_count = _extract_page_table(
                        plumber_pdf, page_data, page_no
                    )
                    if rows is None:
                        continue
                    headers, body = rows[0], rows[1:]
                    prev = merged[-1] if merged else None
                    if (
                        prev is not None
                        and prev["headers"] == headers
                        and prev["pdf_pages"][-1] == page_no - 1
                    ):
                        prev["rows"].extend(body)
                        prev["pdf_pages"].append(page_no)
                        continue
                    issues = []
                    if table_count > 1:
                        issues.append(
                            f"page {page_no}: multiple tables ({table_count}) detected; "
                            "only the first was extracted; second table needs a separate --pages run"
                        )
                    if (
                        prev is not None
                        and prev["headers"] != headers
                        and prev["pdf_pages"][-1] == page_no - 1
                    ):
                        issues.append(
                            f"page {page_no}: column definition mismatch with page "
                            f"{prev['pdf_pages'][-1]}; kept separate"
                        )
                    merged.append(
                        {"headers": headers, "rows": body, "pdf_pages": [page_no], "issues": issues}
                    )

                for item in merged:
                    ev_id = f"ev-{next(counter):04d}"
                    table_path = excerpts / f"{ev_id}.table.json"
                    write_json(
                        table_path,
                        {
                            "headers": item["headers"],
                            "rows": item["rows"],
                            "pages": item["pdf_pages"],
                        },
                    )
                    evidences.append(
                        {
                            "evidence_id": ev_id,
                            "section_id": sid,
                            "pdf_pages": item["pdf_pages"],
                            "kind": "table",
                            "file": f"excerpts/{table_path.name}",
                            "method": "pdfplumber_table",
                            "complete": True,
                            "issues": item["issues"],
                        }
                    )

    # New files never replace an existing ID. Repeated identical extractions
    # reuse the original evidence; additions preserve all earlier references.
    # Page text does not depend on which section requested it, so a page whose
    # text is already extracted keeps one evidence ID and only gains a section.
    known = {e["source_key"]: e for e in existing}
    known_text = {}
    for record in existing:
        record_path = run_dir / record["file"]
        if record["kind"] == "text" and record_path.exists():
            key = _text_key(record, record_path.read_bytes())
            known_text.setdefault(key, record)
    merged = list(existing)
    for evidence in evidences:
        payload = (run_dir / evidence["file"]).read_bytes()
        identity = json.dumps(
            [source_sha, evidence["kind"], evidence["pdf_pages"],
             evidence["section_id"], evidence["method"], hashlib.sha256(payload).hexdigest()],
            ensure_ascii=False,
        )
        evidence["source_key"] = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        if evidence["kind"] == "text":
            evidence["section_ids"] = [evidence["section_id"]] if evidence["section_id"] else []
            reused = known_text.get(_text_key(evidence, payload))
        else:
            reused = known.get(evidence["source_key"])
        if reused is not None:
            (run_dir / evidence["file"]).unlink()
            sid = evidence["section_id"]
            if evidence["kind"] == "text" and sid and sid not in evidence_sections(reused):
                reused["section_ids"] = sorted(evidence_sections(reused) | {sid})
                reused["section_id"] = reused.get("section_id") or sid
            continue
        known[evidence["source_key"]] = evidence
        if evidence["kind"] == "text":
            known_text[_text_key(evidence, payload)] = evidence
        merged.append(evidence)
    manifest = {
        "schema_version": 1,
        "document_sha256": source_sha,
        "page_count": document["page_count"],
        "evidences": merged,
    }
    write_json(run_dir / "extraction_manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="提取重点章节的文字、表格与图片证据")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--sections", default="", help="逗号分隔的 section_id 列表")
    parser.add_argument("--pages", default="", help="页码，如 18-22 或 9,10")
    args = parser.parse_args(argv)

    run_dir = Path(args.run_dir)
    section_ids = [s.strip() for s in args.sections.split(",") if s.strip()]
    pages = _parse_pages_spec(args.pages) if args.pages else None

    try:
        manifest = extract_sections(run_dir, section_ids=section_ids, pages=pages)
    except (FileNotFoundError, ValueError) as exc:
        print(f"extract_sections failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    issues = [
        issue for evidence in manifest["evidences"] for issue in evidence["issues"]
    ]
    incomplete = [e for e in manifest["evidences"] if not e["complete"]]
    emit_status(
        "ok" if not incomplete else "partial",
        {"extraction_manifest": str(run_dir / "extraction_manifest.json")},
        issues,
    )
    if incomplete:
        raise SystemExit(2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
