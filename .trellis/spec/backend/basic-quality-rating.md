# Basic Quality Rating — Automation JSON Contract

## Scope / Trigger

Apply when changing the「自动化 JSON 输出模式」section of
`finance-macro/basic-quality-rating/SKILL.md` or its Web consumer contract.
The interactive rating mode of the same skill is out of scope here, except
that both modes live in one file and must not contradict each other.
`dividend-quality-scoring` was removed on 2026-10-24; its JSON contract now
lives inside `basic-quality-rating` v2.2+.

## Two scoring calibers, do not mix

- Interactive mode (human asks): E uses 10-year average ROE + 5-year OCF/NI
  per the quality-screen caliber. Free data access.
- Automation mode (personal-web calls): E uses the input-contract caliber
  (3-year ROE base + debt/earnings/trend caps). The payload has no cash-flow
  data; never score E with the interactive caliber under this mode.

## Signatures

Single stock payload → one bare JSON object. The existing consumer lives in
`personal-web/backend/dividend-select/src/services/quality_service.py`:
`build_stock_payload(stock)`, `parse_quality_output(raw, code, name)`, `QualityScore`.
The skill makes no platform API calls and has no publishing side effects.

## Contracts

- The skill documents all 30 current payload keys. Code remains a string.
- Exactly 11 output fields: `code`, `name`, `dimensions`, `weighted_score`,
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

## Wrong vs Correct

Wrong: a passing schema test proves a company rating is factually reliable.
Correct: schema tests prove interoperability; source-backed research and live
model runs establish additional evidence. Keep local development, installation
and live acceptance status separate. The Web source copy lives at
`personal-web/backend/dividend-select/skills/basic-quality-rating/SKILL.md`;
synchronize it when editing the maintained skill and inspect both hashes before
reporting synchronization.
