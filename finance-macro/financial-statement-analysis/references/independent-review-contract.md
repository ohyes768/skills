# 独立复核合同：A1–E1

写 report spec 前读取。`report --spec <path> --independent-review` 在成功终态前执行预检、
渲染、固定 validate_report 和独立复核；各关卡不能相互替代。
输入与格式符见 [report-inputs-example.md](report-inputs-example.md)，指标见 [metric-catalog.md](metric-catalog.md)，
骨架见 [report-template.md](report-template.md)。

## 检查项完整表

修复均指有原文依据地修源输入，再运行流程。spec 生成 report_inputs 时修 spec；手写时修 report_inputs。

| 编号 | 检查对象和通过条件 | 失败后处理 |
|---|---|---|
| A1 | 正文第一个以 `## ` 开头的标题严格等于 `## 核心结论` | 调整 sections 顺序和 anchor |
| A2 | 存在 `## 核心结论` 二级标题 | 添加该节 |
| A3 | 此 anchor 对应输入的句数为 3–5：每个 statement 算一句，paragraphs 按中文句号切分非空片段计数 | 调整结论输入，段落仅留无数字定性文字 |
| A4 | 二级标题分别包含“核心结论、报表、比率、盈利、风险、数据质量”六个关键词 | 使用报告模板标题，不换成无关键词的近义标题 |
| A5 | 每段连续以竖线开头的表格，各行竖线数与首行相同 | 修表头/cells 数量，避免单元格静态文字内裸竖线 |
| A6 | 正文无符合 `{name}`/`{name:format}` 模式的未解析占位符 | 修 template/bindings |
| B1 | 独立重渲染每个 statement（含格式及默认引用），文本须作为完整一行出现在正文；不可渲染也失败 | 修源绑定/模板/格式后重生成，不手改正文 |
| B2 | 独立渲染每个表格单元格与整行，整行逐字匹配正文；decline 单元格自动带“下降” | 修行标签、单元格格式与列数 |
| B3 | 复算全部 computed 且非 null 的指标，不限报告引用项；使用 input_fact_ids 与 formula；误差 ≤ `abs(复算值)*1e-9 + 1e-9` | 查事实/期间/单位后重算；computed 指标无法复算记失败 |
| C0 | 被 statement/table 直接使用或通过指标依赖的事实 review_status 必须 verified | 回查原文、修事实 spec/fact_inputs 后 compute，不直接改状态 |
| C1 | 上述事实 raw_value 去逗号和空格后须出现在其 evidence_ids 对应的 text/table excerpt | 查原值、证据 ID、定位与单位，补证据后重建事实 |
| C2 | 相同 metric/scope/attribution/period/basis/currency/unit 的多条事实涉及多个 evidence_id 时 value 必须一致 | 查混表、错期间与重述，修冲突 |
| C3 | claims 的每个 source_page 存在于提取清单证据页集合中 | 修输入或证据链，由渲染器重建 claims |
| C4 | 使用的事实须 consolidated；parent 事实仅在该 statement 的 anchor/template 或该行 anchor/label 明示“母公司”时可对照；另查 raw_label 前的表标题防止混表 | 查表标题与归属，修映射，不按页码/section_id 推断口径 |
| D1 | 按 document.period.end 和 start 前一天，分别检查资产=负债+权益，绝对残差 ≤ `0.01` | 核对 total_assets/total_liabilities/total_equity；总权益不能用归母权益代替 |
| D2 | 期初现金及等价物+CFO+CFI+CFF+汇率影响−期末现金及等价物，绝对残差 ≤ `0.005` | 查现金等价物与货币资金区别、ref=opening、期间、汇率影响；缺失不是零 |
| E1 | 每个表格绑定单元格可格式化且以 `元`/`万元`/`亿元`/`%`/`个百分点` 之一结尾 | 用支持的 amount/percent/pp 格式，不能只在表头写单位或自造倍数格式 |

## 缺数据与输出

- B3 对非 computed 或 null 指标记录 `not_applicable`，不复算；这些指标不能数值绑定。
- D1/D2 只使用已核验合并事实；缺所需日期/科目记 `not_applicable`。
  同科目值冲突、计量维度不兼容或算术异常则失败，不按缺数据跳过。
  容差针对台账基准值，不是亿元/万元展示值，也不是相对误差。
- C1 要求所用事实有 excerpt 原值链。结构化事实即使有双源抽查背书，也不自动满足 C1。
  若它阻断独立复核，按主入口 `--pdf-only` 路径补齐有原文依据的事实输入并重算，受原目录剩余预算约束。
  不预设每次执行两遍 compute，不改 source 或伪造 evidence。
- `independent_review.json` 字段：`passed`、`checks`、`issues`、`not_applicable`、`categories`。
  checks 为实际检查次数，categories 按编号计数；同一编号可检查多行/多个指标。
  passed=true 表示无失败，不代表所有科目有数据；报告说明未验证事项。
- 诊断用独立 CLI 退出码：0 通过、1 有失败、2 缺输入/无法运行；统一流水线退出码按主 SKILL.md 解释。

## 修复边界

集中读 issues 后修源输入。正式 report 初检加两次修复，run_state.json 持久计数；
相同输入重跑不消耗预算，预检不消耗正式预算。源码/依赖/校验器故障交维护任务。
不改 scripts、references、生成结果或预算账本来使分析通过；耗尽后按 maintenance_required 披露。
变异测试用于维护验收，不在逐份报告中重复运行。
缺基期不编同比、标签是否符合绑定含义、因果与风险仍需语义判断。
收到 `quality_status: verified` 且 `terminal: true` 后立即交付，不追加复核或研究。
