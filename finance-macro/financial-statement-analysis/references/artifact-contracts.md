# Artifact Contracts

All JSON artifacts are written UTF-8 (`ensure_ascii=False`, indent 2) via `scripts/artifacts.py::write_json`.
Optional values are `null`, never absent keys. Amounts use decimal strings; floats are forbidden in
financial amount fields. Every artifact file lists `schema_version` unless noted.

Script stdout carries exactly one status line from `emit_status`: `{"status": ..., "artifacts": {...}, "issues": [...]}`.
Detailed logs go to stderr or files. Exit codes: 0 success/complete, 1 fatal fetch or contract error,
2 deliverable but incomplete (agent must read `issues` and downgrade affected conclusions).

## source.json — fetch_pdf.py

| Field | Type | Notes |
|---|---|---|
| schema_version | int | |
| requested_url | string | original input |
| final_url | string | after redirects |
| downloaded_at | string ISO-8601 | UTC |
| sha256 | string | of stored file |
| size_bytes | int | |
| etag | string \| null | from response headers |
| last_modified | string \| null | from response headers |
| parser_version | string | PDF library + version used for validation |

## document.json — inspect_pdf.py

| Field | Type | Notes |
|---|---|---|
| schema_version | int | |
| company_name | string \| null | |
| stock_code | string \| null | |
| report_type | string | annual / semi_annual / q1 / q3 / summary / unknown |
| period | object | same shape as `financials.json` period |
| is_full_text | bool \| null | full report vs abstract; null when undetermined |
| accounting_standard | string \| null | e.g. CAS |
| currency | string \| null | original currency, no conversion |
| audit_status | string | audited / unaudited / unknown |
| page_count | int | 1-based physical pages |
| metadata_conflicts | list[object] | {field, values, pages} when cover/TOC/body disagree |
| applicability | object | which analysis frameworks this document supports (general/financial, full/summary) |

## pages.jsonl — inspect_pdf.py (one JSON object per line)

| Field | Type | Notes |
|---|---|---|
| pdf_page | int | 1-based physical page |
| printed_page | int \| null | page number printed on the page |
| blocks | list[object] | {text, bbox} text blocks with coordinates |
| text_quality | string | native / poor_text / scanned |
| scanned_region_ratio | number \| null | 0-1, null for pure native |
| heading_candidates | list[string] | heading-like lines found on the page |

Full text lives only in this local index; never printed to stdout or returned as tool output.

## sections.json — inspect_pdf.py

| Field | Type | Notes |
|---|---|---|
| schema_version | int | |
| sections | list[object] | each: see below |

Section object fields: `section_id` (stable, e.g. `s-consolidated-balance-sheet`),
`title`, `start_page`, `end_page` (inclusive, 1-based), `priority` (int, lower = earlier),
`location_basis` (bookmark / printed_toc / keyword_scan), `verified` (bool — keyword hits alone
are never verified=true).

## extraction_manifest.json — extract_sections.py

`document_sha256` binds the manifest to the exact source PDF. Extraction appends evidence;
existing IDs and files are immutable. `source_key` identifies identical source/content selections
so repeated requests reuse prior records. A changed PDF or a legacy nonempty manifest without
this binding requires a new run directory; never rebind existing claims to a new document.

| Field | Type | Notes |
|---|---|---|
| schema_version | int | |
| evidences | list[object] | each: see below |

Evidence object fields: `evidence_id` (stable, e.g. `ev-0001`), `section_id` \| null,
`pdf_pages` (list[int]), `kind` (text / table / image_crop), `file` (path under `excerpts/`),
`method` (pymupdf_text / pdfplumber_table / ocr / image_crop), `complete` (bool),
`issues` (list[string], e.g. cross-page header mismatch, OCR unavailable).

Image crops are `complete: false` until visually reviewed; context packets contain `file`
(absolute image path), `requires_visual_review: true`, IDs and pages, never decoded PNG text.
The initial `locate` packet works before any extraction manifest exists.

## fact_inputs.json — written by agent, consumed by build_financials.py

Compact fact input; see [fact-inputs-example.md](fact-inputs-example.md) for the full contract.
Each entry carries only judgment fields: `metric` (contracted name or registered alias),
`raw_label`, `raw_value`, `raw_unit`, `period_ref` (`current`/`prior`/`closing`/`opening`),
optional `scope`/`basis`/`aggregation`/`review_status`/`note`, and an `evidence` object
(`evidence_id` plus `locator` `{row, col}` for tables or `{line}` for text).
Attribution is never an input — the metric contract fixes it. Undisclosed tokens
(`—`/`–`/`-`/`--`) produce `value: null` with a program-supplied `missing_reason`.

## financials.json — written by build_financials.py, validated by financial_schema.py

Top level: `schema_version`, `document_sha256`, `currency`, `facts` (list).

Each fact:

| Field | Type | Notes |
|---|---|---|
| fact_id | string | stable, e.g. `f-0001` |
| metric | string | normalized metric name, e.g. `revenue`, `net_profit_group` |
| raw_label | string | as printed in the PDF |
| raw_value | string \| null | as printed |
| raw_unit | string \| null | 元/千元/万元/亿元 |
| value | string \| null | decimal string in base unit of `currency`, or null |
| unit | string | base unit, e.g. 元 |
| currency | string | original currency kept, no conversion |
| scope | string | consolidated / parent |
| attribution | string | group / owners / not_applicable |
| period | object | see below |
| basis | string | as_reported / restated |
| evidence_ids | list[string] | required when value is not null; must be parseable |
| review_status | string | verified / ambiguous / missing / conflict |
| missing_reason | string \| null | required when value is null; null for normal values |

Period object: `kind` (instant/duration), `start` (ISO date, nullable for instant), `end` (ISO date),
`frequency` (annual/half_year/quarter), `aggregation` (instant/cumulative/single_period).

Rules: consolidated/parent, group/owners, cumulative/single_period, as_reported/restated must never be
mixed silently. Missing is never zero. A null value with empty `missing_reason` is a contract violation;
fabricated evidence for null values is a fatal error.

### financial_schema.py API

- `parse_amount(raw_value, raw_unit) -> Decimal | None` — converts the printed string to the base
  unit (元) as `Decimal`; supports 元/千元/万元/亿元, thousands separators, and parenthesized
  negatives; dashes, blanks and unknown units return `None`. Floats never enter the amount path.
- `validate_financials(document) -> list[dict]` — returns a list of
  `{"fact_id", "field", "error"}`; an empty list means the document conforms. Violations (bad enums,
  float values, null value without `missing_reason`, value without evidence, duplicate ids) must
  never pass silently.
- `select_facts(document, metric, scope, attribution, aggregation) -> list[dict]` — returns ALL
  matching candidates across periods and bases; the caller must resolve period/version itself and
  must not default to the first item when candidates conflict.

## metrics.json — calculate_metrics.py

All operands share the document target period, scope, currency, base unit and reporting basis.
If no target period is supplied, infer it once from consolidated duration facts. YoY requires
the same start/end interval one year earlier. Opening balances are at the day before that
interval starts, closing balances at its end; parent balances never enter group calculations.
Null/unverified inputs produce `insufficient_data`; explicit or dimension conflicts produce
`conflict`, with no numeric output. Equivalent verified duplicates may be deduplicated.

Each entry: `metric_id`, `value` (decimal string \| null), `status`
(computed / not_applicable / insufficient_data / conflict), `formula`, `input_fact_ids` (list),
`source_pages` (list[int]), `reason` (null when computed).

## validation.json — calculate_metrics.py

Each entry: `check_id`, `status` (passed / failed / not_applicable), `input_fact_ids`, `residual`
(decimal string \| null), `tolerance` (decimal string \| null), `issues`. Extraction conflicts are
reported here as data problems, independent of financial risk conclusions.

## mapping_validation.json — build_financials.py

`schema_version`, `document_sha256`, `input_facts`, `mapped_facts`, `issues`, `warnings`.
Each issue: `input_index` (position in fact_inputs.json), `error` (with row/col locator or
unknown-label detail), optional `field`/`evidence_id`/`severity`. Any issue blocks
`financials.json`; the agent fixes `fact_inputs.json` per `input_index` and reruns.

## report_inputs.json — written by agent, consumed by render_report.py

Structured rendering input; see [report-inputs-example.md](report-inputs-example.md).
Sections carry `anchor`, `statements` (template + bindings + claim_type), `paragraphs`
(qualitative free text — static numbers limited to years and page citations), and optional
`table` (display_unit, columns, rows of label + bound cells). Placeholders `{name:format}`
bind one `fact_id` or `metric_id` each; formats cover amount scales, percent precision,
percentage points, and `decline_*` variants (positive value with a decline format is a
render-time contract violation).

## render_issues.json — render_report.py

`schema_version`, `issues` — each carries a position (`anchor`, `statement_index`,
`row_index`/`row_label`, `paragraph_index`) plus `error`, so one repair pass can fix every
problem without guessing locations. Written instead of deliverables when rendering is
blocked; fix `report_inputs.json` and rerun. `run_pipeline` relays all issues in stdout
up to a 4000-character budget before truncating to the file reference.

## run_state.json — run_pipeline.py

Diagnostic only, not a security authority. `schema_version`, `stage`, `repairs`
(per-stage `count` of distinct-input submissions), `input_sha256` (idempotency keys),
`quality_status` (`verified` / `partial` / `maintenance_required`). Initial submission plus
at most two repairs per stage; identical input reruns never consume budget; restarts never
reset it. Deleting or editing this file to reset the budget is a violation — when the
budget is exhausted, deliver with an explicit `maintenance_required` disclosure instead.
Protected-mode budgets and final verification belong to the host.

## report_claims.json — written by render_report.py

Each entry: `claim_id`, `report_anchor` (exact Markdown heading in analysis.md), `text`,
`fact_ids` (list), `metric_ids` (list), `evidence_ids` (list), `source_pages` (list[int]),
`claim_type` (fact / calculation / inference / company_explanation).

The nonempty claim text must occur in that heading's section. Cover every numeric statement,
including table rows, headings, explanations and inferences. `fact` values must be verified;
`calculation` metrics must be computed and finite. All declared required values must appear,
and extra numeric values need support even in explanations/inferences. `source_pages` equals
the union of pages resolved through claim → metrics → facts → evidence; inline PDF citations
must use those pages. Use separate `（PDF 第 N 页）` citations for multiple pages.

Amounts are compared in base units with explicit 元/千元/万元/亿元 or yuan scaling;
percentages divide by 100 and cannot represent amounts. Display rounding uses the displayed
decimal precision (ROUND_HALF_UP). Optional `display_unit` supplies a shared table-row unit.
Calendar years in the supporting facts' periods are exempt with period suffixes
(`2026年`, `2026上半年`, `2026 H1`); decline wording (`下降 27.80%`) models a negative value;
`N 个百分点` matches ratio changes at ×100; product-style tokens (`3D`) and range page
citations (`第56-57页`) are not numbers. Machine checks bind values and references; they do
not verify that a sentence names the correct metric or establishes a causal relationship.
Semantic review remains required.

## report_validation.json — validate_report.py

| Field | Type | Notes |
|---|---|---|
| schema_version | int | |
| unknown_fact_ids | list[string] | cited but not in financials.json |
| unknown_metric_ids | list[string] | cited but not in metrics.json |
| unknown_evidence_ids | list[string] | cited but not in extraction_manifest.json |
| out_of_range_pages | list[object] | {claim_id, page} beyond page_count |
| value_mismatches | list[object] | claim_id plus fragment or unbound_number |
| missing_evidence_claims | list[string] | risk/fact claims without evidence |
| body_mismatches | list[string] | empty report/ledger or claim absent at anchor |
| unclaimed_numeric_lines | list[string] | uncovered numeric Markdown lines |
| invalid_support | list[string] | unusable inputs or document-version mismatch |
| page_mismatches | list[string] | declared/cited pages differ from resolved evidence |
| passed | bool | machine checks only; semantic review is separate |

## context_usage.jsonl — pack_context.py (one JSON object per line, append-only)

`request_id`, `stage` (locate/map/analyze/review), `packet_sha256`, `evidence_ids`,
`character_count`, `byte_count`, `cursor` (null for first page of a packet). Re-reads append new
lines; total delivered characters accumulate — repeats are never subtracted.

## model_usage.json — optional

Written only when the host exposes request-level usage: `input_tokens`, `output_tokens`,
`cached_tokens`, `requests_covered`. When unavailable, the file records `null` values with
`"available": false` note. Tool-side character counts must never be presented as model token usage;
tokenizer-derived numbers are always labeled `estimated_input_tokens` with tokenizer name/version.
