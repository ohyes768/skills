---
name: daily-pick-brief
description: 每日财报阅读选股播报 skill。Use when Hermes/task-web 需要运行 daily_pick 选股管线（财报候选筛选、去重、钉钉推送），随后直接执行财报分析与年报行业学习两个 AI skill 完成深度分析。由 task-web 定时触发；脚本自带当日去重守卫与推送历史，不得绕过或手工改写历史文件。不适用于盘中实时选股或非财报类推荐。
---

# 每日财报阅读（daily-pick）

本 skill 是**自包含独立闭环**：选股脚本在本 skill 的 `scripts/` 里，数据在本 skill 的
`data/` 里，不依赖 stock-info-dingding 仓库。流程：**跑选股脚本 → 读结果 → 依次执行
两个 AI skill → 推送产物**。不经 Hermes Runs API 提交分析任务，分析由 agent 在本会话
内直接完成。agent 不重写选股逻辑、不凭记忆补充股票事实。

> 运行副本：NAS `~/.hermes/skills/daily-pick-brief/`（脚本/数据/配置全在此）。
> 源文件：skills 仓库 `investment-analysis/daily-pick-brief/`（SKILL.md + scripts/ +
> tests/ + data/，2026-11-08 自 stock-info-dingding 迁入）。
> 运行环境：python3 + pandas + akshare（可复用 task-web 的 stock-info:latest 镜像挂载本目录）。
> `.env`（不入 git）放本目录，至少含 `DAILY_PICK_WEBHOOK`（财报群机器人）。

## 目录契约

```
daily-pick-brief/
├── SKILL.md                     # 本文件（编排剧本）
├── scripts/daily_pick.py        # 选股主脚本（含 --latest-annual 辅助入口）
├── scripts/dingtalk_push.py     # 钉钉发送（委托公共 dingtalk-push CLI）
├── scripts/sw_industry_mapping.csv  # 申万行业映射基础数据
├── data/daily_pick_history.json # 推送历史（脚本维护，agent 不得手改）
├── data/reports/                # AI 分析产物落盘处
└── .env                         # DAILY_PICK_WEBHOOK 等（不入 git）
```

## 流程

### 第 1 步：执行选股主流程（真实推送）

```bash
cd ~/.hermes/skills/daily-pick-brief && \
  HERMES_ENABLED=0 DAILY_PICK_ONCE_DAILY=1 PUSH_MODE=1 python3 scripts/daily_pick.py
```

- `HERMES_ENABLED=0`：显式声明不走 Runs API（脚本已无该链路，此为防御性守卫）。
- 脚本内建守卫：`DAILY_PICK_ONCE_DAILY=1` 时若 `data/daily_pick_history.json` 显示今日
  已推送 → 输出"今日已推送 XXX"并正常退出（退出码 0），不是失败。
- 去重与推送历史由脚本维护（推送成功才落盘），agent 不得手工编辑历史文件。

### 第 2 步：读取选股结果

推送成功后，从 `data/daily_pick_history.json` 最后一条记录取：
`code`（股票代码）、`name`（名称）、`latest_report_url`（格式为「公告标题 公告URL」，
从中解析出报告期，如 `2026年三季度报告` → `2026-09-30`）。
「今日已推送/无可推荐」则如实转述后结束，不执行第 3/4 步。

### 第 3 步：财报分析（AI skill：financial-statement-analysis）

按 `financial-statement-analysis` skill 执行，输入：股票代码 + 报告期。
产物 Markdown 存 `data/reports/{code}-{period}-fsa-{yyyymmdd}.md`。

### 第 4 步：年报行业学习（AI skill：annual-report-industry-learning）

先查年报公告：

```bash
cd ~/.hermes/skills/daily-pick-brief && python3 scripts/daily_pick.py --latest-annual <code>
```

输出「披露日 标题 PDF直链 报告期」；输出 `NO_ANNUAL_REPORT` 则跳过本步（如实转述）。
按 `annual-report-industry-learning` skill 执行，输入：年报 PDF URL。
产物 Markdown 存 `data/reports/{code}-{period}-industry-{yyyymmdd}.md`。

### 第 5 步：推送分析结果

- 每份分析完成后：摘要（第一部分/结论段）经公共 `dingtalk-push` CLI 推财报群，
  关键词「财报」必须在标题中（如「【财报分析】润建股份（002929）」「【财报行业学习】…」）。
- 第 3/4 步互不依赖：任一失败记下原因继续另一边，不影响选股主推送已成功的事实。
- 最终回复只写：选股结果 + 两个分析是否完成（失败写原因），不要粘贴全文。

## 边界

- 不得修改 SKILL.md、daily_pick.py、历史 JSON；不得额外推送第二遍。
- 分析事实只来自 skill 读到的财报原文，不得凭记忆编造财务数据。
