# 可复用工具与开工纪律

这些工具从 Hermes profile 的 `financial-pitfall-recovery` 迁入主 skill，主流程无需再寻找
sibling 或读取其全部历史案例。主 skill 的脚本、合同与测试是迁入工具的维护入口。
`financial-pitfall-recovery` 仍可作为历史案例参考；其中旧 workaround、`report → review`、
固定公司页码与旧预算解释不能覆盖本 skill 当前流程。

## 工具入口

| 工具 | 主流程如何使用 | 何时单独调用 |
|---|---|---|
| `build_fact_inputs_verified.py` | `run_pipeline.py compute --spec <spec.json>` 内调用 | 调试 spec 生成问题 |
| `verify_fact_values.py` | 生成器复用金额序列检查规则，先核对原值再写输入 | 已有手写 fact_inputs 的逐值诊断 |
| `report_inputs_builder.py` | `run_pipeline.py report --spec <spec.json>` 内调用 | 单独调试 spec 构造问题 |
| `verify_report_inputs.py` | builder 写文件前及 `report --independent-review` 内调用 | 输入结构诊断 |
| `verify_report_independent.py` | `report --independent-review` 内调用 | 维护或既有产物诊断 |

脚本统一放在主 skill 的 `scripts/` 下，按主 SKILL.md 的 uv 命令前缀执行。
旧 `build_fact_inputs.py` 已废弃，不迁入。原变异测试写死公司数值和 fact ID，改为
`tests/test_skill_tools.py` 的动态夹具和变异回归；维护变更时跑 pytest，不在每份分析中跑变异测试。

## 开工先定齐事实

第一次 compute 前一次确定：合并三表主体、首页主要财务数据、必要的母公司对照、
风险判断所需附注。只抽取本次判断所需页面，不为凑事实数量扩读全文。
对照事实明确 `scope: parent`，不得混入合并指标。指标是否缺基期由资料决定，不得补估值。

章节索引只用于定位候选页；内容归属、同页双表与跨页表尾按
[提取规则](extraction-rules.md)的 "Same-page dual tables" 节处理。
已有样本页码不可套用到新公司。

## spec → 事实输入

适用于标签和金额分行的 text 证据；先确认本期/比较期列顺序、币种、单位及合并归属。
`raw_unit` 必填，按原表抄写；绝不默认金额是元。例：

```json
{"facts": [
  {"metric": "revenue", "label": "营业收入", "cur": "120.00", "prior": "100.00",
   "page": 6, "raw_unit": "万元"},
  {"metric": "cash_equivalents", "label": "加：期初现金及现金等价物余额",
   "cur": "30.00", "ref": "opening", "page": 8, "raw_unit": "万元"}
]}
```

```bash
run_pipeline.py compute --run-dir <run-dir> --spec <run-dir>/spec.json
```

同次生成、逐值核对、构造和计算，返回分析包。locator.line 按 excerpt 的一基行号生成，
不使用 pages.jsonl 的 block 下标；指标期间类型直接读取 `METRIC_CONTRACTS`。
重复标签、同页多个 text 证据、值不匹配或未知单位必须先核实，不猜选。
复杂表格、行内金额、缺失值或重复标签需要明确映射时，按
[事实输入示例](fact-inputs-example.md)构造紧凑 fact_inputs，用原 `compute` 入口；
不要为迁就生成器改证据文件或修改脚本。

## 报告输入构造（report --spec）

把声明式 spec 写进 run-dir，结构与 report_inputs.json 相同，另支持表格行尾空串自动
来源页码；`report --spec` 一次完成构造、预检与正式 report，spec 写入与执行合并在
同一次工具调用，不读回刚写的 JSON。示例（按报告模板补齐主要报表、关键比率、盈利、
风险和数据质量等章节）：

```json
{"sections": [{
  "anchor": "## 核心结论",
  "statements": [
    {"template": "本期收入 {rev:amount_wan}。",
     "bindings": {"rev": {"fact_id": "<实际收入fact_id>"}}, "claim_type": "fact"},
    {"template": "收入同比变化 {yoy:percent2}。",
     "bindings": {"yoy": {"metric_id": "revenue_yoy"}}, "claim_type": "calculation"}
  ],
  "paragraphs": ["这里补充有证据支持的盈利判断。", "这里补充主要风险判断。"],
  "table": {"columns": ["指标", "本期", "来源"],
            "rows": [{"label": "营业收入",
                      "cells": [{"fact_id": "<收入fact_id>", "format": "amount_wan"}, ""]}]}
}]}
```

行尾空串在构造时替换为该行所有绑定证据页并集的页码（`PDF 第 N 页`）。构造器逐项
校验绑定、格式与来源，失败不写文件、不消耗 report 预算；格式规则与渲染合同共用，
支持年份、百分点及表格 decline_* 自带方向词，不沿用旧 sibling 的过期禁令。
定性段落一律零数字，含年份和页码引用也不行。

```bash
run_pipeline.py report --run-dir <run-dir> --spec <run-dir>/report_spec.json --independent-review
```

## 最终复核一次完成

```bash
run_pipeline.py report --run-dir <run-dir> --spec <run-dir>/report_spec.json --independent-review
# 已有 report_inputs.json 时省略 --spec；调用方要求全文时追加 --include-report。
```

命令依次预检输入、渲染、固定机器校验、独立复核，再决定是否返回终态。
独立复核重算已计算指标、独立格式化逐字比较，并检查表格列数、核心结论句数、
来源口径风险与可用的会计恒等式；详细结果落在 `independent_review.json`。
缺数据的指标和勾稽记为 `not_applicable`，不编零、不假称已核对。
任何复核失败不返回正文与成功终态；修复仍使用原 report 预算，不另起无限循环。
输入预检不消耗正式提交预算，也没有程序化轮次上限——应集中修改、少数几轮内收敛，
不要把预检当作无限重试入口。

机器检查不能确认全部语义：混合页上的表头归属、期间列对应、缺基期却编同比、
公司因果解释和风险覆盖，仍须在最终命令前按已读证据做语义复核。
全部通过并返回 `terminal: true` 后立即交付，禁止追加 review 或新一轮研究。
回复首行锚定公司全称、代码、报告期；简称与 PDF 不符时先说明身份差异。
