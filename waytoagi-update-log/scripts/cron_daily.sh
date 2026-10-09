#!/bin/bash
# WaytoAGI 每日更新推送 - 定时脚本
# 仅在有数据时推送钉钉

SKILL_DIR="$HOME/.openclaw/workspace/skills/waytoagi-update-log"

# 读取 .env 中的 DINGTALK_WEBHOOK（避免 token 入 git）
if [ -f "$SKILL_DIR/.env" ]; then
  set -a
  . "$SKILL_DIR/.env"
  set +a
fi

WEBHOOK="${DINGTALK_WEBHOOK:-}"

# 昨天日期（如 5月6日）
YESTERDAY=$(date -d "yesterday" +"%-m月%#d日")

# 抓取主文档（固定 obj_token）
WIKI_TOKEN="NDsAdX4spozsglxgqm7caJqdnVf"
CONTENT=$(curl -s "https://open.feishu.cn/open-apis/wiki/v2/spaces/get_node?token=QPe5w5g7UisbEkkow8XcDmOpn8e" \
  -H "Authorization: Bearer $(cat $SKILL_DIR/.token 2>/dev/null)" 2>/dev/null)

# 生成报告（调用 Node 脚本处理 + 推送）
if [ -z "$WEBHOOK" ]; then
  echo "错误: WEBHOOK 未配置，请检查 $SKILL_DIR/.env 中是否设置了 DINGTALK_WEBHOOK" >&2
  exit 1
fi

node "$SKILL_DIR/scripts/cron_runner.js" "$YESTERDAY" "$WEBHOOK"
