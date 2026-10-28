# F10 接口与产物合同

## 数据源

唯一来源为东财 F10 datacenter 接口：
`https://datacenter.eastmoney.com/securities/api/data/v1/get`

| kind | reportName |
|---|---|
| balance | RPT_F10_FINANCE_GBALANCE |
| income | RPT_F10_FINANCE_GINCOME |
| cashflow | RPT_F10_FINANCE_GCASHFLOW |

查询参数为 columns=ALL、SECUCODE 和 REPORT_DATE 过滤、source=HSF10、client=PC。接口金额以元为单位；程序用 Decimal 解析并序列化为十进制字符串。证券与日期必须与请求一致。空 data 为 no_data；HTTP、业务错误、畸形响应为 fetch_failed，有限重试后保留问题。

## 产物

- document.json：代码、公司名、人民币、合并口径、累计报告期；不是额外数据来源。
- structured_financials.json：原始行按日期/报表保存，带 requested、response_sha256、fetched_at、fetch_failures。
- financials.json：source=structured_eastmoney，source_sha256 绑定留档文件字节；facts 每项包含 metric、value、raw_value、单位、币种、scope、attribution、period、basis、review_status、missing_reason。
- 普通事实 source=structured，source_ref 包含 security_code、report_kind、report_name、report_date、field、response_sha256。派生事实 source=derived，附 input_fact_ids、formula。来源字段由程序生成，agent 不编辑。
- metrics.json：十四项指标（含可用状态、公式、input_fact_ids）、现金勾稽与 red_flags。缺失值不参与数值绑定。
- report_spec.json：agent 撰写定性分析的唯一输入；report_inputs.json 由程序构造。
- analysis.md 与 report_claims.json：同源渲染。claim 记录实际正文、anchor、fact_ids、metric_ids、source_refs，引用必须等于绑定事实的来源闭包。
- report_validation.json、independent_review.json：来源/正文校验与独立复算结果；run_state.json 保存报告预算；context_usage.jsonl 记录交付量，未获模型 token 用量时留空。

本期、比较期和期初的缺失分别处理。空值有 missing_reason，不能使用未经支持的数字。无记录、错误记录、格式异常、NaN/Infinity 和维度不兼容不得转成可用事实。刷新后必须重新 compute 和 report。
