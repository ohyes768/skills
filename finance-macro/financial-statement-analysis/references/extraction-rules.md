# Extraction Rules

## Section selection (extract_sections.py)

- `--sections` takes a comma-separated list of stable `section_id` values from `sections.json`
  (e.g. `s-consolidated-balance-sheet,s-mdna`).
- `--pages` takes page ranges like `18-22` or `9,10` for targeted re-extraction; selected pages
  that already belong to a chosen section are not extracted twice.
- Page coverage is always 1-based physical PDF pages, never printed page numbers.

## Heading → section mapping (inspect_pdf.py)

| Canonical title | section_id |
|---|---|
| 会计数据和财务指标摘要 | s-summary-financials |
| 管理层讨论与分析 | s-mdna |
| 重要事项 | s-important-events |
| 合并资产负债表 | s-consolidated-balance-sheet |
| 母公司资产负债表 | s-parent-balance-sheet |
| 合并利润表 | s-consolidated-income-statement |
| 母公司利润表 | s-parent-income-statement |
| 合并现金流量表 | s-consolidated-cash-flow |
| 母公司现金流量表 | s-parent-cash-flow |
| 审计报告 | s-audit-report |

Matching rules:

- A title line matches when the line equals the canonical title, or the title appears inside a
  short line (line length ≤ title length + 6, which allows prefixes like `第三节 ` and suffixes
  like `（续）`).
- Long body sentences that merely begin with a section name (e.g. narrative text in MD&A) are
  never treated as headings.
- Location priority: bookmark → printed TOC (entry must be verified against the target page) →
  keyword scan (always `verified: false`).
- Consolidated vs parent statements are distinguished by their exact titles; their ranges must
  never be merged.

## Period and scope rules for extraction

- Consolidated (合并) statements are the default analysis scope; parent-company (母公司) statements
  are separate evidence and must not fill missing consolidated values.
- Continued pages (`（续）`) belong to the same section; a table is merged across pages only when
  the column headers match exactly. On header mismatch the pages stay separate evidences and the
  mismatch is recorded in `issues`.
- Keep every cell exactly as printed: `—`, blank, `(25,000,000.00)` are preserved verbatim.
  Converting dashes/blanks to zero happens nowhere in extraction; missing-value semantics are
  decided later in `financial_schema.py` (`parse_amount`).
- Year columns may switch mid-table (本期/上期); column headers are part of the evidence file so
  downstream mapping can align periods correctly.

## Table extraction strategy

1. `pdfplumber.extract_tables()` (line-based) — preferred when the PDF has ruling lines.
2. Text-line split (2+ spaces as separators) — fallback for borderless text tables; recorded as
   `method: text_lines`.
3. If neither yields a table, the page text evidence alone is kept and the gap is visible in
   `extraction_manifest.json`.

## OCR routing

- Capability probe: `tesseract` on PATH with the `chi_sim` language pack. Neither present → OCR
  is unavailable and the page is listed as not extracted (CLI exit 2).
- Pages with fewer than 5 text characters are treated as image-only and routed to OCR
  (injected runner or the default tesseract runner).
- Mixed pages (scanned ratio between 0.05 and 0.8) keep their native text evidence and save each
  image region as a cropped PNG (`image_crop`) for review or later OCR.
- For a scanned document without a usable TOC, chapter discovery first requires per-page light
  OCR; without OCR capability this degrades visibly instead of silently producing empty sections.
- OCR output is marked `method: ocr` in the evidence so downstream steps can weigh its
  reliability separately from native text.

## Same-page dual tables and cross-page main tables (field lesson, 2026-10)

A-share interim reports do not map physical pages to statements one-to-one: one page can
carry the tail of the previous statement and the header of the next. Choose evidence by
content attribution, never by page attribution.

Known behavior:

- `extract_tables()` sees every recognizable table on the page, but `extract_sections`
  keeps only the first usable one (>= 2 rows). When more than one usable table exists,
  the produced table evidence carries an explicit `multiple tables ... only the first was
  extracted` issue; the second table is a known limitation, not an extraction failure.
- The tail of a consolidated statement typically sits on the page carrying the NEXT
  statement's title: consolidated balance-sheet tail before "母公司资产负债表",
  consolidated income-statement tail before "母公司利润表", consolidated cash-flow tail
  before "母公司现金流量表".

Rules for the agent:

1. Before picking an evidence page, confirm from the pages index which statement the page
   actually carries; then decide between table and text evidence.
2. Attribution requires title + column headers + account rows to agree; a page (or
   `section_id`) alone never assigns statement scope.
3. When one page holds two statements, prefer text evidence (`kind=text` with
   `locator.line`) for the non-first table; a `kind=table` evidence may point at the
   other statement (consolidated vs parent amounts differ wildly — misusing it corrupts
   the analysis silently).
4. If the target table was not extracted, re-extract with `--pages` and verify content
   attribution yourself; never reuse the requested `section_id` as content attribution.
