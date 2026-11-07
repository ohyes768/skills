# 新功能接入与部署

## 最短接入路径

先安装完整 dingtalk-push 包（含 scripts），将 `DINGTALK_PUSH_SKILL_DIR` 配为包的绝对路径；Hermes/OpenClaw 沿用 skill-manager 预览/发布，Windows/Codex 使用实际安装根。不新增同步器，不依赖其他业务项目目录。普通程序通过 argv 数组调用脚本并解析 JSON，不需要读取 skill 或导入 Python 模块。

PowerShell（变量需由实际安装位置配置）：

```powershell
python "$env:DINGTALK_PUSH_SKILL_DIR/scripts/dingtalk_send.py" send --title "沪深300简况 2026-11-06" --file "C:/reports/csi300.md" --keyword "沪深300" --dedupe-key "csi300:2026-11-06" --dry-run
```

Bash：

```bash
python3 "$DINGTALK_PUSH_SKILL_DIR/scripts/dingtalk_send.py" send --title "沪深300简况 2026-11-06" --file - --keyword "沪深300" --dedupe-key "csi300:2026-11-06" < /reports/csi300.md
```

正式已授权投递时去掉 dry-run。标题、关键词与唯一键由业务决定；正文通过 UTF-8 文件或 stdin 传入，避免把长正文拼进 shell 命令。

## 配置

CLI > 环境变量 > 默认值：

| CLI | 环境变量 | 默认 |
|---|---|---|
| --webhook | DINGTALK_WEBHOOK | 无（必须提供，或经 --env-file 提供） |
| --env-file | 无 | 无（文件内读 DINGTALK_WEBHOOK，可含注释与引号） |
| --state-dir | DINGTALK_PUSH_STATE_DIR | Windows LOCALAPPDATA/dingtalk-push；Linux XDG_STATE_HOME 或 ~/.local/state/dingtalk-push |
| --keyword | DINGTALK_KEYWORD | 无（群机器人关键词安全校验的预检词） |
| --timeout | DINGTALK_PUSH_TIMEOUT | 单次 POST 20 秒 |

webhook 形如 `https://oapi.dingtalk.com/robot/send?access_token=…`，加签（secret）机器人暂未支持，需要时扩展 `--secret`。TLS 使用系统信任 CA；oapi.dingtalk.com 证书有效，本包不提供 insecure 开关。

运行状态为 state-dir/receipts.sqlite3。身份 = webhook 摘要 + dedupe-key，摘要覆盖 title+text；同键内容不同会 conflict。多个同来源包装器必须共享状态目录，且只安排一个业务发送责任方。不同机器使用不同 SQLite 目录仍可能同时发送，不作分布式幂等保证。SQLite 状态应使用本机可靠磁盘。

## 输出、异常与恢复

JSON schema_version=1，固定字段 status/errcode/errmsg/dedupe_key/verification/error；错误对象包含 code/message。sent、duplicate、preview 退出 0；failed=2、unknown=3、conflict=4。诊断写 stderr，stdout 只留 JSON。父进程不要用短超时在 POST 后强杀子进程。

webhook/token 不会出现在任何输出里：错误信息与 errmsg 都经过 `access_token=…` 脱敏，回执只存 webhook 的 sha256 摘要前 16 位。

failed 的两种来源：请求根本没有发出（关键词预检、输入无效、连接被拒/DNS 失败），此时占位已释放，修正后重试是安全的；钉钉显式拒绝（HTTP 4xx 或 JSON `errcode≠0`，典型为 310000 关键词不匹配），同样释放占位，但同内容重试仍会被拒——先改内容或配置。

unknown 表示 POST 可能已送达：超时、响应被截断/损坏、HTTP 5xx、响应缺 errcode、或发现遗留 pending。重跑完全相同的命令只读回执，不会再次 POST。先人工到群里核对消息是否已出现；确有人工证据证明从未送达时，由维护者备份并清理该身份回执后才能重新发送。没有通用 force 开关，不要自动删除 SQLite 行或换随机键解除阻塞。

## 既有入口迁移

| 来源 | 接入方式 | 状态 |
|---|---|---|
| csi300-brief | `brief.py --push` 经公共 CLI 发送，键 `csi300:{price_as_of}`；skill 已于 2026-11-07 迁出至 stock-info-dingding 仓库 `csi300_brief/`（纯脚本，task-web 调度），委托 shim 随迁 | 已接入 |
| waytoagi-update-log（手动路径） | `scripts/send_dingtalk.js` 是定位 shim：仅 subprocess 调公共 CLI，自带 HTTP 已移除；title 固定「WaytoAGI 更新日报」+ `--keyword WaytoAGI`，正文可走 argv 或 stdin | 已接入 |
| waytoagi-update-log（cron 路径） | `scripts/cron_runner.js` 经 `send_dingtalk.js` 的 stdin 入口委托公共 CLI，本文件不再含 POST；`sent`/`duplicate` 都记录 `data/pushed_articles.json` 业务回执，failed/unknown 只报错不记 | 已接入 |
| daily-review（每日复盘） | 根目录 `dingtalk_relay_client.py` 定位 shim（探测含同级 `skills` 仓库），`daily_review.py` 键 `review:标题:正文摘要`，与 RSS 侧同约定；`sent`/`duplicate` 返回成功，webhook 缺失沿用原「跳过」语义 | 已接入 |
| 其他旧流程（stock-info-dingding 老项目等） | 独立脚本各自发送（gold/pusher、damai、natgeo），接入时逐个迁移 | 未开始 |

兼容 shim 定位顺序：`DINGTALK_PUSH_SKILL_DIR` > 逐级父目录探测（`dingtalk-push/scripts/dingtalk_send.py` 或 `personal-tools/dingtalk-push/scripts/dingtalk_send.py`）> `~/.hermes/skills`、`~/.codex/skills`、`~/.agents/skills`。找不到公共包时报错退出，不得回退内联 POST。

## 发布顺序与回滚

1. 发布公共包，配置外置 state 目录，先 dry-run 验证载荷与键。
2. 更新消费方（csi300-brief、waytoagi 手动与 cron 路径、daily-review）；waytoagi 的 `data/pushed_articles.json` 业务回执不变，daily-review 的 `.env` 只需原有 `DINGTALK_WEBHOOK`。
3. 用群机器人做一次真实小消息冒烟（需群管理员确认关键词配置），再挂到既有授权任务。

回滚时恢复业务旧调用入口，保留公共回执用于查证。加签机器人、多 webhook 路由、发送频率限制处理均需另行实施。
