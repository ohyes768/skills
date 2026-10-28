# Quality rating execution tools

## Goal
Implement the user's selected improvements 1, 2 and 4: deterministic financial
E scoring, reusable PDF caching/retrieval, and one coherent validation contract.

## Requirements
- Retain the v3 nullable ten-field output; do not introduce valuation/trade advice.
- E uses only original supplied financial inputs, with explicit rule traces,
  periods, missing/invalid data and financial-sector handling.
- PDF sources are cached with provenance and hashes, searched/read in bounded
  page-cited packets; repeated reads must not download/parse the PDF again.
- Reuse existing PDF downloading/indexing where possible; no per-run dependency
  installation, temporary tool development, or full-document terminal output.
- Validation reuses rating_math arithmetic; accept canonical grouped boundary
  text and nulls; do not reject disclaimers or unrelated coincident financial numbers.
- Remove conflicting runbook instructions through a maintained migration path.
- This iteration changes local source and tests only. Remote installed skill,
  application consumers, deployment, commits and pushes are outside this request.

## Acceptance
- Tests cover E thresholds, cap precedence, all weak-factor combinations,
  sector rules, missing/bad values and periods, latest continuous ROE window.
- PDF tests use real generated PDF pages and mocked HTTP to verify cache hits,
  provenance, changed/corrupt cache, snippets/page continuation and scanned pages.
- Validator regression tests cover the recorded grouped-boundary rejection,
  nullable outputs, malformed JSON/types, score mismatches, disclaimers and
  financial numbers equal to total score.
- Existing rating tests and any impacted PDF tests, lint and metadata validation pass.
- Run an end-to-end invocation through each new CLI and record limitations.

## Follow-up: bounded research (user approved 2026-10-27)

Implement remembered source failures/fallback and per-dimension evidence progress.
Permanent quota/auth failures stop reuse of that route for this run. Transient
failures have bounded retries and return an alternative without blocking sleep.
No source available means a disclosed evidence gap, never invented findings.
Persist evidence and initial+two follow-up rounds per A-D dimension. Completed
dimensions freeze; one concrete material conflict permits one reopen round.
Repeated commands/restarts must not reset counters or change the stock identity.
Keep the final ten output keys; optional finalization gate requires terminal
research state and null scores for dimensions closed with evidence gaps.
Host tools are still called by the agent: these helpers govern documented
before/after calls, not a network proxy or a host-level interception mechanism.
No remote installation, application changes or automatic commit/push in this follow-up.

## Follow-up: bank financial analysis (user approved 2026-10-27)

Support bank E with a dedicated rubric and explicit official-source evidence
sidecar; keep original input immutable and the ten-field nullable output intact.
Assess profitability, asset quality, capital surplus and liquidity rather than
industrial leverage. Required evidence gaps remain ungraded; verified weakness
receives a low score. Keep report dates/scopes/provenance and reject future data.
Provide reusable candidate extraction and validation, not unchecked PDF-to-score
conversion. Document heuristic score bands and absence of empirical calibration.
Preserve other sectors. Verify against real official disclosures and regressions.

## Follow-up: insurance financial analysis (user approved 2026-10-27)

Support life, property and mixed insurance groups with traceable official-source
sidecars and a dedicated E rubric. Preserve bank/enterprise behavior, immutable
stock and ten-field nullable output. Distinguish group from legal insurers and
material bank/asset-management segments; no averaged solvency or bank proxies.
Separate missing evidence from real weakness, research bands from legal minima,
and NBV/CSM business value from regulatory capital. Reuse PDF cache and budgets.
Plan and execute locally; no commit/push/deployment or published company rating.

## Follow-up v3.5 (2026-10-28): fast, simple execution

User requested removal of the PDF route to reduce runtime complexity. Keep stock
JSON, sector scoring and nullable output; source additional facts from existing
structured data or readable official web content. Remove PDF tools/dependencies,
not sector evidence requirements. No automatic commit/push or remote deployment.
Acceptance: no PDF tool calls/imports remain; dependency metadata is empty;
remaining scoring, research and finalization tests work without site-packages.

## Follow-up v3.5.1: whole-skill review and source presentation

User invoked skill-creator to review/optimize the entire skill and clarify final
sources. Preserve PDF removal, scoring and exact nullable ten-field output. Make
sources traceable within report_md without extra searches, forced counts or dates.
Remove duplicated execution instructions and isolate mechanical E explanation.
