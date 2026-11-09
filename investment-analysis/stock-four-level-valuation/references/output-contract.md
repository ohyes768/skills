# 输出、模型合同与命令

Python >=3.12，标准库，无需安装NAS项目或第三方运行依赖。路径以实际 Skill 目录为准；下面的 `<skill目录>` 替换成该目录，不假设工作目录或NAS路径。

## 1. 执行

```text
python <skill目录>/scripts/validate_result.py finalize --stock stock.json --input draft.json --output result.json
python <skill目录>/scripts/validate_result.py check --stock stock.json --input result.json
```

finalize 成功将完整JSON打印stdout，并原子保存到明确的output；check 从保留的输入模型/analysis重算并检查最终结果，成功返回短JSON回执。错误exit=2、stderr说明、stdout无伪成功对象；失败不能拿旧result.json当本轮产物。输出不能覆盖stock或draft。脚本不联网、不读取evidence.origin、不扫描目录。

同一轮一个目录。保留stock/draft/result，不随意更改已用来源；修改模型或判断后必须重新finalize/check。成功后语义复核并将result整个JSON原样交付；不是只交付check回执。

## 2. stock.json

恰好 `code/name/as_of/currency`：代码六位字符串，公司名非空，日期YYYY-MM-DD，币种CNY。name与code都必须经输入核对，程序只能比较传入身份一致性，不能证明实际证券名称。

## 3. draft.json

草稿不允许填写计算结果、版本号或最终报告；这些由工具生成。

| 键 | 类型与含义 |
|---|---|
| code/name/as_of/currency | 与stock完全一致 |
| status | ready / insufficient_data / blocked / not_applicable |
| summary | 非空中文概述，不藏另一套参考挡位 |
| confidence | `{level,reason}`；level=high/medium/low/unavailable，reason非空 |
| risks | 字符串数组（数组本身可为空）；每个元素为非空中文文本，仅写已证实风险与有依据的不确定性 |
| invalidation_conditions | 字符串数组：触发复核的可观察条件 |
| data_gaps | 字符串数组：缺失、冲突及影响；ready也可列不阻断的次要限制 |
| analysis | 恰有business/normalization/dividend/valuation/risk五个非空段落 |
| evidence | 来源数组，结构如下 |
| valuation | ready为下述模型对象；其他状态必须null |

所有17字段最终输出含analysis，是为了保留非ready研究，不因valuation=null丢失五段。分析文本必须与结构化状态一致；脚本不能理解所有自然语言暗示，所以非ready时人工检查summary/analysis不能泄露四点价格。

### evidence每项

恰好 `id/title/kind/origin/locator/period/published_at/accessed_at/verification`。

- id唯一非空；title真实标题，locator为材料栏目/段落/字段定位；period事实期间。
- kind：official/data_platform/research/media/upstream/input。
- origin：描述材料实际来源。实际http(s)URL或明确的本地材料路径；聊天/调用请求中直接提供的内联材料写 `inline:<日期>:<简短描述>`（如 `inline:2026-11-08:调用方提供的2025年报摘要`），不得编造URL或文件路径，禁止javascript等执行协议。脚本只存文本，不去访问。
- published_at/accessed_at：YYYY-MM-DD或null。披露不能晚于as_of；访问可以发生于后来，但只能支持截止日前可得事实。历史数据重述风险另写限制。
- verification：read（本轮读到）、reused（上游材料复用）、unverified（只有线索）。ready引用不能仅由unverified支持；不存在的引用直接拒绝。

一个事实跨多维可复用同一id，别为凑数量伪造独立来源。假设不必都有外部来源“批准”，但其rationale要说明事实基础与本次判断区别。

### ready valuation六个输入键

1. `primary_method`：pe_multiple/pb_multiple/equity_cashflow_pv。
2. `anchor`：非空说明，定义四点共用的盈利/权益/现金流价值基础。
3. `scenarios`：恰有bear/base/bull，每项 `{model,rationale,evidence_ids}`；各自模型同主模型，未舍入价值应有悲观≤基准≤乐观的解释。
4. `decisions`：恰有heavy_position/add_position/reduce_position/full_exit，每项同上述结构；PE的eps、PB的bvps共用，参数理由逐点写。
5. `metric_inputs`：恰有ttm_eps/common_bvps/annual_dps/dps_basis/period/share_basis/evidence_ids。数值可null；period/share_basis非空，明确报告期和股份基准。dps_basis=ttm_ordinary/forward_ordinary/none；有DPS不可none。提供数值必须有可用证据。
6. `sensitivity`：2至8项，每项 `{label,base_level,model,rationale,evidence_ids}`。base_level为四个决策键之一；模型同主模型且至少一个参数实际变化，不能只复制换标签。

`rationale`是参数论证，不接受“经验值/行业惯例/安全起见”替代具体依据。脚本仅检查结构、引用和计算，无法判定理由是否充分。每一模型及每条敏感性都需非空的可用evidence_ids。

## 4. 数学节点字段

数值可为JSON数字或严格十进制字符串（推荐字符串保留精度），禁bool、NaN、Infinity。审计结果保留模型数值的原始输入类型（仅缺省margin补为字符串"0"）；所有派生的exact_price为十进制字符串。所有模型可带margin，缺省0，区间[0,1)。不支持任意表达式或未知字段。

| method | 必需字段 |
|---|---|
| pe_multiple | eps>0、multiple>0 |
| pb_multiple | bvps>0、multiple>0 |
| equity_cashflow_pv | cashflows数组1至100项、discount_rate>0、cashflow_basis(dividend/fcfe)、finite_life(bool)、terminal |

cashflows为年末普通股股东每股CF，允许负值，不自动截零。公式为Σ CF_t/(1+r)^t + TV_N/(1+r)^N，再乘(1-margin)。最终价格须正。

terminal恰为三种之一：

| kind | 其余字段 | 含义 |
|---|---|---|
| value | value>=0 | 第N年末股权值，可为0 |
| exit_pe | eps>0,multiple>0 | 第N年末EPS×退出PE |
| perpetuity | next_cashflow>0,growth>-1且<discount_rate | 第N+1年CF/(r−g)，算出第N年末值；finite_life=true禁止 |

各模型数值限制、字段错误以实际CLI报错为准，不通过就修具体输入，不改脚本绕过。

## 5. 最终17字段及状态

恰为 `schema_version/skill_version/code/name/currency/as_of/status/levels/valuation/evidence/data_gaps/confidence/risks/invalidation_conditions/summary/analysis/report_md`。

- schema_version当前1.0.0，skill_version读实际SKILL.md metadata.version，不能伪造升级。
- levels四键固定，各为 `{price,pe,pb}`。price舍入到分，PE/PB四位小数。非ready三项全部null。
- pe=price/正TTM EPS；pb=price/正普通股BVPS。缺失或分母非正为null，绝不显示负PE。选定估值PE在model.multiple，不能混在levels.pe。
- ready valuation保留六个输入键，并添加 `formula_version="1"`、`calculated`、`scenario_values`、`sensitivity_values`、`level_metrics`：
  - calculated：四点→`{exact_price,price}`，exact_price是未舍入十进制字符串。
  - scenario_values：bear/base/bull同结构。
  - sensitivity_values：顺序数组，`{label,base_level,exact_price,price,delta_pct}`。
  - level_metrics：四点→`{dividend_yield_pct}`，普通DPS/舍入price×100，四位小数；DPS未知则null，0则0。
- 非ready valuation=null，不保留计算节点来间接暗示价格；五段研究仍在analysis。

| status | 核心要求 |
|---|---|
| ready | 四个正价舍入后严格递增，证据与理由齐全，无阻断性冲突和风险 |
| insufficient_data | 有具体缺口，不能把已核实坏消息说成缺失 |
| blocked | 有已核实重大红线及原因，不等于价格跌了 |
| not_applicable | 说明首版模型不适用原因，不假装公司没价值 |

代码会校验可执行合同，不能独立判断每个data_gap是否关键、risk是否达到阻断门槛或参数是否合理；这些必须人工语义审查。check通过不等于获准交易/回写。

## 6. 唯一完整示例：虚构计算练习

使用随附 `tests/fixtures/ready.json` 与 `tests/fixtures/stock.json`。它们是最小可运行输入，不是关于真实公司的证据，不得照抄倍数作为真实定价规则。

```text
python <skill目录>/scripts/validate_result.py finalize --input <skill目录>/tests/fixtures/ready.json --stock <skill目录>/tests/fixtures/stock.json --output <本轮目录>/result.json
python <skill目录>/scripts/validate_result.py check --input <本轮目录>/result.json --stock <skill目录>/tests/fixtures/stock.json
```

此示例帮助理解输入形状、正常化EPS与TTM显示口径、计算记录及报告。真实任务必须替换为实际读取的事实、公司级参数论证与风险判断，不能只替换代码/名称就当研究完成。

## 7. 交付检查

1. 身份、截止日与股份/报表口径无矛盾。
2. 四点均有论据；不是一条价值乘任意比例，免责声明不能豁免。
3. 银行/经营权/分红风险门槛已回答或明确不出价。
4. JSON与报告同一批数值，非ready没有暗藏参考四点。
5. 当前执行finalize/check均成功，旧文件不能代替成功回执。
6. 输出一个JSON，调用端自行决定展示、存储及批准更新；无enabled或自动写网站字段。
