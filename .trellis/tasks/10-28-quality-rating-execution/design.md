# Design

Extend the existing research ledger with an opt-in execution contract: immutable global research-call limit, delivery reserve, phase and calculated dimension digest. Existing ledgers/callers remain compatible. New documented analysis uses this contract from init. Each newly reserved route attempt consumes one call; retries and reopening share the same budget, replay does not double-charge. Host reads/searches must each reserve a receipt; the script cannot observe bypassing calls or certify historical provenance.

`calculate --research-state` checks terminal evidence and saves a dimension snapshot, using the existing arithmetic owner. Checked finalize rejects absent/stale snapshots for controlled ledgers. Reopening invalidates it. CLI finalize can atomically save the exact JSON via --output, while retaining stdout. No consumer or Hermes host changes. Document a fixed delivery reserve and stop on host exhaustion warnings; no invented host iteration accounting.

Rollout: run regression suite and metadata validation, back up changed installed files, sync selected files with hashes. Old runs are resumed in place without fabricated budget reconstruction.
