#!/usr/bin/env bash
cd "$(dirname "$0")/.." && uv run scripts/fetch_all.py "$@"
