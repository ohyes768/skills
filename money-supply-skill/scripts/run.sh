#!/bin/bash
# 运行 money-supply-skill 数据抓取

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$(dirname "$SKILL_DIR")")"
MONETARY_SKILL="$PROJECT_DIR/monetary-policy-skill"

# 设置 Python 路径，包含 monetary-policy-skill/scripts（复用 fetch_common）
export PYTHONPATH="$MONETARY_SKILL/scripts:$PYTHONPATH"

# 运行
python "$SCRIPT_DIR/run_all.py" "$@"
