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

### Step 1：确定待推送文章（增量查重，核心规则）

**禁止**用"最新一个有内容日期"作为推送目标——waytoagi 假期可能连续多天不更新，回退会导致同一批文章每天重复推送（2026-10 国庆曾连续 4 天重推同一批 8 篇）。

正确逻辑：

1. 遍历「近 7 日更新日志」**全部日期章节**，收集每篇文章的 `mention-doc` token
2. 读取已推回执（skill 目录下 `data/pushed_articles.json`），**过滤掉已推送的 token**
3. 剩余未推送的文章才是本次推送目标，按日期分组输出
4. 若没有未推送的文章 → 静默退出，不推送任何内容

- **指定日期（如"5月6日"）** → 只在原文档该日期章节内做上述过滤
- 已推文章即使被划进其他日期章节也必须跳过（token 是文章唯一标识，比日期章节更可靠）

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

**调用脚本**（在 skill 目录下执行）：
```bash
node scripts/send_dingtalk.js \
  "$DINGTALK_WEBHOOK" \
  "<完整markdown内容>"
```

> `DINGTALK_WEBHOOK` 从 skill 目录下的 `.env` 文件加载（`.env` 已被 `.gitignore` 排除）。

**注意：**
- 脚本会自动将 Markdown 包装为钉钉 `msgtype: markdown` 格式
- 标题自动渲染，链接 `[]()` 格式可点击
- 图片行（`![]()`）钉钉不支持自动忽略

### Step 7：推送成功后记录回执（必做，防重复的核心）

任一渠道（RSS / 钉钉）推送成功后，**立即**把这批文章的 mention-doc token 写入回执文件 `data/pushed_articles.json`（相对 skill 目录，`data/` 目录不存在则创建）：

```json
{
  "articles": {
    "<wiki_node_token_1>": "2026-10-07T10:03:00+08:00",
    "<wiki_node_token_2>": "2026-10-07T10:03:00+08:00"
  }
}
```

规则：
- key 是文章的 `mention-doc` token，value 是推送时间（ISO 8601）
- 更新时**保留**文件里已有的其他 token，只新增本次的
- 漏记回执 = 下次必然重复推送，推送成功但未写回执视为任务失败
- 回执只增不删；用户明确要求重推某篇时，先征得同意再删除对应 token

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