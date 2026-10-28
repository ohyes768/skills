# Implementation

1. Extend research_state init/dispatch/snapshot validation without changing existing scoring rules.
2. Add calculate ledger binding and atomic finalize output; document five operational rules and host limits.
3. Add behavioral budget, stale-score, reopening, failure-output and compatibility tests; run suite/lint.
4. Update executable spec, inspect merged concurrent changes, commit and push Git per final user direction; do not synchronize NAS.

## Validation
- 156 rating tests passed, including six new execution-control regressions.
- Ruff check/format and skill metadata validation passed.
- Concurrent web-only/four-followup changes preserved and tested together.
- No Hermes caller integration or live model acceptance claimed.
