#!/usr/bin/env bash
# risk-appetite-skill 运行脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

cd "$SKILL_DIR" || exit 1

# 使用 uv 运行
uv run python scripts/run_all.py "$@"
