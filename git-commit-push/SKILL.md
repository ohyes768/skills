---
name: git-commit-push
description: 自动生成规范的 commit message，提交更改到 git，并推送到远程仓库
allowed-tools: Bash, Read, Grep
---

# Git 自动提交和推送

自动执行 git add、commit 和 push 操作，生成符合规范的 commit message。

## Commit Message 规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范：

### 格式
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式调整（不影响功能）
- `refactor`: 重构（既不是新功能也不是修复 bug）
- `perf`: 性能优化
- `test`: 添加测试
- `chore`: 构建过程或辅助工具的变动
- `revert`: 回滚之前的 commit

### Subject 主题
- 使用中文描述
- 不超过 50 字
- 首字母不大写
- 结尾不加句号
- 使用祈使句

### Body 正文（可选）
- 详细描述本次修改的内容
- 说明修改的原因和背景
- 列出主要的变更点

### Footer 脚注（可选）
- 关联的 Issue：`#123`
- 破坏性变更：`BREAKING CHANGE:`

## 处理流程

### 1. 检查仓库状态
```bash
git status
```

### 2. 查看改动内容
```bash
git diff
git diff --staged  # 如果有已暂存的文件
```

### 3. 查看最近的 commit 历史
```bash
git log -5 --oneline
```
用于了解项目的 commit message 风格

### 4. 分析改动并生成 commit message
根据改动内容，自动生成符合规范的 commit message：
- 分析改动的类型（feat/fix/docs 等）
- 提取改动的核心内容作为 subject
- 根据需要添加 body 和 footer

### 5. 执行 git 操作
```bash
# 添加所有改动
git add .

# 提交（使用 HEREDOC 确保 commit message 格式正确）
git commit -m "$(cat <<'EOF'
<type>(<scope>): <subject>

<body>

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"

# 推送到远程
git push
```

### 6. 确认结果
```bash
git status
git log -1 --pretty=full
```

## Commit Message 模板

根据不同的改动类型，使用相应的模板：

### 新功能 (feat)
```bash
feat(<模块>): 添加<功能描述>

- 实现<具体功能点1>
- 实现<具体功能点2>
- 添加<配置/参数>
```

### 修复 Bug (fix)
```bash
fix(<模块>): 修复<问题描述>

- 修复<bug 具体表现>
- 根本原因：<原因分析>
- 解决方案：<解决方法>
```

### 文档更新 (docs)
```bash
docs(<文档名>): 更新<更新内容>

- 更新<章节1>：<具体变更>
- 更新<章节2>：<具体变更>
- 补充<新增内容>
```

### 重构 (refactor)
```bash
refactor(<模块>): <重构目标>

- 提取<方法/类>：<说明>
- 简化<逻辑>：<说明>
- 优化<结构>：<说明>
```

## 使用示例

当用户说：
- "提交代码"
- "生成 commit 并推送"
- "commit 并 push"
- "提交到 GitHub"

你会：
1. 执行上述处理流程
2. 根据实际改动生成合适的 commit message
3. 执行 git add、commit、push 操作
4. 报告执行结果

## 注意事项

- **确保在 git 仓库中执行**：先检查 `.git` 目录是否存在
- **检查是否有改动**：如果没有改动，提示用户无需提交
- **避免重复提交**：如果 HEAD commit 已经包含相同的改动，提示用户
- **处理敏感文件**：如果发现 `.env`、`credentials.json` 等敏感文件，警告用户
- **检查远程仓库**：确认远程仓库已配置（`git remote -v`）
- **网络问题**：如果 push 失败，提示用户检查网络连接或认证
- **冲突处理**：如果 push 时遇到冲突，提示用户先 pull 并解决冲突

## 错误处理

### 没有改动
```
工作目录是干净的，无需提交。
```

### 没有配置远程仓库
```
未检测到远程仓库，请先配置：
git remote add origin <仓库地址>
```

### Push 失败
```
推送失败，可能原因：
- 网络连接问题
- 认证信息过期
- 远程仓库有新的提交
请检查后重试。
```

### 敏感文件警告
```
⚠️ 警告：检测到敏感文件：
- .env
- credentials.json

请确认这些文件应该在 .gitignore 中
```

## 示例 Commit Message

### 示例 1：新功能
```
feat(comment-widget): 添加评论计数器显示

- 在界面左下角显示"当前/总数"格式的计数器
- 实时更新计数器显示当前评论位置
- 无评论时显示"0/0"

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

### 示例 2：修复 Bug
```
fix(window): 修复窗口调整大小时位置偏移问题

- 在调整高度前保存窗口位置
- 调整后恢复原始位置
- 确保窗口只在用户手动拖动时才移动

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

### 示例 3：文档更新
```
docs(readme): 更新项目文档至 v3.0

- 更新 README.md 反映系统托盘功能
- 更新 PRD.md 添加系统托盘需求
- 更新 TDD.md 添加托盘模块设计
- 更新文档索引版本信息

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

## 快捷命令

用户也可以通过以下方式调用：
- `/commit` - 快速提交并推送
- "帮我提交代码" - 完整流程
- "commit 并 push" - 简洁命令
