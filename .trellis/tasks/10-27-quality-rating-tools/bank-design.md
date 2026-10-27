# Bank financial quality extension — approved direction, v3.3

The user approved a dedicated bank E rubric and traceable official-source
enrichment after reviewing the research and plain-language proposal. This is a
continuation of the active task. No deployment, commit or push is included.

## Boundaries

Keep the original 30-field stock input immutable, the five dimensions/weights,
and the exact ten output fields. Introduce an explicit optional `--bank-data`
sidecar, bound to code/name and a SHA-256 of canonical original stock JSON.
Ordinary enterprises, insurance and other financial companies retain their
existing behavior. Banks without usable evidence are `insufficient_data`, not
an assertion that banks cannot be rated.

Bank source acquisition reuses existing PDF prepare/search/read and host search.
Add an empty packet template, strict evidence validation, and bounded candidate
extraction from cached PDF text. Candidate numeric strings NEVER become accepted
scoring values automatically: an analyst confirms table columns, units, scope,
period and source before filling the packet. No new provider or unbounded crawler.
One initial + two focused follow-ups for E, then preserve gaps. Reuse cached pages.

## Bank packet and scoring owner

`bank_financial.py` owns template/validation/scoring. `score_bank(stock, packet)`
returns the existing E score/status/checks/issues/risks/sector shape, plus policy
version and warnings. `make_template(stock, as_of)` returns schema_version=1,
code/name/stock_sha256/as_of, reports=[], requirements={}, peers=[].
Reports are objects with period_end/published_at (ISO dates), period_type
(annual/interim/quarter), scope=group and metrics. Every metric is an object with
finite numeric value in percentage units, source_url http(s), locator and basis
(point_in_time/period/quarter_average). Shape validation is not source verification.

Require latest report snapshot npl_ratio/provision_coverage/cet1_ratio/tier1_ratio/
total_capital_ratio/lcr/nsfr; require latest three consecutive annual reports
with roe/roa/npl_ratio. The latest annual report must be the latest completed
calendar year expected after April 30 (before May use the previous year if the
new year is not present); never backfill a missing recent year with older data.
Latest snapshot cannot be older than 400 days as of as_of. Disclosures published
after as_of, mixed scopes, duplicates/conflicts, invalid periods/types and identity
hash mismatch block grading. Keep known weaknesses even with missing evidence.
Only LCR/NSFR bank regime is initially scoreable; explicitly unsupported liquidity
regimes remain ungraded rather than using invented proxy metrics.

Requirements cet1_ratio/tier1_ratio/total_capital_ratio are sourced metric objects
representing the bank's FULL applicable requirements, not bare statutory minima.
Optional provision_coverage/loan_provision_ratio requirements enable actual breach
checks only when known. Never declare a violation from a generic 150% line.
Require requirements_period_end to equal latest snapshot and require
requirements_published_at <= as_of. Invalid/missing applicability suppresses
capital/provision regulatory conclusions; unsupported liquidity regimes preserve
facts but cannot claim an LCR/NSFR floor breach. Extend the research ledger with
init --bank-research to append E's four topics while preserving A-D budgets and
source circuits; bank sidecar + research gate requires terminal E evidence.
Optional latest loan_provision_ratio, special_mention_ratio, overdue_90_ratio,
nim, cost_income_ratio provide cross-checks/risks without missing-data penalties.
Optional peers are explicit same-group/same-period bank observations; comparisons
are advisory and cannot be invented or interpreted as proof of quality.

Policy bank-research-v1 is an explicit research heuristic, not a regulatory rating
or empirically calibrated predictor. Profit base=min(three-year mean ROE bands
15/12/8/5, ROA bands 1/.8/.5/.25). Caps: NPL <=1/1.5/2/3 gives 5/4/3/2 else1;
coverage >=300/200/150/120 gives 5/4/3/2 else1 (QUALITY bands, not legal minima).
Capital cap uses minimum surplus across all three capital ratios against their
full sourced requirements: >=3/2/1/0 percentage points gives5/4/3/2, below0=>1.
Liquidity cap=min(LCR,NSFR): >=130/120/110/100 gives5/4/3/2, below100=>1.
Confirmed regulatory capital/liquidity/provision breach caps at1. Rising annual
NPL +.2pp caps at3, +.5pp at2; two annual ROE declines caps at4 (no automatic
industrial earnings penalty). E=min(base,caps); no debt_asset_ratio penalty.
Document these bands and their uncalibrated status; test observations rather
than claiming empirical validation. Missing peers/auxiliary metrics alone impose
no cap. No overall stars if E or another dimension is null.

## Integration / tests

Extend score_financial(stock, bank_data=None), rating_math financial/finalize and
canonical validator with explicit sidecar support. `--bank-data` in finalize
requires --stock --check-financial. Evidence/scoring drift cannot bypass the
existing check by silently treating the bank as an ordinary company.

Tests first: complete bank, absent core evidence, bad identity/hash/dates/types,
history gaps, genuine weak values vs missingness, regulatory buffer, auxiliary
gaps, debt independence; candidate output column ambiguity and bounded cache use;
CLI end-to-end ten-field output, checked rejection of score drift. Live official
PDF smoke verifies source/location extraction only, not calibration. Update skill,
tool reference, backend spec and version. Run full unittest/Ruff/metadata checks.
