# 宏观 Skill 下线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 下线由 Web 服务接管的四个宏观 Skill，并把两套综合判断模型归档为文档。

**Architecture:** 保留四个原始宏观数据 Skill 及其线上推送接口。删除汇率、风险偏好和两种综合指数 Skill 的实现、注册和文档引用；以一份静态 Markdown 保存原有模型的可重建规则。

**Tech Stack:** Markdown、JSON、Python unittest。

---

### Task 1: 建立隔离工作区

**Files:**
- Modify: `.gitignore`
- Create: `.worktrees/macro-skill-sunsetting/`

- [ ] **Step 1: 确认 `.worktrees/` 被 Git 忽略。**

Run: `git check-ignore -q .worktrees`
Expected: exit code 0.

- [ ] **Step 2: 创建 `codex/macro-skill-sunsetting` worktree。**

Run: `git worktree add .worktrees/macro-skill-sunsetting -b codex/macro-skill-sunsetting`
Expected: worktree 创建成功。

### Task 2: 归档综合判断逻辑

**Files:**
- Create: `finance-macro/ARCHIVED_MACRO_DECISION_LOGIC.md`

- [ ] **Step 1: 写入 A 股和债市模型的维度、权重、评分方向、时效与缺失数据处理。**

The document must preserve the original six dimensions and distinguish the four core inputs from optional market sentiment.

- [ ] **Step 2: 复读文档，确认其不依赖已删除目录。**

Run: `Get-Content finance-macro/ARCHIVED_MACRO_DECISION_LOGIC.md`
Expected: two models and their reconstruction rules are readable.

### Task 3: 移除已下线 Skill 与注册引用

**Files:**
- Delete: `finance-macro/exchange-rate-skill/`
- Delete: `finance-macro/risk-appetite-skill/`
- Delete: `finance-macro/a-share-macro-skill/`
- Delete: `finance-macro/bond-market-overview-skill/`
- Modify: `registry.json`
- Modify: `README.md`
- Modify: `skill-agent-matrix.html`

- [ ] **Step 1: 从注册表删除四个 skill 条目，并删除所有依赖项。**

- [ ] **Step 2: 从仓库索引文档和 HTML 矩阵删除它们的卡片与依赖标签。**

- [ ] **Step 3: 删除四个 skill 目录。**

### Task 4: 清理保留 Skill 的过时交叉引用

**Files:**
- Modify: `finance-macro/monetary-policy-skill/scripts/upload_signal.py`
- Modify: `finance-macro/money-supply-skill/scripts/upload_signal.py`
- Modify: `finance-macro/entity-economy-skill/scripts/upload_signal.py`
- Modify: `finance-macro/inflation-skill/scripts/upload_signal.py`
- Modify: `finance-macro/monetary-policy-skill/scripts/run_all.py`
- Modify: `finance-macro/money-supply-skill/scripts/run_all.py`
- Modify: `finance-macro/entity-economy-skill/scripts/run_all.py`

- [ ] **Step 1: 移除将已删除 skill 作为上传白名单或特殊结构示例的注释。**

- [ ] **Step 2: 保持四个存活 skill 的 `macro_signal.json` 上传契约不变。**

### Task 5: 验证下线结果

**Files:**
- Test: retained macro skill Python modules

- [ ] **Step 1: 搜索活动代码、注册表与 README，确认不存在删除 skill 的引用。**

Run: `rg -n -i 'exchange-rate-skill|risk-appetite-skill|a-share-macro-skill|bond-market-overview-skill' README.md registry.json finance-macro`
Expected: only the archival document may name the former skills.

- [ ] **Step 2: 对保留的四个 skill 编译 Python 脚本。**

Run: `python -m compileall -q finance-macro/monetary-policy-skill/scripts finance-macro/money-supply-skill/scripts finance-macro/entity-economy-skill/scripts finance-macro/inflation-skill/scripts`
Expected: exit code 0.

- [ ] **Step 3: 查看 Git diff 与状态，确认删除范围及文档归档完整。**

Run: `git status --short; git diff --check`
Expected: only planned files changed and no whitespace errors.
