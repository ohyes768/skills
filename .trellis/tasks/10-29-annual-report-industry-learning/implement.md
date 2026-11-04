# Implementation

- [x] Create skill instructions and output contract.
- [x] Implement download and page/section candidate extraction CLI.
- [x] Add boundary and download failure tests.
- [x] Validate skill, run tests, and inspect a real report.
- [x] Record validation and limitations.

Rollback: remove only the new skill and its new tests; no existing skill behavior changes.

## Validation results
- Seven unittest checks passed (HTTP/local validation, atomic cleanup, nested heading preservation/deduplication, TOC exclusion and missing-heading warnings).
- Generated Chinese PDF integration passed using bundled reportlab/pdfplumber: four topics and page-tagged artifacts written.
- Skill quick_validate passed using temporary PyYAML dependency.
- Real smoke test: 230-page 2024 Chengmai Technology annual report downloaded and parsed. Candidate ranges: industry 15, business 15–17, competitiveness 17–19, outlook 33–34 (physical PDF pages). No separately headed risk candidate; warning retained for semantic review.
- This smoke test validates download/extraction and candidate boundaries, not a completed human-reviewed source/summary deliverable for that report.
- No bundled OCR engine. Tables and ambiguous headings require invoking-agent review as defined in SKILL.md.
- Working changes are left uncommitted for review.

## Optimization pass
- [x] Restrict table extraction to candidate or explicitly selected pages.
- [x] Correct risk aliases and heading levels.
- [x] Add assembly and length-validation CLI.
- [x] Run regression tests and both cached real-report checks.

Optimization validation: 13 unit tests pass. Cached Goldwind and Sino Biological reports both now recognize risk sections (36; 29–30). Assembly CLI preserves reviewed source text and counts summaries as 1332/1353 visible characters; below-budget sections emit warnings without blocking. Table call regression confirms unrelated pages are skipped.
