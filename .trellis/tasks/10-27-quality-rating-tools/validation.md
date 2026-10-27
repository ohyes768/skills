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
