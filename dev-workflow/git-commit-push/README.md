# Git 自动提交和推送

分析 git 改动，生成 Conventional Commits 风格的中文 commit message，按用户意图执行提交/推送。

## 功能

- 六步流程：识别模式 → 检查状态 → 只读本次提交范围 → 简单 message 直接提交 → 按要求推送 → 精简确认结果
- 四种模式：仅 message / commit / 仅 push / commit + push
- 尊重部分暂存；按需读取 diff、历史与 message 参考，减少重复命令和输出
- 简单说明使用 `git commit -m`；复杂说明使用系统临时文件，兼容 PowerShell 5.1 / 7、Bash / zsh 和 worktree
- 仅依赖 Git 和系统已有 shell，不要求 GitHub CLI、Python 或 Node.js
- 敏感文件检测与安全约束

## 使用

在对话中说：

- 「写个 commit message」（仅生成，不提交）
- 「帮我提交代码」（commit，不 push）
- 「只推送已有提交」（push，不提交工作区改动）
- 「提交并推送到 GitHub」（commit + push）

## 文件结构

```
git-commit-push/
├── SKILL.md
├── README.md
└── references/
    ├── commit-types.md   # type / scope / subject 规范
    ├── commit-message-shell.md # 复杂 message 的跨平台写入与失败处理
    ├── templates.md      # 各类型 body 模板
    └── examples.md       # 完整 message 示例
```

## 自定义

编辑 `SKILL.md` 调整流程与安全约束；编辑 `references/` 调整格式规范与模板。
