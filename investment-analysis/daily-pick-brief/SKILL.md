---
name: daily-pick-brief
description: 每日财报阅读选股播报 skill。Use when Hermes/task-web 需要运行 daily_pick 选股管线（财报候选筛选、去重、钉钉推送），随后直接执行财报分析与年报行业学习两个 AI skill 完成深度分析。由 task-web 定时触发；脚本自带当日去重守卫与推送历史，不得绕过或手工改写历史文件。不适用于盘中实时选股或非财报类推荐。
---

# 每日财报阅读（daily-pick）

本 skill 是独立闭环编排：**跑选股脚本 → 读结果 → 依次执行两个 AI skill → 推送产物**。
不经 Hermes Runs API 提交分析任务（不走 hermes_client），分析由 agent 在本会话内直接完成。
agent 不重写选股逻辑、不凭记忆补充股票事实。

> 业务代码与数据在 `stock-info-dingding` 仓库（NAS 路径 `/home/ohyes768/stock-info-dingding`）。
> 本 skill 只做编排。运行副本部署在 NAS `~/.hermes/skills/daily-pick-brief/`，
> 源文件为 skills 仓库 `investment-analysis/daily-pick-brief/SKILL.md`（2026-11-07 收编进版本管理）。

## 流程

### 第 1 步：执行选股主流程（真实推送）

```bash
cd /home/ohyes768/stock-info-dingding && \
  HERMES_ENABLED=0 DAILY_PICK_ONCE_DAILY=1 PUSH_MODE=1 python3 daily_pick.py
```

- `HERMES_ENABLED=0`：关闭脚本内置的 Runs API 分析提交，改由本 skill 第 3/4 步直接执行。
- 脚本内建守卫：`DAILY_PICK_ONCE_DAILY=1` 时若 `data/daily_pick_history.json` 显示今日已推送
  → 自动跳过并输出"今日已推送 XXX"，属**正常结束**（退出码 0），不是失败。
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
cd /home/ohyes768/stock-info-dingding && python3 daily_pick.py --latest-annual <code>
```

输出「披露日 标题 PDF直链 报告期」；输出 `NO_ANNUAL_REPORT` 则跳过本步（如实转述）。
按 `annual-report-industry-learning` skill 执行，输入：年报 PDF URL。
产物 Markdown 存 `data/reports/{code}-{period}-industry-{yyyymmdd}.md`。

### 第 5 步：推送分析结果

- 每份分析完成后：摘要（第一部分/结论段）经公共 `dingtalk-push` CLI 推财报群，
  关键词「财报」必须在标题中（如「【财报分析】润建股份（002929）」「【财报行业学习】…」）。
- 全文可选推 RSS relay（source=daily-pick / annual-industry-learning，channel=caibao）。
- 第 3/4 步互不依赖：任一失败记下原因继续另一边，不影响选股主推送已成功的事实。
- 最终回复只写：选股结果 + 两个分析是否完成（失败写原因），不要粘贴全文。

## 边界

- 不得修改 SKILL.md、daily_pick.py、历史 JSON；不得额外推送第二遍。
- 分析事实只来自 skill 读到的财报原文，不得凭记忆编造财务数据。
