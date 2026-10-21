# 执行计划（P0–P3 已完成；P4 性能对比待跑）

## P0：结构化拉取层

- [x] `fetch_structured.py`：三表请求、UA/超时/重试、缓存与 requested 参数核对、`structured_financials.json` 全量留档；非 JSON/无数据退出 1。
- [x] 离线测试（mock httpx）：正常拉取、缓存复用、重试、坏响应拒绝；真实网络冒烟测试标记可选。
- 验证：pytest 新增用例全绿；301313 真实拉取人工核对已并入 research/structured-source-evidence.md（2026-10-21，不入库）。

## P1：合同与映射

- [x] `_FACT_FIELDS` 加 `source`，`validate_financials` 校验枚举，旧产物无字段兼容。
- [x] `STRUCTURED_FIELD_MAP` 覆盖 METRIC_CONTRACTS 全部条目；`build_financials` 双源分支；Decimal 转换禁走 float。
- [x] 回归：期初/期末、本期/比较期、frequency 归一化在结构化分支同样成立；缺失映射 warning。
- 验证：pytest + Ruff；无 source 字段的旧 financials 读取测试。

## P2：抽样核对与冲突

- [x] `structured_check.json`：建议科目清单（约 15 项，`RECOMMENDED_SAMPLE_METRICS`）+ 抽查单可自由增删（偏离原设计「固定五项」：改为建议清单 + warnings 提示补充）；`unchecked`（未找到）与 `conflict`（数值不一致）分开计数，另有全量 `presence` 存在性统计。
- [x] 冲突 → conflict 且 run 不得 verified；缺失字段 → missing 语义。
- 验证：A3 构造冲突样本测试已有；A2 全量金样本比对未做——关键指标（营收/归母净利）与 PDF 实抽值一致性见 research 证据，全量比对并入 P4 实跑时完成。

## P3：run_pipeline 接入与回退

- [x] ~~`compute --structured / --no-structured`~~ → **决策变更（2026-10-21）**：默认结构化打底，`--pdf-only` 为逃生门强制纯 PDF；结构化失败自动回退纯 PDF 并在 warnings 标注。理由：简化主流程（LLM 只写抽查单），纯 PDF 降级为回退路径而非日常路径；无 SLA 第三方接口不作单点依赖，故不删 PDF 抽取路径。
- [x] SKILL.md / artifact-contracts.md / fact-inputs-example.md 增补结构化模式说明（数据源声明、抽样核对语义、source 字段）。
- 验证：A5 回退路径测试有（拉取失败自动回退、`--pdf-only` 绝不拉取、无抽查单且结构化不可用致命退出）；A4 全链 verified 以合同级测试覆盖（structured fact + clean check 的 report 校验），真实 PDF 全链实跑并入 P4。测试侧加 conftest 离线护栏：除 mock HTTP 单测外 `fetch_structured` 一律拒绝，防止默认翻转后离线套件意外触网。

## P4：性能对比与验收

- [x] 全量 pytest + Ruff：2026-10-21 294 passed、Ruff 全过；既有回归零破坏。
- [ ] 同一 PDF 两模式各 ≥3 次（同模型同 profile），报告轮数与 output tokens 中位数及原始 usage（R8/A7）；A2 全量金样本比对随实跑补做。
- [ ] 对齐 Trellis spec 复核。
- [x] 按用户指令提交（2026-10-21）；不自行发布。

## 决策与偏离记录

1. 不引入 akshare / 巨潮 XBRL（实测不可用），自封装东财 datacenter F10 HTTP。
2. 结构化默认开（原设计为文件存在即启用，实现先做成 opt-in，2026-10-21 翻转为默认 + `--pdf-only` 逃生门）。
3. 纯 PDF 抽取路径保留不移除：抽查单复用其校验与证据绑定；东财两接口自差 3115 万证明单一源不可为权威；无 stock_code 场景（未上市招股书）与冲突以 PDF 为准的修复路径依赖它。
4. 抽样核对从「固定五项样本」改为「建议科目清单 + 缺失 warnings」，抽查单由 LLM 按报告实际情况增删。

## 验证命令（Windows）

skill 自带 .venv 跑 pytest，`--basetemp` 指向独立临时目录；Ruff 检查 scripts/tests；元数据用 skill-creator quick_validate。真实网络请求只在显式标记的可选测试或人工冒烟中进行。

## 回滚点

每阶段增量分支；`compute --pdf-only` 或删除 structured_financials.json 即回到纯 PDF 现状。测试失败停在对应阶段，不得通过放宽校验或扩大豁免继续。
