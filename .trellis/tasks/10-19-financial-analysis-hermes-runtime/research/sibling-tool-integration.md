# Sibling tool integration — 2026-10-21

User approved migrating existing tools into the main skill and concise workflow documentation;
Hermes core and caller stay unchanged. No additional financial report or publication requested.

Inspected the live profile sibling at
`/home/ohyes768/.hermes/profiles/ohyes768/skills/financial-pitfall-recovery`.
It has 996 lines and 7 Python files, including a deprecated fact generator. Main skill had no
reference to it. The sibling's fixed-year checks, minority-profit equality, company-specific
mutation strings, copied metric type set and post-report review were unsafe to adopt verbatim.

Implementation:
- Move the verified fact generator, report builder, fact preflight, report preflight and
  independent report verifier into main scripts, with current-contract adaptations.
- `compute --spec` combines generation and compute. `report --independent-review` combines
  preflight, rendering, original validation and independent verification before terminal.
  Keep legacy no-flag calls compatible.
- Main SKILL.md points to a short reusable-tools guide. Do not duplicate the sibling's case
  history. Existing complex/table fact mappings remain supported.
- Convert the 7 sample-specific mutation intentions to synthetic regression tests (including
  balance identity with nonzero minority profit), run during maintenance rather than each run.

Validation baseline: ten failing integration tests before implementation. Final full-suite
results recorded in implement.md after completion. No model-level timing comparison implied.
