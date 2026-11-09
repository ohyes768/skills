# 钉钉推送公共 skill 与 csi300/waytoagi 接入

## 背景

`personal-tools/waytoagi-update-log/scripts/send_dingtalk.js` 是仓库里唯一的钉钉发送实现，但它是业务内嵌脚本：title 硬编码「WaytoAGI 更新日报」、无超时、无回执去重、失败不区分 310000（关键词不匹配）与网络 unknown、只支持 Node。`investment-analysis/csi300-brief` 需要新增钉钉推送，按 rss-relay-publish 的既有范式（公共包 canonical CLI + 消费方薄接入）抽公共 skill，避免第二份漂移实现。

cron 关键路径 `cron_runner.js` 内联了自己的钉钉 POST，属于既有已上线流程，本轮**不迁移**，在文档中登记为后续项。

## 目标

1. 新建公共 skill `personal-tools/dingtalk-push`：canonical `scripts/dingtalk_send.py`（Python 3.10+，纯标准库），对齐 rss-relay-publish 的契约风格。
2. `waytoagi-update-log`：`send_dingtalk.js` 降级为定位 shim（argv 兼容：`node send_dingtalk.js "<webhook>" "<markdown>"`），文档同步。
3. `csi300-brief`：`brief.py` 增加 `--push`（自动标题/去重键），SKILL.md 更新。
4. 三处离线测试全部通过；README 增补索引。

## 范围

### dingtalk-push CLI

```
python dingtalk_send.py send --title <t> (--text <s> | --file <p|->)
     [--keyword <k>] [--dedupe-key <k>] [--webhook <url>] [--env-file <p>]
     [--state-dir <d>] [--timeout <sec>] [--dry-run]
```

- 载荷：`{msgtype:'markdown', markdown:{title, text}}`，POST 到群机器人 webhook。
- webhook 解析优先级：`--webhook` > 环境变量 `DINGTALK_WEBHOOK` > `--env-file` 中的 `DINGTALK_WEBHOOK`。webhook 及其 access_token 不得出现在 stdout/stderr/错误信息/回执。
- 关键词预检：给 `--keyword` 且 title/text 均不含该关键词时，发送前判 `failed`（不发起网络请求）。钉钉机器人关键词安全校验（310000）不可靠重试，预检省掉白跑。
- 回执：sqlite（state 目录在包外，默认 Windows LOCALAPPDATA/dingtalk-push，Linux XDG）。身份 = webhook 摘要 + dedupe-key；摘要 = sha256(title+text)。`pending` 在 POST 前落库，成功转 `confirmed`。
- 去重：同身份同摘要 → `duplicate`（exit 0，不重发）；同身份不同摘要 → `conflict`（exit 4）。未给 `--dedupe-key` 时自动用正文摘要键，重跑同内容不会刷屏。
- 结果判定：HTTP 200 + errcode=0 → `sent`；errcode≠0 → `failed`（显式拒绝，释放占位，可修正后重试）；连接被拒/DNS 失败（请求未发出）→ `failed`；超时/响应被截断/畸形成功 → `unknown`（exit 3，保留 pending，不自动重发）。
- 退出码：sent/duplicate/preview=0，failed=2，unknown=3，conflict=4。stdout 只有一个 JSON（schema_version=1），诊断走 stderr。
- `--dry-run` → `preview`，无网络、无回执写入。

### csi300-brief 接入

- `brief.py --push`：取数与概况生成不变；push 时标题默认「沪深300简况 {price_as_of}」，去重键 `csi300:{price_as_of}`，正文为 `summarize()` 原文；经 `--env-file`（skill 目录 .env）向公共 CLI 传 webhook，自身不接触 token。
- 定位公共 CLI：`DINGTALK_PUSH_SKILL_DIR` > 逐级父目录探测（与 rss_relay_client.py 相同策略）。找不到即报错，不回退内联 POST。
- stdout：概况一行 + 发送结果 JSON 一行；退出码 0（sent/duplicate）/继承 CLI 失败码；取数失败时与现状一致（exit 1，不推送）。
- SKILL.md 第 33 行「不调用钉钉」改为：默认只读；仅 `--push` 时经公共 dingtalk-push 投递。

### waytoagi 接入

- `send_dingtalk.js` 重写为 shim：定位 dingtalk_send.py，spawn `python`，传 `--title "WaytoAGI 更新日报" --keyword WaytoAGI --env-file <skill>/.env --file -`，argv[2] webhook 存在时传 `--webhook`。stdin=markdown，stdout/stderr 透传，退出码透传。
- SKILL.md Step 6 与 references/config.md：注明 canonical 为 dingtalk-push，脚本仅兼容入口；关键词坑文档保留。
- cron_runner.js 不改；在 SKILL.md 登记为后续迁移项。

## 验收

- [ ] `python -m unittest discover -s tests -v`（dingtalk-push 与 csi300-brief 两处）全绿；覆盖：成功发送、重复、冲突、关键词预检、310000、连接拒绝、超时 unknown、畸形响应 unknown、dry-run、env-file、token 不泄漏。
- [ ] shim 冒烟：`DINGTALK_PUSH_SKILL_DIR` 指向 stub 时 `node send_dingtalk.js` 透传退出码与 JSON。
- [ ] dry-run 演示两处消费方命令可行（无真实 webhook，不发起真实发送）。
- [ ] README 主题索引增补 dingtalk-push 行。

## 非目标

- 不创建 cron/定时任务；不迁移 cron_runner.js；不做真实群机器人发送（webhook 未提供）；不做加签/secret 校验型机器人（后续可扩展 `--secret`）。
