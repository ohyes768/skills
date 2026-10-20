# Journal - codex (Part 1)

> AI development session journal
> Started: 2026-10-16

---

## 2026-10-20 — Financial delivery and tool round trips

User approved implementing reliable completion and combining deterministic steps. Added an explicit
semantic-review receipt with fresh validation, bounded ledger packets from compute, and evidence
extraction plus first-packet delivery in one command. Added an opt-in Hermes Runs API adapter and
caller integration with independent host verification, absorbing terminal states and no extra
budget-exhaustion model summary for financial jobs.

Deployed skill and integration with backups on NAS. Verified the runtime imports installed
site-packages, restarted only the idle ohyes768 gateway, checked capabilities and invalid-input
rejection. No real report/model run or message publication. Tests: local 239; NAS 234+5 skipped;
installed Runs API 27; caller 27. Work remains uncommitted; wider P4 benchmarking/isolation remains.

## 2026-10-20 — Revoke the host patch; retain Skill-only optimization

User explicitly requested removing the core patch. Restore the original installed API and client,
remove the bridge/receipt mechanism, and keep evidence/compute packet batching. Semantic review
precedes the final report; verified report signals stop and optional --include-report returns
the exact body for legacy full-Markdown callers. Prior host-integration notes are historical.

Rollback verified byte-for-byte against original API/client backups. Removed live capability,
gateway helper, custom tests and bridge installer. Restarted only the idle profile gateway.
Validation: local Skill 232 passed; NAS 227 passed/5 optional skips; original API 23 passed;
original caller 26 passed; Ruff and Skill metadata passed. No model run or publication.

