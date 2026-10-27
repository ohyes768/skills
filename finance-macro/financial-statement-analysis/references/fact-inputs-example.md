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
| evidence.locator | 表格必填 | `{"row": int, "col": int}`：table JSON 的 `rows[row][col]`，均从 0 起；文本证据可给 `{"line": int}`，为 excerpt 文件从 1 起的行号，详见下节 |
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

### 表格 locator：按 rows 与 headers 定位

从 `extraction_manifest.json` 找到该 evidence_id 对应的表格 JSON 文件，读取其 `headers`
和目标附近的 `rows` 即可定位，无需读取 `build_financials.py`。`locator.row` 是该文件
**`rows[]` 的 0 起下标，不是 PDF 页内行号，也不是去掉空行/分类行后的序号**。
`headers` 不计入 row；`rows` 内的分类占位行、空行都占下标，不得先过滤再计数。
`locator.col` 是该行数组的 **0 起下标**，科目名、附注和空单元格同样占列位。

例如某资产负债表抽取为：

```json
{
  "headers": ["项目", "附注", "2026年6月30日", "2025年12月31日"],
  "rows": [
    ["流动资产：", "", "", ""],
    ["货币资金", "七、1", "500,000,000.00", "450,000,000.00"]
  ]
}
```

这张表中 col=0 为科目名，col=1 为附注，数据从 col=2 开始；货币资金是 row=1，
不是 row=0。因此期末值用 `{"row": 1, "col": 2}`，上年末值用 `{"row": 1, "col": 3}`。
若报告期间从年初开始，上年末才对应期初 opening；仍须核对 document 的实际期间。

**列的数量与本期/上期顺序不固定**。上述 col=2 仅适用于该示例；没有附注列时数据列
可能从 col=1 开始，也可能比较期列在前。每张表都要根据 `headers` 的日期/期间判断，
再与 `period_ref` 配对；不能默认 col=2 总是本期，或 col=3 总是上期。
列头缺失、错位或无法确认期间时，不猜列义，改用可确认归属的文本证据或保留未验证状态。

### 文本 locator：excerpt 文件行号从 1 起

文本的 `locator.line` 是 evidence 对应 excerpt 文件按原样读取时的 **1 起行号**，
包含文件中的页码标记行、空行等；不是 PDF 页内行号，也不是 pages.jsonl 的下标。
不要删掉标记/空行后再数行。表格 `row=0` 指 rows 第一项，文本 `line=1` 指 excerpt 第一行，
两种基准不能混用。

### 同页多表与跨页表尾

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
同一标签行可被本期与比较期两条事实共用（`period_ref` 不同、`locator.line` 都指向标签行），
不要让其中一条指向数值行。

## 标签、空值与期末现金（实跑常见失败）

**标签按整行逐字照抄。** spec 生成器按"整行相等"匹配标签，不做包含匹配、不补括号。
长标签在 PDF 里折行时，**只抄折行前的第一行**，补齐后半截一定 `LABEL NOT FOUND`；
数值取标签行之后的连续金额行，跨行标签的数值落在 +2/+3 行属正常。
先在 excerpt 文件里找到确切字符串再写，不凭印象。常见写法：

| 科目 | 照抄的整行（示例，以本次原文为准） |
|---|---|
| 营业收入 | 利润表页首常是 `一、营业总收入`，`其中：营业收入` 可能在下一页，按所在页写 |
| 营业成本 | `其中：营业成本` |
| 营业利润 / 利润总额 / 净利润 | `三、营业利润（亏损以“-”号填列）` 等，折行则只抄第一行 |
| 归母净利润 | 三表中常折行；首页"主要会计数据"的 `归属于上市公司股东的净利润` 为单行，数值相同，优先取这里 |
| 归母净资产 | 同上，取 `归属于上市公司股东的净资产` |
| 资本开支 | `购建固定资产、无形资产和其他长期`（折行，只抄第一行） |
| 资产总计 | 注意与 `负债和所有者权益总计` 区分，按需要的那一行抄 |

负号按原文抄写（多为 ASCII `-`），不要换成全角破折号。

**期末现金只写本期。** 现金流量表"期末现金及现金等价物余额"的第二列是**上年同期期末**，
不是本期期初。把它写成 `prior` 会和 `ref: "opening"` 的真期初落在同一日期，
`cash_reconciliation` 直接 conflict。期末现金只写 `cur`；期初另起一条，
用"加：期初现金及现金等价物余额"并标 `ref: "opening"`。

**空值不填 0，也不填"—"。** 期初为空白的科目（如长期借款）只写 `cur` 并加 `note`
（如"期初未列示金额"）；spec 里写 `prior: "—"` 会报 `VALUE NOT FOUND`。
整行都没有金额的科目（如无商誉）直接不提交该事实，红旗相应项落为"资料不足"。

**切换计算模式会重排 fact_id。** 先跑过默认结构化模式、再改用 `--pdf-only` 重算后，
`fact_id` 会整体重新编号；report spec 里的绑定必须按 compute 新返回的事实重新对应，
沿用旧编号会静默绑到别的科目。

## 8 项红旗需要的科目

只提交三表主体时，部分红旗会因缺科目落为 `insufficient_data`。需要完整红旗基线时一并提交
（期末与期初两条）：

| 红旗 | 需要的科目 |
|---|---|
| 存贷双高 | `monetary_funds`、`short_term_borrowings`、`long_term_borrowings`、`revenue` |
| 应收暴增 | `accounts_receivable`、`revenue`（两期） |
| 存货突升 | `inventory`、`revenue`（两期） |
| CFO 为负而净利为正 | `cfo`、`net_profit_group` |
| 少数股东损益异常 | `net_profit_group`、`net_profit_owners`（两期） |
| 商誉占比高 | `goodwill`、`total_equity_owners` |
| 预付突升 | `prepayments`、`revenue`（两期） |
| 在建不转固 | `construction_in_progress`、`fixed_assets` |

借款行为空白时不要填 0，让存贷双高落为"资料不足"。两期集团净利润都为负时，
少数股东损益异常必然是 `insufficient_data`，这是正确结论，不要凑数。

## 指标与期间类型

duration（利润表/现金流量表）：`revenue`、`cost_of_sales`、`gross_profit`、`selling_expenses`、
`admin_expenses`、`finance_costs`、`r_and_d_expense`、`operating_profit`、`net_profit_before_tax`、
`income_tax_expense`、`net_profit_group`、`net_profit_owners`、`cfo`、`cfi`、`cff`、
`fx_effect_on_cash`、`capex_purchase_fixed_assets`。

instant（资产负债表）：`total_assets`、`total_liabilities`、`total_equity`、`total_equity_owners`、
`monetary_funds`、`cash_equivalents`、`accounts_receivable`、`notes_receivable`、`inventory`、
`fixed_assets`、`goodwill`、`total_current_assets`、`total_current_liabilities`、
`short_term_borrowings`、`long_term_borrowings`、`contract_liabilities`、`prepayments`、
`construction_in_progress`。

以上即 `financial_schema.METRIC_CONTRACTS` 的全部科目（测试锁定两者一致），无需读源码确认。

指标集需要扩展时属于维护变更：修改 `financial_schema.METRIC_CONTRACTS` 并补测试，
不在分析运行中临时注册。
