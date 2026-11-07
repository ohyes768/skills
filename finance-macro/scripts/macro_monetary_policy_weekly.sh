#!/usr/bin/env bash
export PATH="$HOME/.hermes/bin:$PATH"
# Hermes cron 包装入口（jobs.json script 指向 ~/.hermes/scripts/ 同名文件）
# 真实实现：finance-macro cron_run_skill.sh（抓取→macro_signal.json→推送 personal-web）
exec bash /home/ohyes768/skills/finance-macro/scripts/cron_run_skill.sh monetary-policy-skill "$@"
