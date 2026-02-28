---
name: notes-deal
description: 自动整理浏览器插件采集的知识点，按关键词分类到对应资源目录
allowed-tools: Read, Write, Edit, Grep, Bash
---

# 笔记整理 Skill (Notes Deal)

**强制执行指令**：你必须严格按照以下步骤执行，不得跳过或自由发挥。

## ⚠️ 执行前必读

在执行任何操作前，你必须：

1. **必须先读取配置文件**：`Read "{skill_dir}/config/settings.json"`
2. **必须使用配置中的绝对路径**：不要使用相对路径
3. **必须按步骤顺序执行**：不要跳过任何步骤
4. **必须在每步完成后验证**：确认操作成功后再进行下一步

## 📋 执行流程（严格按顺序）

### 步骤 1：读取配置（必须执行）

```bash
Read "C:\Users\Administrator\.claude\skills\notes-deal\config\settings.json"
```

从配置中提取：
- `source_dir`: 源目录（必须使用这个路径）
- `resource_base_dir`: 资源目录（必须使用这个路径）
- `excluded_tags`: 排除的标签列表
- `cleanup_source`: 是否删除源文件

**验证**：确认路径存在且正确后再继续。

### 步骤 2：扫描源目录（必须执行）

```bash
ls -la "{source_dir}"
```

**必须**使用配置文件中的 `source_dir`，不要自己猜测路径。

列出所有 `.md` 文件，输出格式：
```
找到以下文件：
1. 笔记_xxx_2026-02-03.md
2. 笔记_yyy_2026-02-03.md
...
```

### 步骤 3：筛选当天文件（必须执行）

从文件名中提取日期，格式：`_YYYY-MM-DD.md`

**只处理**当天日期的文件，输出：
```
待处理文件（当天）：
1. 笔记_xxx_2026-02-03.md
2. 笔记_yyy_2026-02-03.md
```

### 步骤 4：处理每个文件（循环执行）

对每个待处理文件，**必须**按以下子步骤执行：

#### 4.1 读取文件（必须）

```bash
Read "{source_dir}/{文件名}"
```

#### 4.2 提取关键词（必须）

从文件内容中提取 `**关键词**::` 字段。

**格式示例**：
```markdown
- **关键词**:: 提示词, AI生图, knowladgeCollect
```

**提取规则**：
- 逗号分隔
- 排除 `excluded_tags` 中的标签（如 `knowladgeCollect`）
- 保留其他所有关键词

**输出示例**：
```
文件：笔记_xxx_2026-02-03.md
提取关键词：["提示词", "AI生图"]
```

**验证**：如果没有关键词或没有有效关键词，跳过该文件并记录警告。

#### 4.3 加载 Prompt 模板（必须）

```bash
Read "C:\Users\Administrator\.claude\skills\notes-deal\config\prompt-template.md"
```

#### 4.4 AI 整理内容（必须）

按照 prompt 模板的要求整理内容，输出整理后的完整 Markdown。

**必须包含**：
- YAML frontmatter（title, publish_date, read_date, source, tags, summary）
- 核心要点（3-5个）
- 结构化内容

#### 4.5 按关键词分发（必须）

对**每个**有效关键词：

**必须**使用配置中的 `resource_base_dir`，不要自己构建路径。

```bash
# 目标目录格式
{resource_base_dir}/{关键词}/

# 示例
F:\Obsidian\第二大脑\Resource_资源\提示词\
```

**操作步骤**：
1. 创建目录（如不存在）：
   ```bash
   mkdir -p "{resource_base_dir}/{关键词}"
   ```

2. **转换文件名**：将 `笔记_` 前缀替换为 `highlight_`
   ```bash
   原文件名：笔记_xxx_2026-02-03.md
   新文件名：highlight_xxx_2026-02-03.md
   ```

3. 写入文件（使用新文件名）：
   ```bash
   Write "{resource_base_dir}/{关键词}/{新文件名}" "整理后的内容"
   ```

**验证**：确认文件已写入目标目录。

#### 4.6 删除源文件（按配置决定）

**如果**配置中 `cleanup_source == true`：
```bash
rm "{source_dir}/{文件名}"
```

**如果**配置中 `cleanup_source == false`：
- 保留源文件
- 在报告中说明"源文件已保留"

### 步骤 5：输出处理报告（必须）

**必须**输出详细的处理报告：

```
✅ 处理完成

配置信息：
- 源目录：{source_dir}
- 资源目录：{resource_base_dir}
- 删除源文件：{cleanup_source}

统计：
- 成功处理：{N} 个文件
- 跳过：{M} 个文件
- 失败：{K} 个文件

成功文件列表：
1. 笔记_xxx_2026-02-03.md
   关键词：[提示词, AI生图]
   目标目录：
     - {resource_base_dir}/提示词/
     - {resource_base_dir}/AI生图/

跳过文件列表：
1. 笔记_yyy_2026-02-03.md
   原因：无有效关键词

失败文件列表（源文件已保留）：
1. 笔记_zzz_2026-02-03.md
   原因：AI 整理失败
```

## 🚫 禁止行为

**不要做以下事情**：

- ❌ 不要跳过读取配置文件
- ❌ 不要使用相对路径
- ❌ 不要在源目录下创建子目录
- ❌ 不要自己猜测或构建路径
- ❌ 不要移动文件（必须复制后删除）
- ❌ 不要自由发挥修改流程

## ✅ 必须遵守的规则

1. **路径必须使用配置文件的值**
   - 源目录：`{source_dir}`
   - 资源目录：`{resource_base_dir}`

2. **关键词必须从原文提取**
   - 从 `**关键词**::` 字段提取
   - 排除 `excluded_tags` 中的标签

3. **必须验证每步操作**
   - 确认目录创建成功
   - 确认文件写入成功
   - 确认删除操作成功

4. **必须输出详细报告**
   - 成功/跳过/失败的文件列表
   - 每个文件的目标路径
   - 失败原因

## 📝 示例执行流程

用户说："整理今天的知识点"

你的执行：

```
1. 读取配置文件
   ✓ source_dir: F:\Obsidian\第二大脑\Archive_归档\knowladgeCollect
   ✓ resource_base_dir: F:\Obsidian\第二大脑\Resource_资源
   ✓ cleanup_source: false

2. 扫描源目录
   找到 5 个 .md 文件

3. 筛选当天文件
   待处理：2 个文件
   - 笔记_高手对话AI秘诀_2026-02-03.md
   - 笔记_0成本get圣诞胶片写真_2026-02-03.md

4. 处理文件 1/2
   文件：笔记_高手对话AI秘诀_2026-02-03.md
   转换文件名：highlight_高手对话AI秘诀_2026-02-03.md
   提取关键词：["提示词"]
   AI 整理... ✓
   写入：F:\Obsidian\第二大脑\Resource_资源\提示词\highlight_高手对话AI秘诀_2026-02-03.md ✓
   源文件已保留（cleanup_source=false）

5. 处理文件 2/2
   文件：笔记_0成本get圣诞胶片写真_2026-02-03.md
   转换文件名：highlight_0成本get圣诞胶片写真_2026-02-03.md
   提取关键词：["提示词", "AI生图"]
   AI 整理... ✓
   写入：F:\Obsidian\第二大脑\Resource_资源\提示词\highlight_0成本get圣诞胶片写真_2026-02-03.md ✓
   写入：F:\Obsidian\第二大脑\Resource_资源\AI生图\highlight_0成本get圣诞胶片写真_2026-02-03.md ✓
   源文件已保留（cleanup_source=false）

6. 输出报告
   ✅ 成功：2 个文件
   ❌ 失败：0 个文件
```

## 🔧 故障排除

如果遇到问题：

1. **配置文件读取失败**
   - 检查路径：`C:\Users\Administrator\.claude\skills\notes-deal\config\settings.json`
   - 确认文件存在

2. **目录不存在**
   - 使用 `mkdir -p` 创建
   - 不要继续执行，先解决问题

3. **文件写入失败**
   - 检查目标路径权限
   - 保留源文件，记录错误

4. **关键词提取失败**
   - 检查文件格式是否正确
   - 跳过该文件，记录警告

---

**重要**：本 Skill 的核心是严格按照配置文件执行，不要自由发挥！
