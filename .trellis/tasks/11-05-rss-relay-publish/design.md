# 技术设计

## 结构与职责

建议源码放 knowledge/rss-relay-publish/，包含 SKILL.md、scripts/rss_publish.py、references/integration.md、tests/test_rss_publish.py。Python 3.10+ 标准库实现，暂不制作 PyPI 包或常驻服务。

skill 负责发布场景、授权、安装位置解析、参数与结果解释；公共脚本是唯一投递实现。业务层生成内容及唯一键，通过 subprocess 调用，避免跨仓库 Python 导入依赖。报告 validator、macro 看板同步等仍在业务层。

## 命令契约

```text
python <skill-dir>/scripts/rss_publish.py publish --file <report.md> --title <title> --channel <channel> --source <source> --dedupe-key <key>
```

可选参数：--url、--dry-run、--base-url、--state-dir、--ca-file、--insecure。实现时提供 PowerShell/Bash 各自原生语法示例。正文按 UTF-8 读取（允许 BOM），不修改内容。空白必填字段拒绝；source/channel/key 的业务含义由调用方决定，日期按其业务时区生成，公共层不自动加入今天。

安装位置：AI 从已加载 skill 路径定位；普通脚本通过 RSS_RELAY_SKILL_DIR 或部署配置获取包根。不从 cwd 猜测。Hermes/OpenClaw 通过 skill-manager 登记/发布；Windows 使用实际安装根或变量，不另造同步工具。升级发布只更新代码，不覆盖运行状态。

配置优先级：CLI > RSS_RELAY_* 环境变量 > 默认 API 基址。默认基址 https://web.duomi77.cn:9443/rss/api/rss-relay，派生 /post、/posts、/post/{id}、/channels；内网可设 http://host:8099/api。不猜路径，不读取其他项目 .env，不需要 RSS 订阅 token。默认 TLS 校验，可指定 CA；insecure 需显式指定，对 GET/POST 一致生效。超时有限，输出不泄漏秘密。

## 去重与不确定结果

外置 SQLite 保存回执。默认 Windows LOCALAPPDATA/rss-relay-publish；Linux XDG_STATE_HOME/rss-relay-publish 或 ~/.local/state/rss-relay-publish；可覆盖，不写安装目录。身份为规范化 API 基址+channel+source+dedupe-key，保存五字段载荷摘要、id、detail_url、状态及核对时间。

1. 校验输入；dry-run 只预览，不网络发布、不写回执。
2. SQLite 事务原子占用身份为 pending；同键不同载荷返回 conflict；同键并发最多一个进程 POST。本地 confirmed 重跑返回 duplicate，历史记录不代表原文仍在保留期。
3. 无回执时读相同频道最近 200 篇；只将 source/title/url/content 全部相等的唯一文章视为候选，并按 id 核对后记录。标题不是唯一身份。列表失败不继续 POST。多个完整匹配归 unknown，交人工核查。
4. POST 201 且 id/detail_url 有效后先记录响应，再 GET /post/{id} 核对 id 与五字段；一致才置 confirmed 并报告 published。
5. 超时、断连、无法解释的响应或崩溃遗留 pending：已有 id 则按 id，否则按列表做有限 GET 核对。唯一匹配确认后恢复回执；没找到不能证明未写入，返回 unknown，下次重跑仅核对，不自动 POST。
6. 明确未接受的请求返回 failed；只有确认未被接受才允许修复后重新 POST。状态库不可写在发布前失败；发布后回执写失败属于 unknown。pending 不因超时自动释放。

限制：dedupe-key 是客户端字段，不是现有 API 参数，不嵌入正文、不借用 source/url。多机器不同状态目录仍可能并发重复，15 天/200 篇限制导致历史不可完整追溯；本期不承诺全局一次发布。独立版本应使用新键并在正文或标题体现版本，避免与完全相同的远端稿件混淆。integration.md 必须说明 unknown 查证、人工解除及回执丢失的处理方式；不默认暴露无条件 force 重发。

## 结果契约

stdout 单个 JSON：schema_version=1、status、id、detail_url、verified、verification（current/historical/none）、error（code/message 或 null），可附 warnings；诊断写 stderr。

| status | 退出码 | 含义 |
|---|---|---|
| published | 0 | 新写入，当前读回核对成功 |
| duplicate | 0 | 已发布，不重复写；核对范围见 verification |
| preview | 0 | dry-run 输入有效 |
| failed | 2 | 输入、配置或明确请求失败 |
| unknown | 3 | 可能已写入，需核查 |
| conflict | 4 | 同键不同载荷 |

verified=true 仅指本次完整读回一致。历史回执重复返回 verified=false/verification=historical，不能宣称当前文章仍可阅读。旧入口依赖不同字段/退出码时由其适配层转换。

## 兼容迁移

- B 站：按现有实现确认 BV/分P等实际身份规则，映射到键；保留字幕产物和旧回执兼容。
- 宏观：报告裁剪、告警、strict 与 macro 看板同步保留；RSS duplicate 也必须允许继续重试失败的看板同步。
- IPO：键区分日期/股票/研究或回测，不能因昨日报告跳过今天。
- WaytoAGI：mention-doc 与多渠道回执保留，不用公共 RSS 回执替代业务状态。
- daily-review/新闻联播：外部仓库本期迁移，保留 --push、dry-run 和调度器契约。
- csi300-brief：保留只读生成能力，由未来编排层调用发布 CLI。

生产发布、频道新增和定时任务均不在此次规划执行范围。回滚恢复旧业务入口/skill 版本，保留公共回执，不自动重推。

## 全量迁移决策与交付边界

用户已确认本期迁移全部现有来源。公共基础先完成，再分批接入，但所有 8 类均为本期验收要求。WaytoAGI 等仅在 skill 中描述 HTTP 的入口也要改为公共 CLI，不能只迁移 Python 文件。

跨仓库代码分别在 skills、daily-review、stock-info-dingding 的适用 Trellis/AGENTS 规范下实施；现有任务作为需求和集成验收入口。实施前核对外部仓库工作区、调用方、测试和可写权限；需要独立任务时关联本规划，不能因拆分遗漏交付。跨仓库未完成迁移不得将主任务标为完成。

迁移顺序与发布顺序不同：运行环境先安装公共包、配置稳定路径和外置状态，再切换业务入口；公共包不可用时返回明确失败，不静默走旧 POST 路径。首发前应导入或接管可核验的既有回执，禁止把“没公共回执”直接当成“从未发布”。不同包装器需要共享同一公共状态目录，同一内容须固定唯一业务发布责任方。

只删除重复的 RSS 传输职责，不删除宏观 validator/看板同步、B 站提取、业务去重或其他渠道实现。旧接口转换适配层可以保留；跨仓库提交与部署不由本次规划授权自动执行。

## 实现补充

所有 8 类来源已完成源码迁移。旧包装器保留 GET 业务查重，只有公共 CLI 执行 RSS POST；macro 看板 POST 留在原业务层。包内兼容定位 shim 以公共 scripts/rss_relay_client.py 为真源复制，跨仓库一致性由 test_clients.py 验证；新功能直接调用 CLI，无需复制 shim。

原换行发送，读回只允许服务端 CRLF/CR 到 LF 的文本存储等价，不放宽其他正文比较。WaytoAGI 用 SQLite 写锁覆盖整个旧 JSON 回执读/合并/原子替换；截断 HTTP 响应归入保守核对恢复。
