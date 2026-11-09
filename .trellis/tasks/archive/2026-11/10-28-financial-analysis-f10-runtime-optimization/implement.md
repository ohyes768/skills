# 实施清单

- [x] 0. 已重读任务、backend/financial-statement-analysis.md 和 skill 代码。九期三表用离线夹具，不访问东财。
- [x] 1. 离线夹具覆盖九张报表留档、字段为空、no_data、fetch_failed、未映射和未计算。
- [x] 2. analysis_pack.json 输出分层覆盖、利润桥、费用率和余额变化。投资收益保持未映射，空差额保持 null。
- [x] 3. `_paragraphs_todo` 带章节、位置、句数余量、证据和缺失限制。四条核心 statement 时定性段落最多一句。
- [x] 4. compute 与 pack_context 都暴露顶层 packet.next_cursor。非法游标返回 failed，且 ended=false。
- [x] 5. 无支持的主要归因、确认转固和杜邦同比驱动会在校验中拦截。其余定性句子仍留给人工复核。
- [x] 6. stock-info-dingding 的 f10-v3 提示词已在本地改完，尚未部署；Hermes 终态停循环和读源码权限仍未改。两处均为本仓库外的依赖，已登记于 research/external-dependencies.md（2026-11-09 复核：提示词仍在 stock-info-dingding 本地未部署，Hermes 宿主侧未改），不计入本任务完成证据。
- [ ] 7. 本地 pytest 与 Ruff 已跑。MiniMax 三次回放和真实会话耗时尚未执行，不能声称工具次数已下降。**登记为外部依赖后关闭**：实测由后续单独任务承接，本次不伪造回放数据。

## 验证入口（实施时先核验环境与路径）

```powershell
python -m pytest finance-macro/financial-statement-analysis/tests -q
python -m ruff check finance-macro/financial-statement-analysis
python -X utf8 C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py finance-macro/financial-statement-analysis
git diff --check
```

样本回放用隔离目录，不复用正式产物目录，不发送真实钉钉/RSS。模型服务调用及部署按后续实施范围执行。本次仅文档建档，无需业务测试。

## 交付门槛

- [x] 保留所有既有负例，更新真实实现对应的 spec，明确方案与已实现能力。已核对：financial-statement-analysis 的 148 项 pytest 全绿（含来源、事实、公式、正文、引用、预算负例）；.trellis/spec/backend/financial-statement-analysis.md 已写入覆盖分层、analysis_pack、顶层 next_cursor、修复预算与终态语义。
- [ ] 性能结果含中位数/范围、工具/API、源码访问、可得 token 统计和语义质量。**未执行，登记为外部依赖**：A6 回放需要模型侧运行与同一留档样本，本次按用户决定不跑，不得把 50 次工具/536.6 秒的旧基线写成已下降。
- [x] 不重置修复预算、不以减少必要覆盖换速度、不承诺未经实测的固定分钟数。已核对：run_pipeline.py 的 BUDGET_POLICY 与 run_state.json 持久预算禁止删除或改写以重置；覆盖分层保留 no_data/fetch_failed/未映射/未计算；SKILL.md 与文档未出现固定耗时承诺。

## 收尾与外部依赖（2026-11-09）

仓库内实现、spec、负例与文档全部完成并随本仓库提交留存。归档时未完成项仅剩下列外部依赖：

| 遗留项 | 现状 | 接续方式 |
|---|---|---|
| A6 性能回放（≥3 次 MiniMax-M3.1-Flash，同一留档，记录耗时中位数/范围、工具/API 次数、源码访问、可得 token、语义质量） | 未执行 | 单独任务承接；仓库侧条件已具备（留档、紧凑分析包、统一游标可用，2026-11-09 已验证 F10 prepare 对 301261/2026-09-30 可用） |
| stock-info-dingding 的 f10-v3 提示词部署 | 本地已改、未部署 | 该仓库自行部署与验收 |
| Hermes 终态停循环与读源码权限 | 未改；Skill 侧仅能返回 terminal=true、next_action=null | 宿主策略单独验收，见 research/external-dependencies.md |

未做的实测不计入完成声明：归档表示仓库侧收口，不表示工具次数已下降或受保护运行已验证。
