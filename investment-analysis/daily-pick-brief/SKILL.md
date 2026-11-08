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

### 第 5 步：全文进 RSS，钉钉只推摘要 + 链接

两份分析用**同一套投递契约**，顺序固定为**先 RSS、后钉钉**。钉钉群只承载摘要，
全文一律落到 RSS 详情页，由「阅读完整分析」链接进入。

1. **先把全文发布到 RSS relay**（`channel=caibao`、`source=daily-pick`）：

   ```bash
   python3 ~/skills/knowledge/rss-relay-publish/scripts/rss_publish.py publish \
     --file data/reports/<code>-<period>-<fsa|industry>-<yyyymmdd>.md \
     --title '<名称> <报告期> 财报分析|行业学习' \
     --channel caibao --source daily-pick \
     --dedupe-key 'daily-pick:<code>:<period>:<fsa|industry>:<yyyymmdd>' \
     --url '<该期报告 PDF 直链>'
   ```

   读 stdout JSON：`status` 为 `published`/`duplicate` **且 `detail_url` 非空**才算成功，
   记下 `detail_url`（`https://web.duomi77.cn:9443/rss/view/<id>`，15 天有效）。
   首次接新环境先加 `--dry-run` 确认 payload，再正式发。
   本部署是**自签证书**：不带 `--insecure` 会在预检阶段报
   `failed / preflight_failed / Could not read remote posts`（TLS 校验失败，实际一篇都没发）；
   有正式 CA 时才改用 `--ca-file`。

2. **钉钉只推摘要**，正文按模板拼，**不要自由发挥首行与排版**：

   ```markdown
   ### 📊 AI 财报分析：{名称}（{报告期}）

   {摘要}

   [阅读完整分析]({detail_url})
   ```

   行业学习把首行换成 `### 📚 AI 财报行业学习：{名称}（{报告期}）`，
   链接文案换成 `[阅读完整学习]({detail_url})`，其余结构相同。

   - 财报分析摘要 = 报告里第一个 `## 核心结论` 到下一个 `## ` 之间的原文（通常 4–5 条、
     约 400–600 字）；没有该标题时取报告开头 300 字。**照抄原文**，不改写不压缩。
   - 行业学习摘要 = 把「第一部分：AI 行业学习摘要」压成 4 段，
     **正文 300–450 字（硬上限 450）**。超过就继续删，钉钉上没人读得完 1,700 字。
     四段固定顺序，每段 1–2 句：
     1. 赛道：处于哪几条产业链，共同下游，当下增量最集中的方向；
     2. 壁垒：先进工艺产能、垂直一体化、客户结构各一句；
     3. 行业变化：市场规模与增速（数字一律照搬摘要，不许改口径或换算）；
     4. 风险：1–2 句，写传导路径（外部条件 → 承压环节 → 结果）。
     压缩只允许「删句 + 重组已有句子」，不得引入摘要里没有的事实、不得新增数字。
     示例（东山精密 2025 年报，约 340 字）：

     > 同时押注四条产业链：PCB、光模块与光芯片、精密组件、光电显示模组，共同下游是消费电子、汽车、数据中心与通信设备，增量最集中在 AI 算力基础设施。
     >
     > 壁垒在三点：78 层以上超高多层与 7 阶 HDI 的先进产能；收购索尔思后成为全球唯一具备 PCB＋光芯片＋光模块全流程能力的企业；客户覆盖前五大消费电子品牌中的四个、前五大云厂商中的四个，早期即参与产品定义。
     >
     > 行业变化：2025 年全球 PCB 产值 852 亿美元、同比增约 16%，2029 年有望超 1,160 亿；2026 年数通光模块 228 亿美元，800G/1.6T 占约 64%，电信侧仅 53 亿。
     >
     > 风险：客户集中度高、技术迭代跟不上即被淘汰、出口占比高受贸易摩擦影响。
   - 链接行独占正文最后一行：财报分析 `[阅读完整分析]({detail_url})`，
     行业学习 `[阅读完整学习]({detail_url})`；
     RSS 失败或没拿到 `detail_url` 时一律退化为 `[财报原文]({PDF 直链})`。
   - 推送标题：`【财报分析】{名称}（{代码}）` / `【财报行业学习】{名称}（{代码}）`。

3. **不得把全文塞进钉钉**：钉钉 markdown 单条有长度上限，`industry-learning.md`
   约 50KB（摘要 + 所引原文全文），直推会截断或整条失败。全文只有第 1 步一个出口。
   标题必须含关键词「财报」（「【财报分析】…」「【财报行业学习】…」），否则 `--keyword` 预检直接拦。

- 第 3/4 步互不依赖：任一失败记下原因继续另一边，不影响选股主推送已成功的事实。
- 最终回复只写：选股结果 + 两个分析是否完成 + 各自的 `detail_url`（失败写原因），不要粘贴全文。

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
