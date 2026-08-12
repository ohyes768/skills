# 个人 Skill 库

统一管理个人 agent skill 的仓库。Skill 分两大类，统一通过 [registry.json](registry.json) 维护清单和各 agent 的安装配置：

- **自研 skill**（`source: local`）：自己开发维护，按主题目录存放在本仓库；
- **外部 skill**（`source: github`）：来自 GitHub 上的 skill 仓库，本仓库只记录链接与安装分配，不存代码。

## 目录结构

```
finance-macro/        # 金融宏观分析（8 个）
dev-workflow/         # 开发工程（5 个）
agent-methods/        # Agent 方法论（5 个）
design/               # UI/UX 设计（1 个）
knowledge/            # 知识管理（1 个）
scripts/              # 维护脚本（sync_github_versions.py 刷新外部 skill 版本）
registry.json         # skill 注册表 + agent 安装配置（唯一事实来源）
README.md
```

## 主题分类索引

以下为自研 skill（`source: local`），按主题分类。

### 金融宏观分析 `finance-macro/`

| Skill | 说明 | 状态 |
|---|---|---|
| [a-share-macro-skill](finance-macro/a-share-macro-skill) | A股宏观环境综合评估（编排器，依赖下方 6 个子 skill） | active |
| [bond-market-overview-skill](finance-macro/bond-market-overview-skill) | 债市宏观环境综合评估（编排器，依赖下方 6 个子 skill） | active |
| [monetary-policy-skill](finance-macro/monetary-policy-skill) | 货币政策松紧分析（DR007/LPR/MLF） | active |
| [money-supply-skill](finance-macro/money-supply-skill) | 货币供应与流动性（M1/M2/社融） | active |
| [entity-economy-skill](finance-macro/entity-economy-skill) | 实体经济强弱判断（PMI/固投/社零） | active |
| [inflation-skill](finance-macro/inflation-skill) | 通胀分析（CPI/PPI/核心CPI） | active |
| [risk-appetite-skill](finance-macro/risk-appetite-skill) | 市场风险偏好（成交额/换手率/两融） | active |
| [exchange-rate-skill](finance-macro/exchange-rate-skill) | 汇率与资金流向（美元指数/TED利差） | active |

> 两个编排器 skill 需与其依赖的 6 个子 skill 一起安装才能完整运行。

### 开发工程 `dev-workflow/`

| Skill | 说明 | 状态 |
|---|---|---|
| [git-commit-push](dev-workflow/git-commit-push) | 自动生成规范 commit message 并推送 | active |
| [update-doc](dev-workflow/update-doc) | 根据改动自动更新相关文档 | active |
| [python-venv](dev-workflow/python-venv) | Python 虚拟环境初始化 | active |
| [docker-cn-source](dev-workflow/docker-cn-source) | Docker 国内镜像源配置 | active |
| [windows-bat-dev](dev-workflow/windows-bat-dev) | Windows 批处理脚本最佳实践 | active |

### Agent 方法论 `agent-methods/`

| Skill | 说明 | 状态 |
|---|---|---|
| [think-skill](agent-methods/think-skill) | 深度分析模式（/think） | active |
| [ask-me](agent-methods/ask-me) | 任务前深度访谈消除歧义 | active |
| [skill-creator](agent-methods/skill-creator) | 创建/改进/评测 skill | active |
| [find-skills](agent-methods/find-skills) | 发现并安装 agent skill | active |
| [claudeception](agent-methods/claudeception) | — | empty（待补充） |

### UI/UX 设计 `design/`

| Skill | 说明 | 状态 |
|---|---|---|
| [ui-ux-pro-max](design/ui-ux-pro-max) | 设计智能：67 风格/96 配色/57 字体搭配/13 技术栈 | active |

### 知识管理 `knowledge/`

| Skill | 说明 | 状态 |
|---|---|---|
| [notes-deal](knowledge/notes-deal) | 浏览器采集知识点的自动分类整理 | active |

## 外部 skill（GitHub）

来自外部 GitHub skill 仓库（`source: github`），安装时直接从远程仓库拉取。[registry.json](registry.json) 中对应条目包含 `repo`（仓库地址）和可选 `path`（skill 目录在仓库中的子路径），以及 `latest_version` / `head_commit` / `checked_at`（最新远程版本快照）。

| Skill | 来源仓库 | 最新版本 | 检查日期 | 主题 | 说明 | 安装到 |
|---|---|---|---|---|---|---|
| UZI-Skill | [wbh604/UZI-Skill](https://github.com/wbh604/UZI-Skill) | v3.9.1 | 2026-08-12 | 量化股票分析 | 游资（UZI）A股/港股/美股分析：22维数据×180条量化规则×17种机构分析方法 | — |

**刷新远程版本**：运行 `python scripts/sync_github_versions.py`（可加 `--dry-run` 只看不写）。脚本对每个 github skill 执行 `git ls-remote`（不走 GitHub REST API、无需 token），取最新 tag 回填 `latest_version`/`head_commit`/`checked_at`，并打印版本变化；无 tag 的仓库以 `HEAD@<短commit>` 记录。刷新后请同步更新上表的「最新版本/检查日期」列。

## Agent 安装配置

以 [registry.json](registry.json) 的 `agents` 字段为准。agent 安装 skill 时：读取 `agents.<agent名>.skills` 中的 skill 名称列表 → 在 `skills` 数组中按 `name` 匹配 → 根据 `source` 安装：`local` 按 `dir` 路径取本仓库目录；`github` 按 `repo`（必要时加 `path`）从远程仓库安装。

| Agent | 定位 | 安装的 skill |
|---|---|---|
| **openclaw** | 研究/金融场景 | 金融宏观全套 8 个 + find-skills |
| **hermes** | 开发工程场景 | Agent 方法论 4 个 + 开发工程 5 个 + ui-ux-pro-max + notes-deal |

> 以上为初始默认分配，请按实际使用情况调整 `registry.json`。

## 维护指南

**新增自研 skill**：
1. 在对应主题目录下创建 `<skill名>/SKILL.md`；
2. 在 `registry.json` 的 `skills` 数组中登记条目（source: local，name/dir/theme/status/summary）；
3. 如需安装，把 name 加入相应 agent 的 `skills` 列表；
4. 更新本 README 的分类索引表。

**新增外部 skill**：
1. 在 `registry.json` 的 `skills` 数组中登记条目：`source: "github"`，并填写 `repo`（GitHub 仓库地址）、可选 `path`（skill 目录子路径）、theme/status/summary；
2. 运行 `python scripts/sync_github_versions.py` 自动回填 `latest_version` 等版本字段；
3. 如需安装，把 name 加入相应 agent 的 `skills` 列表；
4. 在本 README「外部 skill（GitHub）」表中加一行。

**新增 agent**：在 `registry.json` 的 `agents` 中添加条目（description + skills 列表），并同步 README 的 Agent 安装配置表。

**修改 skill 清单**：skill 的启用/停用通过条目的 `status`（active / empty / deprecated）标识，deprecated 的 skill 应从各 agent 的 skills 列表中移除。
