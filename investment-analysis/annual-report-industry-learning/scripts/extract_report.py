# /// script
# requires-python = ">=3.10"
# dependencies = ["pdfplumber>=0.11,<0.12"]
# ///
"""Download annual reports and propose auditable, page-tagged section candidates."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_BYTES = 150 * 1024 * 1024
TOPICS = {
    "industry": ("公司所处行业情况", "所处行业基本情况", "行业情况", "行业发展情况"),
    "business": ("公司从事的主要业务", "主要业务", "主要业务及经营模式"),
    "competitiveness": ("核心竞争力分析", "核心竞争力"),
    "outlook": ("公司未来发展的展望", "未来发展展望", "未来发展的讨论与分析"),
    "risks": ("风险因素", "公司面临的风险", "可能面对的风险", "可能面临的风险", "风险及应对措施"),
}
CHAPTER = re.compile(r"^第[三3](?:节|章)管理层讨论与分析$")
NEXT_CHAPTER = re.compile(r"^第[四4](?:节|章)")
HEADING = re.compile(r"^(?:[一二三四五六七八九十百]+[、．.]|[（(][一二三四五六七八九十百0-9]+[）)]|\d+[、．.])\s*\S+")


def compact(text):
    return re.sub(r"\s+", "", text)


def obtain_pdf(source, target):
    """Validate before atomic replacement; failed downloads leave no partial PDF."""
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as out:
            temporary = Path(out.name)
            if urlparse(source).scheme in ("http", "https"):
                incoming = urlopen(Request(source, headers={"User-Agent": "AnnualReportIndustryLearning/1.0"}), timeout=60)
            else:
                incoming = open(source, "rb")
            with incoming:
                size = 0
                while True:
                    chunk = incoming.read(65536)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise ValueError("PDF exceeds 150 MiB limit")
                    out.write(chunk)
        with temporary.open("rb") as stream:
            if b"%PDF-" not in stream.read(1024):
                raise ValueError("Input is not a PDF (possibly an HTML error page)")
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def locate(pages):
    lines = [(p["page"], line) for p in pages for line in p["text"].splitlines()]
    starts = [i for i, (_, line) in enumerate(lines) if CHAPTER.fullmatch(compact(line))]
    warnings = []
    if not starts:
        return [], ["Management discussion chapter not found; inspect pages.md and locate manually."]
    # A stand-alone heading excludes the usual TOC dotted leaders and page number.
    start = starts[-1]
    end = next((i for i in range(start + 1, len(lines)) if NEXT_CHAPTER.match(compact(lines[i][1]))), len(lines))
    if end == len(lines):
        warnings.append("Next chapter boundary missing; verify chapter end manually.")
    chapter = lines[start + 1:end]
    headings = [i for i, (_, line) in enumerate(chapter) if len(compact(line)) < 90 and HEADING.match(compact(line))]
    candidates = []
    for i in headings:
        page, title = chapter[i]
        normalized = compact(title)
        matched = [key for key, aliases in TOPICS.items() if any(alias in normalized for alias in aliases)]
        if not matched:
            continue
        # Stop at the next heading of the same or higher level, preserving children.
        level = heading_level(normalized)
        stop = next((j for j in headings if j > i and heading_level(compact(chapter[j][1])) <= level), len(chapter))
        content = chapter[i:stop]
        candidates.append({"topics": matched, "title": title, "start_page": page,
                           "end_page": content[-1][0], "lines": [{"page": p, "text": t} for p, t in content]})
    # Child headings remain in their parent's text; avoid duplicate topic candidates.
    candidates = [c for index, c in enumerate(candidates)
                  if not any(set(c["topics"]).issubset(parent["topics"])
                             and c["lines"][0] in parent["lines"][1:]
                             for parent in candidates[:index])]
    found = {topic for c in candidates for topic in c["topics"]}
    for topic in TOPICS:
        if topic not in found:
            warnings.append(f"No heading candidate for {topic}; inspect full chapter, do not infer absence from this heuristic.")
    return candidates, warnings


def heading_level(text):
    if re.match(r"^[一二三四五六七八九十百]+[、．.]", text):
        return 1
    if re.match(r"^[（(][一二三四五六七八九十百]", text):
        return 2
    if re.match(r"^[（(]\d", text):
        return 4
    return 3


def markdown_lines(lines):
    result, previous = [], None
    for item in lines:
        if item["page"] != previous:
            previous = item["page"]
            result.append(f"\n<!-- PDF page {previous} -->\n")
        result.append(item["text"])
    return "\n".join(result)


def parse_page_ranges(value):
    """Parse one-based comma-separated page numbers/ranges for fallback review."""
    result = set()
    try:
        for part in value.split(','):
            ends = part.split('-')
            if len(ends) > 2:
                raise ValueError
            first, last = int(ends[0]), int(ends[-1])
            if first < 1 or last < first:
                raise ValueError
            result.update(range(first, last + 1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use positive page numbers/ranges, e.g. 10-15,28") from exc
    return result


def extract(pdf_path, out, extra_table_pages=None):
    import pdfplumber
    pages, warnings = [], []
    with pdfplumber.open(pdf_path) as pdf:
        for number, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if len(compact(text)) < 20:
                warnings.append(f"PDF page {number}: little/no text; inspect visually and OCR if needed.")
            pages.append({"page": number, "text": text, "tables": None})
    candidates, section_warnings = locate(pages)
    warnings.extend(section_warnings)
    table_pages = {line["page"] for candidate in candidates for line in candidate["lines"]}
    table_pages.update(extra_table_pages or ())
    if any(n < 1 or n > len(pages) for n in table_pages):
        raise ValueError("Requested table page is outside the PDF")
    # Only revisit relevant pages; unrelated financial statement tables are skipped.
    with pdfplumber.open(pdf_path) as pdf:
        for number in sorted(table_pages):
            pages[number - 1]["tables"] = pdf.pages[number - 1].extract_tables()
    payload = {"status": "candidates_require_review", "sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
               "page_count": len(pages), "table_pages": sorted(table_pages), "warnings": warnings, "candidates": candidates}
    (out / "pages.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "pages.md").write_text(markdown_lines([{"page": p["page"], "text": p["text"]} for p in pages]), encoding="utf-8")
    (out / "candidates.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    body = "# 待核验的行业学习原文候选\n\n" + "\n".join(f"- {w}" for w in warnings)
    for candidate in candidates:
        body += f"\n\n## {candidate['title']}\n" + markdown_lines(candidate["lines"])
    (out / "candidates.md").write_text(body + "\n", encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="HTTP(S) PDF URL or local PDF")
    parser.add_argument("--output-dir", required=True, type=Path, help="New directory for this report")
    parser.add_argument("--table-pages", type=parse_page_ranges, default=set(),
                        help="Additional pages for tables if heading detection misses content, e.g. 10-15,28")
    args = parser.parse_args()
    try:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        pdf_path = args.output_dir / "source.pdf"
        obtain_pdf(args.source, pdf_path)
        payload = extract(pdf_path, args.output_dir, args.table_pages)
        (args.output_dir / "input.json").write_text(json.dumps({"source": args.source}, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({"output_dir": str(args.output_dir.resolve()), "status": payload["status"], "warnings": payload["warnings"]}, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
