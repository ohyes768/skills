# Runtime review: eee96671659f4df0b1b1dbe822477e26

Reviewed 2026-10-28. Scope: read-only remote investigation, no runtime edits.
Source directory: /home/ohyes768/work/gm-sessions/eee96671659f4df0b1b1dbe822477e26/.
Sources: summary.json, timeline.md, messages.jsonl and tools.jsonl. Also checked
artifact existence in /home/ohyes768/work/qr-600036/; this is a shared working path,
so current artifacts are corroboration rather than an immutable run snapshot.

## Confirmed observations

- Single-stock CMB (600036) analysis using basic-quality-rating v3.6.1.
- Export spans 22.93 minutes, 83 assistant/API turns and112 tool calls, including
  45 execute_code and40 terminal calls. ended_at/end_reason are null, so the export
  does not establish the final outcome of the run beyond its recorded cutoff.
- New candidate fetcher succeeds around +0.73min:18 rows, latest usable2026-06-30,
  no row issues, report_alignment=not_requested (no explicit report-date).
- At +0.73min web_search fails with Firecrawl402; at +2.46min web_extract also fails
  with Firecrawl402. They are separate route IDs over one failed provider dependency.
- The old quality-rating-pipeline-runbook is loaded alongside the new main skill.
  It still prescribes PDF-first extraction and mandatory input reverse calculations.
  Main v3.6.1 prohibits the PDF path and limits rechecking to material conflicts.
  This is a deployed-rule conflict; latest main skill sync alone did not retire it.
- Do not misread summary skill_view count: four basic-quality-rating entries are
  main SKILL plus three distinct references, not four duplicate full entrypoint loads.
- +3.21min scans local search ports; +3.7–6.5min fetches/inspects site JavaScript,
  guesses API endpoints and switches browser/HTTP paths. This expands task scope
  into temporary source-tool development during a rating run.
- By +6.8min, announcement content through np-cnotice-stock.eastmoney.com works.
  Later list/content requests retrieve annual summaries, interim disclosures and
  Pillar3 text using announcement IDs and page_index; the same small custom fetch
  function is re-created repeatedly in execute_code. Source is a distributor's
  copy of issuer announcements, not automatically a first-party certified source.
- Many subsequent calls print overlapping text windows and financial requirement
  tables. Six read_file calls inspect scorer/research implementation rather than
  using their public CLI contracts; no rating_math financial/finalize calls occur
  in the exported112 tools.
- Recorded research status at +19.18min: business/moat/industry/management open,
  rounds_used=0, evidence_count=0; financial open, rounds_used=1, evidence_count=0.
  There are init/start/two failure-result/status calls but no success-result/close.
  A large question and one pending round allow uncontrolled work outside the ledger.
- +19.85min four optional peers are fetched; one code/name pair in the temporary
  input looks inconsistent and the command suppresses stderr, leaving only FAIL.
  Do not classify that failure as provider unreliability without the actual error.
- Current working artifacts: stock.json898bytes, research.json2248bytes,
  bank-data.json319bytes with zero reports/requirements; draft.json/rating.json absent.
- Recorded tool call-to-result windows sum158.67s, union123.59s, across1375.67s
  total. These are log response windows, not pure network timing; the remaining
  interval includes model generation/orchestration/scheduling and cannot all be
  attributed to a single component. Faster HTTP alone cannot explain or fix this run.

## Recommended order (not yet implemented)

1. Retire deployed old runbook with backup/forwarding and remove its automatic
   selection trigger. Verify one active policy version. Keep nullable/sector rules.
2. Enforce execution budget at host/orchestrator: elapsed time, real tool/request
   counts and phase progress. A per-round ledger without host enforcement does
   not cap calls hidden inside terminal or execute_code. At limits, preserve
   verified facts and complete the report with null for unresolved dimensions.
3. Group route health by actual backend (e.g. shared Firecrawl402), and configure
   one known alternate. Do not scan local ports, guess endpoints or develop crawlers
   within rating runs. Provider availability checks belong to deployment/maintenance.
4. Script the observed announcement list -> period/type selection -> paginated
   content -> bounded search/read path. Cache by announcement ID/period/provenance,
   cap pagination/output/retries, verify issuer and date, and preserve official
   original links plus distributor access URLs. Mark empty/partial bodies explicitly.
   Validate real issuer source/column context before promoting numeric candidates.
5. Build explicit evidence-to-sidecar assembly with required-field gap checklist
   and compact CLI diagnostics. Record A-D/evidence progressively; compute E once
   core data is verified, instead of rereading source and recomputing mentally.
   Do not infer undisclosed capital add-ons are zero or weaken score requirements.
6. Defer optional peers and nonmaterial background until required facts are closed.
   Extract relevant table/header/footnote once; reuse it rather than reprinting
   overlapping windows. Canonical identity prevents hand-written peer-name errors.
7. Use a run-ID-specific workspace, while sharing immutable source caches safely.
   Existing qr-600036 path alone does not isolate repeated/concurrent analyses.

## Validation plan for subsequent development

Replay the same input with the same source snapshot. Compare complete output or
explicit unrated delivery, end-to-end duration, model/tool calls, source-fetch count,
repeated windows, ledger coverage and phase closure. Include provider402 and missing
capital/solvency evidence cases. Do not equate successful acquisition with completed
rating or promise the former estimated2–5minute latency without new real runs.

Remote follow-up reads briefly failed because automatic approval review hit an
account usage limit. After explicit user continuation, the same read-only queries
succeeded. No approval bypass, live-process cancellation or remote mutation occurred.
