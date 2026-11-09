# Implementation
1. Add fetch/normalization/scoring module and provenance packet.
2. Integrate mutually exclusive F10 sidecar into arithmetic/finalize.
3. Replace default skill financial routing with unified F10; retain legacy CLI.
4. Run offline unit suite, CLI smoke and diff/reference checks. Attempt bounded live fetch if network available; report actual coverage only.

## Verification completed
- 170 unittest cases passed, including new F10 period/identity/hash/duplicate/missing/finalizer checks.
- Ruff check and formatting passed for new module/tests and changed arithmetic/validator; skill metadata validator passed; local reference and git diff checks passed.
- Live public F10 smoke: 600036, 600519, 601318 at target 2026-06-30. All produced a score under f10-basic-v1. Bank/insurance generic balance/cashflow queries failed and remain explicit issues; core profitability came from main indicators. This is not proof of universal company coverage.
- Real CLI financial/finalize/read-only validator accepted a temporary bank serialization fixture. Fixture is not a researched company report; narrative warnings expected. No stock report was published.
- Existing unrelated/in-progress bank-liquidity edits retained. No commit or NAS synchronization performed in this turn.

## F10 ledger repair verification (2026-10-29)

- Added --f10-research / mode=f10 and f10_data topic, sharing existing budgets
  and closed-state/snapshot checks. Checked F10 finalization requires that mode.
- Nine new tests first reproduced absent Python/CLI support, then passed after
  implementation: CLI receipt lifecycle, budget/replay/exhaustion, A-D append,
  mode immutability, all-sector support, missing evidence and checked delivery.
- Full 179-test suite passed without site-packages, with tempfile.tempdir pointed
  to .tmp/quality-rating-tests. The initial default Windows sandbox temp directory
  caused 13 filesystem permission errors; no scoring assertion failures.
- Metadata, changed-file Ruff/format, offline lock and diff checks passed.
- No remote deployment, live-model latency claim, commit or push in this repair.

## v4.2 source reuse and score explanations (2026-10-29)

- Reduced the default entrypoint from 11,805 to 6,064 characters, retaining A-D
  rubrics; input/output contracts are contextual references. Legacy ledger and
  sector flows remain compatible and outside the normal entrypoint.
- New progress schema 2 stores stable shared citation metadata and source_id
  facts; schema 1/inline facts remain readable. sources CLI renders referenced
  A-D and applicable recomputed F10 sources offline, without mutating files or
  inventing missing publication dates/titles. Exact URLs reuse citation IDs.
- F10 explanation exposes base/caps/final/missing/text; financial caps are
  independently visible, ordinary traces reuse scorer checks. Policy unchanged.
- Full 196-test suite passed without site-packages using workspace temp files;
  new tests exercise source reuse/date failures/legacy input, real sources CLI,
  checked nullable finalization and ordinary/financial/missing score explanations.
- Ruff, formatting, metadata, offline lock, Markdown references and diff checks
  passed. No live-model performance claim, NAS synchronization or commit/push.
