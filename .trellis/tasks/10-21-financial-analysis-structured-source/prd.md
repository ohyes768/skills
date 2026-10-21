# 财报 Skill 结构化数据源接入：东财 F10 双源核对

## Goal

把「LLM 从 PDF 抽数」改为「程序从东财 F10 拉结构化三表打底 + PDF 原文验证」：LLM 职责缩减为抽查关键数字回原页验证与分析判断，降低提取与修复的轮次和 token 消耗。校验免疫系统（勾稽、维度、期间、渲染校验、修复预算）全量保留，纯 PDF 模式保留为默认回退。

## Background and Evidence

实测证据见 research/structured-source-evidence.md。要点：

- 东财 F10 datacenter API：301313 2026H1 数据与 PDF 同日披露；利润表营业总收入/归母净利与 Hermes 从 PDF 实抽的数值完全一致；资产负债表 140 非空字段覆盖合同全部指标。
- akshare 1.19.1 东财源对本样本全部失败（库内请求层问题），同机 curl 直连正常 → 自封装 HTTP，不引入 akshare。
- 结构化源自身体验：简化接口与 F10 接口同报告期总资产相差 3115 万 → 双源核对（结构化 vs PDF）必须保留，任何单一源不可作为唯一权威。
- 纯 PDF 模式的痛点（run_968d6c8e）：提取+核对+修复消耗大量轮次；同页双表、错位列、跨页表尾问题全部源于「从 PDF 抽数」。

## Requirements

- R1 新增 `fetch_structured.py`：自封装东财 F10 三表 HTTP（浏览器 UA、超时、有限重试、哈希缓存与 requested 参数核对，风格对齐 fetch_pdf.py），产物 `structured_financials.json` 记录 source=structured_eastmoney、拉取时间、reportName 与字段版本。依赖仅 httpx，不引入 akshare。
- R2 fact 合同新增 `source` 字段（`structured` / `extracted`），`financial_schema.validate_financials` 接受并校验该字段；旧 financials（无此字段）读取兼容。
- R3 `build_financials.py` 新增双源模式：以 structured_financials.json 生成 facts（source=structured，映射走既有 METRIC_CONTRACTS），PDF 证据降级为抽样核对——LLM 指定 N 个关键数字（默认覆盖营收/归母/CFO/总资产），程序核对其在 PDF 证据中的存在性与一致，不一致按冲突处理。
- R4 双源不一致处理：同一科目结构化值与 PDF 验证值差异超容差 → 计入 conflict 并在 mapping_validation/review 输出，不得静默采用任一侧；结构化源字段缺失 → 对应 fact 走既有 missing 语义，不得编造。
- R5 校验层不动：勾稽、维度、期间、渲染同源校验、初检+2 次修复预算、quality_status 语义全部保持。
- R6 回退：结构化拉取失败或字段严重缺失时自动回退纯 PDF 模式，并在 run 结果中标注本次数据源；回退不视为失败。
- R7 run_pipeline 的 prepare/evidence/compute/report 阶段接入（prepare 同时拉结构化数据或作为独立可选命令），现有 CLI 兼容不受影响。
- R8 性能对比：同一份 PDF 在结构化模式与纯 PDF 模式各跑 ≥3 次（同模型同 profile），报告工具轮数、模型轮数、output tokens 中位数；不以单次结果下结论。

## Acceptance Criteria

- [ ] A1 fetch_structured 离线测试（mock HTTP）：正常拉取、缓存复用核对 requested 参数与哈希、超时重试、非 JSON/缺字段拒绝。
- [ ] A2 双源一致性回归：301313 2026H1 的结构化 facts 与已验证的 PDF facts 全量比对，合同指标无差异（容差内）。
- [ ] A3 冲突路径：构造不一致样本 → conflict 计入且 run 不判 verified；缺失字段 → missing 语义，不出现编造值。
- [ ] A4 端到端：结构化模式下 run_pipeline 全链（prepare→evidence→compute→report）到 quality_status=verified，且报告页码引用仍来自 PDF 证据。
- [ ] A5 回退路径：mock 结构化源失败 → 自动回退纯 PDF 模式完成分析，结果标注数据源。
- [ ] A6 既有 255+ 例测试与 Ruff 全过；结构化分支新增测试覆盖映射与冲突。
- [ ] A7 性能对比报告：轮数与 output tokens 中位数对比，附原始 usage；不承诺固定分钟数。

## Out of Scope

不接巨潮 XBRL、不做港股/美股结构化源、不换模型、不删或弱化任何既有校验、不改 Hermes 核心/调用端、不在本轮推送钉钉/RSS。结构化源的字段映射扩展（新增指标）按维护流程走 METRIC_CONTRACTS 变更。
