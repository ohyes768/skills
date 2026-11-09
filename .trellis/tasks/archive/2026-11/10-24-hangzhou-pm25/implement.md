# Implementation plan

Use the approved task PRD and design. Work inline in new `environment/hangzhou-pm25/` files; existing dirty finance files belong to other work and must be preserved.

1. Write failing behavioral tests in `tests/test_pm25.py` for provider normalization and report contracts, including zero/missing, radius, freshness, calendar coverage and fallback. Run with `python -m unittest discover -s environment/hangzhou-pm25/tests -v` and record the expected missing-feature failures.
2. Implement standard-library `scripts/providers.py` and `scripts/report.py` until those tests pass. Keep source metadata and valid-hour counts in JSON; derive Markdown from the same report.
3. Add CLI tests before `scripts/hangzhou_pm25.py`. Verify offline snapshot replay, invalid input, nonzero total-outage status, output files and machine-readable stdout. Implement bounded HTTP reads/retries and concurrent provider fetches.
4. Write `SKILL.md` and source/interpretation reference. Add a small environment category to README without altering unrelated edits.
5. Run the entire new suite, Python compile checks, skill quick_validate and `git diff --check`. Run the real CLI against public APIs into a temporary directory; inspect JSON and Markdown, actual freshness and coverage. Fix demonstrated issues and rerun affected checks.
6. Record accepted limitations, test evidence and a task-specific backend contract. Leave changes reviewable and uncommitted; no installation, publishing, scheduling, or unrelated task archiving.

Rollback is removal of this task's new skill directory and its own README/spec entries only. Public requests are read-only queries and do not modify external state.

## 2026-10-27 short-report refinement

User requested an immediately understandable final report with controlled length. Add failing short-report tests (maximum 300 visible characters and correct fallback/missing labels), replace only the Markdown rendering, retain JSON and collection logic, and update the Skill's response-length instructions. Update the CLI assertion for remaining-hours semantics, run the whole suite/Ruff/Skill validation, and regenerate the already-fetched report offline. The user subsequently authorized committing and pushing this refinement; the full 29-test suite, Ruff and Skill validation pass.
