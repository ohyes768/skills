# Bilibili subtitle RSS implementation plan

**Goal:** Create a reusable skill that extracts timestamped Bilibili subtitles with the user-selected pinned CLI and publishes Markdown to the existing RSS Relay.

**Architecture:** A standard-library Python helper resolves BV/video/b23 links, invokes the pinned CLI with `--subtitle-timeline --json`, validates the schema and renders complete subtitles. Explicit `--push` checks recent remote posts and local receipts before submitting. No changes to personal-web.

**Tech stack:** Python 3.10+, uvx, bilibili-cli commit 6962d5b, urllib, unittest.

- [x] Add failing tests for URL handling, the CLI envelope, missing/malformed subtitles, safe full-text rendering, duplicate checks, and publishing failure.
- [x] Implement `bilibili-subtitle-rss/scripts/subtitle_rss.py` and run tests (11 passed).
- [x] Write `SKILL.md` and UI metadata; validate the skill (`Skill is valid!`).
- [x] Extract the sample video, inspect the generated document, publish once and verify the returned post through the list API. Check a second invocation skips the existing post. All 504 segments rendered; remote body equals local Markdown. Both local-receipt and remote-list duplicate detection verified.
- [x] Install the validated skill in the user's Codex skills directory without replacing an existing installation. Created a junction to the repository source.

**Live verification:** Post `20261008-174655-c21abf`, video `BV1dnbV6TEMy`. No changes to personal-web. No commits or pushes performed.

**Known constraints:** The pinned CLI always uses `pages[0]`; reject `p > 1` rather than publish the wrong subtitles. Remote duplicate detection is limited to the latest 200 retained posts; local receipts supplement it. The server does not provide atomic idempotency across machines. Do not automatically retry an ambiguous POST failure. Existing login credentials are used by the CLI; never copy them into the skill. Missing subtitles do not trigger ASR or summaries.
