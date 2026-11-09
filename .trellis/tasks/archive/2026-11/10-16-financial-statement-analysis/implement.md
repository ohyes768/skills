# Financial Statement Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Project workflow: `.trellis/workflow.md`; current Codex mode is inline. Do not dispatch workers merely because this plan exists.

**Goal:** 将单个 A 股财报 PDF 链接转为可追溯、可校验、上下文消耗可观察的中文 Markdown 分析。

**Architecture:** Python 处理下载、索引、原始提取和计算，agent 映射事实并分析写作；按阶段交付重点证据。运行产物保存在源码外，OCR 按能力降级。

**Tech Stack:** Python 3.12、uv、httpx、PyMuPDF、pdfplumber、jsonschema、pytest、ruff；OCRmyPDF/Tesseract 为可选系统能力。

本轮只编写计划。以下框选项全部是开发时的待执行步骤，测试命令均未运行；`uv run` 可能首次安装已锁定依赖。所有命令从仓库根 `F:/personal-projects/skills` 执行。任务目录为 `.trellis/tasks/10-16-financial-statement-analysis/`。

## 开发范围及阶段依赖

| 阶段 | 任务 | 前置 | 阶段完成条件 |
|---|---|---|---|
| M1 PDF 数据准备 | T1-T4 | 先完成本任务文档审阅 | URL 能生成可定位的重点章节证据 |
| M2 财务事实与计算 | T5-T6 | T1 的文件合同；T4 提供集成样本 | 同口径事实、指标与勾稽可复核 |
| M3 Skill 与报告 | T7-T8 | T4-T6 | agent 可按 skill 生成有证据的报告 |
| M4 样本与成本验收 | T9-T10 | T1-T8 | 真实样本、退化行为、上下文目标均有记录 |

目录责任按 design.md 的文件边界划分。修改文件前检查工作区，已有 git-commit-push 的修改保持原样。除 T10 索引外不改根 README；业务实现不修改 Trellis 核心脚本、全局 agent 配置或其他主题 skill。

## T1：环境、产物合同和测试入口

**Create:** skill 根的 `pyproject.toml`、`.python-version`、`scripts/artifacts.py`、`references/artifact-contracts.md`、`tests/conftest.py`、`tests/test_artifacts.py`。

- [ ] 创建独立 Python 3.12 环境，pyproject 将运行依赖与 pytest/ruff 开发依赖分组；声明 `[tool.uv] package = false`；pytest 配置将本 skill 的 scripts 放入 pythonpath。
- [ ] 先写离线用例：临时运行目录、UTF-8 中文 JSON、Decimal 序列化为字符串、原子写入中断不覆盖已有有效文件、stdout 不包含正文。
- [ ] 运行 `uv run --project finance-macro/financial-statement-analysis pytest finance-macro/financial-statement-analysis/tests/test_artifacts.py -q`，先确认因缺少模块/行为失败。
- [ ] 实现 `write_json(path: Path, value: dict) -> None`、`read_json(path: Path) -> dict`、`emit_status(status: str, artifacts: dict, issues: list) -> None`，保持 import 无副作用。将 design.md 的所有产物字段逐项写入 artifact-contracts.md。
- [ ] 重跑同一命令，预期全部通过；执行 `uv lock --project finance-macro/financial-statement-analysis`，将锁文件列入后续提交范围。

**Gate:** 产物字段、CLI 退出码和事实 ID 合同稳定后再进入依赖这些接口的任务。

## T2：PDF 下载、来源与缓存

**Create:** `scripts/fetch_pdf.py`、`tests/test_fetch_pdf.py`。本节路径均相对 skill 根。

- [ ] 用 httpx MockTransport 测试有效 PDF、302、HTML 假文件、超限、读取中断、临时错误后成功及第三次仍失败；所有测试离线，不依赖真实网站。
- [ ] 运行对应测试文件，确认上述行为在实现前失败。
- [ ] 按 design.md 默认值实现下载；检查文件头并用 PDF 解析器打开。下载先写临时文件，完成后落盘；source.json 保存最终 URL 和哈希。
- [ ] 实现相同内容复用与 URL 更新重检；注入 transport 与等待函数，测试不得真实 sleep 或发送网络请求。
- [ ] 运行 `uv run --project finance-macro/financial-statement-analysis pytest finance-macro/financial-statement-analysis/tests/test_fetch_pdf.py -q`，预期通过；不完整或无效的下载不得留下可复用的有效缓存标记。

## T3：逐页索引、报告识别与章节定位

**Create:** `scripts/inspect_pdf.py`、`tests/test_inspect_pdf.py`、`tests/fixtures/build_synthetic_pdfs.py`。

- [ ] 使用 PyMuPDF 生成小型 PDF 夹具：目录与物理页偏移、书签、正文关键词误命中、合并及母公司同名表、原生与混合页。文件生成器属于测试，不向仓库放入整份真实年报。
- [ ] 为公司/期间冲突、目录目标核验、起止页、同名报表范围和稀疏文字页写失败用例。
- [ ] 实现 document.json、pages.jsonl、sections.json；保留 1-based 物理页与可空印刷页。章节候选必须有定位依据及已核验/待核验状态。
- [ ] 运行 `uv run --project finance-macro/financial-statement-analysis pytest finance-macro/financial-statement-analysis/tests/test_inspect_pdf.py -q`，预期通过；文本只出现在本地索引，不通过 stdout 返回全文。

## T4：重点章节、表格与扫描降级

**Create:** `scripts/extract_sections.py`、`tests/test_extract_sections.py`、`references/extraction-rules.md`。

- [ ] 写跨页表头、换年度列、括号负数、损坏文字层、图像表格和缺失 OCR 能力的失败用例；OCR runner 通过依赖注入替换，常规测试不调用外部 OCR。
- [ ] 实现 `--sections` 和 `--pages` 选择、文字块与坐标保存、表格提取策略和 evidence_id；拼接跨页表格前核验列定义。
- [ ] 实现 OCR 能力探测；无目录扫描件的章节发现先做逐页轻量 OCR，混合页按区域处理。环境缺少能力时明确退出 2 并列出未提取页面。
- [ ] 保存关键疑难页的图片或裁剪证据，记录方式和缺失原因；空白、破折号不擅自转零。
- [ ] 运行 `uv run --project finance-macro/financial-statement-analysis pytest finance-macro/financial-statement-analysis/tests/test_extract_sections.py -q`，预期通过，并人工查看一份跨页表格与一份混合页的保存产物。

**M1 检查点:** agent 可以从 URL 得到章节候选与原始证据；尚不能声称财务语义映射正确。

## T5：标准化事实、范围与期间合同

**Create:** `scripts/financial_schema.py`、`tests/test_financial_schema.py`；更新 `references/artifact-contracts.md`。

- [ ] 将以下测试写入 test_financial_schema.py，并追加 scope、attribution、period、basis、evidence_id 的缺失/非法组合测试。

```python
from decimal import Decimal
import pytest
from financial_schema import parse_amount

@pytest.mark.parametrize(("raw", "unit", "expected"), [
    ("1,234.50", "万元", Decimal("12345000.00")),
    ("(25.00)", "万元", Decimal("-250000.00")),
    ("0", "元", Decimal("0")),
    ("—", "元", None),
    ("", "元", None),
])
def test_parse_amount_preserves_value_and_missing(raw, unit, expected):
    assert parse_amount(raw, unit) == expected
```

- [ ] 运行该测试文件，确认模块/行为缺失导致失败；再实现 parse_amount 和 validate_financials，使用 Decimal，禁止二进制浮点偷偷进入金额合同。
- [ ] 实现筛选接口 `select_facts(document: dict, metric: str, scope: str, attribution: str, aggregation: str) -> list[dict]`；冲突不能默认取第一项。
- [ ] 运行 `uv run --project finance-macro/financial-statement-analysis pytest finance-macro/financial-statement-analysis/tests/test_financial_schema.py -q`，预期通过。

## T6：指标与三表校验

**Create:** `scripts/calculate_metrics.py`、`tests/test_metrics.py`、`tests/test_reconciliation.py`。

- [ ] 用 T5 合同构造完整事实夹具：营收 1000→1200，集团净利润 80→120，归母 70→110，扣非归母 90，CFO 150，购建长期资产现金 50，平均总资产 2000、平均总权益 800。预期同比收入 20%、集团净利率 10%、CFO/集团净利 1.25、简化自由现金流 100、集团简化 ROE 15%。
- [ ] 追加零/负基期、缺平均余额、季度累计、母公司重复值、重述前后混杂的失败用例。记录不得计算的指标应返回哪种状态和原因。
- [ ] 构造现金勾稽夹具：期初 100、CFO 20、CFI -10、CFF -5、汇率影响 2、期末 107，应通过；另设货币资金为 130，不能因此报现金勾稽失败。
- [ ] 先运行两个测试文件确认失败，再实现 calculate_metrics(document)、CLI 和 validation.json；容差按输入精度而不是固定差额 1。
- [ ] 运行 `uv run --project finance-macro/financial-statement-analysis pytest finance-macro/financial-statement-analysis/tests/test_metrics.py finance-macro/financial-statement-analysis/tests/test_reconciliation.py -q`，预期通过。

**M2 检查点:** 计算与验证结果来自稳定事实合同；原始披露值和计算值可区分。

## T7：上下文包、读取台账与用量边界

**Create:** `scripts/pack_context.py`、`tests/test_pack_context.py`。

- [ ] 构造超过 12,000 字符的文字块和跨页表格，先测试包上限、完整表头、分页后证据无遗漏、游标恢复、中文字符计数及重复包计量。
- [ ] 实现 design.md 的四阶段包和选择器。返回一个包并提供 next_cursor；大表按行组分页，必要时重复表头和证据编号。
- [ ] 将每次实际输出追加到 context_usage.jsonl，重复读取也累计交付总量；同时输出唯一包量供诊断。
- [ ] optional tokenizer 的结果命名 estimated_input_tokens；模型实际用量不可获取时用 null，不能写成 0。禁止将工具字符量标成模型总 token。
- [ ] 运行 `uv run --project finance-macro/financial-statement-analysis pytest finance-macro/financial-statement-analysis/tests/test_pack_context.py -q`，预期通过。

## T8：Skill 指令、分析规则与报告检查

**Create:** `SKILL.md`、`references/analysis-framework.md`、`references/report-template.md`、`scripts/validate_report.py`、`tests/test_validate_report.py`。

- [ ] 在写 skill 正文前，用一份真实请求做基线行为记录，观察缺少本 skill 时的章节选择、期间和来源引用；按 writing-skills 的方法记录实际失败，评估是否需要独立行为验证。
- [ ] 为 report_claims 的未知 fact_id/metric_id、越界页码、无证据风险、报告数字与 metrics 不符、披露值/推断混淆写失败用例。
- [ ] 实现 validate_report 的机器可验证部分并跑通对应测试。语义因果、管理层解释是否充分仍由 agent 审阅，不宣称正则能验证全部金融结论。
- [ ] 写精简 SKILL.md，包含 URL→本地处理→有限读包→映射事实→脚本计算→分析回查→报告与台账→机器检查和语义复核的执行顺序。
- [ ] 将原设计财务规则迁入 references，保留适用条件；风险信号不推算造假概率。明确两轮补提取上限、缺失状态、审计与金融行业降级规则。
- [ ] 执行 `python C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py finance-macro/financial-statement-analysis`，预期 skill 元数据与目录校验通过。
- [ ] 运行 `uv run --project finance-macro/financial-statement-analysis pytest finance-macro/financial-statement-analysis/tests/test_validate_report.py -q`，预期通过；用相同基线请求验证 skill 行为确实改善并保留结果。

**M3 检查点:** 用户只需 URL，agent 可按 skill 编排并生成有来源的中文报告；没有新增模型 API 服务。

## T9：真实样本、退化行为与成本基准

**Create:** `tests/fixtures/sample-manifest.json`、`tests/e2e/test_saved_artifacts.py`；运行结果写入 `finance-macro/output/financial-statement-analysis/acceptance/`。

- [ ] 从巨潮、上交所或深交所的官方公告中选取至少两份非金融企业年报（其中一份超过 100 页）、一份季报/半年报及一份金融企业报告；记录准确 URL、公司、期间、报告类型和 SHA-256，不把下载文件提交到仓库。
- [ ] 人工标注每份报告的三表关键字段、范围、单位、期间和 PDF 页码。扫描/混合页及重述案例可使用明确标记为合成的夹具，不能把合成结果当真实文档效果。
- [ ] 按 SKILL.md 运行全部链路，保存 financials、metrics、validation、analysis、report_claims 及机器/语义复核记录。用 saved_artifacts 测试对比人工标注；不可识别项明确登记，不补造。
- [ ] 对长年报统计全文候选文本量与实际按需交付总量，复读也计入总量。记录至少降低 50% 的目标是否达到，同时核对所有关键字段和风险证据没有丢失。
- [ ] 记录冷/热缓存、回查次数、OCR/图片调用、耗时；若宿主暴露用量，则记录实际 input/output/cached tokens，否则明确无法测得计费总量。
- [ ] 汇总 A01-A10 的结果与证据路径到 acceptance.md。任何关键数值错列、来源错误、虚构趋势或 token 口径错误均阻止完成；资料未披露导致的正确降级属于正常结果。

## T10：完整验证与交付

**Modify:** `README.md`（仅新增金融分类索引）；按验收结果更新本任务文档和必要 references。

- [ ] 运行 `uv run --project finance-macro/financial-statement-analysis pytest finance-macro/financial-statement-analysis/tests -q`，预期离线与已保存样本回归均通过，真实网络测试不混入默认离线测试。
- [ ] 运行 `uv run --project finance-macro/financial-statement-analysis ruff check finance-macro/financial-statement-analysis/scripts finance-macro/financial-statement-analysis/tests`，预期无错误。
- [ ] 再运行 quick_validate.py，核对 references 链接、安装环境说明、退出 2 的处理和运行产物忽略规则。
- [ ] 人工检查最终报告：核心结论与页码一致、集团/归母和累计口径清楚、行业与数据不足项明确、未把筛查线索写成造假结论。
- [ ] 全部验收通过后增加 README 索引并记录 skill 的源码路径和运行示例；不自动安装或发布，不自动提交本仓库既有修改。

## 回滚与暂停点

- M1 无法稳定定位/提取：保留 PDF、索引和缺失清单，先修提取；不进入无来源的财务判断。
- M2 事实合同有歧义：回到 T5 修合同，重新跑 T5/T6；原始证据不改写。
- M3 报告引用不一致：回查 report_claims 与 evidence，受影响结论降级，检查通过前不交付完整分析。
- M4 未达到上下文目标：先检查重复装载和过宽章节选择，再优化；保留关键数字与附注证据，不以删证据换取低字符数。
- 暂停或重跑时保留运行目录；旧缓存可以绕过并重新解析，无需改动其他 skill。

## 需求覆盖

| 需求 | 任务 |
|---|---|
| R01-R02 | T1-T3、T9 |
| R03-R04 | T3-T4、T9 |
| R05-R06 | T5-T6、T9 |
| R07-R08 | T8-T10 |
| R09 | T7、T9 |
| R10 | T3-T6、T8-T9 |
| R11 | T1-T2、T10 |

规划自查完成：需求有任务映射，CLI/产物/API 名称一致，四个阶段依赖明确，真实用量与交付量区分。进入开发时先加载项目 trellis-before-dev 和执行计划技能，之后按 Trellis 生命周期推进；本轮不运行 task.py start。
