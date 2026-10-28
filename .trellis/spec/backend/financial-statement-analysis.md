# F10 Financial Analysis Contract

## Scope

Applies to finance-macro/financial-statement-analysis when changing source ingestion, facts, metrics, bounded context or report verification. The sole source is Eastmoney F10 consolidated statements. Older source-specific task documents are historical, not active contracts.

## Entrypoints

- run_pipeline.cmd_prepare(code, period_end, run_dir, refresh=False): stock code plus quarter-end date, one source/security/period per run directory.
- build_financials.build_financials_structured(run_dir, archive): exact-decimal normalized facts, nulls and source references.
- source_provenance.source_errors(run_dir, financials=None): archive hash, field identity, values, periods, dimensions and derived operands.
- calculate_metrics.calculate_metrics(financials): deterministic metrics, accounting checks and risk flags.
- pack_context.build_packet: analyze/review only, bounded packets with a version-bound cursor. compute and pack_context both expose packet.next_cursor at the top level. A null cursor ends the walk. An invalid cursor is an error with ended=false, not an end marker. compute.context remains a compatibility alias and is not present on pack_context.
- run_pipeline.cmd_report: source validation, canonical calculation validation, bound rendering and independent review, always enabled.

## Source and Fact Invariants

Use existing F10 report kinds balance/income/cashflow and strict security/report-date matching. Empty data is no_data; malformed shape, business errors and HTTP failures are fetch_failed. Archive successful entries and only retry missing entries, with finite retries. Keep exact Decimal parsing; reject boolean, float, malformed and nonfinite monetary values.

financials.source_sha256 binds the serialized archive. Structured facts carry source_ref with security, report name/kind, report date, field and response hash. Derived gross profit declares revenue and cost operands. Null does not mean zero. Opening cash can use prior-year END_CCE or target-period BEGIN_CCE with its actual source reference. PREPAYMENT, CIP and RATE_CHANGE_EFFECT mappings were verified against saved F10 responses; null FX remains unavailable and cannot complete cash reconciliation.

No analyst-entered facts or alternate source fallback. Optional comparison statements missing means nullable ratios and partial delivery. Coverage distinguishes archive presence, no_data, fetch_failed, field null, unmapped, not calculated and withheld from the model input. An archived comparison balance sheet must not be described as not retrieved. Null deltas stay null. F10 cannot substantiate audit opinions, restrictions, related-party details or business-cause narratives.

analysis_pack.json is recomputed from source-bound facts. It carries the profit bridge, expense ratios, balance changes and qualitative support flags. Those ratio names are not metric_id values. Primary profit attribution, confirmed transfer from construction in progress, and a DuPont year-over-year driver are blocked unless their deterministic support flag is true. Other qualitative wording still needs human review. Report todos state the section, paragraph position, remaining core-sentence budget, evidence and these limits.

## Calculation and Report Invariants

Operands share scope, unit, currency and basis. Select explicit current cumulative interval; prior flows use the same interval last year, average balances use exact opening/closing dates. Preserve group/owners distinction. Use Decimal throughout.

Stored metrics, formulas, operand IDs, statuses, checks and risk flags must equal canonical recalculation from source-bound facts before delivery. Independent review then recomputes available metrics with its own formula evaluator; it must not accept an arbitrary persisted formula as authority.

Report body and claims are generated together. Claims contain the complete source_refs closure, not unbound metadata strings. Exact generated citations are excluded from numeric matching; arbitrary numeric text is rejected. Qualitative paragraphs have no digits; financial numbers are bound. Risk rows use this run's red_flags, never template defaults. Missing rows and disclosures are stated as limitations.

Formal report repair budget is initial attempt plus two repairs, persisted in run_state.json. Failed recompute/revalidation revokes any previous verified state; never leave an old success stamp after detecting source or metric changes. A final verified result has terminal=true, next_action=null. Full-body callers request include-report once. Partial is not a complete verified report.

## Verification

Run the complete skill pytest suite and Ruff. Keep arithmetic period/scope/unit tests plus HTTP failure/cache tests, source/fact/formula/risk/body/citation mutation tests, report-budget tests, bounded-cursor version tests and F10-to-report integration. Relevant sibling consumer tests run separately to avoid module-path collisions. Windows tests use a unique workspace basetemp. No runtime deployment, client edits, Git commit or push without the corresponding user request.
