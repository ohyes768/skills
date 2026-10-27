# report spec 自动生成（build_report_spec）

`report --build-spec` 从[报告骨架](report-spec-skeleton.json)生成 report spec，
省掉手工绑定 `fact_id` 的环节。生成结果是纯结构与绑定，**不含语义内容**——
`paragraphs` 仍是骨架里的占位说明，需 agent 按实际情况改写。

## 用法

```bash
# 一条命令走完 spec 生成 → 构造 → 预检 → 渲染 → 校验 → 独立复核
uv run --project . python scripts/run_pipeline.py report \
  --run-dir <运行目录> --build-spec --independent-review

# 只生成 spec（dry-run 看解析说明，不写文件）
uv run --project . python scripts/build_report_spec.py --run-dir <运行目录> --dry-run

# 只生成 spec 并落盘
uv run --project . python scripts/build_report_spec.py --run-dir <运行目录> --out spec.json
```

## 映射规则

| 骨架占位 | 解析规则 |
|---|---|
| `FACT_<科目>_CUR` | `financials.json` 里该科目的**本期/期末**事实 |
| `FACT_<科目>_PREV` | 比较期事实——**duration 科目取上年同期，instant 科目取上年末** |
| `metric_id` 绑定 | `metrics.json` 里 `status == computed` 且 `value` 非空 |

科目名映射表在 `scripts/build_report_spec.py` 的 `PLACEHOLDER_TO_METRIC`，
新增骨架科目时同步补这张表（有测试锁定覆盖率）。

**scope**：只取 `consolidated`。母公司（`parent`）事实不进正文——
骨架的「母公司口径」要求由 agent 在 anchor 或行 label 里明示「母公司」，
且独立复核 C4 会检查这一点，机器不自动替换。

## 裁剪规则

- 本次没有的科目（无商誉、无借款、无研发费用等）：**整行删除**，不填零
- `metric` 不可用（`not_applicable`、未计算）：整行删除，statement 整条删除
- `decline_*` 格式符遇到正值指标：自动改用 `percent*`（`decline_*` 只接受非正值，
  否则渲染阻塞）

## 输出

- `spec.json` — 生成的 spec（`report --build-spec` 时写入运行目录）
- `spec._paragraphs_todo` — **待 agent 改写的定性段落清单**（anchor + 序号 + 提示语片段）。
  骨架里「这里写…」「写清…」「逐条写明…」这类祈使句是写作提示，不是分析结论；
  报告阶段前必须按本次实际情况改写成真正的判断，否则成品里会留下提示语。
- stderr 上的 `[note]` 行 — 每个被丢弃的行/语句及原因，便于审计

## 不做什么

- **不写定性段落**。骨架里 `## 经营与三表分析`、`## 盈利质量与杜邦分解` 等章节的
  `paragraphs` 是「写清驱动方向」这类提示语，必须由 agent 按本次实际情况改写。
  `paragraphs` 是严格模式，任何数字都会被拒绝。待办位置由 `_paragraphs_todo` 标出。
- **不推断口径**。同一科目可能同时有合并与母公司两份事实，脚本只取合并口径；
  口径归属的判断由 agent 与独立复核 C4 负责。
- **不改上游标题约定**。标题固定为 `{公司}（{代码}）{结束年份}分析`，
  由 `validate_report` 按 `document.json` 强制匹配。
