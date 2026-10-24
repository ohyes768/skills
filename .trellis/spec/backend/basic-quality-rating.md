# Basic Quality Rating — Automation JSON Contract

## Scope / Trigger

Apply when changing
`finance-macro/basic-quality-rating/SKILL.md` or its Web consumer contract.
This skill is automation-only as of v2.3.0. Its single scoring rubric lives in
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
- `calculate --input dimensions.json`: five integer dimension keys → the three
  derived fields `weighted_score`, `stars`, `boundary`.
- `finalize --input draft.json --stock stock.json`: seven non-derived output
  fields (derived fields optional) → exact 10-field JSON. Supplied derived fields
  are recomputed; code/name must equal the original stock input if provided.
- Success prints JSON only; invalid dimensions, unknown/missing fields, blank
  required strings, invalid lists or identity mismatch fail without JSON stdout.
  CLI errors go to stderr with exit code 2. This does not validate report semantics.

## Contracts

- The skill documents all 30 current payload keys. Code remains a string.
- Exactly 10 output fields: `code`, `name`, `dimensions`, `weighted_score`,
  `stars`, `boundary`, `summary`, `risks`, `watch_points`, `report_md`.
- Dimensions: `business`, `moat`, `industry`, `management`, `financial`;
  integer scores 1–5, weights 25/25/20/15/15.
- Integer weighted numerator divided by 100; thresholds 2/3/4/4.5 map to
  2/3/4/5 stars, inclusive at each threshold.
- Boundary distance is strictly less than 0.25; validate actual legal ±1
  changes before claiming a transition. Scale endpoints 1 and 5 are not boundaries.
  The boundary text is one verifiable sentence ("踩线 N 星：…direction…"),
  not a per-dimension enumeration (simplified 2026-10-24, v2.2.1).
- E uses supplied financial numbers only. Financial-sector leverage thresholds
  are skipped; absent sector indicators require an explicit provisional result.
- Missing evidence must remain visible beside scores and in summary/watch points.
  The integer-only consumer cannot represent an unscored dimension; conservative
  placeholders must never be described as verified poor business quality.
- No environment variables, URLs, credentials or storage paths belong in the skill.

## Validation & Error Matrix

| Situation | Required behavior |
|---|---|
| Missing/mismatched stock identity | Request correction, do not fabricate a valid result |
| Wrong dimension keys/range, sum, stars, empty report | Consumer rejects output |
| Financial values missing | Apply documented caps; disclose provisional status |
| All financial evidence absent | Provisional 1, explicitly an evidence placeholder |
| Bank with high debt and no regulatory metrics | Skip debt penalty; provisional E capped at 3 |
| Invalid stock identity in automation | Terminate as failed; no interactive question or fabricated rating |

Evidence gathering ends per dimension when its checklist is covered, or after
two targeted follow-up rounds leave an explicit provisional gap. Completed facts
are reused. A concrete conflict that might change a score allows one extra round;
unresolved conflicts remain disclosed/provisional. Do not restart open-ended
search while drafting or load the removed company-example scoring reference.

As of v2.3.1, financial cross-checking is materiality-based: identify the affected
grade threshold or critical argument before further investigation. Background
caliber differences are recorded without open-ended arithmetic/research. Derived
figures that use the supplied value are consistency checks, not independent
verification; restated and original comparison bases must not be mixed.

Only the business and management 2/3 boundaries were clarified. Business 2 needs
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
source links, provisional labeling, identity equality or boundary truthfulness.
Do not claim those properties are enforced by Pydantic.

## Good / Base / Bad Cases

- Good: 4/5/3/3/5 → 4.05, 4 stars, business 4→3 gives 3.80 and 3 stars.
- Base: high ROE, low debt, positive annual/two-quarter profit, rising three-year
  history → E 5; two-year history alone limits this to provisional E 4.
- Bad: treating null as zero, a bank's leverage as industrial distress, or an
  unverified dimension as a researched neutral score.

## Tests Required

Run `python -X utf8 .trellis/tasks/10-23-dividend-hermes-quality/validate_skill_contract.py`
from the skills repository, with the sibling personal-web checkout present.
This checks the actual consumer definitions without starting the application:
input/output keys, example JSON, code preservation, all 3,125 score combinations,
and rejection of malformed numerical results. Also run the skill metadata validator
against `finance-macro/basic-quality-rating`. Use behavioral evaluations for
scoring branches. Real Hermes research/report validation is a separate deployment
acceptance step, not established by these checks.

Run `python -X utf8 -m unittest discover -s tests/basic-quality-rating -v` and Ruff
on the new helper/tests. Tests cover all 3,125 combinations, exact threshold and
strict-distance behavior, grouped boundary truthfulness, 002128 reproduction,
input rejection, identity matching, 10-field assembly and real CLI behavior.

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
