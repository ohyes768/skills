# Validation (2026-10-27)

- Full basic-quality-rating suite: 50 tests pass (unittest).
- Ruff lint and format checks pass; skill metadata validator passes; git diff --check passes.
- Existing 3,125 scored and 211 nullable-combination arithmetic cases still pass.
- E thresholds, all 16 severe-factor combinations, zero/negative/bad inputs,
  adjacent-period parsing, missing history and financial-sector null paths covered.
- PDF cases use real generated pages and parser with mocked HTTP, including cache
  reuse, integrity failure, refresh failure preservation, page citations, cursor
  continuation, scans and CLI behavior. No shared PDF source files changed.
- CLI smoke: financial -> checked finalize -> read-only validator passed;
  PDF prepare -> cached prepare -> search/read returned PDF page 2, with only
  one HTTP fixture download. Results: .tmp/quality-rating-tools-smoke/smoke-result.json.
- Legacy migration preview changes no files; apply preserves backups; repeated
  apply is idempotent; retargeting owned shim preserves original backups.
- Read-only cross-review found and fixed oversized-score validation overflow and
  migration retargeting; original regression cases remain covered.
- Remote installed files were read for context only. No deployment, full live
  Hermes analysis or production speed benchmark is claimed.
