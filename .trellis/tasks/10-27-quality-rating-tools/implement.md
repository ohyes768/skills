# Implementation plan

Use the existing checkout. Ownership is split by independent modules; no worker
may revert another worker's changes. No deployment or Git mutations.

- [x] Financial scorer: tests first, scoring implementation, rating_math CLI integration.
  Files: financial_score.py, test_financial_score.py; parent integrates rating_math.
- [x] PDF evidence: tests first, reuse fetch/index primitives, bounded search/read CLI.
  Files: pdf_evidence.py, pyproject.toml, test_pdf_evidence.py.
- [x] Unified validator: regression tests first, canonical numeric/schema validation,
  advisory semantic checks, old-runbook migration shim/reference.
- [x] Wire SKILL.md commands and remove repeated mechanical E prose; update backend spec.
- [x] Run all basic-quality-rating tests, dependency metadata validation and Ruff.
  Run impacted financial-statement-analysis regressions if shared code changes.
- [x] Review contracts and actual outputs; record completed checks and remaining deployment scope.

Validation: python -X utf8 -m unittest discover -s tests/basic-quality-rating -v;
python -m ruff check/format --check for changed Python; skill-creator quick_validate.
Use temporary directories inside the workspace on Windows. Integration downloads
use a loopback fixture or mocked HTTP plus real PDF parsing; a live official URL
may be smoke-tested separately when available, without fabricating success.

## Delivery boundary

Local implementation/verification complete. No commit, push, remote migration or
consumer deployment was performed. Keep task in progress until the user chooses
integration; do not archive with an automatic Git commit.
