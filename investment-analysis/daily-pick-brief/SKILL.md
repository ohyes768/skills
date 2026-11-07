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

## 运行时与迁移坑位（2026-11-07 实测）

### 路径契约：`.env` 与 `data/` 在 skill 根目录，不在 `scripts/` 下

脚本用 `Path(__file__).resolve().parent` 定位时会把 `.env`、`data/` 当成 `scripts/` 的子目录。
目录契约是 skill 根目录持有 `.env` + `data/`，`scripts/` 下只有脚本与 CSV。
正确写法是 `_skill_dir = Path(__file__).resolve().parent.parent`，
`HISTORY_PATH` 与 `.env` 都锚到 `_skill_dir`；`sw_industry_mapping.csv` 仍锚 `scripts/`。

**症状**：webhook 读不到 → 报「webhook 未配置或不是 http(s) 完整 URL」；
历史文件不存在 → 按空历史运行 → `DAILY_PICK_ONCE_DAILY=1` 守卫失效，有重复推送风险。

### 缺 `import requests` 会伪装成「无可推荐」

`requests` 只在函数体内调用而没有顶层导入时，三处 HTTP 调用（人气榜 / 腾讯行情 / 东财公告）
抛 `NameError`，被 `run_pipeline` 的 `except Exception` 捕获后 `return None, ...`。
**表面上是一条正常的「今日无可推荐」，实际是拉数据全失败。**
判断方法：日志里若同时出现 `拉取数据失败` 且选股为空，先查依赖导入，不要当成真的没有推荐。

### 宿主 python3 没有 akshare，必须用 stock-info 镜像

宿主机 `python3`（3.11）无 `akshare`；`stock-info:latest` 镜像内有 `akshare 1.20.35`。
选股主流程需在镜像内跑：

```bash
docker run --rm --network nginx_nginx-bridge \
  -v ~/.hermes/skills/daily-pick-brief:/skill \
  -v ~/skills/personal-tools/dingtalk-push:/opt/dingtalk-push:ro \
  -v ~/.local/state/dingtalk-push:/state \
  -v <摘要目录>:/digests:ro \
  -e DINGTALK_PUSH_SKILL_DIR=/opt/dingtalk-push \
  -e DINGTALK_PUSH_STATE_DIR=/state \
  -w /skill stock-info:latest python3 scripts/daily_pick.py
```

### 钉钉回执库是容器 root 所有，宿主 CLI 写不进去

`~/.local/state/dingtalk-push/receipts.sqlite3` 由容器内 root 创建，
宿主直接跑 `dingtalk_send.py` 会报 `OperationalError: attempt to write a readonly database`。
推摘要也在容器内做（webhook 经 `--env-file` 传入，**绝不放 argv**）。

### 摘要推送的 webhook 环境变量名不一致

`.env` 里是 `DAILY_PICK_WEBHOOK`，公共 CLI 认 `DINGTALK_WEBHOOK`。
容器内用 `--env-file`（文件里写 `DINGTALK_WEBHOOK=...`）传入，避免命令行泄露。

### 标题必须含关键词「财报」

机器人安全设置是自定义关键词，标题与正文都要覆盖。
主推送标题 `【财报阅读】…`；两个摘要分别是 `【财报分析】…`、`【财报行业学习】…`。

## 两个 AI skill 的验收口径

- `financial-statement-analysis`：以 `run_pipeline.py report --independent-review` 返回
  `quality_status=verified` + `terminal=true` 为完成标志。定性段落**禁止出现任何数字**
  （含静态数字，只有 statement/table 能放数字）；且不得写「利润主要来自…」
  「同比改善的主要驱动…」「确认转固」这类未获支持的归因，验收器会直接拦截。
  `## 核心结论` 句子数 = statements 数 + 定性段落句数，须落在 3–5（4 条 statement 时定性段落只能 1 句）。
- `annual-report-industry-learning`：摘要 1,200–1,600 字（硬上限 1,800），
  六节软预算用 `assemble_report.py` 检查；原文部分不受字数限制，
  正文里不能出现 `【PDF 第 N 页】` 内联标记，页码放元数据或小节标题。
