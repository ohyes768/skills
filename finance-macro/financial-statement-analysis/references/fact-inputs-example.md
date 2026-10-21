# fact_inputs.json — 紧凑事实输入合同

简单场景由 `spec.json` 经 `compute --spec` 程序生成（见[可复用工具](reusable-tools.md)）；
表格 locator、缺失值、重复标签等复杂映射时由 agent 按本合同手写。
`run_pipeline.py compute`（或 `build_financials.py`）消费。
默认 compute 模式（东财 F10 结构化打底）下本文件角色是**抽查单**：只提交 3-5 个从
PDF 抽取的关键数字（带 evidence 定位），程序与东财结构化数据双源比对——一致由勾稽
去重消化，不一致记 conflict 并阻止报告 verified。
模型只提交需要判断的字段：指标映射、原文值、证据定位；公共公司、币种、期间结构、
归属维度、`fact_id`、`missing_reason` 全部由程序从 `document.json` / `source.json` /
`extraction_manifest.json` 推导。**`attribution` 不接受输入**——由指标合同固定
（`net_profit_owners` 恒为 `owners`），模型不能为了计算把 owners 改成 group。

## 完整示例

```json
{
  "schema_version": 1,
  "facts": [
    {
      "metric": "revenue",
      "raw_label": "营业收入",
      "raw_value": "1,234,567,890.12",
      "raw_unit": "元",
      "period_ref": "current",
      "evidence": {"evidence_id": "ev-0001", "locator": {"row": 0, "col": 1}}
    },
    {
      "metric": "cost_of_revenue",
      "raw_label": "营业成本",
      "raw_value": "(800,000,000.00)",
      "raw_unit": "元",
      "period_ref": "prior",
      "evidence": {"evidence_id": "ev-0001", "locator": {"row": 1, "col": 2}}
    },
    {
      "metric": "monetary_funds",
      "raw_label": "货币资金",
      "raw_value": "500,000,000.00",
      "raw_unit": "元",
      "period_ref": "closing",
      "evidence": {"evidence_id": "ev-0001", "locator": {"row": 2, "col": 1}}
    },
    {
      "metric": "cash_equivalents",
      "raw_label": "期末现金及现金等价物余额",
      "raw_value": "—",
      "raw_unit": "元",
      "period_ref": "closing",
      "note": "现金流量表附注未披露，仅资产负债表货币资金可用"
    },
    {
      "metric": "net_profit_owners",
      "raw_label": "归属于母公司股东的净利润",
      "raw_value": "123,456,789.00",
      "raw_unit": "元",
      "period_ref": "current",
      "review_status": "ambiguous",
      "evidence": {"evidence_id": "ev-0003"}
    }
  ]
}
```

## 字段说明

| 字段 | 必填 | 说明 |
|---|---|---|
| metric | 是 | 规范指标名或已注册别名；未注册则整项被拒（见下） |
| raw_label | 是 | PDF 原文标签，原样抄写（含括号注释可，程序会归一化定位） |
| raw_value | 是 | 原文字符串；`—`、`–`、`-`、`--`、空表示未披露，程序自动补 `missing_reason` |
| raw_unit | 是 | `元` / `千元` / `万元` / `亿元` |
| period_ref | 是 | duration 指标用 `current`（本期）/ `prior`（上年同期）；instant 指标用 `closing`（期末）/ `opening`（期初）；**必须与指标的 period_kind 匹配**（利润表/现金流量表科目是 duration，资产负债表科目是 instant），用错类型整项被拒 |
| scope | 否 | `consolidated`（默认）/ `parent`（母公司报表科目必须标 parent） |
| basis | 否 | `as_reported`（默认）/ `restated` |
| aggregation | 否 | duration 默认 `cumulative`；单季值显式给 `single_period` |
| review_status | 否 | 默认 `verified`（表示已对照原文核实）；`ambiguous` / `conflict` 需注明 |
| evidence | 数值必填 | `evidence_id` 必须存在于 extraction_manifest.json |
| evidence.locator | 表格必填 | `{"row": int, "col": int}`（0 起的数据行/列）；文本证据可给 `{"line": int}` |
| note | 否 | 备注或缺席原因补充，写入 `missing_reason` |

## 程序强制的行为

- **表格 cell 核对**：`rows[row][col]` 归一化后必须与 `raw_value` 一致，不一致阻塞并给出具体行列。
- **文本 label 核对**：`raw_label` 必须出现在证据文本（或指定行）中。
- **不可核对证据降级**：`image_crop` 或 `complete: false` 的证据不能支撑 `verified`，自动降为 `ambiguous` 并记录 warning。
- **别名不互通**：`货币资金`（monetary_funds）≠ `现金及现金等价物余额`（cash_equivalents）；
  `cost_of_revenue` 映射为 `cost_of_sales`。别名清单由 `financial_schema.metric_aliases()` 公开。
- **阻塞式输出**：任何 mapping/定位问题都不写 `financials.json`，只写
  `mapping_validation.json`（含 `input_index` 定位）并以退出码 2 返回修复清单。
- `document.json` 缺少可用期间时拒绝构造——先澄清期间，不猜默认值。

## 表格证据与文本证据的选择

同页双表、跨页表尾的内容归属一律按 [extraction-rules.md](extraction-rules.md) 的
"Same-page dual tables" 节处理：以"表标题 + 列头 + 科目行"判断归属，不按页码或
`section_id`；非该页第一张的表一律用 text 证据（`kind=text`）并用 `locator.line` 定位。此类场景的典型写法：

```json
{
  "metric": "contract_liabilities",
  "raw_label": "合同负债",
  "raw_value": "45,000,000.00",
  "raw_unit": "元",
  "period_ref": "closing",
  "evidence": {"evidence_id": "ev-0038", "locator": {"line": 12}}
}
```

注意：text 证据只校验 `raw_label` 出现，**不校验数值**；数值正确性由你对照原文负责。

## 指标与期间类型

duration（利润表/现金流量表）：`revenue`、`cost_of_sales`、`gross_profit`、`selling_expenses`、
`admin_expenses`、`finance_costs`、`r_and_d_expense`、`operating_profit`、`net_profit_before_tax`、
`income_tax_expense`、`net_profit_group`、`net_profit_owners`、`cfo`、`cfi`、`cff`、
`fx_effect_on_cash`、`capex_purchase_fixed_assets`。

instant（资产负债表）：`total_assets`、`total_liabilities`、`total_equity`、`total_equity_owners`、
`monetary_funds`、`cash_equivalents`、`accounts_receivable`、`notes_receivable`、`inventory`、
`fixed_assets`、`goodwill`、`total_current_assets`、`total_current_liabilities`、
`short_term_borrowings`、`long_term_borrowings`、`contract_liabilities`。

指标集需要扩展时属于维护变更：修改 `financial_schema.METRIC_CONTRACTS` 并补测试，
不在分析运行中临时注册。
