# Implementation
1. Update bank scoring and required-topic selection.
2. Update skill and bank/API/research references, bump version, preserve existing working changes.
3. Test missing pair/single metric/invalid records/known weaknesses/core gaps and checked finalization.
4. Run full tests, Ruff and metadata validation; report local delivery status accurately.

## Verification
- 162 rating tests passed, including missing/null/partial liquidity, core gaps, optional topics and checked CLI delivery.
- Ruff check/format, skill metadata validation and git diff --check passed.
- Version 3.8.0 / bank-research-v2. Existing uncommitted web-navigation edits preserved.
- Local implementation complete; no commit/push or NAS synchronization performed in this iteration.
