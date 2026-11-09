# Insurance analysis — v3.4 approved continuation

User requests planning and implementation, especially Ping An. Preserve existing
bank changes. No commit, push, remote deployment or live rating publication.
Keep immutable stock, five dimensions and ten nullable output fields. Add explicit
--insurance-data mutually exclusive with --bank-data and restricted to insurance.

## Evidence contract (insurance_data.py)

make_template(stock,as_of,insurance_type) -> schema_version1,code/name,
stock_sha256,as_of,insurance_type life|property|group,reports=[],entities=[],coverage=null.
Reuse bank_financial.stock_fingerprint/_date. Every numeric fact is
{value,unit:pct|cny_million,source_url,locator,basis:period|point_in_time}.
Finite numbers only, not bool/string; zero is valid. Validate units by metric.
Source structure does not prove factual accuracy. Keep other valid facts when
one metric is invalid, but block grading. Reject future published dates/periods,
duplicates, mixed scopes; latest snapshot max400 days old.

Listed reports: {period_end,published_at,period_type:annual|interim|quarter,
scope:group,metrics}. Require latest three continuous annual roe (weighted ROE
for ordinary shareholders, not operating ROE). Calendar anchor identical to bank:
previous year after Apr30; before May accept previous year's annual if present,
otherwise year before. Annual Dec31, interim Jun30, quarter Mar31/Sep30/Dec31.
Group type additionally requires latest group_solvency_ratio (pct,point_in_time).

Sourced assessment shape: {status:supported|adverse|unknown,statement,source_url,
locator,published_at,period_end}. Must match relevant latest snapshot period and
be available as_of. Unknown core assessment -> gap, adverse -> known weakness.
Evidence statement must describe facts; audit opinion alone does not establish
reserve adequacy or asset-liability matching. Script checks shape, not truth.

coverage is a sourced assessment plus entity_ids:[...] and other_segments:[...].
IDs exactly match material insurance legal-entity roster. Statement explains
materiality from segment disclosures. Group requires life AND property; single
type requires only matching entities. Other material segments contain
name,kind:bank|asset_management|other plus assessment fields; unknown blocks,
adverse caps2. Bank/asset-manager risks are separate, not substituted for insurer
capital. No complete child-bank sidecar required to assess listed group coverage.

Entity: {id,name,kind:life|property,scope:solo,latest:{period_end,published_at,
metrics:{core_solvency,comprehensive_solvency}},risk_rating:{value,period_end,
published_at,source_url,locator},annuals:[...],assessments:{asset_liability,reserves}}.
Entity latest must equal listed latest period; ratios pct/point_in_time. Do not
average solvency across entities. Risk comprehensive rating allowed A,AAA,AA,
B,BBB,BB,C,D (A/B families), not numerical regulatory1-5 or skill stars.
Rating period <=snapshot with lag<=183days; published<=as_of and period<published.
Both ALM/reserve assessments required with same entity snapshot period.

Entity annuals use annual-report shape but scope:solo and comparability_id.
Latest same three annual years. Life requires net_investment_yield (pct,period)
and selected entity.value_metric nbv|new_business_csm (cny_million,period), same
nonempty comparability_id across years; only harmonized actuarial/accounting
assumptions justify matching IDs. Property requires combined_ratio (pct,period)
with same comparability_id. Optional csm_balance (amount,point), continuation_ratio,
surrender_ratio,total_investment_yield (pct,period),net_profit(amount,period)
are supporting only. NBV/CSM are value metrics, not regulatory indicators.

## Scoring owner (insurance_financial.py)

score_insurance(stock,packet) returns score/status/checks/issues/risks/sector,
policy/warnings. insurance-research-v1 is uncalibrated research, not regulatory
or credit rating. Base3y mean listed ROE>=15/12/8/5 gives5/4/3/2 else1.
Per insurer core>=150/120/100/75 gives5/4/3/2 else1; comprehensive>=250/200/150/120
gives5/4/3/2 else1. Core<50, comprehensive<100 or risk rating C/D cap1; describe
only the specified solvency conditions, not full compliance certification.
A family cap5, B family4. Group solvency uses comprehensive quality bands, no
invented group core50 rule. No subsidiary ratio averages.
Life latest comparable value<=0 or decline>=20% caps2; smaller decline caps3;
otherwise5. Prior<=0 does not yield invented percentage growth. Investment-yield
facts/trend shown without arbitrary yield minimum or assumed liability-cost spread.
Property 3y combined mean<=95/98/100/103 gives5/4/3/2 else1; latest>100 cap2,
>105 cap1 (underwriting quality, not regulatory breach). Adverse reserves cap1,
adverse ALM or coverage/other segment cap2. Final min(base,caps); any core issue
->null, retaining only valid dated facts/weaknesses. Missing auxiliary data no cap.
No insurer NPL/provision coverage or enterprise leverage rule.

CLI insurance_financial.py template --stock --as-of --type;
validate --stock --input. JSON stdout; malformed files stderr exit2. Validation
insufficient_data JSON exit2. No network or automatic candidate acceptance.

## Integration/acquisition

Extract common cached metric-label candidate engine from bank_evidence preserving
bank CLI/API/output. insurance_evidence labels solvency, group, NBV, CSM, combined
ratio, investment yields, provisions. Source/hash/page, raw strings,
needs_confirmation and bounded cursor; no auto column/unit acceptance.

Parent integrates score_financial, rating_math and canonical validator with
insurance_data arg/CLI. Sidecar requires --stock --check-financial for finalize;
reject null/nonobject, wrong sector and mutually supplied sidecars.
Research init --insurance-research appends E topics profitability/solvency/
insurance_business/asset_liability, sharing existing round budgets and failures.
Persist dimensions.financial.mode for new states; infer existing E bank mode for compatibility.
No conversion bank<->insurance/reset by init. Sidecar finalization checks correct
mode and terminal evidence; bank legacy tests remain passing.

## Implementation/verification plan

- [x] Tests first insurance_data.py/insurance_financial.py: life/property/group,
  required vs auxiliary, chronology/scope/roster/comparability/units, zero vs null,
  known weak valid facts beside invalid metric, no averaged subsidiary ratios.
- [x] Tests first common candidate engine and insurance wrapper, keep bank API.
- [x] Parent tests first CLI/sidecar/research mode, then integration.
- [x] Source-check official Ping An material, not pasted report numbers. Live
  snapshot may remain ungraded without full history; do not invent a complete score.
- [x] Update SKILL/ref/spec/version; full unittest,Ruff,metadata,independent review.

Run python -X utf8 -m unittest discover -s tests/basic-quality-rating -q;
python -m ruff check/format --check scripts and tests. Empirical calibration,
live analyst accuracy and installed-copy synchronization are separate work.
