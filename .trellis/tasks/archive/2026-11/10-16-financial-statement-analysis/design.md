# 技术设计

这是 Trellis 任务的执行设计。财务规则的详细依据保留在 `docs/superpowers/specs/2026-10-16-financial-statement-analysis-design.md`；本文补齐模块边界、接口、默认值与成本验证。

## 架构与职责

由 skill 所在的 agent 编排流程。Python 工具完成确定性工作；不额外开发一个内嵌模型 API 的应用，不要求用户提供新的 API key。

```text
URL → fetch_pdf → inspect_pdf → extract_sections
    → pack_context → agent 映射 financials.json
    → calculate_metrics → agent 分析并有限回查
    → agent 写 analysis.md + report_claims.json
    → validate_report + agent 语义复核
```

下载、全文提取和计算留在本地。模型通过有限大小的上下文包读取目录、表格和附注；即使本地已经得到全文，也不把全文打印回对话。

## 文件边界

源码目录：`finance-macro/financial-statement-analysis/`。

| 文件 | 职责 |
|---|---|
| `SKILL.md` | 触发、输入输出、agent 与脚本分工、按需读取和完成条件 |
| `pyproject.toml`、`.python-version`、`uv.lock` | 独立 Python 3.12 环境与锁定依赖，`uv` 运行 |
| `scripts/artifacts.py` | 运行目录、UTF-8 JSON、文件原子写入和简短状态输出 |
| `scripts/fetch_pdf.py` | HTTP 获取、文件校验、来源与缓存 |
| `scripts/inspect_pdf.py` | 文档元数据、逐页索引、章节候选、页码核验 |
| `scripts/extract_sections.py` | 指定章节/页面的文字、跨页表格与 OCR 降级 |
| `scripts/financial_schema.py` | 事实合同验证、金额标准化、期间与范围过滤 |
| `scripts/calculate_metrics.py` | 指标、勾稽及计算来源 |
| `scripts/pack_context.py` | 按阶段提供限量证据包、分页游标与读取记录 |
| `scripts/validate_report.py` | 报告数据、页码和引用完整性检查 |
| `references/analysis-framework.md` | 分析规则、附注回查、指标适用性 |
| `references/extraction-rules.md` | 章节/科目映射、合并与期间规则、OCR 路由 |
| `references/artifact-contracts.md` | agent 生成事实与结论台账所需的合同 |
| `references/report-template.md` | 中文 Markdown 模板和来源格式 |
| `tests/` | 本 skill 的离线测试、合成样本及真实样本清单 |

运行目录默认 `finance-macro/output/financial-statement-analysis/<run-id>/`，使用现有忽略规则。缓存位于 `finance-macro/cache/financial-statement-analysis/`。可用 `--output-dir` 改写输出位置。完整财报及批量页面图不进 Git。

依赖拟采用 httpx、PyMuPDF、pdfplumber、jsonschema，开发依赖 pytest、ruff；具体版本在实现并验证后写入锁文件。OCR 通过运行时能力探测接入本机 OCRmyPDF/Tesseract，不能假设 Windows 已安装可用的系统组件和中文语言包。

## CLI 合同

以下命令均通过 `uv run --project finance-macro/financial-statement-analysis python finance-macro/financial-statement-analysis/scripts/<脚本>` 执行。

| 脚本参数 | 产物 |
|---|---|
| `fetch_pdf.py --url <URL> --output-dir <运行目录>` | `source.pdf`、`source.json` |
| `inspect_pdf.py --run-dir <运行目录>` | `document.json`、`pages.jsonl`、`sections.json` |
| `extract_sections.py --run-dir <运行目录> --sections <章节ID列表>` | `extraction_manifest.json`、`excerpts/`；支持 `--pages 18-22` 定向补提取 |
| `pack_context.py --run-dir <运行目录> --stage locate --request-id locate-01` | `context/` 中的上下文包、`context_usage.jsonl`；stdout 返回一个有限大小的包 |
| `calculate_metrics.py --run-dir <运行目录>` | 读取 agent 写入的 `financials.json`，生成 `metrics.json`、`validation.json` |
| `validate_report.py --run-dir <运行目录>` | 读取 `analysis.md` 和 `report_claims.json`，生成 `report_validation.json` |

`pack_context.py` 的 stage 枚举为 `locate/map/analyze/review`；支持 `--sections <ID列表>`、`--pages 18-22`、`--max-chars 12000` 和 `--cursor <不透明游标>`。大包必须在文字块/表格边界分页，不能静默截掉行列。特别大的表格逐批分行并重复必要表头，保持证据编号稳定。

除 pack_context 外，脚本 stdout 只返回单条 JSON 状态与产物路径；详细日志写 stderr 或文件。成功/完整输出退出 0，致命获取或合同错误退出 1，可交付但不完整退出 2。退出 2 时 agent 必须读取缺失清单并降级受影响结论。

## 产物合同

- `source.json`：schema_version、requested_url、final_url、downloaded_at、sha256、size_bytes、etag、last_modified、parser_version；可选值用 null。
- `document.json`：公司、代码、报告类型、期间、全文/摘要、会计准则、币种、审计状态、页数、元数据冲突和文档适用范围。
- `pages.jsonl`：每页的 pdf_page（从 1 开始）、printed_page（可空）、文字块/坐标、文字质量、扫描区域标志和标题候选。原始全文仅在此本地索引中保存。
- `sections.json`：稳定 section_id、标题、起止页、优先级、定位依据及待核验状态；不能仅以关键词命中代表已确认章节。
- `extraction_manifest.json`：每个 evidence_id 的来源页/区域、文字或表格文件、提取方式、完整性和问题。
- `financials.json`：schema_version、document_sha256 和 facts 列表。每条含 fact_id、metric、raw_label、raw_value、raw_unit、value、unit、currency、scope、attribution、period、basis、evidence_ids、review_status、missing_reason。金额 value 为十进制字符串或 null，unit 统一为原币种的基本单位（如元），currency 保留原币种；不擅自换汇，每股及比率使用独立单位。
- `period`：kind 为 instant/duration，start（时点可空）、end、frequency 为 annual/half_year/quarter，aggregation 为 instant/cumulative/single_period。`scope` 为 consolidated/parent，`attribution` 为 group/owners/not_applicable；`basis` 为 as_reported/restated。
- `review_status` 为 verified/ambiguous/missing/conflict。非空 value 必须有可解析的 evidence_ids；value 为 null 时 missing_reason 必填，证据可为空，不得虚造来源。正常数值的 missing_reason 为 null。
- `metrics.json`：每项 metric_id、value、status、formula、input_fact_ids、source_pages、reason。状态为 computed/not_applicable/insufficient_data/conflict。
- `validation.json`：检查项、状态、输入事实、残差/容差和问题原因；抽取冲突独立于财务风险。
- `report_claims.json`：每项 claim_id、report_anchor、text、fact_ids、metric_ids、evidence_ids、source_pages、claim_type（fact/calculation/inference/company_explanation）。
- `report_validation.json`：引用是否存在、页码是否真实、计算值与报告数字是否一致、未解决缺失；不能将机器检查结果称为语义分析已正确。

金额转换 API：`parse_amount(raw_value: str, raw_unit: str) -> Decimal | None`，支持元/千元/万元/亿元和括号负数；破折号及空白默认返回 None。合同验证 API：`validate_financials(document: dict) -> list[dict]`，不符合同的输入不能静默通过。

指标 API：`calculate_metrics(document: dict) -> dict`，只使用通过合同检查的、同期间/范围/归属事实。实现时为 CLI 添加脚本入口，不在模块 import 时下载文件或执行分析。

事实筛选 API：`select_facts(document: dict, metric: str, scope: str, attribution: str, aggregation: str) -> list[dict]`，返回符合条件的候选，调用方仍需核对期间和版本；有冲突时不得默认取第一项。

## 处理默认值与恢复

- HTTP 连接超时 10 秒、读取超时 45 秒、文件上限 200 MiB；临时错误最多三次尝试，退避 1、2 秒。参数可覆盖。
- 文件头检查与可打开性检查同时使用；先临时文件后原子落盘，避免中断污染缓存。
- URL 更新检测利用可用的 ETag/Last-Modified；内容复用依据 SHA-256。提取缓存另含解析版本与选项，不只按 URL 命中。
- 原生文档：书签/目录核验后，全文轻扫、重点页提取。扫描文档有目录时先 OCR 目录；没有可用目录时先逐页轻量 OCR 发现章节。混合页逐区域判断。
- 关键数值回看原表；无法解决的歧义最多两轮定向补提取，之后保留缺失/冲突。不得为了勾稽成立改写原始数字。
- 摘要、季报不要求存在完整附注或审计。金融企业使用有限模式，不运行一般企业完整风险清单。

## 财务计算约束

财务分析详细规则沿用原设计第 7-9 节，执行时特别验证：

1. 同口径的本期/上期比较，累计值不能当单季，重述前后分开。
2. 现金变动勾稽使用现金及现金等价物，纳入汇率等披露调节项；不能拿货币资金直接相减。
3. CFO/集团净利润与扣非归母/归母分别计算；负分母、零分母或口径不齐时不做质量等级推断。
4. 简化自由现金流使用 CFO 减购建长期资产支付的现金；该口径明示，不使用投资现金流净额替代。
5. 杜邦使用集团净利润、平均总资产和平均总权益，与披露的归母加权 ROE 分列。平均余额不足则输出不足，不伪造期初数。
6. 应计比率若计算，采用同期间 `(集团净利润 - CFO) / 平均总资产`；不按统一阈值断言风险。
7. 应收周转以收入/平均适用应收口径作为明示近似，存货周转以营业成本/平均存货；金融企业不适用。
8. 留存收益变化需考虑分红与权益调整，经营现金流桥接优先依据补充资料，不用简式断言异常。

## 上下文与 token 验证

每个上下文包默认最多 12,000 个 Unicode 字符，计数包含实际输出的内容、来源元数据和游标；这是传输上限，不是 token 数。阶段索引返回章节和 evidence_id，需要证据时再取内容。分包必须保留表头与来源，模型从已生成事实和指标继续，不重复装载全文。

`context_usage.jsonl` 追加 request_id、stage、packet_sha256、evidence_ids、character_count、byte_count、cursor。分别汇总交付总量、唯一包量和重复包量；重复读取不能从总量中扣除。

可选指定 tokenizer 时，记录 tokenizer 名称与版本及 estimated_input_tokens；没有 tokenizer 时留空。若宿主可提供请求级 input/output/cached tokens，则原样记录到 `model_usage.json`，并注明涵盖的请求范围。工具载荷统计不能覆盖系统提示、对话历史、推理或图片成本，不能当作实际账单。

基准样本至少包含一份超过 100 页的文字年报。以同样的字符串统计方法比较“全文工具交付”和“按需工具交付”的总字符量，初始目标下降至少 50%；同时要求关键字段、风险证据及最终结论覆盖不下降。基准记录冷/热缓存、OCR/图片调用次数、回查轮次、耗时以及可获取的实际用量。

## 兼容与回滚

不改变已有 skill 的调用方式或发布流程，不在脚本内修改 agent 全局设置。只增加独立 skill 和根 README 中一条索引。未达到验收时不发布；缓存可绕过后重跑，保留原 PDF 与已核验事实。无需修改原有 git-commit-push 的未提交文件。

## 当前状态

接口及默认值为本任务确定的开发合同。真实 PDF 效果、依赖兼容性和上下文节省比例尚未实测，按 implement.md 完成后记录证据。仓库自动生成的全局 bootstrap-guidelines 任务保留，当前不将其他主题的规范整理纳入本任务。
