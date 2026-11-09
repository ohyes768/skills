# Stock Four-Level Valuation — Offline Research Skill Contract

## Scope / Trigger

Applies when changing `investment-analysis/stock-four-level-valuation/` (SKILL.md, references, scripts, tests) or its output contract. The skill prices a single fictional-or-real A-share into four price observation levels (heavy_position/add_position/reduce_position/full_exit) by reusing caller-supplied financial/business-quality research. It is offline, stdlib-only, single-stock, CNY-only, and never reads the favorites API, writes the website, or executes trades. Per-company research pricing: no star-to-PE mapping, no fixed price percentages, no uniform required-return table.

## Signatures

```bash
python <skill>/scripts/validate_result.py finalize --stock stock.json --input draft.json --output result.json
python <skill>/scripts/validate_result.py check --stock stock.json --input result.json
```

- `stock.json`: exactly `code` (6-digit string, leading zeros kept) / `name` / `as_of` (YYYY-MM-DD) / `currency` ("CNY").
- `draft.json`: exactly 13 keys (identity + status/summary/confidence/risks/invalidation_conditions/data_gaps/analysis/evidence/valuation). It never receives computed levels, report text, or versions.
- `valuation_math.evaluate(node) -> Decimal` (unrounded), `round_price` (cents, HALF_UP), `level_metrics` (uses rounded price).
- Success: finalize prints the full result JSON (byte-identical to the file) and saves atomically; check prints a short receipt. Errors: exit 2, stderr reason, empty stdout, no fake result.

## Contracts

- Result: exactly 17 top-level fields including `analysis` (the five research paragraphs, kept for every status so non-ready reports replay losslessly) and `schema_version="1.0.0"` / `skill_version` (read from SKILL.md frontmatter, never invented).
- `levels`: exactly the four site-compatible keys, each `{price,pe,pb}`. `pe = price / positive TTM EPS`, `pb = price / positive common BVPS`, else null; the valuation multiple stays in `model.multiple`. Non-ready statuses: every level field null and `valuation = null`.
- Ready `valuation` keeps six input keys (primary_method/anchor/scenarios bear-base-bull/decisions/metric_inputs/sensitivity 2-8 with a real parameter change vs its base_level) plus derived `formula_version="1"`, `calculated`, `scenario_values`, `sensitivity_values`, `level_metrics`.
- Whitelist math only: `pe_multiple` (eps,multiple>0), `pb_multiple` (bvps,multiple>0), `equity_cashflow_pv` (1..100 year-end flows, r>0, basis dividend/fcfe, finite_life bool, terminal value/exit_pe/perpetuity with r>g>-1; finite life forbids perpetuity). Decimals as strict strings, bool/NaN/Infinity/unknown fields rejected, margin in [0,1). Prices round HALF_UP to cents and must be strictly increasing after rounding — never sorted, shifted, or nudged.
- Evidence items: 9 fixed fields; kind official/data_platform/research/media/upstream/input; origin is a real http(s) URL, a caller-given path, or `inline:<date>:<description>`; `published_at <= as_of`; verification read/reused/unverified; ready may not rest on unverified-only evidence.

## Validation & Error Matrix

| Situation | Required behavior |
|---|---|
| Identity/date mismatch between draft and stock | exit 2, no result |
| Non-ready status with any non-null level or valuation | rejected |
| Rounding collision or wrong level order | rejected, no auto-repair |
| ready relying on unverified-only evidence | rejected |
| Sensitive model copied with only a label change | rejected (fingerprint check) |
| Output path aliases input/stock (incl. hardlinks) | rejected, files untouched |
| Tampered result under check | exit 2 naming the JSON path that differs |
| Numeric bound exceeded (>64 digits, |exp|>100) | rejected |

## Good / Base / Bad Cases

- Good: fixture `tests/fixtures/ready.json` → 4 justified, strictly increasing prices, TTM display PE distinct from the model multiple, check replays byte-stable.
- Base: insufficient/blocked/not_applicable → all-null levels, valuation null, research preserved in analysis.
- Bad: a single present value multiplied by 0.6/0.8/1/1.2 (the baseline failure in `research/baseline.md`), star→PE mapping, special dividends annualized, negative PE display.

## Tests Required

`python -m unittest discover -s investment-analysis/stock-four-level-valuation/tests -v` (57 tests: arithmetic, rejection matrix, CLI failure paths, atomic write, deep tamper comparison, Decimal JSON-number round-trip) plus `ruff check investment-analysis/stock-four-level-valuation`. Behavior scenarios live in `evals/scenarios.md`; the offline baseline and post-skill rerun are recorded under the task's `research/`. These prove contracts and constraint behavior, not real-market valuation correctness.

## Wrong vs Correct

Wrong: generating four prices because "the math works" and labelling them "observation only". Correct: per-point parameter rationale anchored to one shared normalization anchor; without it, return insufficient_data with null levels and keep the reasoning in analysis.
