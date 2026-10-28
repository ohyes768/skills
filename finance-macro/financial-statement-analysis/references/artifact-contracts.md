# Artifact Contracts

All JSON artifacts are written UTF-8 (`ensure_ascii=False`, indent 2) via `scripts/artifacts.py::write_json`.
Optional values are `null`, never absent keys. Amounts use decimal strings; floats are forbidden in
financial amount fields. Every artifact file lists `schema_version` unless noted.

Script stdout carries exactly one status line from `emit_status`: `{"status": ..., "artifacts": {...}, "issues": [...]}`.
Detailed logs go to stderr or files. Exit codes: 0 success/complete, 1 fatal fetch or contract error, 2 not passed — read stdout
`status`: `repair_needed` means fix inputs and rerun, `partial` means deliverable but
incomplete (agent must read `issues` and downgrade affected conclusions).

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
so repeated requests reuse prior records. Text evidence is keyed by page and content only: a
`--pages` re-extraction of a page already extracted through a section (or the reverse, or two
overlapping sections) reuses the same `ev-XXXX` and appends the section to `section_ids`, so
each page keeps one text evidence. Older manifests may still hold identical duplicates; the spec
builder uses the lowest ID and errors only when duplicate texts actually differ. A changed PDF or a legacy nonempty manifest without
this binding requires a new run directory; never rebind existing claims to a new document.

| Field | Type | Notes |
|---|---|---|
| schema_version | int | |
| evidences | list[object] | each: see below |

Evidence object fields: `evidence_id` (stable, e.g. `ev-0001`), `section_id` \| null,
`section_ids` (text only: every section that requested this page),
`pdf_pages` (list[int]), `kind` (text / table / image_crop), `file` (path under `excerpts/`),
`method` (pymupdf_text / pdfplumber_table / ocr / image_crop), `complete` (bool),
`issues` (list[string], e.g. cross-page header mismatch, OCR unavailable).

Semantic constraints learned from real runs: `pdf_pages` is where the content physically
sits; `section_id` reflects the extraction REQUEST, not the content's statement. A
`kind=table` evidence is that page's FIRST usable table only — other tables produce no
table evidence (an explicit `multiple tables` issue is recorded instead). Content
attribution rules live in [extraction-rules.md](extraction-rules.md) ("Same-page dual
tables"): verify title + headers + account rows, never infer scope from `section_id` alone.

Image crops are `complete: false` until visually reviewed; context packets contain `file`
(absolute image path), `requires_visual_review: true`, IDs and pages, never decoded PNG text.
The initial `locate` packet works before any extraction manifest exists.

## structured_financials.json — fetch_structured.py

East Money F10 three statements fetched by program (never the agent): `schema_version`,
`source: structured_eastmoney`, `security_code`/`secucode`, `report_dates` (current,
prior year same period, prior year end), `fetched_at`, `requested`, `response_sha256`
(audit trail), and `reports[date][kind]` with raw rows kept verbatim. Numbers are parsed
with `parse_float=Decimal` and archived as exact strings. Cache reuse is incremental per
`(date, kind)`; `--refresh` refetches. HTTP/non-JSON/empty failures exit 1 — the caller
falls back to PDF-only mode and labels the run's data source.

## structured_check.json — written by compute (structured mode)

Dual-source sample check: `samples` (metric, period_end, structured_value,
extracted_value, status `verified`/`conflict`/`unchecked`, evidence_ids, pdf_pages) plus
counts. The agent's fact_inputs act as the spot-check sheet in this mode; a mismatch
flips the structured fact to `review_status: conflict` and blocks `verified` reports —
validate_report accepts `source: structured` facts only when this file exists with
`conflicts: 0`.

`grounding` counts how non-null structured facts got PDF provenance (alias: 结构化事实出处 /
原值落页): `sample_match` — a verified same-scope spot-check twin with equal amount, whose
`evidence_ids` and literal `raw_value` are copied; `value_presence` — the amount appears
verbatim in a non-image extracted evidence (unscaled, has decimals, |value| ≥ 1000), all
such evidence ids attached and the first literal used as `raw_value`; `ungrounded` — neither,
`evidence_ids` stays `[]`. Conflict facts are never grounded. A structured fact carrying
`evidence_ids` must set `evidence_basis` to one of the two values (`financial_schema`).

## fact_inputs.json — generated from spec.json or written by agent; consumed by build_financials.py

Two paths produce this file: for plain text-evidence facts the agent writes a compact
`spec.json` (`metric`/`label`/`cur`/`prior`/`page`/`raw_unit`, explicit `ref: opening` for
opening cash — see [reusable-tools.md](reusable-tools.md)) and `compute --spec` generates
`fact_inputs.json` via `build_fact_inputs_verified.py`, which also checks excerpt line
numbers and amounts. For complex mappings (table locators, missing values, duplicate
labels) the agent writes `fact_inputs.json` directly per
[fact-inputs-example.md](fact-inputs-example.md). Either way, each entry carries only
judgment fields: `metric` (contracted name or registered alias), `raw_label`, `raw_value`,
`raw_unit`, `period_ref` (`current`/`prior`/`closing`/`opening`), optional
`scope`/`basis`/`aggregation`/`review_status`/`note`, and an `evidence` object
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

Full supported metric IDs, formulas, display scales and availability rules:
[metric-catalog.md](metric-catalog.md). Independent check IDs and missing-data behavior:
[independent-review-contract.md](independent-review-contract.md).

### red_flags — calculated alongside metrics（造假红旗 / 红旗筛查 / 风险信号）

Risk-discovery layer, deliberately separate from `validation.json` (data quality): a
triggered flag never affects exit codes or `quality_status`. The list is constant — always
the same 8 `flag_id` entries (`dual_high_cash_debt`, `receivable_outpacing_revenue`,
`inventory_sudden_rise`, `negative_cfo_positive_profit`, `minority_interest_anomaly`,
`goodwill_heavy`, `prepayment_surge`, `construction_not_converting`) — so the report can
annotate every item. Each entry: `flag_id`, `status` (flagged / clear / insufficient_data),
`value`, `threshold`, `detail`. Correlated-party dealings and auditor changes are NOT
programmable (they need notes/non-financial data) and stay qualitative.

Thresholds (`calculate_metrics._RED_FLAG_THRESHOLDS`, 红旗阈值) and decision rules. All
inputs are consolidated facts; "期初" means the opening balance of the reporting period.
Comparisons are strict (`>` / `<`); a value exactly at the threshold is `clear`.

| flag_id | 中文 | 阈值键 = 值 | flagged 条件 | insufficient_data 条件 |
|---|---|---|---|---|
| `dual_high_cash_debt` | 存贷双高 | `dual_high_ratio` = 0.30 | 货币资金/营收 > 0.30 **且** (短期借款+长期借款)/营收 > 0.30 | 缺 `monetary_funds`、任一借款或营收，或营收 ≤ 0 |
| `receivable_outpacing_revenue` | 应收暴增 | `outpacing_factor` = 1.5 | 应收增速 > 营收增速 × 1.5；增速 = 本期/基期 − 1，应收比期初，营收比上年同期 | 缺任一值或基期 ≤ 0 |
| `inventory_sudden_rise` | 存货突升 | `inventory_surge_factor` = 1.5 | 期末存货/本期营收 > (期初存货/上期营收) × 1.5，且基期比值 > 0 | 缺本期或基期比值（含营收 ≤ 0） |
| `negative_cfo_positive_profit` | CFO 为负而净利为正 | 无 | `cfo` < 0 且 `net_profit_group` > 0 | 缺 `cfo` 或 `net_profit_group` |
| `minority_interest_anomaly` | 少数股东损益异常 | `minority_shift` = 0.20 | \|本期少数股东占比 − 上期占比\| > 0.20；占比 = (集团净利 − 归母净利)/集团净利 | 缺任一期集团或归母净利，或集团净利 ≤ 0 |
| `goodwill_heavy` | 商誉占比高 | `goodwill_ratio` = 0.30 | `goodwill` / 期末 `total_equity_owners`（归母权益）> 0.30 | 缺商誉或归母权益，或归母权益 ≤ 0 |
| `prepayment_surge` | 预付突升 | `prepayment_surge_factor` = 1.5 | 期末预付/本期营收 > (期初预付/上期营收) × 1.5，且基期比值 > 0 | 同存货突升 |
| `construction_not_converting` | 在建不转固 | `construction_ratio` = 0.50 | `construction_in_progress` / `fixed_assets` > 0.50 | 缺任一值或固定资产 ≤ 0 |

These are screening thresholds, not verdicts: a `flagged` item still needs industry context
and notes before it becomes a 「触发」 conclusion. `tests/test_reference_contracts.py` locks
this table to the code.

## validation.json — calculate_metrics.py

Each entry: `check_id`, `status` (passed / failed / not_applicable), `input_fact_ids`, `residual`
(decimal string \| null), `tolerance` (decimal string \| null), `issues`. Extraction conflicts are
reported here as data problems, independent of financial risk conclusions.

## mapping_validation.json — build_financials.py

`schema_version`, `document_sha256`, `input_facts`, `mapped_facts`, `issues`, `warnings`.
Each issue: `input_index` (position in fact_inputs.json), `error` (with row/col locator or
unknown-label detail), optional `field`/`evidence_id`/`severity`. Any issue blocks
`financials.json`; the agent fixes the SOURCE per `input_index` — `spec.json` when
fact_inputs was generated, `fact_inputs.json` when hand-written — and reruns compute.

## report_inputs.json — generated via report_inputs_builder.py; consumed by render_report.py

Structured rendering input; see [report-inputs-example.md](report-inputs-example.md).
The agent normally writes a declarative report spec and runs `report --spec <path>`:
spec sections mirror this contract, the builder validates bindings, formats and sources
while building, and a trailing empty table cell expands to the row's united source-page
citation. Writing report_inputs.json by hand is allowed for special cases.
Sections carry `anchor`, `statements` (template + bindings + claim_type), `paragraphs`
(qualitative free text — no static numbers at all, not even years or page citations;
quantitative content belongs in statements/tables), and optional
`table` (display_unit, columns, rows of label + bound cells). Placeholders `{name:format}`
bind one `fact_id` or `metric_id` each; formats cover amount scales, percent precision,
percentage points, and `decline_*` variants (positive value with a decline format is a
render-time contract violation; table cells render decline with an automatic 「下降」
prefix while statement templates must supply the direction word themselves).

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

`claim_type` 合法值（`_CLAIM_TYPES`，`render_report.py` 与 `validate_report.py` 共用）只有这四个；
`metric`、`derived`、`ratio` 等其他值一律报 `illegal claim_type`。statement 省略时默认
`inference`。`fact` 必须绑定 fact，`calculation` 必须绑定 metric；`inference` 与
`company_explanation` 中出现的数字同样需要绑定支撑。

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

Unfiltered `stage=analyze` packets read financials/metrics/checks when those ledgers exist;
explicit page/section filters continue to read original evidence. `compute` returns the first
bounded analysis packet directly. Cursor continuation uses the same stage and filters.

`request_id`, `stage` (locate/map/analyze/review), `packet_sha256`, `evidence_ids`,
`character_count`, `byte_count`, `cursor` (null for first page of a packet). Re-reads append new
lines; total delivered characters accumulate — repeats are never subtracted.

## Report completion — Skill-only

Semantic review happens before the final `report` call. A successful report result contains
`quality_status=verified`, `terminal=true` and `next_action=null`; the agent must stop tools
and return its final response. `terminal` is a local workflow hint, not a host lifecycle hook.
No completion.json, host verifier or custom Runs API request field is required.

Default output contains paths and status. If the caller explicitly requests full Markdown,
use `report --include-report`: only successful validation adds `report_markdown`, exactly the
rendered analysis.md body, so the final response can deliver it once without another file read.
Failed reports never include this field or a successful terminal signal. Existing validation
and repair budgets remain in force; machine checks do not prove semantic correctness.

New analyses use `report --independent-review` (plus `--include-report` when needed).
Preflight writes `report_preflight.json` on input failure without consuming a formal report
submission. After rendering and the original validation pass, `independent_review.json` records
`passed`, `checks`, `issues`, `not_applicable` and `categories`. Independent failure sets run state
to partial, uses the existing formal report retry budget and returns neither body nor terminal
success. The no-flag API retains its original machine-validation-only behavior for compatibility.
Missing data is explicit, never converted to zero. Semantic review still precedes the command.

`compute --spec <path>` generates fact_inputs from extracted text before the existing compute
stage. Each entry requires `metric`, `label`, `cur`, `page`, `raw_unit`; optional `prior`, `ref`,
`scope`. Generation failure does not replace inputs or consume a compute submission. Period
kinds come from the authoritative metric contracts. Complex evidence can still use direct inputs.

`report --spec <path>` builds report_inputs from a declarative spec before the existing report
flow (preflight → render → validation → independent review). Construction failure writes no
file, consumes no report submission and returns `repair_needed`; construction success writes
report_inputs.json and continues in the same call, so the spec write and the final report
command merge into one tool call.

## model_usage.json — optional

Written only when the host exposes request-level usage: `input_tokens`, `output_tokens`,
`cached_tokens`, `requests_covered`. When unavailable, the file records `null` values with
`"available": false` note. Tool-side character counts must never be presented as model token usage;
tokenizer-derived numbers are always labeled `estimated_input_tokens` with tokenizer name/version.
