# 固定工具用法

以下 `<skill目录>` 是当前 skill 的实际目录；运行数据放在宿主指定的工作目录，不放源码目录。
全部脚本只需 Python 3 标准库，无需下载或解析 PDF，也不依赖其他 skill。维护说明见 [安装与兼容迁移](setup-and-migration.md)。

A-D 取证开工先按 [有预算的取证与失败换路](research-control.md) 初始化 research.json，保存渠道故障、当前缺口、紧凑证据与轮次；已查清就复用，缺证则以 null 收口。

## 1. 财务 E：企业原始输入与银行/保险证据包

```text
python3 <skill目录>/scripts/rating_math.py financial --input <工作目录>/stock.json
```

返回一个 JSON 对象：

- `score`：1–5 整数或 null；`status`：scored / insufficient_data / not_applicable。
- `checks`：各项 rule、原始 input、period、result、cap 和 reason；可直接用于报告说明。
- `issues`：缺失、无效、口径无法对齐或专用指标缺口；写入待验证事项。
- `risks`：已知的财务弱项；不要把 issues 自动改写成经营风险。
- `sector`：ordinary / utility_transport / bank / insurance / nonbank_financial 或 null。

普通企业只读取原始输入，不取外部数字，不计算缺失的 roe_avg_3y，不把字符串、布尔值或 null 当数字。
字段中的 0 和负数有效。所需年度字段为 `roe_year` 与 `annual_profit_year`，接受整数或四位年份字符串，二者须一致。
ROE 历史取 roe_year 及前两年；同年相同值可去重，同年冲突、最近缺年或晚于锚点年份的记录会阻止评分。

`previous_quarter_label` / `latest_quarter_label` 须相邻，支持跨年 Q4→Q1。
可用 `2026Q1`、`2026年第一季度`、`2026一季报`；其他报表名须显式写单季，如 `2026半年报（单季）`。
累计、YTD、H1/H2、未注明单季的半年报/三季报/年报均不能替代单季标签。
不因标签无法识别而擅自改写原始输入；向调用方反馈具体缺口。

行业以 `sw_level1/sw_level2` 显式识别。普通申万行业用普通负债率阈值，公用事业/交通运输用宽容阈值；
行业缺失、不支持或两级冲突时未评分，不从公司名字猜。银行和保险使用下述各自独立证据包；其他非银金融仍返回 null，保留子行业缺口说明。
完整支持的行业集合与标签解析由 `financial_score.py` 维护；脚本返回具体问题，无需为常规运行读取源码。

五维确定后继续用主 skill 的 calculate/finalize。来源编号及报告末尾来源表按主 skill“来源输出”执行。正常 finalize 加 `--stock stock.json --check-financial --research-state research.json`，
能拦截手抄 E 分数错误。若有已披露的外部口径冲突，只能按主 skill 的受限兼容入口交付，不能偷偷替换输入数字。

### 普通企业 E 规则（解释脚本结果时查阅）

先检查可评分性：roe_avg_3y、debt_asset_ratio、年度扣非同比、最近两季单季扣非同比、最近三年连续有效的 roe_history 及对应期间必须足以核对。任一必需数据缺失、无效、年份不连续/同年冲突，或关键口径冲突未解，E 记 null；不得用默认基础分、缺失封顶或单年 ROE 代替。已知弱项仍写入风险，但不因缺失数据制造低分。非计分背景指标缺失不阻止评分。

此段规则由 `rating_math.py financial` 自动执行，不能临时写另一套计算。年度扣非与 ROE 年份须对齐，ROE 历史窗口以 roe_year 为锚；单季标签须明确且两季相邻，不能把半年报/前三季累计当作单季。支持的行业、报告期写法见本节前文，具体失败原因由脚本返回。若发现会影响定分的外部口径冲突，披露并按 null 收口；不要改原始输入来迎合脚本。

数据满足条件后，按以下顺序计算，覆盖规则只取更低分，不能同时匹配多个档位后自由选分。报告逐项列出输入数值、期间、等级与降档原因。

1. **ROE 基础分**：用 roe_avg_3y。≥15 → 5；[12,15) → 4；[8,12) → 3；[5,8) → 2；<5 → 1。不自行计算三年均值或换用单年值。
2. **负债等级**：普通行业 ≤40 为优，(40,60] 为良，(60,75] 为中，>75 为差。公用事业/交通运输阈值依次为 ≤55、(55,70]、(70,80]、>80。行业无法确认时 E 记 null，避免错套阈值。负债率良或中封顶 4，差封顶 2。
3. **盈利等级**：年度扣非同比及最近两季单季同比三项均 >0 为优；数据齐全、两季均 ≥0 且存在 ≤0 项为良；恰有一季 <0 为中；连续两季 <0 为弱。依次封顶 5/4/3/2。
4. **ROE 趋势**：roe_history 按年升序，忽略 null 后核查最近三年连续有效值。最近三年连续两次下降封顶 2；只有最近一年下降封顶 4；其余趋势（含先降后升）不扣。不能跳过最近年份的缺口，改用更早的三年窗口声称当前趋势。
5. **严重弱项优先**：基础 ROE <5 直接为 1。ROE 弱（基础分 ≤2）、负债差、盈利弱、连续两次 ROE 下降这四类中有两类及以上，最终为 1；其余取基础分与各项上限的最小值。这些降分仅由已核实经营弱项触发。

毛利率用于解释商业模式，不抵消负债或盈利弱项，也不因低毛利率惩罚高周转公司。三年 CAGR、年度利润额与分红比例作为风险补充，不替代上述指标。

### 银行分支

先读 [银行证据与评分](bank-financial.md)。用已有数据和可读官方网页补齐证据包，模板/校验使用固定工具，
不修改 stock.json。银行补数明确传 --bank-data；不带时 E 为 insufficient_data，而非认定银行不适用评级。

```text
python3 <skill目录>/scripts/bank_financial.py template --stock stock.json --as-of 2026-10-27
python3 <skill目录>/scripts/rating_math.py financial --input stock.json --bank-data bank-data.json
```

financial 内已校验数据包，不额外先跑 validate；独立 validate 子命令留给修包诊断。
模板 stdout 保存为 bank-data.json，填入已确认的官方数据。核对数值后才入分，表格多年份、
累计/年化、集团/母行须核对。银行四类规则及三年窗口、资本适用要求和辅助指标见银行参考。
正常银行 finalize 和只读 validator 均加 --bank-data bank-data.json --stock stock.json --check-financial；
research.json 先 init --bank-research，E 也须结案。研究分档未实证校准，报告不得称为监管评级。

## 2. 保险分支与取证来源

保险先读 [保险证据与评分](insurance-financial.md)，使用 insurance_financial.py template，
计算/交付加 --insurance-data insurance-data.json。集团/法人分开，金额与百分比单位显式校验；
E 账本先 init --insurance-research。保险不套银行数据包，二者不能同时提供。

优先复用可核对出处的已有结构化数据。A-D 按主 skill 的来源层级选可读网页；银行/保险专用指标仍用官方披露。
每项保留来源链接、网页栏目/表格/行列、期间、主体与单位；原网页缺值不能从摘要猜数。
不下载或解析 PDF，不装解析依赖，不调用其他 skill 补做 PDF 流程。
只有 PDF 来源或网页不可读时，在同一取证预算内换可读且符合对应维度来源要求的材料；核心缺口仍无法补齐则 null。
已有来源链接可以保留为线索，但只有实际读到的内容才能作为已核实证据。

## 3. 只读校验已有结果

```text
python3 <skill目录>/scripts/validate_rating_json.py <rating.json> --stock <stock.json> --check-financial --research-state <research.json>
```

输出 `status/errors/warnings/scope`。退出 0 表示数值结构通过，退出 2 表示输入或合同失败。
不修改原文件；复用 rating_math 的权重、星级、null 传播和规范 boundary，禁止另写第二套算分。
正文缺章节、来源格式、未评级标注或疑似交易措辞仅提醒人工复核，不证明或否定语义正确性。
免责声明、同值的财务指标不会成为机械拒绝原因。是否有真实证据、是否正确回答判别问题仍由分析者检查。
