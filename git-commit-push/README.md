# Git 自动提交和推送

这是一个 Claude Code 自定义命令（skill），用于自动生成规范的 commit message 并推送到 GitHub。

## 功能特性

- ✅ 自动分析代码改动
- ✅ 生成符合 Conventional Commits 规范的 commit message
- ✅ 自动执行 git add、commit、push
- ✅ 检测敏感文件并警告
- ✅ 完整的错误处理

## 使用方法

### 方式 1：使用 Skill 命令
在对话中说：
- "提交代码"
- "生成 commit 并推送"
- "commit 并 push"
- "提交到 GitHub"

### 方式 2：直接触发（推荐）
Claude 会自动识别您想提交代码的意图，直接调用这个 skill。

## Commit Message 格式

遵循 Conventional Commits 规范：

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Type 类型
- `feat` - 新功能
- `fix` - 修复 bug
- `docs` - 文档更新
- `style` - 代码格式调整
- `refactor` - 重构
- `perf` - 性能优化
- `test` - 测试
- `chore` - 构建或辅助工具变动

## 示例

```
用户: 帮我提交代码

Claude:
[自动执行]
1. 检查 git 状态
2. 分析改动内容
3. 生成 commit message
4. 执行 git add, commit, push
5. 报告结果

[输出]
✓ 已提交：feat(comment-widget): 添加评论计数器显示
✓ 已推送到 origin/main
```

## 注意事项

- 这个 skill 会在使用时自动分析您的代码改动
- 如果检测到敏感文件（.env、credentials.json），会警告您
- 如果远程仓库有冲突，会提示您先 pull

## 文件结构

```
git-commit-push/
├── SKILL.md      # Skill 定义文件（Claude 读取）
└── README.md     # 说明文档（您正在阅读）
```

## 自定义

您可以编辑 `SKILL.md` 文件来自定义：
- Commit message 格式
- Type 类型定义
- 错误处理逻辑
- 输出格式
