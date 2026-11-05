---
name: rss-relay-publish
description: 用于将已生成的 Markdown、文章或分析报告发布到个人 RSS 中转服务，或为新功能接入统一 RSS 投递入口；也用于预览、查重及发布结果核对。不负责生成正文、安排定时任务或发送钉钉和微信。
---

# 公共 RSS 发布

用本包 `scripts/rss_publish.py` 发布，Python 3.10+，无第三方依赖。已有业务 skill 保留其内容校验、授权、发布时机和业务回执；公共入口处理实际投递。

## 调用

用户要求发布，或当前已授权工作流包含 RSS 投递时执行。只查看、生成或预览内容时不发布；不能因为加载本 skill 就自动发送。

从本 skill 的实际安装位置解析脚本绝对路径；普通程序可将 `RSS_RELAY_SKILL_DIR` 设为本包目录。不依赖当前工作目录，不复制 POST 实现。

```text
python <skill-dir>/scripts/rss_publish.py publish --file <report.md> --title <title> --channel <channel> --source <feature-name> --dedupe-key <business-key>
```

`--file -` 从 UTF-8 stdin 接收正文。可选 `--url`、`--dry-run`、`--base-url`、`--state-dir`、`--timeout`、`--ca-file`、`--insecure`。详细参数、两平台示例及现有业务迁移约定见 [接入说明](references/integration.md)。新功能接入先读该说明。

频道须已登记且启用，默认不创建频道。正文原样发送，不在这里摘要或改写。默认验证 TLS，自签证书优先指定 CA；只在当前部署明确允许时显式使用 insecure。

## 内容身份和重试

调用方提供稳定唯一键：例如 `daily:2026-11-05` 或 `video:BV…`，按业务时区生成。身份还包括 API 基址、channel、source。同键不同载荷返回 conflict；只有明确要发布修订版时才换版本键，且标题或正文应体现修订。失败重试不能随机换键。

回执位于安装目录之外。共享同一来源的任务需配置同一 `RSS_RELAY_STATE_DIR`；安装或升级不要删除它。没有服务端幂等键，不能保证不同机器/不同状态目录下的全局一次发布。

## 判定结果

stdout 是单个 JSON，读取 status/id/detail_url/verified/verification，不仅检查退出码。

| status | 退出码 | 处理 |
|---|---|---|
| published | 0 | 当前正文与元数据已读回确认，可报告成功和详情链接 |
| duplicate | 0 | 不再发送；historical 只表示过去成功，不代表文章现在仍可访问 |
| preview | 0 | 仅预览，未发送 |
| failed | 2 | 修复输入、配置或明确拒绝原因后重试 |
| unknown | 3 | 可能已接收；同命令重跑只核对，不自动 POST。不能清回执或换键绕过 |
| conflict | 4 | 同键对应不同内容，检查是否误改正文或确有修订需求 |

文章目前只保留 15 天，列表最多 200 篇。查不到不等于从未发布。unknown 查证步骤见接入说明。
