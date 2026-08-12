---
name: git-commit-push
description: >
  分析 git 改动，生成 Conventional Commits 风格的中文 commit message，并在用户明确要求时执行
  git add、commit、push。用户说提交代码、commit、推送、保存到 git、上传 GitHub、生成 commit message、
  帮我提交、commit and push 时必须使用本 skill——即使用户未提及 conventional commits 或本 skill 名称。
  仅 review 代码、讨论改动、或用户未明确要提交/推送时，不要执行 git 操作。用户只说 commit 时不要
  自动 push；只有明确说 push/推送/上传 GitHub 时才推送。
allowed-tools: Shell, Read, Grep, Write
---

# Git 自动提交和推送

分析改动、生成规范 commit message，按用户意图执行 git 操作。

## 模式选择

根据用户措辞判断，**不要默认一条龙**：

| 用户意图 | 行为 |
|----------|------|
| 「写 commit message」「拟提交说明」「先别提交」 | 只输出 message，不执行 git |
| 「提交」「commit」「帮我提交代码」（未提 push） | `git add` + `git commit`，**不 push** |
| 「提交并推送」「commit and push」「推到 GitHub」 | add + commit + push |

## 处理流程

### 1. 并行检查（同一轮工具调用）

```bash
git status
git diff
git diff --staged
git log -5 --oneline
```

- 无改动 → 告知「工作目录干净，无需提交」，停止
- 已有 staged 改动 → 尊重用户暂存，不要无脑 `git add .`
- 参考 `git log` 匹配项目既有 commit 风格

### 2. 安全检查

改动涉及 `.env`、`credentials.json`、`*.pem`、`secrets.*` 等敏感文件时，**警告用户并暂停提交**，除非用户明确确认。

### 3. 生成 commit message

遵循 [Conventional Commits](https://www.conventionalcommits.org/)，中文 subject，匹配仓库风格。

- type / scope / subject 规则 → 读 `references/commit-types.md`
- 各类型 body 模板 → 读 `references/templates.md`
- 完整示例 → 读 `references/examples.md`

正文聚焦「为什么」而非罗列文件名。简单改动可只用一行 subject，不必强行写 body。

### 4. 暂存与提交

按改动范围选择性 `git add`（优先 staged 文件或用户指定路径，避免盲目 `git add .`）。

**跨平台提交**：用临时文件 + `git commit -F`，不要在 PowerShell 里用 Bash HEREDOC。

**PowerShell（Windows 默认）：**

```powershell
$msg = @"
feat(scope): 简短描述

- 主要变更点

"@
$msg | Out-File -FilePath .git/COMMIT_EDITMSG_SKILL -Encoding utf8NoBOM
git commit -F .git/COMMIT_EDITMSG_SKILL
Remove-Item .git/COMMIT_EDITMSG_SKILL -ErrorAction SilentlyContinue
```

**Bash / Git Bash：**

```bash
cat > .git/COMMIT_EDITMSG_SKILL <<'EOF'
feat(scope): 简短描述

- 主要变更点

EOF
git commit -F .git/COMMIT_EDITMSG_SKILL
rm -f .git/COMMIT_EDITMSG_SKILL
```

多行 message 统一写入 `.git/COMMIT_EDITMSG_SKILL` 再 `git commit -F`，比 `-m` 更可靠。

### 5. 推送（仅在被要求时）

```bash
git remote -v          # 确认远程存在
git push               # 或 git push -u origin HEAD（新分支）
```

push 失败时提示可能原因（认证、远程有新提交、网络），建议先 `git pull --rebase` 再重试。

### 6. 确认结果

```bash
git status
git log -1 --pretty=full
```

向用户报告：commit hash、message 摘要、是否已推送。

## 安全约束

- **未明确要求不 commit、不 push**
- 禁止修改 `git config`
- 禁止 `--no-verify`、`--no-gpg-sign`（除非用户明确要求）
- 禁止 `git commit --amend`（除非用户明确要求且符合 amend 条件）
- 禁止交互式 git 命令（`-i` 系列）
- pre-commit hook 失败 → 修复后**新建 commit**，不要 amend

## 错误处理

| 情况 | 响应 |
|------|------|
| 无改动 | 「工作目录是干净的，无需提交。」 |
| 无远程仓库 | 提示 `git remote add origin <url>` |
| push 失败 | 列出认证/冲突/网络等可能原因 |
| 敏感文件 | 列出文件，建议加入 `.gitignore`，等待用户确认 |

## 参考文件

| 文件 | 何时读取 |
|------|----------|
| `references/commit-types.md` | 不确定 type/scope/subject 格式时 |
| `references/templates.md` | 需要结构化 body 时 |
| `references/examples.md` | 需要参考完整 message 时 |
