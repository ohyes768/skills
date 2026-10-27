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
