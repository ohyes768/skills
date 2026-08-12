# Git 自动提交和推送

分析 git 改动，生成 Conventional Commits 风格的中文 commit message，按用户意图执行提交/推送。

## 功能

- 并行检查 `git status` / `diff` / `log`
- 三种模式：仅 message / commit / commit + push
- 跨平台提交（`git commit -F` 临时文件，兼容 PowerShell 与 Bash）
- 敏感文件检测与安全约束

## 使用

在对话中说：

- 「写个 commit message」（仅生成，不提交）
- 「帮我提交代码」（commit，不 push）
- 「提交并推送到 GitHub」（commit + push）

## 文件结构

```
git-commit-push/
├── SKILL.md
├── README.md
└── references/
    ├── commit-types.md   # type / scope / subject 规范
    ├── templates.md      # 各类型 body 模板
    └── examples.md       # 完整 message 示例
```

## 自定义

编辑 `SKILL.md` 调整流程与安全约束；编辑 `references/` 调整格式规范与模板。
