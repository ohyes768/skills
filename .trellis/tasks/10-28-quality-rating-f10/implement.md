# Implementation
1. Add fetch/normalization/scoring module and provenance packet.
2. Integrate mutually exclusive F10 sidecar into arithmetic/finalize.
3. Replace default skill financial routing with unified F10; retain legacy CLI.
4. Run offline unit suite, CLI smoke and diff/reference checks. Attempt bounded live fetch if network available; report actual coverage only.

## Verification completed
- 170 unittest cases passed, including new F10 period/identity/hash/duplicate/missing/finalizer checks.
- Ruff check and formatting passed for new module/tests and changed arithmetic/validator; skill metadata validator passed; local reference and git diff checks passed.
- Live public F10 smoke: 600036, 600519, 601318 at target 2026-06-30. All produced a score under f10-basic-v1. Bank/insurance generic balance/cashflow queries failed and remain explicit issues; core profitability came from main indicators. This is not proof of universal company coverage.
- Real CLI financial/finalize/read-only validator accepted a temporary bank serialization fixture. Fixture is not a researched company report; narrative warnings expected. No stock report was published.
- Existing unrelated/in-progress bank-liquidity edits retained. No commit or NAS synchronization performed in this turn.
