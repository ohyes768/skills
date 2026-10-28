# 保险：寿险、产险与综合集团的 E 评分

用于申万保险子行业。保险不是银行，也不能使用普通企业的资产负债率阈值。
先确认研究对象是寿险、产险还是综合保险集团，再生成独立 insurance-data.json。
原 stock.json 保留；最终仍为五维、固定十字段、任一维 null 则无总星级。

需要结构化补数时先读 [接口取数与缺口](financial-data-api.md)：免费脚本返回候选及原始出处，官方核对后才入下述评分包。

## 取数和预算

```text
python3 <skill目录>/scripts/insurance_financial.py template --stock stock.json --as-of 2026-10-27 --type group
```

--type 为 life / property / group。将模板 stdout 存入 insurance-data.json 后填入确认值。
优先复用已有结构化数据，再读取上市公司/保险法人官网、交易所公告正文及偿付能力摘要的
可读网页。保留来源链接、栏目/表格/行列位置，核对主体、年份、单位、表头、脚注与精算假设。
不从新闻或搜索摘要猜值。正文缺关键表格、表头或脚注时，按 [有限 PDF 补证](pdf-fallback.md)
用现成工具读官方原件相关页，不默认通读 PDF。无工具或原预算内仍缺核心证据则 E=null。

```text
python3 <skill目录>/scripts/research_state.py init --state research.json --stock stock.json --providers <已有渠道ID列表> --insurance-research
```

E 使用 financial 维度，必要主题为 profitability、solvency、insurance_business、asset_liability。
start/result/close 用法见 [取证控制](research-control.md)。所有指标共用一次初查和两轮补查，
沿用全局渠道故障、已读原文与具体冲突一次重开规则，不能按子公司或换关键词重置预算。
已有 A-D 账本可追加保险模式，保留已耗预算；既有银行 E 模式不能改成保险重置预算。
查齐并解决影响分档的冲突再 complete；核心缺口到上限则 gap，E=null。

## 证据包：三个层次分开

顶层：schema_version=1、code/name、stock_sha256、as_of、insurance_type、reports、entities、coverage。
身份与原始输入哈希绑定；as_of 是实际研究截止日，不得为绕过缺口修改。

| 层次 | 内容 | 必须分清的口径 |
|---|---|---|
| 上市集团 reports | 三年财务加权 ROE；集团型最新集团偿付能力 | 集团不能拿银行 ROE 或寿险营运 ROE 替代 |
| 保险法人 entities | 每个重要寿险/产险法人的核心/综合偿付能力、风险综合评级及业务指标 | 不平均各法人偿付能力，不拿集团比例冒充法人比例 |
| 业务覆盖 coverage | 说明重要保险主体及银行/资管等非保险分部的核查范围、重要性和风险 | 平安银行的指标只是银行分部证据，不能代表保险集团安全性 |

脚本只校验数据与引用结构，不证明资料真实、未遗漏重要子公司或监管要求。
coverage 必须基于集团分部披露解释为什么这些主体足以覆盖重要风险；不得用空数组假装
平安没有银行或资管业务。小型非重要主体的排除也要有事实和重要性说明。

每个数字对象形如：

```json
{"value":150,"unit":"pct","basis":"point_in_time","source_url":"https://example.com/solvency","locator":"偿付能力指标表，寿险法人，当期期末列"}
```

这只是格式示例，不是真实公司数据。pct 的150表示150%；金额统一 cny_million（人民币百万元）。
原表单位亿元必须明确换算、保留原表出处，不能只改单位标签。数字不接受字符串、布尔值或非有限值。
未知指标省略，不把 null 补0；零和负值有实际含义时保留。

### 上市集团 reports

每行含 period_end、published_at、period_type、scope=group、metrics。
period_type 为 annual（12月31日）、interim（6月30日）或 quarter（3月31日/9月30日/12月31日）。
最近三年年度 metrics.roe 为普通股股东财务加权ROE，unit=pct、basis=period。
不混用营运ROE、扣非ROE或半年年化ROE。集团型最新行还需 group_solvency_ratio，pct/point_in_time。

年度窗口规则同银行：5月起要求上一完整年度及前两年；1—4月新年报尚未提供时才可退一个年度。
最新快照超过400天、未来披露、重复期间、混合口径会阻止评分；有更近资料应取更近期间，
不能故意省略更新但不完整的报告，用旧完整报告凑分。工具不能证明网上没有更新披露。

### 保险法人 entities

每个主体含 id、name、kind=life|property、scope=solo、latest、risk_rating、annuals、assessments。
集团型至少有重要寿险和产险主体；单类发行人只使用相应类型主体。
latest 含 period_end、published_at、metrics，其报告期必须与集团最新快照一致。
核心指标 core_solvency / comprehensive_solvency 均为pct/point_in_time。

risk_rating 含 value、period_end、published_at、source_url、locator。
value 为风险综合评级 AAA/AA/A 或 BBB/BB/B 或 C/D；不能填监管“1—5级”或本 skill 的星级。
该评级可以较偿付能力快照滞后，但不超过183天；不得使用快照之后的评级期间，
也不得使用截止日之后才披露的结果。缺风险综合评级不能仅凭两个比例宣称偿付能力达标。

annuals 为同样的三年年度窗口，scope=solo，额外提供 comparability_id：

- 寿险：value_metric=nbv 或 new_business_csm；三年均提供对应业务价值（cny_million/period）
  及 net_investment_yield（pct/period）。不能用投资收益率高就认定没有利差损。
- 产险：三年 combined_ratio（pct/period），核对保险服务收入、再保险及费用定义。

同一主体三年 comparability_id 必须一致，且须有原文支持假设/会计口径已对齐。
仅把标签改成一样不是真正可比；NBV、CSM不是监管资本指标。
**中国平安2024年摘要就是典型陷阱**：总览表的原披露比较数与后面的重述比较数不同，
必须读估值假设脚注，不能抓到三个相邻数字就计算增长。无法取得可比历史时明确缺口。

可选 csm_balance（金额/point_in_time）、continuation_ratio、surrender_ratio、
total_investment_yield、comprehensive_investment_yield（pct/period）、net_profit（金额/period）。
缺少这些辅助项目不自动扣分，也不要求给保险本体补银行的不良率/拨备覆盖率。

### 准备金、资产负债匹配与覆盖评估

各主体 assessments 必须含 asset_liability 和 reserves，均用下述格式：

```json
{"status":"unknown","statement":"说明已核对的事实及剩余缺口","period_end":"2026-06-30","published_at":"2026-08-25","source_url":"https://example.com/results","locator":"网页栏目、表格和主体"}
```

status=supported 表示有具体证据支持本次研究判断且未发现未解决的重大问题；adverse 表示已确认弱项，
unknown 表示判断依据不足。前者不能仅用“审计无保留意见”充数。准备金要核查保险负债/赔款准备金
及变动依据；匹配要核查资产与保险负债、利率与流动性压力，不只列一个投资收益率。
期间须与主体最新快照一致，披露日不晚于 as_of。报告说明这是分析者据来源形成的判断，非工具认证。

coverage 也使用该格式，另含 entity_ids（与 entities 的ID恰好相同）和 other_segments 数组。
每个重要非保险分部含 name、kind=bank|asset_management|other 及同样的评估字段；
不能把该分部“未取得资料”写成 supported，也不能凭集团整体盈利掩盖已确认的重大亏损或资本风险。

## insurance-research-v1 分档

这是尚未实证校准的研究规则，不是监管评级、信用评级或未来收益预测。
基础分取集团三年平均财务ROE：≥15/12/8/5分别为5/4/3/2，否则1。
最终E取基础分及以下上限中的最低值，不用强子公司抵消弱子公司。

| 项目 | 研究分档或上限 |
|---|---|
| 法人核心偿付能力 | ≥150/120/100/75为5/4/3/2，否则1 |
| 法人综合偿付能力 | ≥250/200/150/120为5/4/3/2，否则1 |
| 风险综合评级 | A系列上限5，B系列上限4；C/D上限1 |
| 集团综合偿付能力 | 使用综合比例质量分档；不编造集团核心50%的要求 |
| 寿险可比新业务价值 | 最近年度下降≥20%上限2；较小下降上限3；最近值≤0上限2 |
| 产险三年平均综合成本率 | ≤95/98/100/103为5/4/3/2，否则1；最新年度>100上限2，>105上限1 |
| 准备金已确认不利 | 上限1 |
| 匹配、集团覆盖或重要非保险分部已确认不利 | 上限2 |

寿险前期价值≤0时不编造增长率；投资收益率保留数值与趋势，不设置任意统一优秀线，
不在没有可比负债成本时计算利差。产险综合成本率>100说明承保亏损，不能写成监管资本违规。

适用偿付能力规则的核心比例50%、综合比例100%、风险综合评级B类及以上是明确的条件，
与本研究优秀线分开。可以指出某项已核实条件不足，不能仅凭三个项目宣称“全面监管合规”。
任何必需证据缺失、冲突或评估unknown，E仍为null；已核实弱点照常保留，不用缺失制造低分。

## 校验与交付

```text
python3 <skill目录>/scripts/rating_math.py financial --input stock.json --insurance-data insurance-data.json
python3 <skill目录>/scripts/rating_math.py finalize --input draft.json --stock stock.json --check-financial --insurance-data insurance-data.json --research-state research.json
```

正常运行直接 financial → finalize，financial 内已校验证据包；独立 validate 仅用于修包诊断。
显式保险包不能和银行包同时提供，也不能给其他行业用。finalize 要求E与该保险包计算一致，
正常流程提供取证账本，必须是保险模式且已结案；不把证据包加进最终十字段。
兼容API不传 --research-state 时仅校验数值/结构，不证明取证流程已完成，不能据此宣称完整验收。
报告列主体、指标、期间、来源、评估依据、具体缺口及研究分档限制。
只读 validator 也支持相同 --insurance-data --stock --check-financial；已通过后不重复做同样数值校验。

监管依据：[保险公司偿付能力管理规定](https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=962016&generaltype=0&itemId=925)、
[优化偿付能力监管标准说明](https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=1126916&generaltype=0&itemId=915)。
监管制度、会计或公司口径变化时先核对适用期；这些文件不为本研究1—5分阈值背书。
