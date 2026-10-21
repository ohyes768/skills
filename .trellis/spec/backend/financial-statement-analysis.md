# Financial Statement Evidence and Calculation Contract

## 1. Scope / Trigger

Applies to `finance-macro/financial-statement-analysis/` when changing PDF evidence,
fact selection, metric calculation, context delivery or report validation.

## 2. Signatures

- `extract_sections.extract_sections(run_dir, section_ids=None, pages=None, ocr_runner=None) -> dict`
- `pack_context.build_packet(run_dir, stage, request_id, ...) -> dict`
- `fact_selection.FactSelection(document)` exposes target-period `flows` and `balance`.
- `calculate_metrics.calculate_metrics(document) -> dict`
- `validate_report.validate_report(run_dir) -> dict`
- CLI scripts accept `--run-dir`; fetch accepts `--url` and `--output-dir`.

## 3. Contracts

See the skill's `references/artifact-contracts.md` for artifact fields. Manifest evidence
is append-only, bound to `document_sha256`, with content/selection `source_key` deduplication.
Never delete or reassign prior evidence IDs during supplementation. Initial locate does not
require a manifest. Image packets carry paths and a visual-review flag, never binary text.

Select the target period once. All operands must share scope, currency, unit and basis.
YoY uses the same interval one year earlier; average balances use exact opening/closing dates.
Use Decimal for values and explicit display-unit scaling for report comparisons.

Validate actual `analysis.md` and its claim ledger together. Claims resolve via metrics/facts
to evidence; pages equal that evidence closure. Numeric explanations and headings also need
coverage. Machine validation cannot establish metric-name semantics or causality.

## 4. Validation & Error Matrix

| Condition | Result |
|---|---|
| Source changed or nonempty unbound legacy manifest | ValueError; use a new directory |
| No manifest at locate | Section index still delivered |
| Image-only evidence not visually verified | Incomplete image reference |
| Missing/null/unverified fact | insufficient_data, no numeric value |
| Conflict or incompatible measurement dimensions | conflict, no numeric value |
| Empty ledger, wrong body/anchor, unbound number or wrong pages | report passed=false |
| CLI missing artifacts/invalid fact schema | exit 1 |
| CLI report validation failure | exit 2 with issue arrays |

## 5. Good / Base / Bad Cases

- Good: a 2024 consolidated revenue and 2023 comparable revenue produce YoY; a later
  MD&A extraction preserves the report's evidence IDs and validation still passes.
- Base: missing net profit leaves net margin unavailable while revenue YoY can be computed.
- Bad: combine 2024 revenue with 2023 profit, use parent equity in consolidated ROE,
  or write 2% for a computed 0.2 ratio. Reject rather than silently compute/pass.

## 6. Tests Required

- `test_p1_pipeline.py`: first locate, immutable supplement, idempotency, version binding, images.
- `test_p1_metrics.py`: exact periods, group scope, dimensions, null/status propagation.
- `test_p1_report.py`: actual body/anchor, empty ledger, scales, support/page closure and bypasses.
- `test_p1_integration.py`: fresh offline download through report validation, then supplement
  and validate the same report again. HTTP is mocked; PDF extraction and calculations are real.
- Run the complete skill test suite and Ruff. Use a unique workspace `--basetemp` on Windows
  when the system temporary directory is not writable.

## 7. Wrong vs Correct

Wrong: independently choose each metric's latest fact, reset `ev-0001` on every extraction,
or validate only `report_claims.json` while ignoring `analysis.md`.

Correct: select one document period, keep evidence identities immutable, and bind delivered
Markdown text, display values and pages to the resolved source chain.

## 8. Delivery and model round trips

- Use `run_pipeline evidence` for extraction plus the first bounded evidence packet. Cursor
  continuation must not extract again. `compute` returns an analysis packet; unfiltered analyze
  reads the ledgers while explicit page/section selection reads source evidence.
- Complete semantic review before the final report call. After machine validation succeeds,
  return `terminal=true` and `next_action=null`; the agent stops tools and gives a final reply.
  This is a Skill-only hint; it does not force or modify the host lifecycle.
- Full-Markdown callers use `report --include-report`. Return the exact validated body once
  in `report_markdown`, avoiding an extra read. Failed reports must not deliver that field.
- Do not install custom Hermes patches, override iteration-limit summaries, or change the
  financial client to consume an out-of-band artifact receipt. Hermes remains unmodified.
- Machine validation does not prove semantic correctness. A stopped agent is distinct from
  a host process that might still be cleaning up; diagnose actual host failures separately.

## 9. Reusable analysis tools (Skill only)

- Tools migrated from the profile-local `financial-pitfall-recovery` belong to this skill's
  scripts/tests. Never require a hard-coded profile path or load the entire historical skill.
- Normal text mapping uses `compute --spec`: validate excerpt line numbers and literal values
  before replacing inputs, then run the existing construction/calculation stage. Require the
  source unit explicitly; read period kinds from METRIC_CONTRACTS, never a copied constant.
  Ambiguous labels require explicit analyst mapping, not the first match.
- Report builders reuse the current renderer contract (including pp and decline table cells).
  Normal delivery uses `report --independent-review`: input preflight, render, original
  validator, independent numeric/structure checks, then a single terminal result. The old
  no-flag API remains compatible. Independent failure cannot return report_markdown or leave
  state verified. Formal report retries share the original persisted repair budget.
- Independent checks must not assume a company, year, fact ID, zero minority interests or
  complete data. Recompute computed metrics using their input facts; unavailable metrics and
  accounting checks are explicitly not_applicable. Scope comparisons stay separate.
- Maintenance mutation tests use synthetic fixtures and dynamically selected fields, never
  literal numbers/IDs from a live company's report. They do not run per financial analysis.
