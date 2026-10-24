# basic-quality-rating v2.3.0 optimization

## User-approved scope

1. Correct the output contract to 10 fields and provide a deterministic
   weighted-score, stars, boundary and JSON-validation helper.
2. Make basic-quality-rating automation-only; remove the interactive workflow
   and obsolete scoring reference, retaining the current automation rubric.
3. Specify evidence completion and stopping criteria per dimension.

This continues the existing task; no new feature plan or task approval is needed.

## Implementation and checks

- [x] Failing regression: existing consumer check rejects the skill's declared
  11-field count against the actual 10-field example. New helper tests initially
  fail because the helper is absent.
- [x] `scripts/rating_math.py calculate --input dimensions.json` computes exact
  integer-weight scores, stars and grouped one-sentence boundary directions.
- [x] `finalize --input draft.json --stock stock.json` validates the seven draft
  fields, optional derived fields and exact identity, then computes 3 fields.
  Output is exactly 10 fields. CLI rejects nonfinite JSON; no third-party packages.
- [x] Remove old interactive instructions and `references/scoring-rubric.md`.
- [x] Add a per-dimension evidence checklist, two follow-up rounds per unresolved
  question, one bounded conflict reopening and explicit unknown/provisional exit.
- [x] Local unittest: 8 tests, including all 3,125 score combinations, invalid
  inputs, the 002128 arithmetic fixture and UTF-8 CLI behavior.
- [x] Existing consumer compatibility check: 30 inputs/10 outputs, all 3,125
  combinations and malformed-output rejections pass.
- [x] Independent behavioral/code review confirms stop behavior and arithmetic.
  Removed the remaining invalid-input interactive question; terminate as failed instead.
- [x] Metadata validation and Ruff for helper/tests pass; compatibility check and
  all 8 unittest cases pass. Independent review confirms all grouped crossing
  claims across 3,125 combinations. Whitespace check passes.
- Local repository only, as explicitly clarified by the user. Do not synchronize
  Web or NAS source files this round. NAS access in this turn was read-only;
  no deployment, live model run or production rating update was performed.

## Items 4/5/6 — subsequently approved and implemented locally (v2.3.1)

4. Narrow financial input re-verification: investigate only discrepancies that
   could affect scoring; separate algebraic consistency from independent verification,
   including restated comparison bases. Now implemented: unrelated background
   discrepancies are recorded without additional research; material conflicts
   retain the bounded follow-up and provisional handling. Input values remain
   the E source; no data replacement or E score-threshold changes.
5. Clarify adjacent rubric grades: business 2/3 and management 2/3, governance
   event severity/recurrence/remediation. Now implemented narrowly: distinguish
   dominant-business structural erosion from cycle/minor-segment concerns, and
   routine inquiries from confirmed/remediated/repeated governance failures.
   Same-event multiple notices are not counted as repeated events. Other rubric
   grades, weights and star thresholds are unchanged.
6. Reduce repeated report drafting and assembly, and set concise summary/report
   expectations. Now implemented: fix short evidence/reason/score notes, calculate,
   generate the report once as draft data, perform one consolidated semantic check,
   finalize, then repair only affected content. At most one full rewrite for a
   material basis failure; no new word-count limit or renderer is introduced.

These three items were initially deferred, then the user explicitly approved the
recommended scope in the follow-up “可以，修改下吧”. The local-only restriction
persists; no NAS or personal-web writes are authorized for this iteration.

### v2.3.1 validation

- Read-only baseline evaluation identified ambiguous business/management 2/3
  decisions, missing independent-verification wording and no report rewrite limit.
- Follow-up behavior evaluation passed the same scenarios: irrelevant gross-margin
  difference → record/stop; dominant stable-demand business with only minor-segment
  replacement exposure → business 3; inquiry alone → no automatic downgrade;
  confirmed repeated unresolved disclosure violations → management 2 (unless the
  existing serious-risk 1 applies); input-derived Q1/Q2 → algebraic consistency
  only; ordinary report errors → local repair rather than full regeneration.
- Fresh local verification: all 8 unittest cases, 3,125-combination Web consumer
  compatibility, skill metadata validation, helper/tests Ruff and whitespace pass.
- This iteration changed instructions/spec/task notes only; the arithmetic helper,
  E financial thresholds, weights, JSON field contract and star mapping remain
  unchanged. No live model stock analysis or performance measurement was run.

## Evaluation limits

The old task's skill-validation.md and earlier session results labeled the output
as 11 fields. That was a documentation/log-label error: the actual payload always
had 10. The updated compatibility check now asserts the declared count against
the example and actual consumer model, and prints the measured count.

Offline arithmetic/schema and behavioral checks do not establish real-stock facts
or a runtime improvement. A subsequent live comparison must measure model/tool
rounds, generated tokens and final quality on comparable inputs; no speedup claim
is made from this patch alone. Do not modify Hermes core or unrelated Web behavior.
