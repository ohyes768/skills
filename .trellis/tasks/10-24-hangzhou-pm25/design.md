# Hangzhou PM2.5 design

## Scope and authorization

The user approved implementation on 2026-10-24 ("开干"). Default to a Hangzhou urban reference point at 30.2741, 120.1551 and five Shanghai calendar dates including today. No deployment, scheduling, or Git commit is requested.

## Components

Create `environment/hangzhou-pm25/`: `scripts/providers.py` owns public HTTP requests, timestamps, concentration validation, and CNEMC station normalization; `scripts/report.py` owns hourly aggregation and evidence-based Chinese reporting; `scripts/hangzhou_pm25.py` is the CLI. `SKILL.md` documents invocation and interpretation. `references/data-sources.md` records sources, caveats, and thresholds. Tests use the standard library and synthetic responses; no installed third-party dependencies are required (Python 3.10+).

## Data flow

Fetch three public resources concurrently with a timeout and one retry: CNEMC `POST https://air.cnemc.cn:18007/HourChangesPublish/GetAllAQIPublishLive` (empty read-only query body), Open-Meteo air quality (`cams_global`, hourly PM2.5, five dates, Shanghai), and Open-Meteo weather (temperature, humidity, precipitation, wind speed/direction, boundary layer height; wind in m/s). Keep TLS verification enabled. Retain only Hangzhou station rows in saved input. No API key is required.

The CNEMC endpoint was verified live with normal TLS verification on 2026-10-24. It returns station rows containing `Area`, `CityCode`, `TimePointStr`, `PM2_5`, coordinates and station identity. Parse `TimePointStr` as Shanghai local observation hour. Filter the urban sample to 25 km around the reference point, use the latest valid non-future observation hour, and report individual stations, count and range. Its arithmetic mean is a self-computed nearby-station mean, never an official city mean. Missing, negative, nonfinite and nonnumeric concentrations are absent; zero is valid. More than three hours old is stale and cannot be presented as current. A model estimate at the latest available hour at or before now (at most two hours old) is the explicitly marked fallback. Stale observations remain available as historical context.

## Output contract

JSON carries schema version, generated time, timezone, point, status (`ok`, `partial`, `unavailable`), current measurement/estimate, observation detail, daily aggregates, source timestamps, warnings and attribution. Forecast days include date, valid/expected hours, valid start/end, full-day model mean/peak, remaining-hour mean for today, and weather summaries with per-variable counts. All dates mean calendar dates including today, not a rolling 120 hours. Keep model values earlier today explicitly labeled; missing future hours are not zero. Every requested date has a row even when all data are absent.

Only compare daily model means when each has at least 18 hours, and label partial days. Report no synthetic probability or calibrated uncertainty. Do not calculate AQI or apply a PM2.5 pollution grade in v1; raw concentration and trend fulfill the request without confusing hourly values, daily standards, or composite AQI. Day-to-day direction is a descriptive model comparison, not a new prediction model.

Weather is explanatory context, never an extra arbitrary multiplier on CAMS. Count overlapping high-humidity/low-wind and low-boundary-layer/low-wind hours. Rain and stronger wind are conditional dispersion signals; wind direction alone never decides quality, and inversion or regional transport cannot be diagnosed from these inputs. Include numeric supporting evidence. Thresholds are transparent qualitative heuristics, not health thresholds or fitted forecasts. Missing weather fields produce explicit missing counts rather than implied favorable conditions.

## CLI and failures

Default stdout is Chinese Markdown. `--format json` returns machine-readable JSON; `--output-dir` writes report.json and report.md, and `--save-input` writes a replay snapshot. `--input` replays a snapshot offline; optional `--now` is replay-only and must carry a timezone. `--days` accepts 1–5. Network failure of one provider preserves the others and emits warnings. No automatic stale cache fallback. Nonzero exit code only when neither a current value nor any forecast PM2.5 is available, or input/CLI is invalid. An unavailable report is still emitted for network outages. Runtime outputs stay outside source unless explicitly requested.

## Verification and limits

Tests cover zero versus missing, future/stale observations, latest-hour station selection, radius filtering, daily coverage, all-missing dates, cross-midnight times, wind-direction wraparound, missing weather, fallback and complete provider failure, plus CLI offline execution and output files. A live end-to-end run must verify both JSON and readable Chinese output and capture its actual coverage. CAMS is a coarse regional model, not street-level exposure; this version does not claim local forecast skill or calibrated confidence. Free Open-Meteo is for noncommercial use and requires attribution to Open-Meteo and CAMS.
