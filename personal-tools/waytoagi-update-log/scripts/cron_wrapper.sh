#!/bin/bash
# WaytoAGI 每日推送 - Cron 触发器
# 每天 8:50 执行，通过 openclaw 触发 agent session

OPENCLAW_BIN="${HOME}/.npm-global/bin/openclaw"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 加载 .env 中的 DINGTALK_WEBHOOK（避免 token 入 git）
if [ -f "$SKILL_DIR/.env" ]; then
  set -a
  . "$SKILL_DIR/.env"
  set +a
fi

# 检查 openclaw 是否可用
if ! command -v openclaw &>/dev/null; then
  echo "openclaw not found"
  exit 1
fi

if [ -z "$DINGTALK_WEBHOOK" ]; then
  echo "错误: DINGTALK_WEBHOOK 未配置，请检查 $SKILL_DIR/.env" >&2
  exit 1
fi

# 触发 agent 执行 skill
openclaw exec "
请执行 waytoagi-update-log skill，查询昨天的更新日志（5月6日），
如果有文章则发送到钉钉：${DINGTALK_WEBHOOK}
如果没有文章则静默退出不发送。
" 2>&1
