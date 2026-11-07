# RSS Relay Publication

## 1. Scope / Trigger

Apply when adding an RSS producer or changing the common package at `knowledge/rss-relay-publish`. Business code owns final Markdown, authorization, timing, channel, source and identity. Shared transport owns publication and confirmation. Do not create another HTTP publisher for new features.

## 2. Signatures

```text
python <package>/scripts/rss_publish.py publish --file <path-or-dash> --title <title> --channel <channel> --source <source> --dedupe-key <key>
```

Optional: `--url`, `--dry-run`, `--base-url`, `--state-dir`, `--timeout`, `--ca-file`, `--insecure`. `--file -` reads UTF-8 stdin. Python 3.10+, standard library only. Existing consumers may retain compatibility wrappers that invoke this CLI using argv and byte stdin, without a shell.

## 3. Contracts

- POST fields: title/content/channel/source/url. Never send a fictional server-side dedupe-key or inject it into content/source/url.
- Receipt identity: normalized API base + channel + source + caller key. Digest covers all five payload fields. SQLite state is outside the installed package; `pending` is committed before POST, `confirmed` after readback. Upgrades preserve it.
- Configuration: CLI > RSS_RELAY_BASE_URL/STATE_DIR/TIMEOUT/CA_FILE > defaults. RSS_RELAY_SKILL_DIR locates the package for compatibility shims. Explicit legacy endpoints override the public base setting.
- Default base: `https://web.duomi77.cn:9443/rss/api/rss-relay`; internal base may be `http://host:8099/api`. Never infer one endpoint from unrelated project paths.
- TLS verification is default; all requests use the same transport context. No implicit insecure fallback or subscription token lookup.
- Output: one JSON object with schema_version=1, status, id, detail_url, verified, verification, error. Diagnostics belong on stderr. Help is conventional argparse text.
- `verified=true` requires current full id and five-field readback. Preserve transmitted line endings; allow only CRLF/CR-to-LF equivalence in remote content verification because the relay's text storage normalizes them.
- Current backend has no idempotency key, retains 15 days, lists at most 200 articles without pagination. Independent state directories cannot guarantee global exactly-once delivery.

## 4. Validation & Error Matrix

| Situation | Status / exit | Effect |
|---|---|---|
| Valid preview | preview / 0 | No POST, GET or receipt write |
| New write verified | published / 0 | Persist confirmed receipt |
| Existing confirmed identity | duplicate / 0 | Historical evidence; no repost |
| Unique full remote match and readback | duplicate / 0 | Current verification, adopt receipt |
| Same identity, different payload | conflict / 4 | No POST |
| Invalid input, unavailable state or preflight | failed / 2 | No POST; release owned preflight claim when safe |
| Explicit POST rejection (known nonacceptance HTTP code) | failed / 2 | Release claim for corrected retry |
| Timeout, truncated response, malformed success, 5xx, ambiguous matches or readback mismatch | unknown / 3 unless recovered | Retain pending; GET-only recovery |

HTTP errors from readback must never be mistaken for POST rejection. Catch `http.client.HTTPException`, including `IncompleteRead`, as well as URL/OS and JSON errors. Crash leftovers do not expire into automatic repost permission.

## 5. Good / Base / Bad Cases

- Good: `daily:2026-11-05`, same payload and external state on retry. Intentional revision uses stable `:v2` and visible revision content/title.
- Base: local receipt says an article was published previously; return historical duplicate even if retention has since removed it.
- Bad: changing key after unknown, deleting pending on readback 404, deduping globally on title, using different state directories for concurrent copies of the same producer.

## 6. Tests Required

Use local fake HTTP servers and temporary state. Cover id/full-content confirmation, source/channel namespaces, key conflicts, same-key concurrency, crash pending recovery, lost/truncated/malformed POST response, explicit rejection, 404 readback, ambiguous remote matches, unwritable state, dry-run, preserved CRLF and package upgrade receipt retention. Execute core tests on Windows and Linux.

Migration tests must exercise business entry -> compatibility shim -> subprocess CLI -> fake relay. Preserve validators, old outputs and business receipts; macro duplicates must still allow dashboard retry. Serialize WaytoAGI read/merge/replace under its SQLite lock, not just atomic file replacement. Canonical shim is `scripts/rss_relay_client.py`; `scripts/sync_shims.py` propagates it to every consumer (including sibling projects outside the repo), `tests/test_clients.py` verifies byte equality, and the repo pre-commit hook (githooks/) rejects commits with drifted copies.

## 7. Wrong vs Correct

Wrong: `except HTTPError: delete_pending()` around both POST and readback; a readback 404 can make an accepted write eligible for duplicate delivery.

Correct: distinguish whether POST already returned, retain accepted/uncertain identities, and recover with GET only. Report unknown when evidence is insufficient. Existing wrappers may convert public duplicate=0 to legacy duplicate=3, but cannot bypass the public receipt protocol.
