---
name: daily-pick-brief
description: 每日财报阅读选股播报 skill。Use when Hermes/task-web 需要运行 daily_pick 选股管线（财报候选筛选、去重、钉钉推送、Hermes 深度分析）。由 task-web 定时触发；脚本自带当日去重守卫与推送历史，不得绕过或手工改写历史文件。不适用于盘中实时选股或非财报类推荐。
---

# 每日财报阅读（daily-pick）

选股、去重、推送、深度分析全部由既有脚本链路完成，agent 不重写选股逻辑、不凭记忆补充股票事实。

> 来源：本 skill 的运行副本部署在 NAS `~/.hermes/skills/daily-pick-brief/`，
> 由本文件同步（2026-11-07 收编进版本管理）。业务代码在
> `stock-info-dingding` 仓库（NAS 路径 `/home/ohyes768/stock-info-dingding`），
> 本 skill 只做编排：跑脚本 + 判读输出。

## 流程

1. **执行主流程**（真实推送；守卫见下）：

```bash
cd /home/ohyes768/stock-info-dingding && DAILY_PICK_ONCE_DAILY=1 HERMES_SYNC=1 PUSH_MODE=1 python3 daily_pick.py
```

- 脚本内建守卫：`DAILY_PICK_ONCE_DAILY=1` 时若 `data/daily_pick_history.json` 显示今日已推送 → 自动跳过并输出"今日已推送 XXX"，属**正常结束**（退出码 0），如实转述即可，不是失败。
- 去重与推送历史由脚本维护（推送成功才落盘），agent 不得手工编辑历史文件。

2. **结果判读**：
- 退出码 0 且输出含"推送成功" → 转述推荐标的（代码/名称/一句话理由）；随后脚本会自动发起 Hermes 深度分析（同步或后台），无需 agent 重复发起。
- 退出码 0 且输出含"今日已推送" → 回复"今日已推送过（标的 XXX），本次未重复推送"。
- 退出码 0 且"今日无可推荐" → 如实转述。
- 退出码非 0 / 推送失败 → 如实报告 stderr 关键行，不得声称已推送。

## 边界

- 不得修改 SKILL.md、daily_pick.py、历史 JSON；不得额外推送第二遍。
- 最终回复只写：结果（推送成功/已跳过/无推荐/失败）+ 标的信息 + 深度分析是否已发起，不要粘贴全文。
