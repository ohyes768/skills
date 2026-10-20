---
name: financial-statement-analysis
description: A 股财报 PDF 深度分析。输入一份财报 PDF 链接（年报优先），下载后在本地建立页码索引、按需提取重点章节证据，产出带原文页码引用的中文 Markdown 分析，覆盖经营变化、盈利质量、现金与负债、杜邦分解和风险信号，全部关键数字可追溯。当用户要求分析年报/财报/招股书财务部分、解读上市公司业绩、检查财务风险，或给出 cninfo/sse/szse 的财报 PDF 链接时使用。不用于估值定价、目标价、交易建议或行业研究。
---

# A 股财报 PDF 分析

由你（agent）编排流程；Python 脚本完成下载、索引、提取、构造、渲染和校验的确定性工作。全文只存在于本地索引，**任何情况下不要把全文打印回对话或要求脚本输出全文**。先读[产物合同](references/artifact-contracts.md)、[分析框架](references/analysis-framework.md)与[报告模板](references/report-template.md)；提取规则见[提取规则](references/extraction-rules.md)。

## 输入与运行目录

- 必填：财报 PDF 链接（`pdf_url`）。自动识别公司、期间、报告类型；无法确认时中止并说明，不输出貌似完整的分析。
- 运行目录：`finance-macro/output/financial-statement-analysis/<run-id>/`（run-id 用公司加期间，如 `300001-2024`）。所有脚本通过
  `uv run --project finance-macro/financial-statement-analysis python finance-macro/financial-statement-analysis/scripts/<脚本> ...` 执行，命令从仓库根发出；统一入口支持从任意 cwd 执行（路径以脚本位置定位）。
- 脚本 stdout 只有单条 JSON；正文证据通过 `pack_context.py` 的包读取。退出码：0 成功；1 致命错误（修复后重跑）；2 可交付但不完整（读 issues 降级受影响结论）。

## 执行顺序（统一阶段入口）

日常分析用 `run_pipeline.py`（prepare/compute/report/review）；`extract_sections.py` 与 `pack_context.py` 仍直接调用。

1. `run_pipeline.py prepare --url <URL> --run-dir <运行目录>` — 下载、缓存（核对 URL 与哈希，防误复用旧 PDF）、生成 `document.json`/`sections.json`，返回章节定位摘要。`run-dir` 不得指向 Skill 源码目录。
2. `extract_sections.py --run-dir <运行目录> --sections <重点章节ID>` — 增量提取证据，保留旧 ID 与文件。扫描页缺 OCR 能力时退出 2，把未提取页列入报告"未验证事项"。
3. `pack_context.py --run-dir <运行目录> --stage map --request-id map-01 --sections ...` — 读证据内容（每包 ≤12,000 字符；`--pages` 支持 `1,3,5-9` 范围语法；`next_cursor` 非空则继续 `--cursor` 续读）。`image_crop` 必须实际查看图片；未查看或不可辨认时不得据其确认数字。
4. 写 `fact_inputs.json`（合同与示例见[fact-inputs-example](references/fact-inputs-example.md)）— 只提交指标映射、原文值与证据定位；归属维度、期间结构、`missing_reason` 由程序推导，**缺失不是零**。
5. `run_pipeline.py compute --run-dir <运行目录>` — 表格 cell/文本 label 逐项核对后构造 `financials.json`，计算指标与勾稽。exit 2 返回 `mapping_validation.json` 定位修复；按 `input_index` 修改 `fact_inputs.json` 重跑。**初检 + 最多两次修复**，预算持久化在 `run_state.json`，相同输入重跑不消耗预算，重启不重置；预算耗尽后须新建运行目录或申请维护。
6. 分析与回查 — 基于 metrics 与证据分析；初始发现按[分析框架](references/analysis-framework.md)回查表定向补提（`extract_sections.py --pages N-M`），**最多两轮**，仍未解决就保留不确定性。
7. 写 `report_inputs.json`（合同与示例见[report-inputs-example](references/report-inputs-example.md)）— 用结构化绑定（fact_id/metric_id + 格式符）表达定量陈述；不要手写正文再补引用。
8. `run_pipeline.py report --run-dir <运行目录>` — 同源渲染 `analysis.md` 与 `report_claims.json`，随后固定 `validate_report` 独立校验。渲染修复清单见 `render_issues.json`，校验明细见 `report_validation.json`；同样受初检+2 次修复预算约束。
9. `run_pipeline.py review --run-dir <运行目录>` — 只读当前阶段、质量状态与剩余修复次数，不触发重算。

## 运行时边界

- 分析运行不得修改 `scripts/`、`references/`、校验规则、`extraction_manifest.json` 或任何校验结果；事实修复只能改 `fact_inputs.json` / `report_inputs.json`，且必须有原文依据。
- `run_state.json` 是诊断状态，不是安全权威；受保护模式（agent 凭据不可写 Skill 目录）由宿主实施，仅靠提示词不算完成。
- `quality_status`：`verified`（报告通过机器校验，发布方视为正式完成）/ `partial`（预算内可修复或数据不足）/ `maintenance_required`（预算耗尽或源码/依赖/校验器故障，属于维护问题，不在分析任务内修程序）。
- Skill 不直接发钉钉/RSS；发布归调用端，且只把 `verified` 当作完整结果发送，`partial` 不得包装为高质量结论。

## 降级规则

- 摘要、季报：不要求附注与审计；缺比较期不下趋势结论，不年化。
- 重述：比较期用本 PDF 披露的可比口径；调整前后不混用。
- 金融企业（银行/保险/证券）：只做适用的基础分析，明示未使用专用分析框架，不跑一般企业完整风险清单，不计算存货/应收周转。
- 审计：无保留意见中的关键审计事项不等于非标意见；持续经营事项单列。

## 完成条件

- `run_pipeline.py review` 返回 `quality_status: verified`；关键数字全部有来源（原文页码或带输入来源的计算）。
- 风险信号逐项标注：触发 / 已检查未发现 / 资料不足 / 行业不适用；筛查线索不写成造假结论。
- `context_usage.jsonl` 已记录交付量；实际模型 token 用量只有在宿主提供时才记录，否则留空说明不可获取。
