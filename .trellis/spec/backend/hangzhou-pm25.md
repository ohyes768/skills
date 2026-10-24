# Hangzhou PM2.5 contracts

## 1. Scope / Trigger

Applies to `environment/hangzhou-pm25/`, its public-data adapters, JSON consumer contract and Skill. New sources or alternate aggregation must preserve observation/model and hourly/daily boundaries.

## 2. Signatures

```text
python environment/hangzhou-pm25/scripts/hangzhou_pm25.py
  [--days {1,2,3,4,5}] [--format {markdown,json}]
  [--output-dir DIR] [--save-input FILE] [--input FILE] [--now ISO_WITH_OFFSET]
```

`providers.fetch_snapshot(days=5)` fetches CNEMC, CAMS and weather concurrently. `report.build_report(snapshot, now=None, days=5)` is pure with an injected clock; `render_markdown(report)` consumes that same JSON contract. No third-party runtime dependency, API key, installation or push is implied.

## 3. Contracts

- Reference point is 30.2741,120.1551; station sample radius is 25 km. CNEMC `PM2_5` is concentration, `TimePointStr` is the Shanghai observation hour. Select only the latest valid nonfuture hour and deduplicate station codes before averaging. The mean is self-computed, never the official city mean. Observations older than 3 hours are stale. A current model fallback must be within the prior 2 hours and explicitly typed `model_estimate`.
- Snapshot keys: `fetched_at`, `observations` (Hangzhou rows only), `air`, `weather`, `errors`. ISO timestamps carry an offset except the provider's local hourly labels, which require `timezone=Asia/Shanghai`.
- Schema version 1 includes `generated_at`, `input_fetched_at`, `current`, `observations`, `daily`, `trend`, `warnings`, `limitations`, `attribution`, `sources`. `sources.model_initialization_time` stays null unless a provider actually supplies a verifiable value.
- `daily` always includes every requested Shanghai calendar date including today. Zero concentration is valid; invalid/missing values are null. `valid_hours` counts valid hourly values, `complete` requires 24, `mean_pm25` averages only valid hours. Today's whole-day model aggregate includes elapsed hours; `remaining_mean_pm25` uses future hourly labels only.
- Weather has per-variable counts independent of pollutant coverage. Use speed-weighted circular wind direction, and overlapping hours for joint humidity/calm or low-boundary-layer/calm signals. Weather rules explain possible conditions and never alter CAMS concentrations.
- Do not calculate composite AQI or grades in this version. Do not silently reuse stale cache. Keep TLS certificate verification and provider attribution. Open-Meteo free service is for noncommercial use.

## 4. Validation & Error Matrix

| Condition | Behavior |
|---|---|
| `0` concentration | Keep as a valid numeric value |
| negative, NaN, infinity, boolean, missing sentinel | Normalize to null |
| wrong units/timezone, unequal arrays, duplicate/non-hourly timestamps | Reject that hourly provider; retain others and warn |
| stale/unavailable observations | Historical detail or absent; current uses labeled fresh model fallback if available |
| provider HTTP, socket or `HTTPException` failure | At most two attempts for transient errors; isolate the failed source |
| future date/tail has missing hours | Preserve row and valid count; never fill with zero or imply complete daily mean |
| some PM2.5 usable | Exit 0, status `ok` or `partial` |
| all PM2.5 unavailable | Emit report, exit 1, status `unavailable` |
| malformed replay/file/CLI input; naive clock; live `--now` | Clean diagnostic, exit 2 |

## 5. Good / Base / Bad Cases

- Good: latest-hour urban station mean plus five CAMS dates and weather; preserve every source and its time.
- Base: fifth date has 21 valid hours; report partial, and label the effective-hours mean.
- Bad: observations fail or are stale, then label a model estimate as measured current air. Also bad: one truncated HTTP body prevents healthy sources from producing a report.

## 6. Tests Required

Run `python -m unittest discover -s environment/hangzhou-pm25/tests -v`, `python -m ruff check environment/hangzhou-pm25`, and the skill validator with UTF-8 mode on Windows. Assertions cover missing/zero, station geography/latest-hour deduplication/freshness, day rollover and coverage, units/timezone, circular wind, concurrent-hour rules, source isolation including `IncompleteRead`, offline CLI outputs and outage exit codes. Real-API acceptance must inspect JSON and Markdown; it is not a forecast-accuracy backtest.

## 7. Wrong vs Correct

Wrong: `mean = sum(v or 0 for v in values) / 24`; "7-day parameter accepted, therefore all days are valid"; `except OSError` alone for HTTP body reads.

Correct: retain only finite nonnegative numbers, count the valid hours and mark partial dates; verify actual source horizon; catch `http.client.HTTPException` as well as socket/URL errors so `IncompleteRead` cannot destroy other provider results.
