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
scripts/              # 维护脚本（sync_skills.py 同步自研 skill；sync_github_versions.py 刷新版本；sync_github_skills.py 安装 GitHub skill）
registry.json         # skill 注册表真源：skill 清单 + 各 agent 安装分配（可版本控制）
sync-config.json      # 机器本地配置：各 agent 的 skills 目录路径与 enabled 开关
skill-agent-matrix.html  # （legacy）旧版内嵌注册表，仅作历史参考，不再维护
README.md
```

## 注册表（registry.json）

`registry.json` 是本仓库的唯一注册表真源，包含两部分：

- `skills`：skill 条目清单，每条含 `id`（稳定 slug）、`name`、`source`（local/github）、`path`（local 为本仓库内相对目录，github 为仓库内相对目录，可为 `.`）、`repository`（github 必填）、`tags`（主题分类）、`summary`、`status`（active/deprecated）、可选 `depends_on`；
- `agents`：各 agent 的安装分配（`description` + `skills` id 列表）。

版本快照（`latest_version` / `head_commit` / `checked_at`）与发布历史等运行状态**不写回注册表**，由机器本地 `.cache/github-versions.json` 保存（不入 git）。


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
| [claudeception](agent-methods/claudeception) | — | 未登记（目录缺失，待补充后登记） |

### UI/UX 设计 `design/`

| Skill | 说明 | 状态 |
|---|---|---|
| [ui-ux-pro-max](design/ui-ux-pro-max) | 设计智能：67 风格/96 配色/57 字体搭配/13 技术栈 | active |

### 知识管理 `knowledge/`

| Skill | 说明 | 状态 |
|---|---|---|
| [notes-deal](knowledge/notes-deal) | 浏览器采集知识点的自动分类整理 | active |

## 外部 skill（GitHub）

来自外部 GitHub skill 仓库（`source: github`），安装时直接从远程仓库拉取。[registry.json](registry.json) 中对应条目包含 `repository`（仓库地址）和 `path`（skill 目录在仓库中的相对路径，可为 `.`）。

| Skill | 来源仓库 | 主题 | 说明 | 安装到 |
|---|---|---|---|---|
| ui-ux-pro-max | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 设计 | UI/UX 设计智能：67 风格/96 配色/57 字体搭配/13 技术栈 | hermes |
| uzi-skill | [wbh604/UZI-Skill](https://github.com/wbh604/UZI-Skill) | 投资分析 | 游资（UZI）A股/港股/美股分析：22维数据×180条量化规则×17种机构分析方法 | openclaw、hermes |
| luopan | [zhangxiaoqiang1991/luopan](https://github.com/zhangxiaoqiang1991/luopan) | 投资分析 | 行业研究+公司研究路由器：行业格局与产业链权力分析、公司投资/求职价值判断（腾讯自选股数据源） | — |

**刷新远程版本**：运行 `python scripts/sync_github_versions.py`（可加 `--dry-run` 只看不写）。脚本对每个 github skill 执行 `git ls-remote`（不走 GitHub REST API、无需 token），把最新 tag 写入 `.cache/github-versions.json`（机器本地，不入 git），并打印版本变化；无 tag 的仓库以 `HEAD@<短commit>` 记录。

**安装/更新到各 agent**：`registry.json` 的 `agents` 中配置好分配后，编辑 `sync-config.json` 开启对应 agent 的 `enabled`，然后运行：

```bash
python scripts/sync_github_versions.py   # 可选：先刷新版本快照
python scripts/sync_github_skills.py     # clone/pull 到缓存并 junction 到各 agent
python scripts/sync_github_skills.py --status
python scripts/sync_github_skills.py --skill uzi-skill --agent openclaw
```

GitHub skill 缓存在本仓库 `.cache/github-skills/<skill id>/`，各 agent 以 **junction** 指向缓存（若注册表有 `path` 字段则指向子目录）。更新时重新运行 `sync_github_versions.py` + `sync_github_skills.py` 即可 checkout 到最新 tag。

**同步自研 skill 到各 agent**（`source: local`）：

```bash
python scripts/sync_skills.py          # 同步所有已启用 agent
python scripts/sync_skills.py --status # 查看 junction 状态
python scripts/sync_skills.py --skill git-commit-push --agent claudecode
```

自研 skill 以 **junction** 链接到各 agent 的 `skills_dir`，改仓库即生效。`openclaw` / `hermes` 等 agent 路径在 `sync-config.json` 中配置，启用前请确认目录存在或允许脚本自动创建父目录。

## Agent 安装配置

以 [registry.json](registry.json) 的 `agents` 字段为准。agent 安装 skill 时：读取 `agents.<agent名>.skills` 中的 skill id 列表 → 在 `skills` 数组中按 `id` 匹配 → 根据 `source` 安装：`local` 按 `path` 取本仓库目录；`github` 按 `repository`（必要时加 `path`）从远程仓库安装。

当前分配（以 `registry.json` 为准，此处仅概览）：

| Agent | 定位 | 安装的 skill |
|---|---|---|
| **openclaw** | 研究/金融场景 | uzi-skill |
| **hermes** | 开发工程场景 | uzi-skill |
| **claudecode** | Claude Code 编码 agent | git-commit-push |
| **codex** | Codex 编码 agent | （无） |

## 维护指南

**新增自研 skill**：
1. 在对应主题目录下创建 `<skill名>/SKILL.md`；
2. 在 `registry.json` 的 `skills` 中登记条目（source: local，id/name/path/tags/status/summary）；
3. 在 `registry.json` 的 `agents` 中把 skill id 加入目标 agent 的 `skills` 列表；
4. 运行 `python scripts/sync_skills.py`；
5. 更新本 README 的分类索引表。

**新增外部 skill**：
1. 在 `registry.json` 的 `skills` 中登记条目：`source: "github"`，并填写 `repository`、`path`（可为 `.`）、tags/status/summary；
2. 运行 `python scripts/sync_github_versions.py` 刷新版本快照；
3. 在 `registry.json` 的 `agents` 中配置分配，运行 `python scripts/sync_github_skills.py`；
4. 在本 README「外部 skill（GitHub）」表中加一行。

**新增 agent**：在 `sync-config.json` 添加路径与 `enabled`，并在 `registry.json` 的 `agents` 中添加条目（description + skills 列表），同步 README。

**修改 skill 清单**：skill 的启用/停用通过条目的 `status`（active / deprecated）标识，deprecated 的 skill 应从各 agent 的 skills 列表中移除。
