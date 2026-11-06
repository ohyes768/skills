---
name: dingtalk-push
description: 用于将已生成的标题与 Markdown 正文投递到钉钉群机器人，或为新功能接入统一钉钉发送入口；带回执去重、关键词预检、unknown 不盲重与 token 不落日志。不负责生成正文、安排定时任务或发送 RSS/微信。
---

# 公共钉钉推送

用本包 `scripts/dingtalk_send.py` 发送，Python 3.10+，无第三方依赖。已有业务 skill 保留其内容生成、授权与发送时机；公共入口处理实际投递与幂等。

## 调用

用户要求推送钉钉，或当前已授权工作流包含钉钉投递时执行。只查看、生成或预览内容时不发送；不能因为加载本 skill 就自动发送。

从本 skill 的实际安装位置解析脚本绝对路径；普通程序可将 `DINGTALK_PUSH_SKILL_DIR` 设为本包目录。不依赖当前工作目录，不复制 POST 实现。

```text
python <skill-dir>/scripts/dingtalk_send.py send --title <标题> --file <正文.md或-> --keyword <群机器人关键词> --dedupe-key <业务键>
```

`--file -` 从 UTF-8 stdin 接收正文（也可用 `--text <正文>`）。可选 `--webhook`、`--env-file`、`--state-dir`、`--timeout`、`--dry-run`。详细参数、既有业务迁移约定见 [接入说明](references/integration.md)。新功能接入先读该说明。

## webhook 与关键词

- webhook 是群机器人唯一凭据，含 `access_token`。解析优先级：`--webhook` > 环境变量 `DINGTALK_WEBHOOK` > `--env-file` 中的 `DINGTALK_WEBHOOK`。`.env` 已被 gitignore 排除，不要把 webhook 硬编码进调用方或文档。
- webhook 及 token 绝不出现在 stdout、stderr、错误信息或回执中；回执只存 webhook 摘要。
- 群机器人可能开启**关键词安全校验**：正文/标题不含关键词时钉钉返回 `errcode 310000`，重发同样内容必然再被拒。给 `--keyword` 后，发送前预检 title/text，缺关键词直接 `failed`（不发起网络请求）。该关键词属群机器人配置，不是本包常量。

## 内容身份与重试

- 业务键：例如 `daily:2026-11-06`、`csi300:2026-11-06`。未给 `--dedupe-key` 时自动按标题+正文摘要生成键，重跑相同内容不会刷屏；修订版用稳定的新键并在标题体现。
- 回执位于安装目录之外的 state 目录（SQLite）。身份 = webhook 摘要 + dedupe-key，摘要 = sha256(title+text)。同键不同载荷返回 `conflict`。同一来源的任务需配置同一 `DINGTALK_PUSH_STATE_DIR`；安装或升级不要删除它。不同机器/不同状态目录之间不保证全局一次发送。
- `pending` 在 POST 前落库。钉钉没有读回/查询接口：超时或响应异常一律 `unknown`，重跑同命令只会核对回执，不会自动二次 POST。

## 判定结果

stdout 是单个 JSON（schema_version=1），读取 status/errcode/errmsg/dedupe_key/verification/error，不仅检查退出码。

| status | 退出码 | 处理 |
|---|---|---|
| sent | 0 | 钉钉确认 `errcode=0`，已投递到群 |
| duplicate | 0 | 回执已确认同一身份同一内容，不再发送 |
| preview | 0 | 仅预览（--dry-run），未发送 |
| failed | 2 | 显式拒绝（`errcode≠0`、关键词缺失、连接未建立、输入无效）；修正后重试 |
| unknown | 3 | 请求可能已送达（超时/响应损坏/pending 遗留）；不自动重发，先人工核对群消息 |
| conflict | 4 | 同键对应不同内容，检查是否误改正文或确有修订需求 |

图片行（`![]()`）钉钉不支持，发送前由业务过滤；`**粗体**`、`## 标题`、`[]()` 链接正常渲染。
