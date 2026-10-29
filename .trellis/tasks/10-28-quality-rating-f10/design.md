# Design
Add self-contained f10_financial.py using existing standard-library HTTP, response validator and atomic writer. Fetch four datasets over a bounded five-year window, cache by URL, retain raw rows and dates. Main indicators own disclosed weighted ROE and cumulative deducted profit; statement fields provide balance checks/background. Never substitute simple ROE. Derive adjacent single-quarter profits before YOY. Missing or ambiguous periods remain null. Ordinary companies reuse financial_score with normalized payload; financial sectors use explicitly limited ROE/profit caps. Add --f10-data to financial/finalize, recompute from packet rows and bind original identity hash. New skill workflow takes precedence over legacy sector references.

F10 ledger repair: reuse the existing optional financial dimension with mode=f10
and f10_data as its only evidence topic. Explicit init --f10-research keeps old
A-D-only callers unchanged; normal skill commands always include it. It is
mutually exclusive with bank/insurance flags and mode switching. All registered
attempts use the existing global budget and immutable ledger. Complete requires
source-bound evidence; gaps force E=null and open financial prevents sealing.
Pass require_f10 from checked finalization to reject absent/wrong-mode ledgers.
