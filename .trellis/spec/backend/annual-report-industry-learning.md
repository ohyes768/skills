# Annual report industry learning

## Scope / Trigger
Maintain finance-macro/annual-report-industry-learning and its PDF extraction helper.

## Signatures
`uv run scripts/extract_report.py SOURCE --output-dir NEW_DIRECTORY`
Optional `--table-pages 10-15,28` adds fallback table pages.

`python scripts/assemble_report.py --title TITLE --summary REVIEWED_MD --source REVIEWED_MD --output FINAL_MD`

SOURCE is an HTTP(S) URL or local PDF. No credentials or environment variables required.

## Contracts
Successful execution returns JSON with output_dir, status=candidates_require_review and warnings. Files: source.pdf, input.json, pages.json (one-based page, text, tables), pages.md, candidates.json (sha256, page_count, warnings, candidates), candidates.md. Each candidate contains topics, title, start_page, end_page and page-tagged lines. Agent review and assembly produce industry-learning.md; the CLI never claims semantic completeness.

## Validation & Error Matrix
Existing output directory -> exit 1 without overwrite. HTML/non-PDF or >150 MiB -> exit 1, temporary download removed. Missing chapter/heading or sparse text -> successful candidate extraction with explicit warnings, requiring review/OCR. Scanned pages must not be treated as empty disclosure.

## Good / Base / Bad Cases
Good: Chinese text annual report with numbered headings yields source candidates. Base: alternative headings require semantic review of pages.md. Bad: HTML download must never become source.pdf. Full outlook is an intermediate only; final text selects industry trends and risks.

## Tests Required
Boundary tests exclude next chapter and preserve subordinate product text; TOC dotted entries do not start a chapter; missing chapter/section warns; invalid local/HTTP data leaves no partial PDF and preserves existing targets. Real report smoke test checks headings and page ranges.

## Wrong vs Correct
Wrong: use matched candidate text directly as verified full source and summarize from memory.
Correct: verify page boundaries/tables, select outlook paragraphs, retain source page references, and mark undisclosed dimensions.

## Optimization contracts
Text is extracted first; tables are then parsed only on candidate and explicit fallback pages. pages.json tables=null means unprocessed, [] means processed without detected tables. candidates.json table_pages lists processed physical pages. Out-of-range extra pages fail.

Risk aliases include 可能面临的风险. Heading ranks: Chinese top-level, parenthesized Chinese, numeric, parenthesized numeric. Risk children remain in the parent candidate.

Assembler inputs are reviewed Markdown including their part headings. Output preserves their content; statistics include visible total and six section body counts. Counts omit common Markdown syntax and inline URLs. Empty inputs, source inline page markers, input/output collisions or totals >1800 fail without writing output. Budgets are warnings. Tests cover 1800/1801 boundary, source preservation, table/link counts, restricted table calls and nested risk headings.
