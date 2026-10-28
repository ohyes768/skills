# Financial analysis: F10 as the sole source

Updated 2026-10-28 following the user request to remove the document-based source.

## Requirements

- Accept an A-share code and report end date; fetch F10 consolidated statements for the target, comparable prior period and opening balances.
- Remove document download, indexing, extraction, OCR, page citations, analyst-entered facts, sample checks and fallback from active resources, dependencies and tests.
- Keep Decimal arithmetic, period/scope/unit checks, missing-versus-zero, reconciliation, risk screening, bound rendering and independent verification.
- Trace numbers to saved F10 rows, report name, field, security and date. Detect archive and normalized-fact tampering.
- Missing data stays missing, with partial/failed results. Do not invent notes, audit opinions or qualitative business evidence absent from F10.
- Preserve skill name, analysis.md, --run-dir and shared metric/field-map imports used by basic-quality-rating. Remove obsolete source-specific options.
- Repository change only: no Hermes/client changes, deployment, commit or push.

## Acceptance

- Offline F10-to-verified-report integration without extraction artifacts.
- Wrong identity/period, malformed values, source tampering, unbound numbers and display mismatches cannot return verified.
- Missing comparison data yields nullable metrics and partial delivery without fallback.
- Active resources contain no obsolete workflow. Full skill tests, relevant sibling tests and Ruff pass.
