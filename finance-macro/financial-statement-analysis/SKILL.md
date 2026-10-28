---
name: financial-statement-analysis
description: 使用东财 F10 接口分析 A 股公司财务。输入股票代码与报告期，获取合并三表，生成带接口字段和期间来源的中文 Markdown 报告，覆盖盈利质量、现金负债、杜邦分解和风险信号。适用于分析上市公司年报业绩、季度或半年度财务变化与财务风险；不用于估值定价、目标价或交易建议。
---

# A 股 F10 财务分析

数据统一来自东财 F10 合并三表接口。程序负责取数、期间配对、指标计算、来源校验与报告渲染；agent 根据返回数据撰写判断。不手工录入财务数字，不补造接口未提供的公司解释或附注。

## 输入

- 必填：六位股票代码 `code`、报告期末 `period`（如 `2026-06-30`）。支持季度末、半年末和年末，流量数据均为年初至期末累计。
- 使用宿主指定的唯一 `run-dir`；未指定时使用 `finance-macro/output/financial-statement-analysis/<code>-<period>/`。一个目录绑定一个代码和报告期。
- 接口无数据或字段为空时保留缺失，说明覆盖限制；不估算、不填零、不切换其他来源。

## 工作流

命令从仓库根执行，统一前缀为：

```bash
uv run --project finance-macro/financial-statement-analysis python finance-macro/financial-statement-analysis/scripts/
```

开工只读[分析框架](references/analysis-framework.md)和[可复用工具](references/reusable-tools.md)。写报告前读[报告模板](references/report-template.md)、[指标目录](references/metric-catalog.md)与[报告输入](references/report-inputs-example.md)。接口与产物合同见[artifact-contracts](references/artifact-contracts.md)，复核规则见[independent-review-contract](references/independent-review-contract.md)。

1. `run_pipeline.py prepare --code <代码> --period <YYYY-MM-DD> --run-dir <目录>`：拉取本期、上年同期与期初所需三表，留档原始响应、请求参数、抓取时间与响应摘要。已成功的条目使用缓存；缺失条目重跑只补缺失。仅需主动重取时加 `--refresh`。
2. `run_pipeline.py compute --run-dir <目录>`：从留档生成事实、指标、风险筛查和紧凑分析包。stdout 与 `pack_context.py` 使用同一层 `packet.next_cursor`。它非空时用下面的命令续读，直到 `packet.next_cursor` 为 null。`pack_context` 没有 `context` 键；`compute` 里的 `context` 只是兼容别名。游标错误返回 `status=failed` 且 `ended=false`，不能当成结束。正常写作使用分析包里的覆盖、利润桥、比率和待办，不读脚本源码，不把原始响应整文件扫一遍。

```bash
uv run --project finance-macro/financial-statement-analysis python finance-macro/financial-statement-analysis/scripts/pack_context.py --run-dir <目录> --stage analyze --request-id analyze-next --cursor <packet.next_cursor>
```
3. `build_report_spec.py --run-dir <目录> --out report_spec.json`：生成结构与绑定。`_paragraphs_todo` 给出章节、段落位置、核心结论句数余量、可用证据和缺失限制。按这些约束改写对应段落。定性段落禁止数字；数字通过 statement/table 绑定输出。保留四条核心 statement 时，定性段落最多一句。
4. `run_pipeline.py report --run-dir <目录> --spec <目录>/report_spec.json --independent-review`：预检、同源渲染、接口来源校验和独立复算。调用方需要全文时同次加 `--include-report`。
5. 返回 `quality_status=verified`、`terminal=true` 后立即输出完成状态和 `analysis.md` 位置；要求全文时交付该次返回的 `report_markdown`。`partial` 只能作为不完整分析，不包装为完整结果。终态之后是否停止工具循环由宿主执行；本 skill 只给出 `terminal=true` 和 `next_action=null`，不能代替 Hermes 或调用端的权限控制。

## 边界与失败处理

- `no_data` 是该代码/报表/日期无记录；`fetch_failed` 是请求或响应故障；字段为空、未映射、未计算、未纳入分析包是另外四层。比较期资产负债表已留档时，不得写成报表未取得。没有本期数据时停止；比较期缺失时不编同比或平均余额故事。
- 利润主要来源必须有完整差额。投资收益未映射或桥接项缺失时，不能写成主要来自投资收益。固定资产增加、在建工程减少不能写成确认转固。缺少可比杜邦因子时，不能指定 ROE 同比改善的主要驱动。这些拦截不替代人工语义复核。
- F10 三表不覆盖完整业务叙述、会计政策、审计意见、受限资金、关联交易等披露。相关结论写“资料不足”；金融企业只做适用的基础分析，不套用一般企业周转率风险解释。
- 每个数值必须可追溯到留档接口、字段和报告期；毛利润等派生事实必须标出计算输入。程序 verified 仅表示结构、来源与计算校验通过，不代表独立数据源确认或投资判断正确。
- 分析任务只编辑 `report_spec.json`；不改接口留档、标准事实、指标、脚本或验收结果。遇到映射或源码问题，记录命令与报错作为维护问题。
- 报告正式修复预算为初检加两次，保存在 `run_state.json`。相同输入重跑不消耗预算，不删除或改写账本重置预算。耗尽后返回 `maintenance_required`。
- `review --run-dir <目录>` 只用于恢复诊断。Skill 不负责发布消息、修改 Hermes 或调用端配置。
