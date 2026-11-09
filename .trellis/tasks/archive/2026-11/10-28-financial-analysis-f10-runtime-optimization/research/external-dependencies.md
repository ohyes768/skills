# 外部依赖（2026-10-28 实施时未改）

本次只改了本仓库的 financial-statement-analysis。下面两项没有落地，不能算进 A5/A6 的完成证据。

## stock-info-dingding

2026-10-28 已在 `F:/personal-projects/stock-info-dingding` 的 `hermes_client.py` 把提示词改为 `f10-v3`：正式调用不加 `--include-report`，翻页只认顶层 `packet.next_cursor`，verified 且 terminal=true、next_action=null 后只回报状态和路径。发布仍在 Hermes completed 后读取绑定目录的 `analysis.md` 一次。该仓库改动尚未部署。Hermes 宿主的工具循环和读源码权限仍未改。

## Hermes

skill 在 verified 时返回 `terminal=true`、`next_action=null`。它不能关闭宿主工具循环，也不能收回读源码的权限。正常分析是否在终态后立即停止，要等宿主策略单独验收。

## 未做的回放

A6 要求同一留档、MiniMax-M3.1-flash 至少三次回放，并记录耗时、工具次数、API 次数、源码访问和 token。这次没有调用模型，也没有部署。优化前的 50 次工具、536.6 秒只作为基线留在 session-evidence.md，不能写成已经下降。
