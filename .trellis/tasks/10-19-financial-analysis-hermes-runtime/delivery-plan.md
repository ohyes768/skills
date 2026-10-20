# Financial delivery and fewer model round trips

Approved scope (2026-10-20): finish runs after acceptance and combine deterministic steps.
Continue the existing runtime task; do not change financial coverage or raise iteration limits.

## Design

- Add `evidence`: extract selected evidence and return the first bounded context packet together.
  Cursor continuation only reads; it never extracts again.
- Compute returns a bounded facts/metrics packet. Unfiltered analyze packets use the ledgers;
  targeted page/section requests still return original evidence.
- Add `finish --semantic-reviewed`: revalidate the actual report, snapshot artifact hashes and
  atomically write completion.json. Merely reaching machine `verified` is not final delivery.
- Opt-in financial Runs API requests use a unique server-selected directory. The host watches
  completion.json, independently validates current artifacts/source URL, returns analysis.md,
  marks completed and interrupts the agent. No model transcription of the report is required.
  Ordinary API requests keep existing behavior. A financial agent returning without an accepted
  receipt is failed, including budget exhaustion; no extra model summary request is needed.
- Keep execution and delivery distinct: do not remove the active worker until it actually exits.
  Cancellation must not overwrite an already accepted terminal result.

## Execution / verification

- [x] Add failing skill tests for finish, tampering, cursor reads and structured analysis.
- [x] Implement combined commands and completion verification; run skill pytest and Ruff.
- [x] Add failing host/client regressions using the real Runs API adapter with a controlled agent.
- [x] Implement the opt-in adapter and caller; test receipt delivery while agent is blocked,
  invalid/missing receipts, worker failure, interruption and normal legacy requests.
- [x] Sync reviewed skill files and host integration to NAS with backups; do not send reports.
- [x] Run remote checks, update contracts/specs and record deployment/restart status.

Rollback: restore backed-up host/client files and skill files. Old CLI remains supported.
No automatic historical run recovery, RSS publication, model changes or unrelated cleanup.

## Results (2026-10-20)

- Local skill: 239 passed; NAS skill: 234 passed, 5 optional saved-artifact tests skipped.
- Installed Hermes adapter: 27 passed (4 delivery + 23 existing Runs API tests), including
  synthetic report -> real subprocess verifier -> HTTP output while worker cleanup is blocked.
- Caller: 27 passed across delivery, existing HTTP client and analysis/publishing mocks.
- Actual runtime is `/home/ohyes768/agent/hermes-agent/venv/lib/python3.11/site-packages/`,
  not the adjacent source tree. Integration installed there with content-addressed backups.
- Idle profile gateway restarted; authenticated capabilities confirms financial_artifact_delivery,
  malformed financial request returns 400 without creating an agent; caller now opts in.
- No live-model financial benchmark or publication performed. Historical timeout causality is
  not proven by a NULL session ended_at; delivery no longer depends on that inference.
