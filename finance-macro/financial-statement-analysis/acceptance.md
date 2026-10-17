# Acceptance Record — financial-statement-analysis

验收日期：2026-10-17。全部结论基于 2026-10-17 的真实运行，证据路径均相对仓库根。

## 样本

| run-id | 公司 | 报告 | 页数 | 观察 |
|---|---|---|---|---|
| 600519-2024 | 贵州茅台 | 2024 年报（全文） | 143 | annual / audited / general |
| 300001-2024 | 特锐德 | 2024 年报（全文） | 286 | annual / audited / general |
| 300001-2024h1 | 特锐德 | 2024 半年报 | 234 | semi_annual / **unaudited**（正确降级） |
| 600036-2024 | 招商银行 | 2024 年报（全文） | 362 | annual / audited / **financial_institution**（降级触发） |

样本 URL 与 SHA-256 见 [tests/fixtures/sample-manifest.json](tests/fixtures/sample-manifest.json)。PDF 原文件在 `finance-macro/output/financial-statement-analysis/<run-id>/source.pdf`（不入 Git）。

## A01 / R01-R02：下载与诊断

- 通过。茅台（3.5MB）、特锐德（7.7MB）、招行（6.1MB）经 `fetch_pdf.py` 真实下载，`source.json` 记录 final_url、sha256、size；`inspect_pdf.py` 自动识别公司与期间（含"公司代码""股票代碼"繁体、"2024年度报告"变体、封面无代码时的全文兜底）。
- 失败路径（HTML 假文件、超限、截断、4xx/5xx、三次重试）由离线测试覆盖（`tests/test_fetch_pdf.py`，13 例）。

## A02 / R03-R04：章节定位与跨页

- 通过。茅台：审计报告 p55-57、合并资产负债表 p58-61、合并利润表 p63-64、合并现金流量表 p66-69、所有者权益变动表 p70-73，书签定位全部 verified；损坏书签（指向 p2）被核验机制拒绝后由标题扫描找回真实位置。
- 跨页溢出：合并表尾行落在下一节首页（p61/p68 顶部），通过 `--pages 61,68` 定向补提取拿全，勾稽残差 0.00 证明关键字段无缺失。
- 列定义不一致的续页如实拆分并记 issue（茅台 4 处"column definition mismatch"），未静默拼接。
- 扫描/混合页与 OCR 降级由合成夹具验证（`tests/test_extract_sections.py`）；本机未装 tesseract，真实 OCR 路径未在真实 PDF 上运行，环境缺失时退出 2 并列出未提取页。

## A03 / R05：关键字段与来源

- 通过（茅台样本）。32 条事实（`600519-2024/financials.json`）全部合并口径、元单位、Decimal 字符串、带 evidence_ids；归母/集团、期初期末时点、年报期间无混用。回归断言见 `tests/e2e/test_saved_artifacts.py::test_key_facts_match_manual_annotation`。
- 扣非归母净利润未提取（位于未覆盖章节），在 `analysis.md` 中登记为缺失而非补造。

## A04 / R06：指标计算

- 通过。revenue_yoy 15.71%、net_profit_group_yoy 15.24%、net_profit_owners_yoy 15.38%、净利率 52.27%、CFO/净利 1.035、简化 FCF 877.85 亿、简化 ROE 38.37%、杜邦三因子乘积一致、存货周转 0.274。零/负基期、缺平均余额、累计/单季混用、母公司混入、重述冲突在 `tests/test_metrics.py` 覆盖并返回 not_applicable / insufficient_data / conflict。

## A05 / R07-R08：报告可追溯

- 通过。`analysis.md` 交付；14 条 claims（`report_claims.json`）经 `validate_report.py` 机器校验 exit 0（fact/calculation/inference/company_explanation 四类，全部有 evidence/metric 支撑，页码在范围内）。校验器曾抓到 CFO 比率表述与 metric 值不匹配（1.035 vs 1.0350251…），修正为 103.5% 后通过——机器校验有效的直接证据。语义复核（因果、解释充分性）为本报告的人工声明部分。

## A06 / R09：上下文包上限

- 通过。`pack_context.py` 单包 ≤12,000 Unicode 字符（`character_count` 与整包 JSON 长度一致），超限内容按行/行组分页并重复表头，`next_cursor` 续读。测试 `tests/test_pack_context.py`（10 例）。

## A07 / R09：上下文节省 ≥50%

- 通过。茅台 143 页：全文候选文本 144,135 字符；严格按 SKILL.md 的最小读取序列（3 个 map 包 + 1 个补提包）交付 31,286 字符，**削减 78.3%**（目标 ≥50%），关键字段（含跨页溢出行）全部覆盖、勾稽残差 0.00。调试期产生的重复读取台账另存于 `600519-2024/context_usage.debug.jsonl`（12 包 95,090 字符，削减仅 34%——重复装载的实际代价记录在案）。

## A08 / R09：token 口径

- 通过。`context_usage.jsonl` 每行 `estimated_input_tokens=null`、`tokenizer=null`（未接 tokenizer，置空不伪造）；本宿主未提供请求级用量，`model_usage.json` 未生成即表示不可获取，未用字符数冒充计费 token。

## A09 / R10：披露条件降级

- 通过。特锐德半年报识别为 semi_annual 且因明文"半年度报告未经审计"判 unaudited（不要求审计与完整附注）；招行识别为 financial_institution（不跑一般企业风险清单）；茅台扣非归母缺失登记为"资料不足"；无来源的历史趋势未生成。

## A10 / R11：完整验证

- 离线测试：96 例全部通过（`uv run --project finance-macro/financial-statement-analysis pytest finance-macro/financial-statement-analysis/tests -q`，其中 e2e 在产物缺失时自动 skip）。
- 真实样本回归：`tests/e2e/test_saved_artifacts.py` 5 例通过（文档识别、关键字段、指标与勾稽、报告校验、上下文目标）。
- lint 与 skill 元数据校验在 T10 执行记录。

## 已知局限

1. 真实扫描件的 OCR 逐页章节发现未在真实样本上运行（本机无 tesseract）；混合页裁剪图已保存。
2. 母公司所有者权益变动表之后的附注页归入该 section 的 end_page（无独立附注标题可切分），agent 编排层按需选页可规避。
3. 母公司现金流/权益变动表的提取策略与合并表相同，但本次验收未逐一核对母公司报表数值。
