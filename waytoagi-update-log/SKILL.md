---
name: waytoagi-update-log
description: 自动追踪WaytoAGI知识库近7日更新日志，整理指定日期的文章列表（标题、说明、飞书Wiki链接）。当用户说"查看WaytoAGI更新日志"、"整理近7日文章"、"获取昨日文章"、"追踪WaytoAGI文章更新"时触发。
---

# WaytoAGI 更新日志追踪

## 核心能力

自动抓取 [WaytoAGI 知识库](https://waytoagi.feishu.cn/wiki/QPe5w5g7UisbEkkow8XcDmOpn8e) 的「近7日更新日志」板块，整理指定日期的文章列表。

## 输出格式

每个条目包含：
- **标题**：文章标题
- **说明**：一句话描述（从日志正文提取）
- **链接**：
  - **微信来源** → 提供微信原文链接 + 飞书Wiki备份链接（微信为主，Wiki作备）
  - **非微信来源**（博客、播客、社区等）→ 直接使用飞书Wiki链接

## 工作流程

### Step 1：确定目标日期

- **"昨日"** → 取近7日更新日志中**最新一个有内容的日期**
- **指定日期（如"5月6日"）** → 直接定位该日期章节
- **"近7日"** → 遍历全部日期章节

### Step 2：获取主文档

使用 `feishu_wiki_space_node` 和 `feishu_fetch_doc` 获取知识库主文档：

1. Wiki节点 token（从URL提取）：`QPe5w5g7UisbEkkow8XcDmOpn8e`
2. 通过 `feishu_wiki_space_node` action=get 获取 `obj_token`
3. 通过 `feishu_fetch_doc` 获取文档完整内容

### Step 3：定位更新日志

在文档中定位「🎏 近 7 日更新日志」章节，格式为：

```
### 5 月 6 日
- 《文章标题》文章说明...
- 《文章标题》文章说明...

### 4 月 30 日
- 《文章标题》文章说明...
```

每个条目是 `<mention-doc>` 格式，包含 `token="{wiki_node_token}"`。

### Step 4：提取文章链接

从 `<mention-doc token="XXX">` 中提取 `token` 即为Wiki节点token，组合Wiki链接：
`https://waytoagi.feishu.cn/wiki/{token}`

**然后检测来源（重要！）：**

1. 用 `feishu_fetch_doc` 获取该文章Wiki页面的完整内容
2. 在文档中查找 `> 🔗 原文链接：` 或 `🔗 原文链接：` 开头的行，提取微信/原站链接
3. 判断逻辑：
   - 如果原文链接包含 `weixin.qq.com` 或 `mp.weixin.qq.com` → **微信来源**
   - 否则 → **非微信来源**
4. 来源决定输出：
   - 微信来源 → 输出微信原文链接（优先），Wiki链接作备
   - 非微信来源 → 仅输出Wiki链接

### Step 5：输出结果

按日期分组输出，每篇文章格式：
```
**序号**. 《标题》

📝 说明文字

🔗 微信原文：https://mp.weixin.qq.com/...

🔗 飞书Wiki：https://waytoagi.feishu.cn/wiki/...
```

或（适用于非微信来源）：
```
**序号**. 《标题》

📝 说明文字

🔗 飞书Wiki：https://waytoagi.feishu.cn/wiki/...
```

**汇总标题行格式**：`## 📅 WaytoAGI 更新日志 · X月X日 更新 N 篇`

### Step 6：发送至钉钉（可选）

当用户明确要求"发送到钉钉"或"推送到钉钉"时，执行发送：

**钉钉 Webhook 地址**（从 skill 目录下的 `.env` 读取 `DINGTALK_WEBHOOK`，不要硬编码到调用方）：

```bash
# 在调用前先加载 .env
set -a; . "$(dirname $(readlink -f $0))/.env" 2>/dev/null; set +a
# 或者直接读
WEBHOOK=$(grep ^DINGTALK_WEBHOOK .env | cut -d= -f2-)
```

**调用脚本：**
```bash
node ~/.openclaw/workspace/skills/waytoagi-update-log/scripts/send_dingtalk.js \
  "$DINGTALK_WEBHOOK" \
  "<完整markdown内容>"
```

> `DINGTALK_WEBHOOK` 从 skill 目录下的 `.env` 文件加载（`.env` 已被 `.gitignore` 排除）。

**注意：**
- 脚本会自动将 Markdown 包装为钉钉 `msgtype: markdown` 格式
- 标题自动渲染，链接 `[]()` 格式可点击
- 图片行（`![]()`）钉钉不支持自动忽略

## 配置参考

详见 [references/config.md](references/config.md)

## 注意事项

- 文档可能很长（>50000字符），使用 `feishu_fetch_doc` 时关注"近7日更新日志"附近的区块
- 每条文章可能有配图，忽略图片只提取文字内容
- 如果某日期无文章，输出"该日期无更新文章"
- **链接策略（核心规则）**：
  - 微信来源 → 微信原文链接为主，Wiki链接作备
  - 非微信来源 → 仅输出Wiki链接
- 原文链接从文档正文顶部 `> 🔗 原文链接：` 或 `🔗 原文链接：` 字段提取
- 如果原文链接字段缺失，微信来源按"来源不明"处理并同时附上Wiki链接，非微信来源仅保留Wiki