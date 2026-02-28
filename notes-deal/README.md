# 笔记整理 Skill (Notes Deal)

自动整理浏览器插件采集的知识点，按关键词分类到对应资源目录的 Claude Code Skill。

## 概述

本 Skill 专用于处理通过 Chrome 高亮采集插件收集的知识点文件，实现：

- 📅 **智能文件筛选**：按文件名日期自动识别当天/本周采集的文件
- 🤖 **AI 内容整理**：智能摘要生成 + 结构化重组 + Markdown 格式规范
- 🏷️ **关键词分类**：从原文关键词字段提取分类信息，自动分发到对应目录
- 🗑️ **源文件清理**：处理成功后自动删除归档目录中的源文件

## 适用场景

适用于使用 Chrome 高亮采集插件收集知识点的用户，特别是：

- 使用 Obsidian 作为知识管理系统
- 安装了 Claudian 插件（在 Obsidian 中使用 Claude Code）
- 采集的文件保存在 `Archive_归档/knowladgeCollect/` 目录
- 希望按主题分类整理到 `Resource_资源/` 目录

## 安装

### 1. 检查文件结构

确保 Skill 文件已正确安装在：

```
C:\Users\Administrator\.claude\skills\knowledge-collector\
├── SKILL.md                      # Skill 主文件
├── config/
│   ├── prompt-template.md        # AI Prompt 模板
│   └── settings.json             # 配置文件
└── README.md                     # 本文档
```

### 2. 配置路径

编辑 `config/settings.json`，确认路径正确：

```json
{
  "source_dir": "F:\\Obsidian\\第二大脑\\Archive_归档\\knowladgeCollect",
  "resource_base_dir": "F:\\Obsidian\\第二大脑\\Resource_资源"
}
```

### 3. 在 Claudian 中使用

在 Obsidian 中打开 Claudian 聊天窗口，输入：

```
整理今天的知识点
```

Skill 将自动启动并处理当天的采集文件。

## 使用方法

### 基本用法

#### 整理今天的文件

```
整理今天的知识点
```

或

```
处理 knowladgeCollect 目录
```

#### 整理本周的文件

```
整理本周采集的知识点
```

### 高级用法

#### 查看处理进度

Skill 会实时显示处理进度：

```
正在扫描源目录...
找到 3 个待处理文件

正在处理 1/3: 笔记_高手对话AI秘诀_2026-02-02.md
  - 读取文件内容 ✓
  - 提取关键词: 提示词, knowladgeCollect
  - AI 整理内容 ✓
  - 复制到 Resource_资源/提示词/ ✓
  - 删除源文件 ✓
```

#### 处理报告

处理完成后显示详细报告：

```
✅ 处理完成

成功: 3 个文件
失败: 0 个文件

成功文件列表:
  - 笔记_高手对话AI秘诀_2026-02-02.md
    → [提示词]
  - 笔记_0成本get圣诞胶片写真_2025-12-22.md
    → [AI生图, 提示词]
  - 笔记_Gemini API负责人破防_2026-01-06.md
    → [AI新闻]
```

## 配置说明

### settings.json 配置项

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `source_dir` | string | `F:\Obsidian\第二大脑\Archive_归档\knowladgeCollect` | 采集文件源目录 |
| `resource_base_dir` | string | `F:\Obsidian\第二大脑\Resource_资源` | 资源目录基础路径 |
| `excluded_tags` | array | `["knowladgeCollect"]` | 排除的标签列表 |
| `date_formats` | array | `["YYYY-MM-DD", "YYYY/MM/DD", "YYYYMMDD"]` | 支持的日期格式 |
| `file_patterns` | array | `["笔记_*.md", "*.md"]` | 要处理的文件模式 |
| `conflict_strategy` | string | `"overwrite"` | 文件冲突处理策略 |
| `cleanup_source` | boolean | `true` | 是否删除源文件 |
| `max_file_size_mb` | number | `1.0` | 最大文件大小（MB） |
| `max_keywords` | number | `10` | 最大关键词数量 |
| `enable_logging` | boolean | `true` | 是否启用详细日志 |

### conflict_strategy 选项

- `"overwrite"`：覆盖已存在的文件（默认）
- `"skip"`：跳过已存在的文件
- `"rename"`：重命名新文件（添加时间戳）

## 工作流程

### 数据流向

```
Archive_归档/knowladgeCollect/
  └── 笔记_xxx_2026-02-02.md
         ↓
   [1. 读取文件内容]
         ↓
   [2. 提取关键词字段]
         ↓
   [3. AI 整理内容]
     ├── 智能摘要生成
     ├── 结构化重组
     └── Markdown 格式规范
         ↓
   [4. 按关键词分发]
     ├── Resource_资源/提示词/笔记_xxx_2026-02-02.md
     └── Resource_资源/AI生图/笔记_xxx_2026-02-02.md
         ↓
   [5. 删除源文件]
```

### 处理步骤

1. **扫描源目录**：读取 `Archive_归档/knowladgeCollect/` 下所有 `.md` 文件
2. **筛选文件**：从文件名提取日期，匹配当天/本周的文件
3. **逐个处理**：
   - 读取文件内容
   - 提取元数据（标题、日期、链接、关键词）
   - 使用 AI 整理内容（按照 prompt 模板）
   - 为每个有效关键词创建目标目录并写入文件
   - 删除源文件
4. **输出报告**：显示处理结果统计

## 文件格式

### 输入文件格式

采集文件应遵循以下格式：

```markdown
# 笔记 - 文章标题

## 基础信息
- **发布日期**:: 2026年1月11日 20:36
- **阅读日期**:: 2026-02-02
- **原文链接**:: [文章标题](URL)
- **关键词**:: 提示词, knowladgeCollect

---

## 摘要
- 用 1-2 句话概括文章核心内容（避免照搬原文）。

---

## 重点
- 要点1
- 要点2
```

### 输出文件格式

整理后的文件格式：

```yaml
---
title: 文章标题
publish_date: 2026-01-11
read_date: 2026-02-02
source: https://...
tags: [提示词, AI生图]
summary: |
  - 要点1：简洁描述
  - 要点2：简洁描述
  - 要点3：简洁描述
---

# 文章标题

## 核心要点

- 要点1：简洁描述
- 要点2：简洁描述
- 要点3：简洁描述

## [主要内容标题]

[结构化整理后的内容...]
```

## 边缘情况处理

### 没有待处理文件

```
今天没有采集到新的知识点文件
```

### 文件名日期无法识别

```
⚠️ 跳过文件 xxx.md：无法识别日期格式
```

### 关键词字段缺失

```
⚠️ 跳过文件 xxx.md：缺少关键词字段
```

### AI 整理失败

```
❌ 处理失败 xxx.md：AI 整理失败
   源文件已保留
```

### 无有效关键词

排除 `knowladgeCollect` 后无其他关键词：

```
⚠️ 文件 xxx.md 没有有效的分类关键词
   已跳过分发，源文件已保留
```

## 注意事项

### 数据安全

- ✅ 处理失败时绝不删除源文件
- ✅ 所有副本写入成功后才删除源文件
- ⚠️ 建议在处理前备份重要数据

### 性能考虑

- 串行处理，确保稳定性
- 大文件（>1MB）可能需要更多时间
- 每个文件处理时间约 5-10 秒

### 最佳实践

1. **定期处理**：建议每天处理一次，避免文件堆积
2. **检查结果**：处理完成后检查整理效果
3. **备份数据**：定期备份 `Archive_归档/` 目录
4. **优化配置**：根据使用习惯调整配置参数

## 故障排除

### 问题 1：Skill 无法启动

**可能原因**：
- Claudian 未正确安装
- Skill 文件路径不正确

**解决方法**：
1. 确认 Claudian 插件已启用
2. 检查 Skill 文件是否在 `~/.claude/skills/` 目录
3. 重启 Obsidian

### 问题 2：找不到待处理文件

**可能原因**：
- 文件名日期格式不匹配
- 源目录配置错误

**解决方法**：
1. 检查文件名是否包含日期（格式：`_YYYY-MM-DD.md`）
2. 确认 `settings.json` 中 `source_dir` 路径正确
3. 检查文件是否在今天/本周的日期范围内

### 问题 3：文件未复制到目标目录

**可能原因**：
- 关键词字段缺失或无效
- 目标目录创建失败（权限问题）

**解决方法**：
1. 检查源文件的 `**关键词**::` 字段
2. 确认有除 `knowladgeCollect` 外的其他关键词
3. 检查目标目录的写入权限

### 问题 4：源文件未被删除

**可能原因**：
- 处理失败（保留源文件）
- `cleanup_source` 设置为 `false`

**解决方法**：
1. 查看处理报告中的错误信息
2. 检查 `settings.json` 中的 `cleanup_source` 配置

## 与其他 Skill 的区别

### doc-organizer

- `doc-organizer`：整理单个文档的格式，不移动文件
- `knowledge-collector`：批量处理采集文件，自动分类归档

### update-doc

- `update-doc`：根据代码变更更新项目文档
- `knowledge-collector`：处理采集的知识点内容

## 技术架构

- **Skill 格式**：Claude Code Skill (与 Claudian 完美集成)
- **文件操作**：Read, Write, Edit, Bash 工具
- **AI 能力**：使用 Claude 的内置理解和生成能力
- **配置管理**：JSON 配置文件 + Markdown Prompt 模板

## 相关链接

- [Claude Code 官方文档](https://docs.anthropic.com/claude-code)
- [Claudian GitHub 仓库](https://github.com/YishenTu/claudian)
- [Chrome 高亮采集插件](F:\github\person_project\higlightCollect)

## 版本历史

### v1.0.0 (2026-02-03)

- ✨ 初始版本发布
- ✅ 支持按日期筛选文件
- ✅ AI 内容整理（摘要 + 重组 + 格式化）
- ✅ 关键词自动分类
- ✅ 源文件自动清理
- ✅ 完整的错误处理和日志

## 贡献

欢迎提交 Issue 和 Pull Request！

## 许可证

MIT License

---

**作者**：Claude Code + 用户协作
**创建日期**：2026-02-03
**最后更新**：2026-02-03
