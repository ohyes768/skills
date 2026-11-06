#!/bin/bash
# csi300-brief 每交易日盘后推送钉钉。
# 时间：北京时间 16:35（数据管线 16:30 入库；服务器若是 UTC，crontab 写 08:35）。
# 用法：bash scripts/cron_daily.sh     日志落在本 skill 的 logs/ 下。
set -u
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${CSI300_LOG_DIR:-$SKILL_DIR/logs}"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/csi300-brief.log"

cd "$SKILL_DIR" || exit 1
{
  echo "=== $(TZ=Asia/Shanghai date '+%F %T %Z') ==="
  python3 scripts/brief.py --push --insecure --only-today
  echo "exit=$?"
} >>"$LOG_FILE" 2>&1
exit 0
