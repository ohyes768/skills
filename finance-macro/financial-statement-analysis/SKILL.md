---
name: financial-statement-analysis
description: A 股财报 PDF 深度分析。输入一份财报 PDF 链接（年报优先），下载后在本地建立页码索引、按需提取重点章节证据，产出带原文页码引用的中文 Markdown 分析，覆盖经营变化、盈利质量、现金与负债、杜邦分解和风险信号，全部关键数字可追溯。当用户要求分析年报/财报/招股书财务部分、解读上市公司业绩、检查财务风险，或给出 cninfo/sse/szse 的财报 PDF 链接时使用。不用于估值定价、目标价、交易建议或行业研究。
---

# A 股财报 PDF 分析

由你（agent）编排流程；Python 脚本完成下载、索引、提取和计算的确定性工作。全文只存在于本地索引，**任何情况下不要把全文打印回对话或要求脚本输出全文**。先读[产物合同](references/artifact-contracts.md)、[分析框架](references/analysis-framework.md)与[报告模板](references/report-template.md)；提取规则见[提取规则](references/extraction-rules.md)。

## 输入与运行目录

- 必填：财报 PDF 链接（`pdf_url`）。自动识别公司、期间、报告类型；无法确认时中止并说明，不输出貌似完整的分析。
- 运行目录：`finance-macro/output/financial-statement-analysis/<run-id>/`（run-id 用公司加期间，如 `300001-2024`）。所有脚本通过
  `uv run --project finance-macro/financial-statement-analysis python finance-macro/financial-statement-analysis/scripts/<脚本> ...` 执行，命令从仓库根发出。
- 脚本 stdout 只有单条 JSON；正文证据通过 `pack_context.py` 的包读取。退出码：0 成功；1 致命错误（修复后重跑）；2 可交付但不完整（读 issues 降级受影响结论）。

## 执行顺序

1. `fetch_pdf.py --url <URL> --output-dir <运行目录>` — 下载与缓存。失败时诊断 HTML/失效/超限/损坏，不生成假报告。
2. `inspect_pdf.py --run-dir <运行目录>` — 生成 `document.json`（公司、期间、审计状态、适用框架）、`pages.jsonl`（逐页索引）、`sections.json`（章节候选）。`verified: false` 的章节仅是候选。
3. `pack_context.py --run-dir <运行目录> --stage locate --request-id locate-01` — 读章节索引，确定重点章节：财务摘要、管理层讨论与分析、合并三表、审计报告。
4. `extract_sections.py --run-dir <运行目录> --sections <重点章节ID>` — 提取证据。扫描页缺 OCR 能力时退出 2，把未提取页列入报告"未验证事项"。
5. `pack_context.py --stage map --request-id map-01 --sections ...` — 读证据内容（每包 ≤12,000 字符；`next_cursor` 非空则继续 `--cursor` 续读，重复读取计入交付台账，避免无谓复读）。
6. 写 `financials.json` — 按产物合同映射事实：合并/母公司、集团/归母、累计/单季、调整前后不得混用；每个数值带 `evidence_ids`；缺失写 `missing_reason`，**缺失不是零**；破折号与空白保持缺失。
7. `calculate_metrics.py --run-dir <运行目录>` — 脚本计算同比、盈利质量、简化自由现金流、杜邦与勾稽。exit 1 = 事实合同错误，必须修复；exit 2 = 勾稽未过，先回查证据（页码、列映射、单位），不得为凑平改数字。
8. 分析与回查 — 基于 metrics 与证据分析；初始发现按[分析框架](references/analysis-framework.md)回查表定向补提（`extract_sections.py --pages N-M`），**最多两轮**，仍未解决就保留不确定性。
9. 写 `analysis.md`（按[报告模板](references/report-template.md)）和 `report_claims.json` — 每条关键陈述登记 claim：fact/calculation/inference/company_explanation 四类，fact 与 calculation 必须能追溯到 evidence/fact/metric。
10. `validate_report.py --run-dir <运行目录>` — 机器校验引用与页码。exit 2 时修复 claims 后重跑，通过后再做语义复核（因果、管理层解释充分性），机器通过不等于语义正确。

## 降级规则

- 摘要、季报：不要求附注与审计；缺比较期不下趋势结论，不年化。
- 重述：比较期用本 PDF 披露的可比口径；调整前后不混用。
- 金融企业（银行/保险/证券）：只做适用的基础分析，明示未使用专用分析框架，不跑一般企业完整风险清单，不计算存货/应收周转。
- 审计：无保留意见中的关键审计事项不等于非标意见；持续经营事项单列。

## 完成条件

- `validate_report.py` 通过；关键数字全部有来源（原文页码或带输入来源的计算）。
- 风险信号逐项标注：触发 / 已检查未发现 / 资料不足 / 行业不适用；筛查线索不写成造假结论。
- `context_usage.jsonl` 已记录交付量；实际模型 token 用量只有在宿主提供时才记录，否则留空说明不可获取。
