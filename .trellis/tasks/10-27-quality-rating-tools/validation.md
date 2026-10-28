# Validation (2026-10-27)

- Full basic-quality-rating suite: 50 tests pass (unittest).
- Ruff lint and format checks pass; skill metadata validator passes; git diff --check passes.
- Existing 3,125 scored and 211 nullable-combination arithmetic cases still pass.
- E thresholds, all 16 severe-factor combinations, zero/negative/bad inputs,
  adjacent-period parsing, missing history and financial-sector null paths covered.
- PDF cases use real generated pages and parser with mocked HTTP, including cache
  reuse, integrity failure, refresh failure preservation, page citations, cursor
  continuation, scans and CLI behavior. No shared PDF source files changed.
- CLI smoke: financial -> checked finalize -> read-only validator passed;
  PDF prepare -> cached prepare -> search/read returned PDF page 2, with only
  one HTTP fixture download. Results: .tmp/quality-rating-tools-smoke/smoke-result.json.
- Legacy migration preview changes no files; apply preserves backups; repeated
  apply is idempotent; retargeting owned shim preserves original backups.
- Read-only cross-review found and fixed oversized-score validation overflow and
  migration retargeting; original regression cases remain covered.
- Remote installed files were read for context only. No deployment, full live
  Hermes analysis or production speed benchmark is claimed.

## v3.2 follow-up validation

- Full suite: 71 tests pass; Ruff lint/format, skill metadata and diff checks pass.
- New policy tests cover quota/auth/access, bounded transient retries, no-source
  stop, empty/404 scope and stable permanent causes for late outcomes.
- Ledger tests cover persisted budgets/identity, source fallback, last-round
  completion, topic/reference coverage, one reopen, corruption and lock failures.
- Read-only independent review found three defects and verified all fixes:
  blocked-source pending replay, outstanding failure counter and persisted fact
  shape validation. Reproducing regression tests remain in the suite.
- Real CLI smoke with synthetic host outcomes: 402 -> backup; business uses one
  round; industry uses three, fourth rejected; terminal state passes checked
  finalize and validator, with ten fields and stars null for the evidence gap.
  Receipt: .tmp/bounded-research-smoke-f8ywlxuj/smoke-result.json.
- This iteration does not execute host network tools, deploy to NAS, modify the
  application, benchmark live research speed, or create a Git commit/push.

## v3.3 bank follow-up validation

- Full suite: 110 tests pass. Ruff lint/format, metadata validation pass.
- Bank evidence tests cover source shape, immutable stock hash, future dates,
  latest history gaps, ratio consistency, explicit applicable capital requirements,
  null vs known weakness, unsupported liquidity regimes and optional peer gaps.
- Real CLI tests cover sidecar financial -> checked finalize -> canonical validator,
  ten-field output, score drift rejection, wrong sector and explicit null sidecars.
- Persisted bank E research mode preserves A-D rounds and global provider blocks,
  enforces shared 3-round budget and terminal four-topic evidence before finalization.
- Independent review reproduced and verified fixes for a literal-null CLI sidecar
  bypass and applicability-dependent capital/liquidity breach assertions. Regression
  tests remain; reviewer found no remaining material bug in scope.
- Live official CMBC 2025 H1 PDF downloaded/indexed once, 292 pages. Cached bank
  candidate scan found 57 page/metric candidates, bounded first packet to6000
  text characters, continued with source-bound cursor without a second fetch.
  PDF SHA256:58aace1a93fc7d5ff335651f77e3e18fa558b10722307ede2ff34821cc43c294.
  Verified group snapshot on PDF pages9/11 and full capital requirements on46.
  Snapshot-only E remains null without annual history; verified capital surplus
  is1.75/2.87/2.50pp. Coverage145.06% is not called a regulatory breach.
  Smoke receipt:.tmp/bank-smoke/smoke-result.json; small source-linked numeric
  regression fixture is kept in tests/basic-quality-rating/fixtures/.
- Local source only. No deployed skill/app changes, commit or push. Research bands
  are explicit heuristics; no empirical calibration, investment accuracy or full
  live analyst execution is claimed. Official fixture is a historical snapshot,
  not a current company recommendation.

## v3.4 insurance follow-up validation

- Full suite: 147 tests pass (fresh unittest run23.243s). Ruff lint/format,
  skill metadata and git diff whitespace checks pass. No bank regressions.
- Insurance issuer modes life/property/group, source/units, listed-vs-legal
  scopes/coverage, future/stale/lagged facts, three-year comparability, core
  vs auxiliary gaps, noninsurance assessments and no solvency averaging tested.
- Actual CLI financial -> finalize with insurance sidecar and terminal insurance
  ledger -> canonical validator passes with exact ten fields. Synthetic complete
  group E5; numerical stars4. Explicit null/nonobject/wrong-sector/mutual sidecars
  fail; E mode preserves existing A-D rounds and global source failures.
- Independent review reproduced two P2 defects: signed comprehensive yields and
  conflicting annual periods selecting last observation. Both fixed/tests retained,
  reviewer reverified. Negative solvency ratios are valid known capital weakness,
  not missing; strings/ratio contradictions still rejected. No remaining material
  issue found in reviewed scope. API optional-ledger limit explicitly documented.
- Ping An official IR PDF failed after bounded SSL retries; switched to public
  exchange-distributed 2024 annual summary on cninfo.22 pages, SHA256
  5d452a6f91ea17947622dd416d2df72dd08b69f5e5bf8f35391661cce2a4d2e9.
  Candidate tool returned28 page/metric candidates, first packet6000chars, cached
  continuation with no second download. Read PDF6/7/16: group204.1%, life189.2%,
  property205.3% comprehensive solvency remain distinct; NBV original vs restated
  comparison requires assumption/footnote review. Small source-linked fixture
  deliberately lacks legal core ratios and remains ungraded, never group-proxied.
  Smoke receipt:.tmp/insurance-smoke/smoke-result.json distinguishes official
  locator evidence from synthetic complete-group score.
- No complete current Ping An rating, empirical calibration, live-model factual
  accuracy, consumer deployment, commit/push or NAS synchronization is claimed.

## v3.5 PDF route removal (2026-10-28)

- Removed four PDF/cache/candidate scripts and three dedicated suites. No active
  references to their commands/imports remain. Kept historical sourced numeric
  fixtures; they require no PDF parsing and still exercise missing-data safety.
- Regenerated uv.lock offline using the existing Python and workspace-local cache;
  only the project remains, with empty dependencies. Default uv cache was not
  writable, so no package installation or environment repair was attempted.
- python -S -X utf8 -m unittest discover -s tests/basic-quality-rating -q:
  124 tests passed without site-packages. Synthetic bank and insurance fixtures
  use webpage URLs/table locators through checked scoring/finalization.
- Ruff lint and format, skill metadata validation, git diff --check passed.
- No measured live speedup or current live insurer rating is claimed. Missing
  readable official facts can still yield null. No commit/push, installed-copy
  update, sibling financial-statement-analysis edit or NAS deployment performed.

## v3.5.1 whole-skill/source review (2026-10-28)

- Independent read-only review found date ambiguity, missing claim/source mapping,
  an overbroad financial-conflict exception, redundant sector validate calls and
  inconsistent A-D source fallback wording. All five were corrected.
- Entrypoint reduced from 258 to 227 lines relative to HEAD, retaining the scoring
  standards and nullable contract. Enterprise mechanical explanation moved once
  into references/tools.md; output example boilerplate and repeated setup removed.
- Independent forward scenario: undated official product page + dated interim
  report + unread governance-remediation snippet + caller financial inputs.
  Correctly kept management null and all derived values null, distinguished
  publication/access/period dates, cited only read sources, kept caller input
  separate, and reused closed evidence without additional searches/validators.
  This was a synthetic instruction-following check, not a live stock rating or
  source-authenticity test; unavailable full evidence was not invented.
- 124 tests passed with python -S; Ruff lint/format, skill metadata, local Markdown
  reference resolution, offline lock consistency and git diff --check passed.
  The citation reminder remains advisory; no source-truth validator was added.
- No commit/push, deployed-skill synchronization or application changes performed.

## v3.6 API candidate acquisition (2026-10-28)

- Researched Eastmoney free main-finance JSON, Lixinger insurer financial API,
  DataCube bank_id/insu_id and Tushare fina_indicator; references/financial-data-api.md
  records source links, supported fields, credentials and uncovered requirements.
  Only the free endpoint was actually called; no paid-account access is claimed.
- Tests-first: initial missing module failed, then 14 acquisition tests passed.
  Independent review reproduced outsize-integer, malformed timestamp suffix and
  HTTPError cleanup issues. Added regression cases before correcting them; also
  prevent output overwriting stock before network access. All 17 new tests pass.
- Full suite: python -S -X utf8 -m unittest discover -s tests/basic-quality-rating -q:
  141 tests passed. Ruff lint/format, skill metadata, local reference resolution,
  offline dependency-free lock regeneration and scoped diff check passed.
- Real network smoke: 600036/000001/601318/601628 yielded 18/19/18/18 historical
  rows, with no row issues in this sample; each second fetch used verified cache.
  Initial fetch seconds: 0.661/0.457/0.243/0.237 in this environment only.
  Full CLI cached output/compact stdout checked with 600036. Receipts and raw
  response hashes are under .tmp/financial-api-smoke/; no credentials involved.
- All candidates remain third_party/unconfirmed and ready_for_scoring=false.
  No full current insurer or bank E grade was issued, no legal-entity scope or
  solvency type inferred, no official source certification or speed SLA claimed.
- Other active financial-statement-analysis edits were preserved. No commit,
  push, personal-web mutation or runtime installation was performed.

## v3.6.1 explicit target report period (2026-10-28)

- Nine tests added first and observed missing-argument/field failures, then passed:
  exact Q3, H1-only missing Q3, rejected Q3 dates without older fallback, duplicate
  Q3 removal, newer returned period, no requested target, bad-target preflight,
  same raw cache/different targets, CLI missing-target receipt.
- 150 full-suite tests passed without site-packages; Ruff lint/format, skill
  metadata, offline lock generation and scoped diff check passed.
- Saved real raw API responses reused without network: 000001 matched Q3
  2026-09-30; 601318 was missing_target with latest usable 2026-06-30. Both retain
  ready_for_scoring=false. These reflect saved samples, not fresh official filing
  discovery or a claim that Ping An has not published a quarterly report.
- Matching is report-period alignment only, not numeric reconciliation with
  announcement text. No quarterly-to-annual conversion or single-quarter inference,
  no personal-web wiring, source-policy relaxation, commit or remote deployment.
