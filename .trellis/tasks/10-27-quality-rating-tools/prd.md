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
