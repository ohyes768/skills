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

## Follow-up v3.2

- [x] Add failing tests for quota/auth, rate/transient failure, no-source stop,
  permanent blocks across dimensions, and bounded fallback decisions.
- [x] Add persistent research CLI tests for evidence coverage, budgets,
  idempotent/restarted operations, identity binding, terminal/reopen states.
- [x] Implement policy and ledger with standard library only.
- [x] Integrate optional finalization/validation research-state gate; preserve
  old entrypoints. Add regression tests before integration edits.
- [x] Update skill/tools/reference/spec and run complete tests, lint, metadata
  checks and an end-to-end failure -> fallback -> evidence -> stop/submit smoke.

## Follow-up v3.3: bank evidence and scoring

Design contract: bank-design.md. Use existing checkout and shared E result shape.

- [x] Tests first: bank packet provenance, chronology, missing vs weak, ratios,
  capital requirements and scoring caps. Worker owns bank_financial.py and tests.
- [x] Tests first: bank candidate search from hash-verified cached PDF pages,
  bounded output/cursors and ambiguous columns. Worker owns bank_evidence.py/tests.
- [x] Parent: test optional --bank-data through financial/finalize/validator,
  preserve original stock and old command compatibility; integrate sector routing.
- [x] Parent: document packet/rubric/budget and banking A-D questions, update
  version/tools/backend spec; record actual official-PDF smoke and limitations.
- [x] Run whole suite, Ruff lint/format, metadata check, and independent review.

Commands: python -X utf8 -m unittest discover -s tests/basic-quality-rating -q;
python -m ruff check finance-macro/basic-quality-rating/scripts tests/basic-quality-rating;
python -m ruff format --check finance-macro/basic-quality-rating/scripts tests/basic-quality-rating.
No commit, push, installed-copy migration or remote deployment in this request.

## Follow-up v3.4: insurance analysis

Detailed design and ordered execution: insurance-design.md. Tests first; preserve
all v3.3 changes. Worker owns insurance schema/scorer and tests; second worker
owns common candidate engine plus insurance locator and bank candidate regressions.
Parent owns sidecar CLI, sector routing, research mode, docs and verification.
Final gate: whole-suite unittest, Ruff lint/format, skill metadata, diff checks,
official-source smoke and independent review. No Git or remote installation.

## Follow-up v3.5: remove PDF route

Design: delete the four PDF/cache/candidate modules and their three dedicated
suites; keep verified historical numeric fixtures. Use the existing URL/locator
sidecar shape for official HTML/structured facts, preserving sector scoring and
budgets. Remove httpx/PyMuPDF and regenerate the lock offline. Update skill,
sector/tool/migration references and generated legacy handoff text. If readable
sources cannot establish a key fact, preserve null; no parser fallback.

- [x] Remove PDF modules and dependencies; regenerate lock offline.
- [x] Update all active instructions and migration/error text.
- [x] Exercise bank/insurance integration with webpage sources.
- [x] Run dependency-free suite, Ruff, skill validation and diff review.

## Follow-up v3.5.1: skill-creator review

- [x] Read whole entrypoint/references and obtain independent read-only review.
- [x] Define inline source IDs and final source table inside report_md only.
- [x] Handle caller input, unknown dates, summaries/unread sources and deduplication.
- [x] Reduce duplicate entrypoint instructions; move enterprise E explanation to tools.
- [x] Remove mandatory standalone validate calls; constrain conflict exception.
- [x] Forward-test realistic reporting scenario independently; repair observed gaps.
- [x] Run full suite, Ruff, skill/link/lock validation and diff review.
