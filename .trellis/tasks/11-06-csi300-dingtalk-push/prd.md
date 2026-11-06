# csi300-brief 钉钉推送

## Goal

让 `csi300-brief` 生成的沪深300概况能直接投递到钉钉群机器人，供定时任务复用；取值、解读与文案规则保持不变。

## 背景

`scripts/brief.py` 目前只 GET 只读接口并把文本打印到 stdout，`SKILL.md` 明确写了「不调用…钉钉或 RSS 写入接口」。目标群机器人开了关键词校验，关键词为 `ETF`。`waytoagi-update-log/scripts/send_dingtalk.js` 是 node 实现且 title 硬编码为「WaytoAGI 更新日报」，不能直接复用。

## Requirements

- **R1 发送模块**：新增 `scripts/dingtalk_push.py`，仅标准库；读取 `.env` 的 `DINGTALK_WEBHOOK`，以 `msgtype=markdown` POST，返回结构化结果 JSON（`schema_version/status/errcode/errmsg`）。
- **R2 brief.py 开关**：新增 `--push`、`--title`、`--env-file`、`--keyword`、`--push-timeout`、`--dry-run`。stdout 仍然只输出概况文本，推送结果写 stderr，不破坏现有调用方。
- **R3 关键词前置校验**：`title+text` 不含关键词时本地直接失败、不发起 HTTP，避免 `310000 关键词不匹配`。
- **R4 结果分类**：`sent` / `dry_run` / `keyword_missing` / `not_configured` / `rejected` / `unknown`，退出码 0/0/2/2/4/3；`unknown` 表示可能已送达，禁止自动重试。
- **R5 配置**：新增 `.env.example`，只含 `DINGTALK_WEBHOOK`、`DINGTALK_KEYWORD`；token 不硬编码、不打印、不落 git。

## Non-goals

- 不改动 `waytoagi-update-log` 的 cron 与 `send_dingtalk.js`。
- 不实现回执与去重（重复推送只多一条消息，防重仍由调用方负责）。
- 不引入 node 或第三方 Python 依赖。
- 不抽取公共 `dingtalk-push` skill（后续若两个消费方都稳定再收编，参照 `rss-relay-publish`）。

## Acceptance Criteria

- [ ] `python scripts/brief.py --push --dry-run` 输出概况且不发请求，明确告知将发送的标题。
- [ ] 关键词缺失时退出码 2 且未发起 HTTP。
- [ ] `errcode=0` 退出 0；`310000` 退出 2 并提示关键词；`URLerror`/超时退出 3；其余 `errcode` 退出 4。
- [ ] 现有 `tests/test_brief.py` 全绿，新增推送测试覆盖关键词、错误分类、超时与 env 解析。
- [ ] `SKILL.md` 写明 env 键名、`--push` 用法、关键词约束与退出码。
