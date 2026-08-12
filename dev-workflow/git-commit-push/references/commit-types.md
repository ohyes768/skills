# Commit Message 规范

遵循 [Conventional Commits](https://www.conventionalcommits.org/)。

## 格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

## Type 类型

| Type | 用途 |
|------|------|
| `feat` | 新功能 |
| `fix` | 修复 bug |
| `docs` | 文档更新 |
| `style` | 代码格式（不影响功能） |
| `refactor` | 重构（非 feat/fix） |
| `perf` | 性能优化 |
| `test` | 测试 |
| `chore` | 构建、依赖、工具变动 |
| `revert` | 回滚 |

## Subject 规则

- 使用中文
- 不超过 50 字
- 首字母不大写
- 结尾不加句号
- 祈使句（「添加」「修复」「更新」）

## Body（可选）

- 说明修改原因和背景
- 列出主要变更点
- 简单改动可省略

## Footer（可选）

- 关联 Issue：`#123`
- 破坏性变更：`BREAKING CHANGE: <说明>`
