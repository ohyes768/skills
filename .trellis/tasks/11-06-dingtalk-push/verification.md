# Verification

Date: 2026-11-06（本任务与并行任务 11-06-csi300-dingtalk-push 协同完成）

## 关键过程

1. 本会话先建成公共包 `personal-tools/dingtalk-push`（canonical CLI，13→16 测试，TDD 红→绿）并把 waytoagi `send_dingtalk.js` 降级为 shim。
2. 期间并行会话独立实现了 csi300-brief 的钉钉推送（内嵌 `dingtalk_push.py`，in-process 传输），并把本会话已写到工作区的公共包/shim 一并提交（6835d1a「新增公共钉钉发送 skill，waytoagi 改为复用」）。经用户确认对方收尾后，按「立即统一到公共 CLI」策略收编。
3. 统一动作（本任务最终提交）：
   - 公共 CLI 收编对方更优的错误语义：`errcode=310000` → `error.code=keyword_rejected`；缺 webhook → `error.code=not_configured`（均 failed/exit 2）。
   - csi300 `dingtalk_push.py` 重写为纯委托层：无自带 HTTP，webhook 经环境变量传给公共 CLI（不进 argv），正文走 stdin，按标题日期推导回执键 `csi300:{date}`；状态映射 sent/duplicate→SENT、keyword_rejected→KEYWORD_MISSING、failed/conflict→REJECTED、unknown→UNKNOWN；退出码 0/2/2/4/3 与原 SKILL.md 完全一致。
   - csi300 传输测试重写为 stub-CLI 委托断言（ConfigTests 原样保留）；SKILL.md 修正「不做去重」为公共回执去重语义。

## 测试矩阵（全部离线通过）

| 套件 | 数量 | 结果 |
|---|---|---|
| personal-tools/dingtalk-push/tests | 16 | OK（成功/重复/冲突、关键词预检、310000 分类、连接拒绝、超时 unknown 不盲重、畸形响应、dry-run、env-file、token 不泄漏、优先级） |
| investment-analysis/csi300-brief/tests | 50 | OK（概况/TLS/fetch 原有 31 项 + 委托层 19 项） |
| waytoagi shim 冒烟 | 3 项 | 通过（argv 透传、退出码透传、真实 CLI 接线 failed JSON） |
| brief.py --push --dry-run（无 .env） | e2e | exit 2，stderr 输出 `not_configured` 中文 JSON |

## 遗留

- 真实群机器人冒烟未做（本机无 webhook；`.env` 待配置，DINGTALK_KEYWORD=ETF）。
- waytoagi `cron_runner.js` 仍内联钉钉 POST，待迁移到公共 CLI（见 dingtalk-push/references/integration.md 迁移表）。
- README 的 dingtalk-push 行已随 6835d1a 落库；其未提交的 README/financial-statement-analysis 改动属并行会话，本任务未触碰。
