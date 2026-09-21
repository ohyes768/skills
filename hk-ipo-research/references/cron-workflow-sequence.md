# Cron Workflow Sequence (proven)

每次 cron 触发跑港股打新研究时，按以下顺序执行；实测 2026-08-17 君正股份（03223）一次完成 ~14 次工具调用 + 推送。

## 阶段 0：发现（1 次调用）

```bash
python3 ~/.hermes/skills/hk-ipo-research/scripts/daily_rss_report.py \
  --date $(date +%Y-%m-%d) \
  --output /tmp/hk-ipo-discovery.md
```

- 解析输出"今天确认有 **N 只**仍在招股"
- N = 0 → 直接返回 `[SILENT]`，结束
- N ≥ 1 → 取 N 个 code 进入阶段 1

## 阶段 1：每只 IPO 并行/串行研究（每只 ≤ 8 次调用）

实际序列（按调用顺序）：

| # | 调用 | 目的 | 失败兜底 |
|---|---|---|---|
| 1 | `jisilu list --json` | **结构化主源**：招股期、发行价、入场费、总股本、募资、市值、保荐人、招股章程 URL | 改用 daily_rss_report.py 输出 |
| 2 | `tradesmart tracker <CODE>` | 实时孖展 | 首日通常空，写 `未找到（招股首日）` |
| 3 | `analyze <CODE>` | 聚合元数据（依赖 tracker） | **try/except ValueError；用 jisilu 已拿到的字段填充**，不阻塞 |
| 4 | `web_search` × 1（财务）| A 股财报 / 业绩快报 / 公告 | 换 site: / 关键词组合 |
| 5 | `web_search` × 1（基石 + 招股结构）| 智通财经 / 360kuai / 财联社 | 换新浪 / 雪球 |
| 6 | `web_search` × 1（保荐人历史）| 港股评级汇总 / 国泰海通历史战绩 | jisilu `--sponsor <X>` 兜底 |
| 7 | `curl + search_files`（本地 HTML）| 落本地 + grep 关键数字 | 文件已存在 grep 仍失败 → 改用 meta description |
| 8 | `write_file`（最终 Markdown）| 一只一篇，`<!-- HK_IPO_REPORT_START -->` 起 | — |
| 9 | `push_rss.py` | RSS 推送（必须执行） | 见 SKILL.md PITFALLS #10 |

## 阶段 2：推送

```bash
python3 ~/.hermes/skills/hk-ipo-research/scripts/push_rss.py \
  ~/.hermes/cron/output/hk-ipo-daily-YYYY-MM-DD-<CODE>.md \
  --title "YYYY-MM-DD 港股打新｜公司名（00000.HK）｜66分 B" \
  --endpoint https://web.duomi77.cn:9443/rss/api/rss-relay/post \
  --source hk-ipo-research \
  --insecure
```

## 关键约束

- **不要**用 `execute_code` 跑 Python（cron 上下文通常无审批，工具直接拒绝）；改用 `terminal` + `curl` + `search_files`。
- **不要**用 `web_extract` 抓 SearXNG-only 源（返回 `cannot extract URL content`）；直接落本地 HTML 后 grep。
- **不要**抓 HKEX 招股书 PDF（反爬 + 2KB 错误页）；用招股章程 URL 仅作"读者链接"展示，财务/股东数据全部走实时全网搜索。
- **不要**为同一只 IPO 重复跑同一个失败的源（参见 SKILL.md PITFALLS #6）；超时 30 秒切下一源。
- **不要**在没有 `<!-- HK_IPO_REPORT_START -->` 标记的情况下写报告 — `push_rss.py` 会按 cron-recovery.md 裁剪但计入 `quality_warnings`。

## 预算

- 1 只 IPO：约 14 次调用（实测 2026-08-17）
- 2-3 只 IPO：约 30 次调用上限（SKILL.md PITFALLS #10）
- ≥ 4 只 IPO：按评分排序只深度研究前 2-3 只，其余仅标 `待手工核对`

## 验证 checklist

推送成功后确认返回 JSON：

```json
{"pushed": true, "response": {"id": "...", "created_at": "..."}, "quality_warnings": [...]}
```

- `pushed == true` 是成功标志
- `quality_warnings` 是数据缺失告警，**默认不阻断推送**；只有显式传 `--strict` 才阻断
- 不要因为 warnings 而重推；当日同 code 已发过则跳过

## 报告标题命名约定（实测 2026-08-18）

为避免 `push_rss.py` 章节检查的子串误报，二级标题**不要加编号前缀**：

```markdown
## 关键 Offer Terms
## 热度
## 财务基本面
## 业务与股东
## 评分
## 建议
## 风险提示
## 数据来源
```

章节内子结构用三级或四级编号（如 `### 阶段 1：…`、`#### 估值对比`）即可保留层次。`## 1. 关键 Offer Terms` 这种带 `N. ` 前缀的写法会导致 `push_rss.py` 把整组章节报为"缺少"，虽然 `pushed == true` 仍成功，但质量分会被压低。详见 SKILL.md PITFALLS #16。

## 实测调用序列（2026-08-18 君正股份 03223）

本场实测 14 次调用全部成功，预算 ~50% 消耗：