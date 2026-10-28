# Design

Extend rating_math with a `financial` command backed by financial_score.py.
It returns score/status, structured checks with values/periods, issues and risks.
All scoreable E rules remain unchanged; absent/bad required data yields null.
Use exact numeric comparisons; reject bool/string/nonfinite inputs as missing
evidence. Require explicit annual and consecutive quarter periods, ROE history
anchored at roe_year. Industry resolution is explicit, never substring guessing
from stock name. No external financial enrichment.

Add pdf_evidence.py as a thin consumer of existing financial-statement-analysis
fetch_pdf and inspect_pdf. URL-keyed cache directories retain source.pdf,
source.json, document.json, pages.jsonl and a hash-bound index manifest.
Prepare performs one download/index; search/read use persisted page text, bounded
packets and explicit cursors. Return PDF page numbers, source URL/hash and
unreadable-page warnings; no implied OCR or independently verified finance facts.
Declare dependencies during setup and fail with actionable messages at runtime.

Add validate_rating_json.py under basic-quality-rating as the sole validator.
It reuses finalize/calculate instead of copying weights/boundary rules. It checks
the exact output fields, types and canonical derived values without rewriting the
input. Optional original stock verifies identity and computed E. Advisory report
checks are warnings; they cannot prove source validity or semantic accuracy.
Document retirement of the remote runbook; provide a source-controlled migration
shim that forwards its historical positional-file command to the canonical tool,
resolving the main skill via caller path/environment rather than a fixed profile.
Do not mutate installed remote files during this development iteration.

Compatibility: version 3.1.0, no new final output keys. Existing calculate/finalize
commands remain compatible; finalize with --stock verifies E against financial
rules once this mode is explicitly enabled/documented to avoid silently accepting
hand-calculated E. A-D remain analyst judgments.

## Follow-up v3.2: bounded research

Add research_policy.py for deterministic error classification and source circuit
decisions, and research_state.py for a persisted stock-bound research ledger.
The CLI exposes init/start/result/close/reopen/status. start reserves one logical
question/round before host tools, including a specific grading impact and a
request id. result records only a bounded outcome/error, returning the next route
or a stop action; fallback stays in the same round. Each route has bounded
attempts within the round and terminal quota/auth blocks across all dimensions.
The agent invokes actual host search tools; no arbitrary command execution,
credential configuration or new external provider is introduced.

Each dimension has named required topics, cumulative evidence, initial+2-round
budget and one reopen allowance. close complete requires coverage with text,
source URL, locator and period (semantic truth is still analyst-owned). A
budget-exhausted acquisition can still close complete using its last valid
evidence; otherwise close gap and preserve facts. No empty match implies good
governance or absent risk. Completed dimensions cannot search again without a
documented material conflict; unchanged init/request replay does not consume or
reset state. Use exclusive local file locking and atomic replace for writes.

Expose optional --research-state on finalize and the canonical validator. It
checks stock identity, terminal state, and null for gap dimensions without adding
final output fields or changing legacy unflagged signatures. State CLI rejects
corrupt files and cannot clear budgets with init. Note the boundary: an agent or
host bypassing the CLI is not physically intercepted by these local tools.

## Current follow-up: v3.5 / v3.5.1 supersedes PDF design above

No PDF input/downloader/parser/cache/candidate path remains. Reuse host-readable
web evidence and existing sourced structured data. All runtime scripts use the
standard library. Sector evidence requirements remain unchanged.

Source display: report_md inline [S1] markers and one final table mapping actual
read pages to dates/periods, locators and supported facts. Caller input is [I1]
without invented URL; no extra JSON fields. Unknown page dates are explicitly
unknown, not replaced by access dates; sector published_at still mandatory.
Move the explanatory enterprise rubric next to financial command documentation;
keep executable scoring unchanged. Standalone sector validate is diagnostic,
not a normal extra step. Ordinary-company external-conflict compatibility mode
cannot be used with a sector sidecar. Keep semantic source checks advisory.
