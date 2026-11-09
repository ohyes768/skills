# Verification

## Automated checks

- Test-first core: 16 initial missing-feature failures; all passed after implementation.
- CLI: 5 expected missing-feature failures after directing temporary fixtures into the writable test directory; all passed after implementation.
- Network regression: `IncompleteRead` escaped the provider boundary before the fix; now isolated and retried as `HTTPException`.
- Full suite: 24 tests pass (standard-library unittest).
- Ruff check/format, compileall and Skill quick_validate executed. On Windows invoke quick_validate with `python -X utf8` because its default read otherwise uses GBK for the Chinese skill.

## Live acceptance

2026-10-24 16:59:41 Asia/Shanghai: all three public interfaces returned usable data without credentials, using normal TLS verification. Ten stations within 25 km, all at 16:00, yielded an explicitly self-computed mean 9.4 μg/m³ (station range 3–16). CAMS daily model means were 13.38, 17.93, 45.64, 46.20 and 34.67 μg/m³; the final date had 21/24 valid hours and was labeled partial. These are recorded acceptance values, not a current forecast to reuse later.

Input, JSON report and Chinese Markdown are saved outside source at `C:/Users/Administrator/.codex/visualizations/2026/10/24/01a16cb4-84cc-7622-8364-bcb40dbef9eb/pm25-live/`.

## Independent review

A read-only reviewer checked source, requirements and an offline Skill usage exercise. It independently reproduced the truncated-body `IncompleteRead` issue; the fix adds HTTPException to retry and isolation, with a regression test. No other material correctness findings were reported. The exercise correctly distinguished the self-computed observation mean, model forecast, missing tail hours and conditional meteorological explanation.

## Acceptance mapping

- A1: offline CLI and live execution generate JSON and Markdown; Skill documents invocation.
- A2: observation, stale and missing-source tests cover labeling/time; live run verifies station details.
- A3: valid-tail, all-missing day, next-date rollover and zero tests cover counts and calendar semantics.
- A4: joint-hour and missing-weather tests, JSON numeric evidence and transparent rule reference cover interpretation.
- A5: no AQI/grade calculation, explicit concentration units, unit-mismatch rejection and Skill restrictions.
- A6: total outage, retry, 404 and truncated-body isolation tests; report contains source links and attribution.

## Delivery state

Implementation is ready for use from source. The user subsequently authorized a PM2.5-only Git commit, explicitly preserving the pre-existing staged log-cleanup changes. The commit preflight reran all 24 tests, Ruff and the Skill validator successfully. No runtime installation, external publication, recurring task or push was requested. Trellis archiving remains a separate bookkeeping step.
