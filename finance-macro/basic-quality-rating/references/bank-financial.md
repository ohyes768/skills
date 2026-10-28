# 银行：有来源的数据包与专用 E 规则

银行按本参考执行，不使用普通企业的负债率、季度扣非符号或 ROE 趋势重罚。
五维权重、最终十字段及 null 传播不变。保险、证券等不使用本分支。

需要结构化补数时先读 [接口取数与缺口](financial-data-api.md)：免费脚本返回候选及原始出处，官方核对后才入下述评分包。

## 1. 先收证据，再入分

1. 保持调用方 stock.json 不变。用明确的研究截止日期生成独立模板：

   ```text
   python3 <skill目录>/scripts/bank_financial.py template --stock stock.json --as-of 2026-10-27
   ```

   将 stdout 保存为 bank-data.json，再填入确认后的数据。模板中的空值不等于零。
   `as_of` 是本次研究截止日；历史分析只能使用当时已披露的数据，不能为了绕过缺口改日期。
   模板绑定原始股票身份和完整输入哈希；重新取数不修改原 stock.json。

2. 优先复用已有结构化资料，再用宿主搜索/网页读取工具核对银行官网、交易所公告正文、
   官方业绩指标表及第三支柱披露的可读网页。记录 source_url 与 locator（栏目、表格、行列），
   核对公司、年份、单位、集团/母行口径和指标定义，不从新闻或搜索摘要猜数字。
   禁止读取 PDF 或 PDF 缓存。正文缺关键表格、表头或脚注时，在已有预算内搜索其他官方可读网页；
   仍缺核心数据则 E=null。财务表与资本监管表可能口径不同，逐项确认。

3. 银行 E 也使用现有取证账本。初始化时加 `--bank-research`：

   ```text
   python3 <skill目录>/scripts/research_state.py init --state research.json --stock stock.json --providers <已有渠道ID列表> --bank-research --research-limit 24
   ```

   已有账本会追加 financial，不清空 A-D、已耗轮次或渠道故障；之后不带该参数也不会删掉 E。
   `start/result/close` 用法见 [取证控制](research-control.md)，dimension 使用 financial。
   必要主题是 profitability / asset_quality / capital；liquidity 为可选主题，旧账本中的该主题证据仍保留。E 共用一轮初查加四轮网页补查，
   不能按指标或换关键词重新计数；每轮先说明缺口及评分影响。原渠道配额/权限失败继续有效。
   三类核心证据查齐即可结案 complete；LCR/NSFR 缺失不用为它追加搜索，也不阻止 complete。到上限仍缺其他核心证据则 gap、E=null。具体重大冲突仍只允许重开一次。
   账本保存紧凑论据，具体数字和出处保存在 bank-data.json；complete 不替代数值校验。

## 2. bank-data.json 合同

模板：schema_version=1、code/name、stock_sha256、as_of、liquidity_regime=lcr_nsfr、
reports 数组、requirements 对象、requirements_period_end、requirements_published_at、peers 数组。
`requirements_period_end` 必须等于最新快照报告期；要求来源的披露日不得晚于 as_of。
三项资本要求须是该银行当期**完整适用要求**，包含适用储备/附加要求；不能仅填 5/6/8 最低值。
脚本验证引用结构与日期，不能证明分析者确已查全监管要求。

每个 report 包含：

```json
{
  "period_end": "2025-12-31",
  "published_at": "2026-03-28",
  "period_type": "annual",
  "scope": "group",
  "metrics": {
    "roe": {
      "value": 12.5,
      "source_url": "https://example.com/official-results",
      "locator": "主要指标栏目，2025年集团列",
      "basis": "period"
    }
  }
}
```

以上仅示意格式，不是真实银行数据。百分数 `12.5` 表示12.5%，不能填0.125。
数值只能是有限数字，不能是字符串、布尔值或非有限值。零是真实值时保留，未知指标省略，
不得把 null 改成0。每个值都保留 source_url、locator 和 basis。

| 内容 | 字段 | 要求 |
|---|---|---|
| 最近三年年度盈利与风险 | roe、roa、npl_ratio | 三个连续年度；年度末12月31日，roe/roa 的 basis=period |
| 最新快照资产质量 | npl_ratio、provision_coverage | 不良率、拨备覆盖率；basis=point_in_time |
| 最新快照资本 | cet1_ratio、tier1_ratio、total_capital_ratio | 核心一级、一级、总资本；basis=point_in_time |
| 可选最新快照流动性 | lcr、nsfr | 缺失/显式null不阻止评分；有值时来源、口径仍须有效。LCR允许point_in_time或quarter_average；NSFR为point_in_time |
| requirements | 三项资本同名字段 | 同样的数值/来源/定位/basis对象，basis=point_in_time |
| 辅助指标 | loan_provision_ratio、special_mention_ratio、overdue_90_ratio、nim、cost_income_ratio | 缺失不自动扣分；nim/成本收入比为period，其余point_in_time |
| 可选适用拨备要求 | requirements.provision_coverage / loan_provision_ratio | 只有取得该银行明确适用要求，才能判断对应合规缺口 |

scope 统一为 group，不能混用母行数据。period_type 支持 annual（12月31日）、interim（6月30日）、
quarter（3月31日、9月30日、12月31日）。年度盈利不使用半年/季度年化值代替。
默认三年窗口以截止日上一完整年度为锚；1—4月最新年度尚未提供时，才可用再前一年。
5月起缺上一年度则不能倒退旧窗口。最新快照超过400天不评分；有更新披露应取更新期，
不能故意省略更新但不完整的报告，用旧的完整报告规避缺口。脚本不能证明网上没有更新披露。

latest 快照须包含资产质量与资本核心指标（不含可选 LCR/NSFR）；较新报告缺项目时，应补齐同报告期披露，不能拼入旧期数字。
报告期重复、未来披露、混合口径、资本比率顺序冲突或已提供拨贷比与不良率×覆盖率重大不一致，
均阻止评分。无效指标不会抹掉其他可确认事实；限制与已知风险分开记录。
目前只支持适用 LCR/NSFR 制度的银行，其他制度须明确未覆盖，不用代理值凑分。

可选 peers：先设置 peer_group（例如同类股份制银行），每家含 code、peer_group、period_end、
published_at、scope=group、metrics。必须同组同期间，排除自身与重复代码；只比较相同 basis。
无效同业记录忽略并警告；缺同业数据不扣分，不得冒称行业排名或代表全行业。

## 3. 评分规则 bank-research-v2

v2 取消 LCR/NSFR 必填；三年盈利、资产质量、资本及趋势规则不变。与 v1 的完整性要求不同，历史结果不会自动改写，比较时须注明规则版本及流动性覆盖状态。

- 最新期两项均缺失或 null：不设置流动性分数/上限，不补0、不补5；其他核心证据齐全仍可评分。报告及 watch_points 均写“流动性未验证”，说明没有验证流动性安全。
- 仅有一项可靠值：按该项设置上限，另一项仍属“流动性未验证”；不能据一项达标宣称整体达标。两项都有时沿用较弱值。
- 不为缺失项购买接口、改查旧期或追加取证；已有可核实指标必须保留，不能删除弱值以提高评分。显式提供但数值/来源/期间/口径无效时仍按冲突或错误处理，不静默当作缺失。
- 其他核心证据缺失仍 E=null；不支持的流动性制度仍未覆盖，不借此套用其他制度。存贷比、现金余额不替代 LCR/NSFR。

这是**尚未实证校准的经营质量研究分档**，不是监管评级或信用评级，也不代表未来收益。
分档列清楚，避免让模型临场编阈值。监管合规与质量分档分开：150%拨备覆盖率是本研究
质量分档线，绝不是所有银行统一的违规线；同样，资本达标不意味着财务优秀。

| 项目 | 5 / 4 / 3 / 2 / 1 分的研究条件 |
|---|---|
| 三年平均ROE | ≥15 / ≥12 / ≥8 / ≥5 / 更低 |
| 三年平均ROA | ≥1 / ≥0.8 / ≥0.5 / ≥0.25 / 更低 |
| 最新不良率 | ≤1 / ≤1.5 / ≤2 / ≤3 / 更高 |
| 最新拨备覆盖率 | ≥300 / ≥200 / ≥150 / ≥120 / 更低 |
| 资本余量，单位百分点 | 三项“实际－完整适用要求”的最小值 ≥3 / ≥2 / ≥1 / ≥0 / 更低 |
| 可选流动性上限 | 已取得有效指标的最小值 ≥130 / ≥120 / ≥110 / ≥100 / 更低；两项均缺不设上限 |

盈利基础分取ROE/ROA较低档，最终E取基础分与资产质量、资本、已有流动性及趋势上限的最小值，
不能用高盈利抵消安全弱项。资本或适用流动性底线已确认不足、或有来源的适用拨备要求未达到，
上限1。核心证据不足/冲突仍为null，不能因为已知一项弱点就绕过完整性要求硬给1分。

最近年度不良率上升≥0.2个百分点，上限3；≥0.5个百分点，上限2。三年ROE连续两次下降，
上限4，需要结合息差与拨备解释，不使用普通企业“利润连降”重罚。辅助指标和同业差异用于
解释风险，不凭数量加分；逾期90天以上占比高于不良率须核查分类范围与时点。

## 4. 计算与交付

```text
python3 <skill目录>/scripts/rating_math.py financial --input stock.json --bank-data bank-data.json
python3 <skill目录>/scripts/rating_math.py calculate --input dimensions.json --research-state research.json
python3 <skill目录>/scripts/rating_math.py finalize --input draft.json --stock stock.json --check-financial --bank-data bank-data.json --research-state research.json --output rating.json
```

正常运行 financial → calculate（绑定账本）→ finalize；financial 内已校验证据包，独立 validate 仅用于排查修包问题。finalize核对E与该证据包一致，
同时要求银行E取证已结案。最终仍恰好十字段，bank-data本身不塞进输出合同。
只读验证已有结果可加同一 --bank-data；提供证据包时必须配合 --stock --check-financial。
financial 返回 liquidity_status=verified / partial / unverified，仅表示证据包内两项值的有效覆盖状态，不证明来源真实或整体流动性安全。checks 中 bank_liquidity 的 cap=null 表示未计入，warnings 包含具体缺项。
报告写明 as_of、证据截止期、三类核心指标、流动性覆盖状态、资本余量、bank-research-v2、限制与具体缺口。可评分但流动性不完整时，finalize --check-financial 要求 report_md 和 watch_points 均包含“流动性未验证”，缺任一处就拒绝交付；只检查标签存在，不代替语义核对。
银行输入与新披露的实质性冲突须解决后入分，或以E=null交付并说明，不静默覆盖原数据。

## 依据与适用限制

- [商业银行资本管理办法（2024年起施行）](https://www.nfra.gov.cn/cn/view/pages/rulesDetail.html?docId=1134197&itemId=4214)：区分最低资本、缓冲与附加要求。
- [商业银行金融资产风险分类办法](https://www.nfra.gov.cn/cn/view/pages/rulesDetail.html?docId=1095372)：资产质量判断不限于表面不良率。
- [商业银行流动性风险管理办法](https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html?docId=180252)：流动性制度按适用银行区分。
- [中国金融稳定报告2018](https://www.gov.cn/xinwen/2018-11/04/5337137/files/48b31c0c3cec41ac977b18a2b6b9590a.pdf)：拨备监管存在差异化，不能硬编码统一违规线。
- [IMF银行财务稳健性指标指南](https://www.imf.org/en/-/media/files/data/2019/2019-fsi-guide.pdf)：联合分析资本、资产质量、盈利和流动性。

以上支持分析维度与监管事实，不为本研究的1—5分阈值背书。监管制度或具体银行要求变化时，
按当期官方披露更新证据包；不靠旧通用阈值宣称最新合规。实际模型取数准确性、跨银行
可比性和实证分档校准须另行评估；单元测试通过不能证明投资判断正确。
