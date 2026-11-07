# 新功能接入与部署

## 最短接入路径

先安装完整 rss-relay-publish 包（含 scripts），将 RSS_RELAY_SKILL_DIR 配为包的绝对路径；Hermes/OpenClaw 沿用 skill-manager 预览/发布，Windows/Codex 使用实际安装根。不新增同步器，不依赖其他业务项目目录。普通程序通过 argv 数组调用脚本并解析 JSON，不需要读取 skill 或导入 Python 模块。

PowerShell（变量需由实际安装位置配置）：

```powershell
python "$env:RSS_RELAY_SKILL_DIR/scripts/rss_publish.py" publish --file "C:/reports/日报.md" --title "2026-11-05 新功能日报" --channel workreport --source new-feature --dedupe-key "daily:2026-11-05" --dry-run
```

Bash：

```bash
python3 "$RSS_RELAY_SKILL_DIR/scripts/rss_publish.py" publish --file '/reports/日报.md' --title '2026-11-05 新功能日报' --channel workreport --source new-feature --dedupe-key 'daily:2026-11-05' --dry-run
```

正式已授权投递时去掉 dry-run。标题、频道、来源和唯一键由业务决定。视频/文章等用稳定来源 ID，例如 `article:<mention-doc-token>`，同一文章不因日期变化重复发；日报用日期，修订版可加 `:v2` 并在标题体现修订。正文通过 UTF-8 文件或 `--file -` stdin 传入，避免把长正文拼进 shell 命令。

## 配置

CLI > 环境变量 > 默认值：

| CLI | 环境变量 | 默认 |
|---|---|---|
| --base-url | RSS_RELAY_BASE_URL | https://web.duomi77.cn:9443/rss/api/rss-relay |
| --state-dir | RSS_RELAY_STATE_DIR | Windows LOCALAPPDATA/rss-relay-publish；Linux XDG_STATE_HOME/rss-relay-publish 或 ~/.local/state/rss-relay-publish |
| --timeout | RSS_RELAY_TIMEOUT | 每个请求 20 秒 |
| --ca-file | RSS_RELAY_CA_FILE | 系统信任 CA |

base-url 是 API 基址，不带 /post；内网示例 http://rss-relay-backend:8099/api。旧业务脚本的 --endpoint/RSS_RELAY_URL 由各自适配层按原规则转换。显式 endpoint 优先于公共环境基址，修改旧业务部署时也要修改其旧配置。公共层不读取其他项目 .env，不需要 RSS 订阅 token，不把 token 放正文或日志。insecure 只接受显式 CLI 开关。

运行状态为 state-dir/receipts.sqlite3。数据库身份包含基址+channel+source+dedupe-key，摘要覆盖五字段载荷；同键内容不同会冲突。多个同来源包装器必须共享状态目录，且只安排一个业务发布责任方。不同机器使用不同 SQLite 目录仍可能同时发布，不作分布式幂等保证。SQLite 状态应使用本机可靠磁盘；不要把多机网络共享当分布式锁。

## 输出、异常与恢复

JSON schema_version=1，固定字段 status/id/detail_url/verified/verification/error；错误对象包含 code/message。published、duplicate、preview 退出 0；failed=2、unknown=3、conflict=4。诊断写 stderr，stdout 只留 JSON。父进程不要用短超时在 POST 后强杀子进程。

public duplicate 有两种：本地 confirmed 回执返回 historical/verified=false；远端找到唯一完整匹配并读回返回 current/verified=true。历史重复不会为了原文过期而重发。业务包装器可保留旧 duplicate=3 等退出码，调用它们时遵循原约定。

正文原换行发送；读回时只允许服务端文本存储的 CRLF/CR→LF 等价，其他正文和元数据变化均不算核对成功。服务端会去除开头空行，故以空行开头的正文可能读回不符并返回 unknown；业务应在生成最终稿时避免这种格式，公共层不偷偷裁剪正文。

unknown 表示 POST 可能成功或已有 pending。重跑完全相同的命令只做 GET 核对，不会再次 POST。先查询响应 id、对应频道文章和服务端日志，比较 source/title/url/content；不要因为列表里没找到就认定失败（列表只有 200 篇且保留 15 天）。能核对的同键重跑会自动恢复确认。

若仍无法核实，保留 pending 并报告待确认。确有人工证据证明从未接收，或用户明确要求独立修订发布后，才由维护者备份回执、核查该身份再安排新版本投递；没有通用 force 开关。不要自动删除 SQLite 行或换随机键解除阻塞。

## 既有入口迁移

兼容脚本附带 rss_relay_client.py 定位 shim：只 subprocess 调公共 CLI，不含 HTTP；其真源是公共包 scripts/rss_relay_client.py。源码仓库能自动发现 knowledge/rss-relay-publish；独立安装时部署公共包为同级 rss-relay-publish，或显式设置 RSS_RELAY_SKILL_DIR。不得找不到公共包时回退旧 POST。维护 shim 时运行 `python knowledge/rss-relay-publish/scripts/sync_shims.py` 同步全部副本（含仓库外兄弟项目），`tests/test_clients.py` 检查一致性；仓库 pre-commit 钩子（githooks/，core.hooksPath 已指向）在提交涉及 shim 时自动校验，副本漂移会被拒绝提交。

| 来源 | 公共键/原业务职责 |
|---|---|
| B 站字幕 | video:BV；继续优先查旧本地回执和远端 BV，保留字幕产物 |
| A 股/利率债 | macro:标题；保留同频道/source 标题防重、validator/strict 和看板同步；duplicate 仍补试看板 |
| 港股研究/回测 | 报告类型:标题；保留日/code/类型/来源防重、质量检查；--allow-duplicate 绕过旧业务预查，使用正文摘要版本键，仍不绕过公共安全回执 |
| WaytoAGI | article:token；prepared JSON 数组交 scripts/publish_articles.py，每篇成功即写旧 JSON 回执；失败保留前面成功项 |
| 每日复盘 | review:标题:正文摘要；保留 --push、无会话不发，正文变化视为重生成版本；其钉钉投递已改经公共 dingtalk-push CLI（daily-review/dingtalk_relay_client.py 定位） |
| 新闻联播 | news:标题；保留昨日摘要、RSS_DRY_RUN、URL 转换及 bool 返回，不再盲重试 POST |

宏观 --allow-duplicate 同样只允许以内容摘要区分修订，不会把相同稿件无条件发第二遍；失败重试用同一标题和正文。旧业务预查及旧回执保留，所以升级不会因公共库为空而自动重发历史稿件。

## 发布顺序与回滚

1. 发布公共包，配置外置状态和包根，先 dry-run。
2. 更新业务包及定位 shim；WaytoAGI 保留 data/pushed_articles.json，避免代码发布覆盖业务回执。该目录中新增的 lock.sqlite3 是写入锁，也保留。
3. 使用假服务核对渠道、来源、旧输出、回执和二次调用，再按原有授权部署任务；此次实现不创建 cron 或真实推文。

回滚恢复业务旧版本和调用入口，保留公共回执用于查证。MCP、服务端幂等、保留期变更均需另行实施。
