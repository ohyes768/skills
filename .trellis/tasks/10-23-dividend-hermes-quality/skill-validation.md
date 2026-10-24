# Skill continuation — 2026-10-24

Continuation of the approved task in the sibling repository:
`F:/personal-projects/personal-web/.trellis/tasks/10-23-dividend-hermes-quality/`.
The user reported Web frontend/backend complete and requested continuing skill development.
This directory records the skills-side checks, not a replacement of the parent task.

## Delivered locally

- Platform-independent `finance-macro/dividend-quality-scoring/SKILL.md`, one
  self-contained prompt file, no scripts or runtime dependencies in its package.
- Same skill name, 30 input fields and 11 output fields as the actual Web consumer.
- Preserved weights and star thresholds; clarified non-overlapping intervals,
  financial rule precedence, missing evidence and financial-sector limitations.
- Explicit source links in reports and deterministic, checked boundary examples.
- Synchronized the source copy at
  `personal-web/backend/dividend-select/skills/dividend-quality-scoring/SKILL.md`.
  Both SHA256: `8F13C94381416DA1BA221516D5184AF7CB146E8944F8CD59808D75ABB4D73F24`.
- Existing basic-quality-rating and unrelated financial-analysis changes untouched.

## Behavioral evaluation

An independent read-only evaluator first exercised the old Web skill. It found
ambiguous E scoring for severe debt plus negative profits, banks lacking sector
metrics, and all-null financial inputs. Boundary tie-breaking was unspecified.
The revised skill resolved these demonstrated branches:

| Synthetic case | E | Provisional |
|---|---:|---|
| ROE 16, rising 14/15/16, debt 35, annual and both quarters positive | 5 | No |
| Same ROE, debt 85, annual -5 and quarters -10/-20 | 1 | No |
| Bank, high debt, good ROE/profits but no sector regulatory metrics | 3 | Yes |
| All E inputs absent | 1 | Yes, evidence placeholder, not business failure |
| Otherwise excellent but only two years of ROE history | 4 | Yes |
| Otherwise excellent, three-year history 16/14/15 | 5 | No |

The second pass found a general/specific missing-evidence cap conflict and an
uncovered recovering-ROE branch; both were fixed and rechecked successfully.
Boundary fixtures 4/5/3/3/5 and 4/4/4/4/5 both correctly select business 4→3.
These are synthetic financial branch evaluations, not real-stock ratings.

## Commands and actual results

- `python -X utf8 C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py finance-macro/dividend-quality-scoring`
  → `Skill is valid!` (UTF-8 mode is needed on this Windows host).
- `python -X utf8 .trellis/tasks/10-23-dividend-hermes-quality/validate_skill_contract.py`
  → 30 input / 11 output fields, example JSON and leading zero preservation pass;
  all 3,125 five-score combinations accepted by actual Web validation definitions;
  wrong sum, wrong stars, empty report and missing dimension rejected.
- `git diff --check` → no whitespace errors (existing LF/CRLF notices only).

## Outstanding integration acceptance

NAS SSH connectivity was checked read-only; no skill was uploaded or installed.
No real Hermes run, live stock research, production rating update, Git commit or
push occurred. Parent task deployment and ≥3-stock smoke/repeatability checks
remain open. Schema checks do not prove real model behavior or factual accuracy.
