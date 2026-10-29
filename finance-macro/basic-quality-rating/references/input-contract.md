# 调用方输入兼容合同

需要解释调用方字段时读本页。新流程 E 仍以独立 F10 包为准，输入财务值只作背景。

## 输入合同（30 字段）

`code`、`name` 必须非空，code 是字符串，保留前导零。其余字段可缺失或为 null。金额单位元，百分数字段的 `15` 表示 15%，不是 0.15。0 和负值是有效数字，不当作缺失。不得把缺失、无效类型或非有限数值补成 0。

| 字段 | 含义 |
|---|---|
| code / name | 股票代码 / 公司名称，输出原样返回 |
| sw_level1 / sw_level2 | 申万一级 / 二级行业 |
| yield_2023 / yield_2024 / yield_2025 / avg_yield_3y | 各年及三年平均股息率(%) |
| dividend_count_2023 / dividend_count_2024 / dividend_count_2025 | 各年分红次数 |
| payout_ratio | 分红比例(%) |
| roe / roe_year | 最近年度加权 ROE(%) / 年度 |
| roe_avg_3y / roe_history | 三年平均 ROE(%) / 历年 `[{"year":2025,"value":15}]` |
| annual_net_profit_ex_non_recurring / annual_profit_year | 年度扣非净利润(元) / 年度 |
| net_profit_ex_non_recurring_yoy / net_profit_cagr_3y | 年度扣非同比(%) / 扣非三年复合增速(%) |
| previous_quarter_yoy_pct / previous_quarter_label | 上一季单季扣非同比(%) / 报告期 |
| latest_quarter_yoy_pct / latest_quarter_label | 最新季单季扣非同比(%) / 报告期 |
| debt_asset_ratio / gross_profit_margin | 资产负债率(%) / 毛利率(%) |
| shareholder_count / shareholder_change_pct | 股东户数 / 变动幅度(%)，仅作背景 |
| eps / eps_year | 摊薄 EPS(元) / 年度，仅作背景 |

不同年度、年度与单季分别引用，禁止把三年均值写成十年、把累计同比写成单季或把股息率当作业务质量。股息率、EPS、股东户数及毛利率单独缺失不机械扣分；仅在对应论断需要时记录缺口。

输入 code/name 缺失或互相矛盾且无法核实时，终止本次分析并说明具体输入错误，供调用方按失败处理；不发起交互追问，不编造可入库的评级结果。后文输出合同适用于身份有效的完整评级或灰色地带报告；证据不足不等于输入身份错误。
