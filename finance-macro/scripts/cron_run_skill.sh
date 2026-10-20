#!/usr/bin/env bash
# 宏观数据采集 Skill 统一 cron 入口
#
# 被 4 个 openclaw cron job 调用（每周一北京时间 09:00-09:45 依次触发）:
#   macro-monetary-policy-weekly   → monetary-policy-skill
#   macro-money-supply-weekly      → money-supply-skill
#   macro-entity-economy-weekly    → entity-economy-skill
#   macro-inflation-weekly         → inflation-skill
#
# 用法: bash scripts/cron_run_skill.sh <skill-name> [--dry-run]
# 行为: 抓取数据 → 构建 macro_signal.json → 推送线上 macro 后端
#       全部输出写入 logs/cron/<skill>_<YYYYmmdd_HHMMSS>.log
#       退出码即 cron 判定依据（非 0 = 失败）
#
# 注意: 该脚本曾于 2026-09-22 被误删，导致 4 个 job 连续 4 周 exit=1
#       （脚本从未入库，故无法从 git 恢复）。现已重建并纳入版本管理。

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_DIR/logs/cron"
SKILL_NAME="${1:-}"
DRY_RUN="${2:-}"

if [[ -z "$SKILL_NAME" ]]; then
  echo "用法: bash $0 <skill-name> [--dry-run]" >&2
  echo "可用 skill: entity-economy-skill inflation-skill monetary-policy-skill money-supply-skill" >&2
  exit 2
fi

case "$SKILL_NAME" in
  entity-economy-skill|inflation-skill|monetary-policy-skill|money-supply-skill) ;;
  *)
    echo "未知 skill: $SKILL_NAME" >&2
    echo "可用 skill: entity-economy-skill inflation-skill monetary-policy-skill money-supply-skill" >&2
    exit 2
    ;;
esac

SKILL_DIR="$PROJECT_DIR/$SKILL_NAME"
if [[ ! -d "$SKILL_DIR" ]]; then
  echo "skill 目录不存在: $SKILL_DIR" >&2
  exit 2
fi

mkdir -p "$LOG_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_FILE="$LOG_DIR/${SKILL_NAME}_${STAMP}.log"

# ── 抓取 + 构建 + 推送 ────────────────────────────────────────────────────
# 各 skill 的 run_all.py 都支持 --upload（抓取后构建 macro_signal.json 并推送）。
# inflation-skill 的 run_all.py 内部会调用 fetch_all.py 完成实际抓取。
UPLOAD_FLAG="--upload"
if [[ "$DRY_RUN" == "--dry-run" ]]; then
  UPLOAD_FLAG=""
  echo "[dry-run] 跳过上传" >&2
fi

cd "$SKILL_DIR" || exit 1

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] >>> $SKILL_NAME 启动  (dry-run=${DRY_RUN:-no})"
  echo "    log: $LOG_FILE"
  echo "    cmd: uv run python scripts/run_all.py ${UPLOAD_FLAG}"
} > "$LOG_FILE"

START_TS=$(date +%s)

# uv run 需要在 skill 目录下执行（依赖该目录的 pyproject.toml / uv.lock）
uv run python scripts/run_all.py $UPLOAD_FLAG >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

END_TS=$(date +%s)
DURATION=$((END_TS - START_TS))

{
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] <<< $SKILL_NAME 结束"
  echo "    exit=$EXIT_CODE  duration=${DURATION}s"
} >> "$LOG_FILE"

if [[ $EXIT_CODE -ne 0 ]]; then
  echo "[$SKILL_NAME] 失败 exit=$EXIT_CODE，日志: $LOG_FILE" >&2
  tail -30 "$LOG_FILE" >&2
  exit $EXIT_CODE
fi

# 上传成功的强信号校验：日志里必须出现「上传成功」，否则视为推送未完成
if [[ -n "$UPLOAD_FLAG" ]] && ! grep -q "上传成功" "$LOG_FILE"; then
  echo "[$SKILL_NAME] 未见「上传成功」，判定推送失败，日志: $LOG_FILE" >&2
  tail -30 "$LOG_FILE" >&2
  exit 3
fi

echo "[$SKILL_NAME] 完成 exit=0，日志: $LOG_FILE"
exit 0
