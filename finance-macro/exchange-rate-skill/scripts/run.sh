#!/bin/bash
# 运行 exchange-rate-skill 所有数据获取脚本

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# 使用项目虚拟环境
if [ -d ".venv" ]; then
    source .venv/Scripts/activate
fi

# 运行数据获取脚本
python scripts/run_all.py
