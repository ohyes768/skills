# 公共 RSS 发布 Skill 与跨平台脚本

## 目标

后续新功能只负责生成 Markdown、标题、频道、来源和内容唯一键，即可通过稳定命令发布到 RSS Relay；AI 使用公共 skill 找到入口，普通程序和定时任务直接调用脚本，无须复制 HTTP、查重和回执逻辑。用户已批准全量迁移并于本轮要求开始实施；任务已切换 in_progress。

## 已确认事实

- 当前来源包含新闻联播、工作复盘、港股研究/回测、两类宏观展望、WaytoAGI、B 站字幕，其内容校验、发布时机和重复规则各异。
- API 接收 title/content/channel/source/url，返回 id/created_at/detail_url，没有服务端幂等键。频道须已登记且启用。
- 文章保留 15 天，列表最多 200 篇、无分页，可按 id 读完整正文，不能支持无限历史或跨机器全局去重。
- 宏观脚本还负责质量校验和 macro 看板同步；WaytoAGI 有业务 token 回执，不能以公共投递回执替代。
- 仓库已有 skill-manager 管理 Hermes/OpenClaw 发布；Windows/Codex 需按实际安装根定位。证据见 research.md。

## 需求

- R1：公共 rss-relay-publish skill 与跨 Windows/Linux Python CLI，在任意工作目录可调用。
- R2：输入 Markdown 文件、标题、频道、来源、dedupe-key，可选原文 URL、配置覆盖和不发布的预览。正文不摘要、补写或执行业务章节校验。
- R3：统一配置、TLS、请求、响应校验、持久回执和读回核对；stdout 单个版本化 JSON，stderr 诊断，稳定退出码供调度器使用。
- R4：同环境持久回执防重，同键不同内容报告冲突。POST 结果不明时先核对，无法确认则报告待确认，不盲重发、不宣称成功；记录跨机器去重限制。
- R5：业务层保留发布授权、时机、频道、业务唯一键、质量校验及其他渠道发送；公共层不含业务分支。
- R6：skill 包自包含，沿用现有发布机制；不依赖另一业务项目内部路径或个人绝对路径，状态位于安装目录之外以保留升级回执。
- R7：提供新功能接入模板，并在本期迁移全部 8 类现有 RSS 来源。兼容业务回执、宏观看板同步及旧调用方退出码/输出字段；源码跨仓库迁移纳入范围，生产部署单独处理。

## 验收标准

- AC1（R1/R2/R6）：Windows PowerShell 与 Linux 各从包外目录调用同一脚本，读取带空格路径的中文 UTF-8 正文；调用方不增加 HTTP 代码，不要求第三方 Python 包。
- AC2（R2/R3）：dry-run 无网络发布及回执写入；模拟服务发布后按 id 读回正文与元数据一致才返回 published/verified=true。
- AC3（R3/R4）：同键重跑不 POST；同键改文冲突；并发同键、POST 后断连、进程中断、读回失败时不盲重发；不同频道/来源的同名文章不误判。
- AC4（R3/R4）：未知/停用频道、非法 JSON、空 id、正文不符和网络故障都有稳定结果，明确区分失败、待确认、重复、核对成功。
- AC5（R5/R7）：提供日期型报告和来源 ID 型内容两个接入例子；全部来源逐项验证原业务校验、身份规则、频道/source、回执及输出兼容，且真实 RSS 投递均经过公共入口，不残留业务层自建 HTTP 发布实现。
- AC6（R6）：安装根可解析，升级不清空外置回执；不把尚未提供的 Windows 自动安装写成既有能力。
- AC7：技能结构校验通过，自动测试使用本地假服务/隔离状态目录，不向真实 RSS、钉钉或看板发布。

## 不在本期范围

MCP、RSS 服务端改造、全局 exactly-once、创建定时任务、钉钉/微信发送、自动管理频道、修改保留期和生产部署。

## 已确认迁移范围（2026-11-05）

用户选择“本期迁移全部现有来源”。以下 8 类均为本期交付，分批实施不代表推迟到后续任务：

| 内容 | 源码位置（F:/personal-projects 下） | 兼容验收重点 |
|---|---|---|
| 新闻联播 | stock-info-dingding/xwlb_to_rss.py | 昨日摘要、xinwen、默认 dry-run、环境配置及退出码 |
| 每日工作复盘 | daily-review/daily_review.py | workreport、--push、无会话不发 RSS、原钉钉调用边界 |
| 港股研究 | skills/hk-ipo-research/ | hkipo、每只独立、招股期跨天更新、同日防重、原质量告警 |
| 港股回测 | skills/hk-ipo-backtest/，共享研究发布脚本 | hkipo、区分研究来源、成熟案例规则、无案例不发 |
| A 股宏观展望 | skills/finance-macro/a-share-macro-impact-skill/ | macro、标题/结论变化、strict、看板补发 |
| 利率债宏观展望 | skills/finance-macro/bond-market-macro-impact-skill/ | macro、业务 validator、看板补发 |
| WaytoAGI | skills/waytoagi-update-log/ | waytoagi、mention-doc 防重、多渠道回执、改为调用公共入口 |
| B 站字幕 | skills/bilibili-subtitle-rss/ | bilinote、用户推送授权、字幕产物及旧回执兼容 |

抖音独立 RSS 不纳入本次；csi300-brief 目前只读生成，不为其新增自动发布。所有迁移验证均使用假服务；不借迁移实际向钉钉/微信发送消息。详细顺序见 implement.md。
