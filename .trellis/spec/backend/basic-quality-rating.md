# Basic Quality Rating — Automation JSON Contract

## Scope / Trigger

Apply when changing
`finance-macro/basic-quality-rating/SKILL.md` or its Web consumer contract.
This skill is automation-only as of v2.3.0 (nullable scores since v3.0.0). Its single scoring rubric lives in
SKILL.md; the old interactive workflow and scoring reference were removed.
`dividend-quality-scoring` was removed on 2026-10-24; its JSON contract now
lives inside `basic-quality-rating` v2.2+.

## Scoring caliber

- E uses the input-contract caliber
  (3-year ROE base + debt/earnings/trend caps). The payload has no cash-flow
  data. Do not load other skills or historical company score examples.

## Signatures

Single stock payload → one bare JSON object. The existing consumer lives in
`personal-web/backend/dividend-select/src/services/quality_service.py`:
`build_stock_payload(stock)`, `parse_quality_output(raw, code, name)`, `QualityScore`.
The skill makes no platform API calls and has no publishing side effects.

`scripts/rating_math.py` (Python standard library only) is the arithmetic owner:
- `calculate --input dimensions.json`: five integer-or-null dimension keys → the three
  derived fields `weighted_score`, `stars`, `boundary`.
- `finalize --input draft.json --stock stock.json`: seven non-derived output
  fields (derived fields optional) → exact 10-field JSON. Supplied derived fields
  are recomputed; code/name must equal the original stock input if provided.
- Success prints JSON only; invalid dimensions, unknown/missing fields, blank
  required strings, invalid lists or identity mismatch fail without JSON stdout.
  CLI errors go to stderr with exit code 2. This does not validate report semantics.
  Since v3.1, `financial --input stock.json` calculates E and its trace, and
  finalize's optional `--check-financial` checks E against the original --stock.

## Contracts

- The skill documents all 30 current payload keys. Code remains a string.
- Exactly 10 output fields: `code`, `name`, `dimensions`, `weighted_score`,
  `stars`, `boundary`, `summary`, `risks`, `watch_points`, `report_md`.
- Dimensions: `business`, `moat`, `industry`, `management`, `financial`;
  integer scores 1–5 or null, weights 25/25/20/15/15. Any null dimension
  makes weighted_score, stars and boundary all null; never reweight known scores.
- Integer weighted numerator divided by 100; thresholds 2/3/4/4.5 map to
  2/3/4/5 stars, inclusive at each threshold.
- Boundary distance is strictly less than 0.25; validate actual legal ±1
  changes before claiming a transition. Scale endpoints 1 and 5 are not boundaries.
  The boundary text is one verifiable sentence ("踩线 N 星：…direction…"),
  not a per-dimension enumeration (simplified 2026-10-24, v2.2.1).
- E uses supplied financial numbers only. Financial-sector leverage thresholds
  are skipped; absent sector indicators make E null.
- Missing evidence must remain visible beside scores and in summary/watch points.
  Missing key evidence produces null, never a conservative numeric placeholder.
  Summary starts with 灰色地带（证据不足，未评级） when any dimension is null.
  Reports retain known scores and facts and list concrete verification questions.
  Secondary gaps that do not prevent grading do not impose automatic score caps.
- No environment variables, URLs, credentials or storage paths belong in the skill.

## Validation & Error Matrix

| Situation | Required behavior |
|---|---|
| Missing/mismatched stock identity | Terminate with input error; no interactive question or fabricated result |
| Wrong dimension keys/range, sum, stars, empty report | Consumer rejects output |
| Required financial values missing | E null; preserve known weaknesses as risks |
| All financial evidence absent | E null; no overall score or stars |
| Bank with high debt and no regulatory metrics | Skip debt penalty; E null |
| Invalid stock identity in automation | Terminate as failed; no interactive question or fabricated rating |

Evidence gathering ends per dimension when its checklist is covered, or after
two targeted follow-up rounds leave an explicit unscored gap. Completed facts
are reused. A concrete conflict that might change a score allows one extra round;
unresolved material conflicts remain disclosed and unscored. Do not restart open-ended
search while drafting or load the removed company-example scoring reference.

As of v2.3.1, financial cross-checking is materiality-based: identify the affected
grade threshold or critical argument before further investigation. Background
caliber differences are recorded without open-ended arithmetic/research. Derived
figures that use the supplied value are consistency checks, not independent
verification; restated and original comparison bases must not be mixed.

The business and management 2/3 boundaries retain their v2.3.1 clarifications. Business 2 needs
concrete dominant-business structural erosion or demonstrated damage from
unrelated diversification. Cyclicality or a minor segment's substitution risk
alone does not qualify. Management inquiries alone do not establish misconduct;
confirmed unresolved/repeated problems support 2, while a single nonmaterial,
documentedly remediated event can support 3 with other evidence. Multiple notices
for one event are not recurrence. Audit opinions/dividends do not clear misconduct.

Draft once from settled evidence/reason/score notes and calculated results. Run
one consolidated semantic check plus finalize; fix affected fields/paragraphs.
Only a material failure of the report's underlying identity/business/source basis
allows one full rewrite, under the existing research budget. Arithmetic/schema
tests do not verify compliance with these behavioral rules.

The consumer currently validates numeric/schema consistency, not research quality,
source links, evidence-status labeling, identity equality or boundary truthfulness.
Do not claim those properties are enforced by Pydantic.

## Good / Base / Bad Cases

- Good: 4/5/3/3/5 → 4.05, 4 stars, business 4→3 gives 3.80 and 3 stars.
- Base: high ROE, low debt, positive annual/two-quarter profit, rising three-year
  history → E 5; two-year history alone means E null and no overall rating.
- Bad: treating null as zero, a bank's leverage as industrial distress, or an
  unverified dimension as any numeric placeholder.

## Tests Required

Run the skill metadata validator against `finance-macro/basic-quality-rating`.
Use behavioral evaluations for moat depth/trend and evidence sufficiency.
Real Hermes research/report validation is a separate deployment acceptance step.
The historical `10-23-dividend-hermes-quality/validate_skill_contract.py` checks
the v2 integer-only Web consumer. It remains useful for fully scored outputs,
but passing it does not establish v3 null compatibility. Do not weaken that
consumer validation or claim v3 deployment readiness from its passing result.

Run `python -X utf8 -m unittest discover -s tests/basic-quality-rating -v` and Ruff
on the new helper/tests. Tests cover all 3,125 combinations, exact threshold and
strict-distance behavior, grouped boundary truthfulness, 002128 reproduction,
input rejection, identity matching, 10-field assembly and real CLI behavior.
Nullable tests cover all 211 incomplete combinations over null/1/5, rejection of
invalid scores even beside null, stale-score removal and JSON null serialization.

## Wrong vs Correct

Wrong: a passing schema test proves a company rating is factually reliable.
Correct: schema tests prove interoperability; source-backed research and live
model runs establish additional evidence. Keep local development, installation
and live acceptance status separate. The Web source copy lives at
`personal-web/backend/dividend-select/skills/basic-quality-rating/SKILL.md`;
synchronize it only when deployment/synchronization is authorized and inspect
both hashes before reporting synchronization. On 2026-10-24 the user explicitly
limited this optimization to the local skills repository; Web/NAS copies remain
unchanged in that iteration.

## v3.0.0 scoring and migration (2026-10-25)

Moat scores follow depth, durability and trend rather than counting categories:
4 accepts one strong stable moat; 5 requires mutually reinforcing moats with
widening evidence; 3 accepts a demonstrated but shallow advantage or unclear
trend; 2 requires actual erosion; 1 requires researched absence of advantage.
Unknown existence/stability is null, not 1 or 2. Do not double-count evidence.

E no longer defaults missing ROE to 3 or applies caps for missing data. Required
input values, industry, periods and the latest consecutive three-year history
must support the rules; otherwise E is null. Existing verified financial
thresholds remain unchanged. Financial firms lack required sector metrics under
the current payload and therefore cannot receive a complete E score.

The ten field names remain unchanged. Fully scored arithmetic remains identical.
The helper accepts null dimensions, validates all other scores before returning
null derived fields, and clears stale derived scores in finalize. It cannot
validate evidence sufficiency, narrative consistency or research quality.

The user authorized nullable scores on 2026-10-25. The existing sibling Web
consumer and deployed copies have NOT been migrated by this local skill change.
Before deployment, adapt consumer models, parser, persistence and UI to nullable
dimension/total/star fields, show an explicit ungraded state, and prevent null
from becoming zero, low stars or a previous rating. Synchronization requires its
own authorized scope. Source metadata version 3.0.0 marks this breaking change.

## v3.1.0 execution tools (2026-10-27)

- `financial_score.score_financial(stock)` is the sole executable E scorer.
  `rating_math financial` exposes score/status/checks/issues/risks/sector.
  Return null for incomplete inputs; financial firms are not_applicable under
  this enterprise rubric. Values must be finite numbers, not bool/string.
  ROE and annual-profit years align; history uses the anchor's latest three
  consecutive years. Quarter labels must unambiguously denote adjacent single
  quarters (including Q4 -> Q1). Invalid chronology cannot establish consecutive
  decline or verified severe earnings weaknesses. Do not recompute absent averages.
- Finalize without the new flag retains compatibility. Normal v3.1 runs use
  `--stock --check-financial` to reject E drift. An explicitly documented material
  outside-source conflict can require E null despite a computable input score;
  only then may the analyst use the unflagged path, preserving original inputs
  and explicitly disclosing the conflict in the report/watch points.
- `validate_rating_json.py` is a read-only validator of final ten-field outputs.
  It reuses finalize/calculate rather than defining weights, bands or boundary
  enumeration. Check original derived values, don't silently repair them. Canonical
  grouped boundary text and nullable results are valid. Optional stock verifies
  identity; `--check-financial` also verifies E. CLI emits one JSON with
  status/errors/warnings; exit 0/2. Report wording checks are advisory, not proof.
  Disclaimers and coincident financial numbers must not trigger semantic rejection.
- `pdf_evidence.py prepare/search/read` reuses existing fetch_pdf/inspect_pdf
  functions from sibling financial-statement-analysis (or explicit --tools-dir).
  Declare httpx/PyMuPDF at installation; don't install packages during analysis.
  URL-keyed cache binds source PDF, provenance, metadata and page index hashes.
  Cached prepare/search/read never downloads or reparses the PDF. Refresh is
  explicit; failed refresh preserves the previous cache. No OCR is implied.
  Search is literal, first hit per query/page; no hit doesn't prove absence.
  Packets contain PDF page, text offsets, source URL/hash, bounded text and
  source/selection-bound continuation cursor. Never print entire annual reports.
- `retire_legacy_runbook.py` is installation maintenance only: default read-only
  preview, explicit --apply backs up legacy SKILL/validator and forwards the old
  command. Preserve conflicting backups; don't delete history or patch arithmetic
  to satisfy stale validators. Its documented deployment is distinct from local
  development; no remote files were changed in this iteration.

Regression tests include threshold/weakness combinations, period/null inputs,
real-PDF mock HTTP cache/continuation/scan cases, canonical validation/disclaimer
cases, and migration preview/backup/idempotent forwarding. Tests do not establish
live model research speed or factual rating correctness.

## v3.2.0 bounded research (2026-10-27)

- `research_policy.py` classifies tool error envelopes only. Quota/auth/access
  failures disable that configured route for the run; transient failures first
  yield a ready alternate, with one bounded retry per route in a round. Counters
  remain bounded for multiple outstanding receipts. Preserve a permanent block's
  original cause when late results arrive. 404/410/empty are request-specific.
- `research_state.py init/start/result/close/reopen/status` persists A-D evidence
  and budgets in a stock-input-hash-bound JSON. Writes use an exclusive lock and
  atomic replace. Init never resets existing state. One initial + two follow-up
  rounds are shared per dimension (not per renamed question); fallback stays in
  the same round. Start requires a question and grading impact. Replayed IDs
  cannot change intent or overwrite outcomes. Revalidate global route blocks
  when replaying pending reservations; cancelled receipts reject late results.
- Evidence is compact, referenced and topic-keyed; complete requires all required
  topics. Revalidate persisted facts, not only newly inserted ones. Keep source,
  locator, period and statement fields. This proves reference shape, not truth.
  Gap preserves facts and missing topics. Last-round success can still complete.
  Closed dimensions freeze; a concrete material conflict allows one reopen round
  per dimension, with old evidence and budgets retained.
- Normal v3.2 finalize includes --research-state; the optional gate also works
  in validate_rating_json. Require terminal A-D states and null scores for gaps,
  verify stock identity/input hash, and retain the exact ten output fields.
  Legacy unflagged calls remain compatible. E is outside this research ledger.
- No credentials, new search services or arbitrary subprocess execution. The
  agent still invokes actual host tools and records outcomes. These scripts do
  not intercept bypassing calls; host-enforced receipts require separate caller
  integration. Neither live deployment nor measured speedup is established here.

Tests cover quota/auth fallback, transient waits, empty results, persisted budgets,
duplicate/cancelled receipts, global blocks with outstanding calls, completed/gap
evidence, conflict reopening, corruption/locking and checked CLI finalization.
