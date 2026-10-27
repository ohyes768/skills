# report_inputs.json — 同源渲染输入合同

通常用 `report_inputs_builder.py` 按 spec 生成（构造时自动查绑定、格式与来源）；
特殊场景可直接手写本 JSON。
`run_pipeline.py report`（或 `render_report.py`）消费。
正文与 `report_claims.json` 由渲染器从结构化绑定**同时生成**——不手写正文再补引用，
禁止根据正文数值在 facts 里搜索碰巧相等的支持事实。渲染产物直接交给固定
`validate_report` 校验；渲染后篡改正文会被拒绝。

写 spec 前同时读[完整指标目录](metric-catalog.md)和[独立复核合同 A1–E1](independent-review-contract.md)。
下例只演示一个 section 的字段形状，不是完整可验收报告；完整标题与核心结论要求见[报告模板](report-template.md)。

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
| `decline_*` 前缀变体 | 值 ≤ 0 | 正幅度；表格单元格自动带「下降」前缀，statement 由模板措辞；值为正时阻塞 |

注意：`percent` 与 `pp` 的区别是"百分比"与"百分点"；比率水平用 `percent`，
比率的变化量（毛利率下降 2.3 个百分点）用 `pp`。

### 格式符选择（实跑教训：选错一次浪费一轮修复预算）

先判断数值的**语义类型**，再选格式符：

- **比值/水平类**（`cfo_to_net_profit_group`、`net_margin_group`、披露的资产负债率或毛利率事实）：
  值是当前水平，用 `percent*`，负值原样带负号输出，永远不用 `decline_*`。
- **降幅/变化量类**（同比 `*_yoy`、毛利率变动）：值为负表示下降，用 `decline_*`；
  值为正（实际增长）会被阻塞，此时换 `percent*` 并在模板写"增长/同比"。
- **表格行**用 `decline_*` 时单元格自动输出 `下降75.18%`（自包含方向词，校验器
  可独立匹配）；**statement 模板**用 `decline_*` 时模板必须自己写"下降/同比"方向词
  （`同比下降 {yoy:decline_percent2}`），否则校验器无法把正幅度匹配到负值。
- 判断口诀：这句话在描述"是多少"用 `percent*`；在描述"变了多少且在变差"用 `decline_*`。

## 程序强制的行为

- **claim 随片段生成**：每个 statement / 表格行各生成一条 claim，`fact_ids`、`metric_ids`、
  `evidence_ids`、`source_pages` 全部从台账解析，正文页码引用 `（PDF第N、M页）` 自动附加
  （`cite_pages: false` 可关闭）。
- **定量陈述必须绑定（数字校验 / 静态数字检查，`render_report._check_static_text`）**：
  数字按 `report_values.NUMBER_RE` 识别（含千分位、小数、正负号及 元/万元/亿元/% 单位）。
  两种文本宽严不同：
  - 模板静态文本（template 去掉占位符后、表格中的字符串单元格）只放行两类：
    紧跟 `PDF第` / `p.` 的整数页码；以及后接期间后缀（`年`、`上半年`、`下半年`、
    `Q1`–`Q4`、`H1`/`H2`、`第一季度` 等，即 `_PERIOD_SUFFIX_RE`）的四位整数年份。
    `2026年` 可以，单写 `2026`、`30%`、`3家` 都会被拒。
  - `paragraphs` 定性段落为严格模式：任何数字都拒，年份和页码也不例外。
  报错信息分别为 `static number in free text must be a year or page citation` 与
  `qualitative paragraphs must not contain numbers`；处理方式是把数字改成绑定占位符。
- **类型一致性**：amount 格式不能用于 ratio 值，反之亦然；`simplified_fcf` 视为 amount。
- **claim_type 约束**：`calculation` 必须有 metric 绑定；`fact` 必须有 fact 绑定。
- **标题自动生成**：document 元数据完整时正文标题固定为
  `{company_name}（{stock_code}）{year}分析`，与校验器豁免规则一致。
- **阻塞式输出**：任何渲染问题都不写 `analysis.md` / `report_claims.json`，只写
  `render_issues.json` 并以退出码 2 返回修复清单。

## 定性分析

`paragraphs` 支持自由文字（因果解释、风险讨论、不确定性说明），**禁止出现任何数字**——
包括年份与页码引用，与验收器的正文覆盖规则一致；需要数字或来源页码时改用
statement/table 绑定（页码由 `cite_pages` 自动附加）。指代位置写"详见下表来源标注"
这类无数字表达。语义正确性（因果是否成立、管理层解释是否充分）仍由 agent 复核——
机器校验不验证语义。
