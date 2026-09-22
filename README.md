# 个人 Skill 库

统一管理个人 agent skill 源码的仓库。Skill 分两大类：

- **自研 skill**（`source: local`）：自己开发维护，按主题目录存放在本仓库；
- **外部 skill**（`source: github`）：来自 GitHub 上的 skill 仓库，本仓库只记录来源。

## 登记与发布

本仓库**只存放 skill 源码与目录结构**。skill 的登记（清单/元数据）与发布（安装到 OpenClaw/Hermes）由 **skill-manager** 管理（`personal-web/backend/skill-manager`，FastAPI），登记真源为 skill-manager 的 SQLite：

- 自研 skill 目录在首次访问管理台 `GET /api/skills` 时自动对账登记（元数据取 SKILL.md frontmatter）；
- 外部 skill 在管理台按 GitHub 仓库登记，发布时缓存并检出远端 HEAD；
- 发布目标为 OpenClaw / Hermes，支持计划预览、下架与回滚。

> **遗留说明**：`git-commit-push` 已发布到 claudecode / codex 的 junction（`~/.claude/skills/git-commit-push`、`~/.codex/skills/git-commit-push`）是原 sync 工具链产物，继续存在、由各自 agent 使用，但不归 skill-manager 维护。

## 目录结构

```
finance-macro/        # 金融宏观分析
dev-workflow/         # 开发工程
agent-methods/        # Agent 方法论
design/               # UI/UX 设计
knowledge/            # 知识管理
README.md
```

## 主题分类索引

以下为自研 skill（`source: local`），按主题分类。

### 金融宏观分析 `finance-macro/`

[bond-market-macro-impact-skill](finance-macro/bond-market-macro-impact-skill)：读取聚合快照 API，分析未来四周国内利率债整体及长短端差异，不涉及信用债。

新增 [a-share-macro-impact-skill](finance-macro/a-share-macro-impact-skill)：只读聚合快照 API，分析未来四周 A 股整体和成长／价值风格；不依赖本地数据抓取 skill。

| Skill | 说明 | 状态 |
|---|---|---|
| [monetary-policy-skill](finance-macro/monetary-policy-skill) | 货币政策松紧分析（DR007/LPR/MLF） | active |
| [money-supply-skill](finance-macro/money-supply-skill) | 货币供应与流动性（M1/M2/社融） | active |
| [entity-economy-skill](finance-macro/entity-economy-skill) | 实体经济强弱判断（PMI/固投/社零） | active |
| [inflation-skill](finance-macro/inflation-skill) | 通胀分析（CPI/PPI/核心CPI） | active |
| [ARCHIVED_MACRO_DECISION_LOGIC.md](finance-macro/ARCHIVED_MACRO_DECISION_LOGIC.md) | 已下线综合模型的判断逻辑归档 | archived |

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

来自外部 GitHub skill 仓库，发布时经 skill-manager 缓存并检出远端 HEAD。实际发布目标以 skill-manager 管理台为准（下表"安装到"为历史参考）。

| Skill | 来源仓库 | 主题 | 说明 |
|---|---|---|---|
| ui-ux-pro-max | [nextlevelbuilder/ui-ux-pro-max-skill](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill) | 设计 | UI/UX 设计智能：67 风格/96 配色/57 字体搭配/13 技术栈 |
| uzi-skill | [wbh604/UZI-Skill](https://github.com/wbh604/UZI-Skill) | 投资分析 | 游资（UZI）A股/港股/美股分析：22维数据×180条量化规则×17种机构分析方法 |
| luopan | [zhangxiaoqiang1991/luopan](https://github.com/zhangxiaoqiang1991/luopan) | 投资分析 | 行业研究+公司研究路由器：行业格局与产业链权力分析、公司投资/求职价值判断（腾讯自选股数据源） |

## 维护指南

**新增自研 skill**：
1. 在对应主题目录下创建 `<skill名>/SKILL.md`（frontmatter 写 `name`、`description`）；
2. 访问 skill-manager 管理台，列表会自动对账出现该 skill；
3. 在管理台选择目标（OpenClaw / Hermes）发布；
4. 更新本 README 的分类索引表。

**新增外部 skill**：在 skill-manager 管理台按 GitHub 仓库地址扫描并登记，缓存后发布。

**下架/回滚**：在 skill-manager 管理台操作，发布历史与快照持久化在 SQLite。

**修改 skill 清单**：启用/停用通过管理台维护；自研 skill 目录被移除时登记条目保留并提示源缺失（不自动删除）。
