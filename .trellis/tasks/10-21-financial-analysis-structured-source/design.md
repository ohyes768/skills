# 设计：结构化打底、PDF 验证、免疫系统不动

## 1. 边界与核心决策

数据流反转：结构化数据由程序拉取并直接生成 facts（source=structured），PDF 从「数据来源」降级为「验证来源 + 页码引用来源」。LLM 不再从 PDF 抽数，其 PDF 侧职责是抽查验证与分析判断。校验层零改动——勾稽、维度、期间、渲染同源校验、修复预算、quality_status 语义照旧。

不引入 akshare（实测其请求层对本样本失败），直接封装东财 datacenter F10 HTTP。结构化源永远不是唯一权威：与 PDF 抽查不一致即 conflict。

## 2. 新增与改动

### fetch_structured.py（新增）

- CLI：`fetch_structured.py --code 301313 --report-date 2026-06-30 --run-dir DIR`；`run_pipeline.py` 新增 `structured` 子命令包装（或并入 prepare，设计倾向独立命令，由 compute 前置调用）。
- 三表各一次请求（RPT_F10_FINANCE_GBALANCE / GINCOME / GCASHFLOW），columns=ALL，浏览器 UA，超时与有限重试对齐 fetch_pdf 常量风格。
- 产物 `structured_financials.json`：
  - `schema_version`、`security_code`、`report_date`、`fetched_at`、`source: structured_eastmoney`
  - `reports: {balance: {...}, income: {...}, cashflow: {...}}`（原始字段全保留，不裁剪——映射规则演进时无需重拉）
  - `response_sha256` 与 requested 参数记录，缓存复用时核对（同 fetch_pdf 的 requested_url 逻辑）
- HTTP 失败/非 JSON/无数据 → 退出 1；由调用方决定回退纯 PDF 模式（R6），fetch 层不做静默降级。

### fact 合同与映射（financial_schema.py / build_financials.py）

- `_FACT_FIELDS` 增加 `source`；取值 `{"structured", "extracted"}`，缺省视为 `extracted`（旧产物兼容）。`validate_financials` 校验枚举。
- `build_financials.build_financials(run_dir, inputs, structured=None)`：传入 structured_financials 时走新分支——
  - 字段映射表 `STRUCTURED_FIELD_MAP`（STATIC dict）：metric → (report, field)，如 revenue→(income, TOTAL_OPERATE_INCOME)、net_profit_owners→(income, PARENT_NETPROFIT)、cfo→(cashflow, NETCASH_OPERATE)、cash_equivalents→(cashflow, END_CCE)、capex→(cashflow, CONSTRUCT_LONG_ASSET)、monetary_funds→(balance, MONETARYFUNDS) 等，覆盖 METRIC_CONTRACTS 全部条目；缺失映射的 metric 在 mapping_validation 记 warning（结构化模式不支持，需 PDF 证据）。
  - period 由 report_date 推导（复用既有 `_resolve_period`，frequency 归一化逻辑复用）。
  - 生成的 fact：`source=structured`、`evidence_ids=[]`、`review_status=verified`（来自程序拉取的披露口径，非 LLM 判断——但必须过 R4 抽查才能用于报告）。
- 单位：东财数值为元（float 进 JSON 会失真，字段原样保留为 number，映射时转 Decimal 字符串，禁止经 float 舍入路径——原始 JSON 解析即 str 或 Decimal）。

### 抽样核对（R3/R4 的核心机制）

- `structured_sample_check(run_dir, structured_facts, sample_size)`：默认样本 = 营收、归母净利、CFO、总资产、货币资金五项；LLM 可通过 fact_inputs 的 override 增删。
- 核对方式：对每个样本，在既有 PDF 证据（text/table excerpts）中定位该数值（复用 pack_context 的证据检索 + report_values 的数值匹配），一致 → 通过；找不到或数值不一致 → mapping_validation 记 conflict，run 不得 verified。
- 抽样核对由 compute 阶段执行，结果落 `structured_check.json`；样本「找不到」与「数值不一致」分开计数（前者可能只是证据未提取，提示 evidence 补提而非数据错误）。

### run_pipeline 接入（R7）

- `compute` 增加可选 `--structured`：存在 structured_financials.json 时走双源分支；显式 `--no-structured` 强制纯 PDF。
- prepare 不自动拉结构化（保持 prepare 语义纯净），`structured` 作为独立子命令或 compute 的前置步骤，失败时输出回退提示（R6）。
- report 不感知数据源差异（校验合同统一）。

## 3. 不变项

- validate_report / render_report / pack_context / extract_sections / inspect_pdf / fetch_pdf：零改动或仅文档。
- 修复预算、quality_status、运行时边界、SKILL.md 的红线表述：不变。
- 纯 PDF 模式路径：为默认回退且保持可用（A5）。

## 4. 风险与对策

- 东财接口改版/限流：response 结构校验 + 字段版本记录 + 回退路径（R6）；接口字段在 structured_financials.json 全量留档，重放诊断不依赖再次请求。
- float 精度：JSON number → Decimal 转换统一走 `str(value)` → Decimal，禁止直接 Decimal(float)。
- 口径差异（重述/调整）：结构化源的 REPORT_DATE 期数据可能与 PDF 披露的调整前口径不同 → 抽样核对就是为此设计的闸门；冲突时以 PDF 为准并记 conflict。
- 测试样本依赖：A2 用 301313 已验证数据做金样本；不把私有运行产物提交仓库，测试内嵌最小 fixture。

## 5. 验收与回滚

- 性能对比（R8）与 Hermes 任务 10-19 的 A8 同风格：固定 PDF/模型/profile，两模式各 ≥3 次。
- 回滚：`--no-structured` 或删除 structured_financials.json 即回到现状；新代码全部为增量分支，不影响既有路径。
