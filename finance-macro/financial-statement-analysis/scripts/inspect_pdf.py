"""文档元数据、逐页索引、章节候选与页码核验。"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pymupdf
from artifacts import emit_status, write_json

SECTION_DEFS = [
    {"id": "s-summary-financials", "title": "会计数据和财务指标摘要", "priority": 10},
    {"id": "s-mdna", "title": "管理层讨论与分析", "priority": 20},
    {"id": "s-important-events", "title": "重要事项", "priority": 25},
    {"id": "s-consolidated-balance-sheet", "title": "合并资产负债表", "priority": 30},
    {"id": "s-parent-balance-sheet", "title": "母公司资产负债表", "priority": 31},
    {"id": "s-consolidated-income-statement", "title": "合并利润表", "priority": 32},
    {"id": "s-parent-income-statement", "title": "母公司利润表", "priority": 33},
    {"id": "s-consolidated-cash-flow", "title": "合并现金流量表", "priority": 34},
    {"id": "s-parent-cash-flow", "title": "母公司现金流量表", "priority": 35},
    {"id": "s-consolidated-equity-changes", "title": "合并所有者权益变动表", "priority": 36},
    {"id": "s-parent-equity-changes", "title": "母公司所有者权益变动表", "priority": 37},
    {"id": "s-audit-report", "title": "审计报告", "priority": 40},
]

_SECTION_TITLE_BY_LENGTH = sorted(
    ((d["title"], d) for d in SECTION_DEFS), key=lambda pair: -len(pair[0])
)
_SECTION_HEADING_RE = re.compile(r"^第[一二三四五六七八九十]+节")
_TOC_ENTRY_RE = re.compile(r"^(.+?)\s*\.{3,}\s*(\d+)\s*$")
_STOCK_CODE_RE = re.compile(r"(?:股票|证券|公司|A股|A 股)[代碼码][:：]?\s*(\d{6})")
_STOCK_CODE_FALLBACK_RE = re.compile(r"代[码碼][:：]?\s*(\d{6})")
_PRINTED_PAGE_RE = re.compile(r"^(?:第\s*)?(\d{1,4})\s*(?:/\s*\d{1,4})?\s*页?$")
_REPORT_TYPE_RE = re.compile(r"(\d{4})\s*年(年度|度|半年度|第一季度|第三季度)报告")
_KIND_MAP = {"年度": "annual", "度": "annual", "半年度": "semi_annual", "第一季度": "q1", "第三季度": "q3"}
_PERIOD_END = {
    "annual": "-12-31",
    "semi_annual": "-06-30",
    "q1": "-03-31",
    "q3": "-09-30",
}
# period.frequency 直接产事实合同值（financial_schema._FREQUENCIES），下游不再归一化。
_FREQUENCY_BY_TYPE = {"annual": "annual", "semi_annual": "half_year", "q1": "quarter", "q3": "quarter"}
_FINANCIAL_KEYWORDS = ("商业银行", "保险公司", "证券公司", "信托公司", "银行业")
_BASIS_RANK = {"bookmark": 0, "printed_toc": 1, "keyword_scan": 2}


def match_section_def(text: str) -> dict | None:
    for title, defn in _SECTION_TITLE_BY_LENGTH:
        if title in text:
            return defn
    return None


def _page_text(page: dict) -> str:
    return "\n".join(block["text"] for block in page["blocks"])


def _is_title_line(line: str, title: str) -> bool:
    stripped = line.strip()
    if stripped == title:
        return True
    return len(stripped) <= len(title) + 6 and title in stripped


def _page_has_title(page: dict, title: str) -> bool:
    return any(_is_title_line(block["text"], title) for block in page["blocks"])


def _extract_printed_page(blocks: list[dict], page_rect: pymupdf.Rect) -> int | None:
    threshold = page_rect.height * 0.88
    for block in blocks:
        bbox = block["bbox"]
        if bbox[1] >= threshold:
            match = _PRINTED_PAGE_RE.match(block["text"].strip())
            if match:
                return int(match.group(1))
    return None


def _classify_quality(char_count: int, scanned_ratio: float) -> str:
    if char_count < 5 and scanned_ratio >= 0.5:
        return "scanned"
    if char_count < 50 and scanned_ratio >= 0.3:
        return "poor_text"
    return "native"


def _index_pages(doc: pymupdf.Document) -> list[dict]:
    pages: list[dict] = []
    for pno in range(doc.page_count):
        page = doc[pno]
        page_area = abs(page.rect) or 1.0
        blocks: list[dict] = []
        headings: list[str] = []
        char_count = 0
        for raw_block in page.get_text("dict")["blocks"]:
            if raw_block["type"] != 0:
                continue
            for raw_line in raw_block["lines"]:
                text = "".join(span["text"] for span in raw_line["spans"]).strip()
                if not text:
                    continue
                char_count += len(text)
                blocks.append({"text": text, "bbox": [round(v, 1) for v in raw_line["bbox"]]})
                if _SECTION_HEADING_RE.match(text) and len(text) <= 30:
                    headings.append(text)
        images = page.get_image_info()
        scanned_ratio = min(
            1.0, sum(abs(pymupdf.Rect(info["bbox"])) for info in images) / page_area
        )
        for title, _defn in _SECTION_TITLE_BY_LENGTH:
            if any(_is_title_line(block["text"], title) for block in blocks):
                headings.append(title)
                break
        pages.append(
            {
                "pdf_page": pno + 1,
                "printed_page": _extract_printed_page(blocks, page.rect),
                "blocks": blocks,
                "text_quality": _classify_quality(char_count, scanned_ratio),
                "scanned_region_ratio": round(scanned_ratio, 4),
                "heading_candidates": headings,
            }
        )
    return pages


def _parse_toc_page(pages: list[dict]) -> tuple[int, list[tuple[str, int]]] | None:
    for page in pages:
        text = _page_text(page)
        if not re.search(r"^目\s*录$", text, flags=re.MULTILINE):
            continue
        entries = []
        for block in page["blocks"]:
            match = _TOC_ENTRY_RE.match(block["text"].strip())
            if match:
                entries.append((match.group(1).strip(), int(match.group(2))))
        if entries:
            return page["pdf_page"], entries
    return None


def _locate_sections(doc: pymupdf.Document, pages: list[dict]) -> list[dict]:
    found: dict[str, dict] = {}

    def add(defn: dict, start: int, basis: str, verified: bool) -> None:
        if defn["id"] in found:
            return
        found[defn["id"]] = {
            "section_id": defn["id"],
            "title": defn["title"],
            "priority": defn["priority"],
            "start_page": start,
            "end_page": None,
            "location_basis": basis,
            "verified": verified,
        }

    pending_bookmarks: list[tuple[dict, int]] = []
    for _level, title, target_page in doc.get_toc():
        defn = match_section_def(title)
        if defn is None or not (1 <= target_page <= doc.page_count):
            continue
        if _page_has_title(pages[target_page - 1], defn["title"]):
            add(defn, target_page, "bookmark", True)
        else:
            pending_bookmarks.append((defn, target_page))

    toc = _parse_toc_page(pages)
    if toc is not None:
        toc_page_no, entries = toc
        toc_printed = pages[toc_page_no - 1]["printed_page"]
        offset = (toc_page_no - toc_printed) if toc_printed is not None else 1
        for title, printed in entries:
            defn = match_section_def(title)
            if defn is None or defn["id"] in found:
                continue
            physical = printed + offset
            if 1 <= physical <= doc.page_count and _page_has_title(
                pages[physical - 1], defn["title"]
            ):
                add(defn, physical, "printed_toc", True)

    for defn in SECTION_DEFS:
        if defn["id"] in found:
            continue
        for page in pages:
            if _page_has_title(page, defn["title"]):
                add(defn, page["pdf_page"], "keyword_scan", False)
                break

    for defn, target_page in pending_bookmarks:
        add(defn, target_page, "bookmark", False)

    sections = sorted(found.values(), key=lambda s: s["start_page"])
    for i, section in enumerate(sections):
        next_start = sections[i + 1]["start_page"] if i + 1 < len(sections) else doc.page_count + 1
        section["end_page"] = next_start - 1
    return sections


_UNAUDITED_RE = re.compile(r"(?:报告|报表)未经审计")


def _extract_document_meta(doc: pymupdf.Document, pages: list[dict], sections: list[dict]) -> dict:
    cover_text = _page_text(pages[0])

    company_name = None
    for block in pages[0]["blocks"]:
        text = block["text"].strip()
        if text.endswith("公司") and "代码" not in text:
            company_name = text
            break

    code_match = _STOCK_CODE_RE.search(cover_text)
    if code_match is None:
        for page in pages:
            code_match = _STOCK_CODE_FALLBACK_RE.search(_page_text(page))
            if code_match is not None:
                break

    matches: list[tuple[int, str, str]] = []
    for page in pages[:3]:
        for year, kind in _REPORT_TYPE_RE.findall(_page_text(page)):
            matches.append((page["pdf_page"], year, _KIND_MAP[kind]))

    report_type = None
    year = None
    conflicts: list[dict] = []
    if matches:
        cover_matches = [m for m in matches if m[0] == 1]
        chosen = cover_matches[0] if cover_matches else matches[0]
        year, report_type = chosen[1], chosen[2]
        for page_no, other_year, other_type in matches:
            if other_year != year or other_type != report_type:
                conflicts.append(
                    {
                        "field": "report_period",
                        "values": sorted({f"{year}年度", f"{other_year}{other_type}"}),
                        "pages": [page_no],
                    }
                )

    audit_status = "unknown"
    section_ids = {s["section_id"] for s in sections}
    full_text = "\n".join(_page_text(p) for p in pages)
    if _UNAUDITED_RE.search(full_text):
        audit_status = "unaudited"
    elif "s-audit-report" in section_ids:
        audit_status = "audited"

    has_summary = "摘要" in cover_text
    is_full_text = False if has_summary else (len(sections) >= 3 or report_type is not None)

    framework = (
        "financial_institution"
        if any(keyword in full_text[:5000] for keyword in _FINANCIAL_KEYWORDS)
        else "general"
    )

    period = None
    if report_type and year:
        period = {
            "kind": "duration",
            "start": f"{year}-01-01",
            "end": f"{year}{_PERIOD_END[report_type]}",
            "frequency": _FREQUENCY_BY_TYPE[report_type],
            "aggregation": "cumulative",
        }

    return {
        "schema_version": 1,
        "company_name": company_name,
        "stock_code": code_match.group(1) if code_match else None,
        "report_type": report_type,
        "period": period,
        "is_full_text": is_full_text,
        "accounting_standard": "CAS" if "企业会计准则" in full_text else None,
        "currency": "CNY" if "人民币" in full_text or "元" in full_text else None,
        "audit_status": audit_status,
        "page_count": doc.page_count,
        "metadata_conflicts": conflicts,
        "applicability": {
            "framework": framework,
            "audit_available": audit_status == "audited",
            "full_text": is_full_text,
        },
    }


def inspect_pdf(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    source_pdf = run_dir / "source.pdf"
    if not source_pdf.exists():
        raise FileNotFoundError(f"missing source.pdf under {run_dir}")

    with pymupdf.open(filename=str(source_pdf)) as doc:
        pages = _index_pages(doc)
        sections = _locate_sections(doc, pages)
        document = _extract_document_meta(doc, pages, sections)

    write_json(run_dir / "document.json", document)
    with open(run_dir / "pages.jsonl", "w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(page, ensure_ascii=False) + "\n" for page in pages)
    write_json(run_dir / "sections.json", {"schema_version": 1, "sections": sections})
    return {"document": document, "sections": sections, "pages": pages}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成文档索引、元数据与章节候选")
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args(argv)

    try:
        result = inspect_pdf(Path(args.run_dir))
    except FileNotFoundError as exc:
        print(f"inspect_pdf failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    run_dir = Path(args.run_dir)
    emit_status(
        "ok",
        {
            "document_json": str(run_dir / "document.json"),
            "pages_jsonl": str(run_dir / "pages.jsonl"),
            "sections_json": str(run_dir / "sections.json"),
        },
        [f"unverified sections: {len([s for s in result['sections'] if not s['verified']])}"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
