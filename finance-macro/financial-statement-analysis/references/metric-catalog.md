# metrics.json 指标目录

写 report spec 前读取。以下是计算器支持的全部 14 个 `metric_id`；本次能否绑定仍以
compute 的 analyze 包为准：仅 `status == "computed"` 且 `value != null` 可数值引用。
`fact_id` 指披露事实，`metric_id` 指计算结果；事实字段 `metric` 不是 `metric_id`。

## 完整清单

公式同时列出所需事实。默认取目标期间合并口径、本期累计流量、集团归属；归母净利润同比取 owners。
`average X` 为目标期间期初与期末余额均值，期初日是目标期间开始日前一天。
同比比较期为上一年相同起止区间；币种、单位、重述口径必须兼容。

| metric_id | 含义 | 公式与所需事实 | 展示 |
|---|---|---|---|
| `revenue_yoy` | 营业收入同比 | `(revenue_cur - revenue_prev) / revenue_prev` | 百分比 |
| `net_profit_group_yoy` | 合并净利润同比 | `(net_profit_group_cur - net_profit_group_prev) / net_profit_group_prev` | 百分比 |
| `net_profit_owners_yoy` | 归母净利润同比 | `(net_profit_owners_cur - net_profit_owners_prev) / net_profit_owners_prev` | 百分比 |
| `net_margin_group` | 合并净利率 | `net_profit_group / revenue` | 百分比 |
| `cfo_to_net_profit_group` | 经营现金流/合并净利润 | `cfo / net_profit_group` | 百分比，说明比值含义 |
| `simplified_fcf` | 简化自由现金流 | `cfo - capex_purchase_fixed_assets` | 金额 |
| `roe_group_simple` | 集团简单 ROE | `net_profit_group / average total_equity` | 百分比，非披露加权归母 ROE |
| `dupont_net_margin` | 杜邦净利率 | `net_profit_group / revenue` | 百分比，同 net_margin_group 公式 |
| `dupont_asset_turnover` | 杜邦总资产周转率 | `revenue / average total_assets` | 当前格式器用百分比，未年化 |
| `dupont_equity_multiplier` | 杜邦权益乘数 | `average total_assets / average total_equity` | 当前格式器用百分比，说明倍率含义 |
| `roe_dupont` | 杜邦 ROE | `dupont_net_margin * dupont_asset_turnover * dupont_equity_multiplier` | 百分比，集团口径 |
| `receivable_turnover` | 应收账款周转率 | `revenue / average accounts_receivable` | 当前格式器用百分比，未年化 |
| `inventory_turnover` | 存货周转率 | `cost_of_sales / average inventory` | 当前格式器用百分比，未年化 |
| `accrual_ratio` | 应计比率 | `(net_profit_group - cfo) / average total_assets` | 百分比 |

没有 `net_margin`、`gross_margin`、`debt_ratio` 这些计算指标 ID，不要猜别名。
其他披露比率若已入事实台账，可绑定对应 fact_id；不临时发明 metric_id 或改 metrics.json。
`validation` 的 cash_reconciliation 和 `red_flags` 的 flag_id 不是 metric_id。

## 状态、单位与格式

- `computed`：有结果。比率值 `0.125` 用 `percent2` 显示 `12.50%`。
- `insufficient_data`：缺期间/期初余额、值为 null 或输入未核验；说明缺项，不填零。
- `not_applicable`：分母为零或负数（包括上年亏损时的净利润同比）；不强算增长率。
- `conflict`：值或计量维度冲突，基于原文修事实输入后 compute 重算。
  杜邦 ROE 的三因子任一不可用则不计算；有 conflict 传播 conflict，否则输出 insufficient_data。

仅 simplified_fcf 为 amount，按元/万元/亿元缩放；其余均视作 ratio。
完整格式符见 [report-inputs-example.md](report-inputs-example.md)。当前没有倍数、次数或天数格式符：
权益乘数值 `2` 用 percent2 输出 `200.00%`，需以定性文字解释资产与权益的比值。
不要绑定金额格式、手写未绑定的“2倍”或伪造格式符。
季度/半年流量计算的周转率与 ROE 不年化，不凭本期水平编同比。
`decline_*` 用于非正的下降变化量，负的比率水平用普通 percent；缺比较期比率不能写提升/下降若干百分点。

```json
{"template": "合并净利率为 {margin:percent2}。",
 "bindings": {"margin": {"metric_id": "net_margin_group"}},
 "claim_type": "calculation"}
```

仅在该指标 computed 时使用。验收条件见 [independent-review-contract.md](independent-review-contract.md)。
