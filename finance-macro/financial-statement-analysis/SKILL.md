---
name: financial-statement-analysis
description: A 股财报 PDF 深度分析。输入一份财报 PDF 链接（年报优先），下载后在本地建立页码索引、按需提取重点章节证据，产出带原文页码引用的中文 Markdown 分析，覆盖经营变化、盈利质量、现金与负债、杜邦分解和风险信号，全部关键数字可追溯。当用户要求分析年报/财报/招股书财务部分、解读上市公司业绩、检查财务风险，或给出 cninfo/sse/szse 的财报 PDF 链接时使用。不用于估值定价、目标价、交易建议或行业研究。
---

# A 股财报 PDF 分析

由你（agent）判断章节、事实含义和分析结论；Python 脚本连续完成下载、索引、提取、构造、渲染和校验。全文只存在于本地索引，**任何情况下不要把全文打印回对话或要求脚本输出全文**。开工先合并读取[分析框架](references/analysis-framework.md)、[报告模板](references/report-template.md)、[事实输入示例](references/fact-inputs-example.md)和[报告输入示例](references/report-inputs-example.md)；完整[产物合同](references/artifact-contracts.md)与[提取规则](references/extraction-rules.md)按需读取，不读源码猜接口。

## 按阶段读取

写 report spec 前，合并读取[指标目录](references/metric-catalog.md)与[独立复核合同](references/independent-review-contract.md)：前者给出全部 metric_id、公式和可用状态，后者解释 A1–E1、缺数据行为与修复路径。格式和输入形状见[报告输入](references/report-inputs-example.md)，标题见[报告模板](references/report-template.md)。不要用业务名称猜指标 ID；这些合同足够完成常规报告，不为找枚举或验收条件逐个读源码。reference 确有缺口或报错指向实现故障时记录维护问题，不在分析运行内改程序。

## 输入与运行目录

- 必填：财报 PDF 链接（`pdf_url`）。自动识别公司、期间、报告类型；无法确认时中止并说明，不输出貌似完整的分析。
- 运行目录：优先用宿主指定的唯一目录，不要另建公司同名目录替代；无宿主指定时用 `finance-macro/output/financial-statement-analysis/<run-id>/`（run-id 用公司加期间，如 `300001-2024`），且不能指向 Skill 源码目录。
- 所有脚本经 `uv run --project finance-macro/financial-statement-analysis python finance-macro/financial-statement-analysis/scripts/<脚本> ...` 从仓库根执行；统一入口支持任意 cwd（路径以脚本位置定位）。
- 脚本 stdout 只有单条 JSON；正文证据通过 `pack_context.py` 的包读取。退出码：0 成功；1 致命错误（修复后重跑）；2 未通过——以 stdout 的 `status` 区分：`repair_needed` 先修复重跑，`partial` 才是可交付但不完整（读 issues 降级受影响结论）。

## 执行顺序（统一阶段入口）

主 skill 自带事实生成器、报告构造器与预检工具，入口和最小示例见[可复用工具](references/reusable-tools.md)。新标的开工先读此短指南，不逐个读源码、不重建 locator/报告生成器。工具、合同和验收规则均在本 skill 内维护，无需加载其他财报 skill。

日常分析用 `run_pipeline.py`（prepare/evidence/compute/report）；旧提取/读包 CLI 保留兼容，默认不拆开调用；`review` 仅诊断恢复时用。写入紧凑输入后可在同一次工具调用中执行下一阶段，无需先读回刚写入的文件。仅使用 Skill 自带流程，不安装宿主补丁、不改调用端或 Hermes 配置。

1. `run_pipeline.py prepare --url <URL> --run-dir <运行目录>` — 下载、缓存（核对 URL 与哈希，防误复用旧 PDF），生成 `document.json`/`sections.json` 并返回章节定位摘要。
2. `run_pipeline.py evidence --run-dir <运行目录> --sections <重点章节ID> --request-id map-01` — 增量提取与首包交付一次完成，保留旧 ID 与文件。证据页的内容归属（含同页双表与跨页表尾）统一按[提取规则](references/extraction-rules.md)的 "Same-page dual tables" 节处理：以表标题、列头和科目行判断，不按页码或 `section_id` 推断合并/母公司口径。扫描页缺 OCR 能力时退出 2，把未提取页列入报告"未验证事项"。
3. 直接读取上一步 JSON 的 `context.packet`（每包 ≤12,000 字符）；`next_cursor` 非空才以相同 sections/pages 和 `--cursor` 续读 `evidence`，续读不重新提取。`--pages` 支持 `1,3,5-9`。`image_crop` 必须实际查看图片后才能据其确认数字。
4. 从已读证据写**抽查单** fact_inputs（推荐科目：营收/归母净利润/净利润/CFO/总资产/货币资金/营业成本/归母权益/负债合计/期末现金及等价物/汇率影响/应收/存货/短长期借款，约 15 项，示例见[fact-inputs-example](references/fact-inputs-example.md)）：只抽证据中已确认的数，**缺失不是零**；对照事实显式标 parent，不混入合并指标。抓取方法：先跑 `locate_samples.py --run-dir <运行目录>` 生成候选（evidence_id/行号/数值，并与东财值自动比对标注），复核挑选后写入 fact_inputs——`locator.line` 用 excerpts 文件的行号，**不要为抽查自行编写定位脚本**。
5. `run_pipeline.py compute --run-dir <运行目录>` — 默认以东财 F10 结构化三表打底（自动从 `document.json` 的 stock_code 与 period 推导拉取日期，失败自动回退纯 PDF 模式并在 warnings 标注明细——`no data` 多为报告未披露或银行/保险不在通用三表，`request failed` 为接口故障；已留档部分重跑只补缺失项，无需 `--refresh`）：程序生成结构化 facts，与抽查单双源比对，结果落 `structured_check.json`，缺失建议科目在 warnings 提示补充；另做全量数值存在性检查——每个结构化值都应在 PDF 证据文本中出现（`presence` 统计）。结构化事实（`source: structured`，无 evidence 链）由抽样核对背书——存在任何双源冲突时报告不得 verified。修复预算为初检 + 2 次，持久化在 `run_state.json`：相同输入重跑不消耗、重启不重置，换新运行目录不算重置手段，耗尽后按维护规则处理。
5a. 回退与逃生门 `compute --run-dir <运行目录> --pdf-only`（结构化自动回退、无法提供 stock_code，或双源冲突需以 PDF 口径修复时）— 纯 PDF 全量抽取：**第一次 compute 前定齐事实范围**：合并三表、首页主要数据交叉核对、必要的母公司对照及风险附注。text 证据优先写紧凑 `spec.json`（期初现金显式 `ref=opening`），字段与示例见[可复用工具](references/reusable-tools.md)，不要手写 locator；表格、缺失值或重复标签等复杂映射按[fact-inputs-example](references/fact-inputs-example.md)构造 fact_inputs。`compute --spec <运行目录>/spec.json` 同次生成 fact_inputs、逐值核对、构造 `financials.json`；生成器失败先修 spec，不提交 compute；映射失败按 `mapping_validation.json` 修输入。
6. 分析与回查 — `compute` 已返回 facts/metrics/checks 的 `context.packet`，不要重读原文或整个 JSON。分页用 `pack_context.py --stage analyze --request-id analyze-N --cursor <游标>`；原文定向回查用 `run_pipeline.py evidence --run-dir <运行目录> --pages N-M`，最多两轮，仍未解决就保留不确定性。语义复核在交付前完成，不在交付后追加新一轮研究。
7. 把声明式 report spec 写进运行目录（结构与 report_inputs.json 相同，表格行尾空串自动生成来源页码，示例见[可复用工具](references/reusable-tools.md)），`report --spec <spec>` 一次完成构造、预检与正式 report；构造失败不写文件、不消耗预算。输入合同见[report-inputs-example](references/report-inputs-example.md)。**在最终 report 命令之前完成一次语义复核**：检查口径、期间、单位、风险与结论，缺基期的比率不编同比故事。
8. `run_pipeline.py report --run-dir <运行目录> --independent-review` — 同次预检、同源渲染、固定 `validate_report` 校验、独立复算与展示检查，全部通过才返回终态。诊断在 `report_preflight.json` / `render_issues.json` / `report_validation.json` / `independent_review.json`，与 compute 一样受初检+2 次修复预算约束；预检不消耗正式预算、也没有程序化轮次上限，应集中在少数几轮内修完。变异测试属于维护验收，不在每份报告里跑。调用方要求完整 Markdown 时同次加 `--include-report`，成功直接提供 `report_markdown`，不再读取报告；旧无标志入口仅保留兼容，不作为新分析的默认交付路径。
9. **report 返回 `quality_status: verified`、`terminal: true` 后立即停止调用工具并输出最终回复**：默认只报完成状态和报告位置；调用方要求全文时交付上一步的 `report_markdown` 一次。之后不再追加 review、重算或回查。`terminal` 是 Skill 给 agent 的停止提示，不改变宿主运行状态；Hermes 按原有流程处理最终回复。

## 运行时边界

- 分析运行不得修改 `scripts/`、`references/`、校验规则、`extraction_manifest.json` 或任何校验结果；事实修复只能改 `fact_inputs.json` / `report_inputs.json`，且必须有原文依据。
- **`run_state.json` 是修复预算的唯一账本，禁止删除、清空或改写来重置预算。** 预算耗尽时的合法出路：基于已产出的 `metrics.json` 与证据撰写分析，并在报告开头明确声明"未通过机器校验，quality_status=maintenance_required"，交由调用方决定是否采用；绕过校验输出未验收报告等同于任务失败。
- 受保护模式（agent 凭据不可写 Skill 目录与运行状态）由宿主实施，仅靠提示词不算完成。
- `quality_status`：`verified`（报告通过机器校验，发布方视为正式完成）/ `partial`（预算内可修复或数据不足）/ `maintenance_required`（预算耗尽或源码/依赖/校验器故障，属于维护问题，不在分析任务内修程序）。
- Skill 不直接发钉钉/RSS；发布归调用端，且只把 `verified` 当作完整结果发送，`partial` 不得包装为高质量结论。

## 降级规则

- 摘要、季报：不要求附注与审计；缺比较期不下趋势结论，不年化。
- 重述：比较期用本 PDF 披露的可比口径；调整前后不混用。
- 金融企业（银行/保险/证券）：只做适用的基础分析，明示未使用专用分析框架，不跑一般企业完整风险清单，不计算存货/应收周转。
- 审计：无保留意见中的关键审计事项不等于非标意见；持续经营事项单列。

## 完成条件

- 最终 report 前已完成语义复核，使用 --independent-review 且独立复核通过，report 返回 `quality_status: verified`、`terminal: true`；关键数字全部有来源（原文页码或带输入来源的计算）。机器校验不能代替语义判断。
- 风险信号逐项标注：触发 / 已检查未发现 / 资料不足 / 行业不适用；筛查线索不写成造假结论。
- `context_usage.jsonl` 已记录交付量；实际模型 token 用量只有在宿主提供时才记录，否则留空说明不可获取。
