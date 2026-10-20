# report_inputs.json — 同源渲染输入合同

由 agent 编写，`run_pipeline.py report`（或 `render_report.py`）消费。
正文与 `report_claims.json` 由渲染器从结构化绑定**同时生成**——不手写正文再补引用，
禁止根据正文数值在 facts 里搜索碰巧相等的支持事实。渲染产物直接交给固定
`validate_report` 校验；渲染后篡改正文会被拒绝。

## 完整示例

```json
{
  "schema_version": 1,
  "report_title": "可选；document 元数据完整时程序自动生成标准标题",
  "sections": [
    {
      "anchor": "## 经营分析",
      "statements": [
        {
          "template": "2026上半年公司实现营业收入 {rev:amount_yi}，同比下降 {yoy:decline_percent2}。",
          "bindings": {
            "rev": {"fact_id": "f-0001"},
            "yoy": {"metric_id": "revenue_yoy"}
          },
          "claim_type": "calculation"
        }
      ],
      "paragraphs": [
        "收入下滑主要受行业需求收缩影响，公司未在管理层讨论中给出量化归因，需后续跟踪。"
      ],
      "table": {
        "display_unit": "亿元",
        "columns": ["指标", "本期", "同比"],
        "rows": [
          {"label": "营业收入", "cells": [{"fact_id": "f-0001", "format": "amount_yi"}]},
          {"label": "收入同比", "cells": [{"metric_id": "revenue_yoy", "format": "decline_percent1"}],
           "claim_type": "calculation"}
        ]
      }
    }
  ]
}
```

## 绑定与格式符

占位符 `{name:format}` 的 `name` 必须在 `bindings` 中定义，缺绑定、缺格式符都阻塞渲染。
每个绑定引用一个 `fact_id` 或 `metric_id`；金额单位与精度由格式符决定，
值来自台账（fact 必须 verified，metric 必须 computed）。

| 格式符 | 适用 | 输出示例（值 -1234567890.12 / -0.278） |
|---|---|---|
| `amount_yuan` / `amount_wan` / `amount_yi` | amount | `-1,234,567,890.12元` / `-123,456.79万元` / `-12.35亿元` |
| `percent0` / `percent1` / `percent2` | ratio | `-27.8%` / `-27.80%` |
| `pp0` / `pp1` / `pp2` | ratio | `-27.80个百分点` |
| `decline_*` 前缀变体 | 值 ≤ 0 | 输出正幅度（"下降 27.80%"）；值为正时阻塞（方向词与符号矛盾） |

注意：`percent` 与 `pp` 的区别是"百分比"与"百分点"；比率水平用 `percent`，
比率的变化量（毛利率下降 2.3 个百分点）用 `pp`。

## 程序强制的行为

- **claim 随片段生成**：每个 statement / 表格行各生成一条 claim，`fact_ids`、`metric_ids`、
  `evidence_ids`、`source_pages` 全部从台账解析，正文页码引用 `（PDF第N、M页）` 自动附加
  （`cite_pages: false` 可关闭）。
- **定量陈述必须绑定**：自由段落与模板静态文本中的数字只允许年份（`2026上半年`、`2026年`）
  和页码引用；出现其他静态数字阻塞渲染。
- **类型一致性**：amount 格式不能用于 ratio 值，反之亦然；`simplified_fcf` 视为 amount。
- **claim_type 约束**：`calculation` 必须有 metric 绑定；`fact` 必须有 fact 绑定。
- **标题自动生成**：document 元数据完整时正文标题固定为
  `{company_name}（{stock_code}）{year}分析`，与校验器豁免规则一致。
- **阻塞式输出**：任何渲染问题都不写 `analysis.md` / `report_claims.json`，只写
  `render_issues.json` 并以退出码 2 返回修复清单。

## 定性分析

`paragraphs` 支持自由文字（因果解释、风险讨论、不确定性说明），不强制绑定；
但其中出现定量陈述时必须改用 statement/table 显式绑定。语义正确性（因果是否成立、
管理层解释是否充分）仍由 agent 复核——机器校验不验证语义。
