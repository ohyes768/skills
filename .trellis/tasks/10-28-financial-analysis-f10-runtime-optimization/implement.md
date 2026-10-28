# 实施清单

- [x] 0. 已重读任务、backend/financial-statement-analysis.md 和 skill 代码。九期三表用离线夹具，不访问东财。
- [x] 1. 离线夹具覆盖九张报表留档、字段为空、no_data、fetch_failed、未映射和未计算。
- [x] 2. analysis_pack.json 输出分层覆盖、利润桥、费用率和余额变化。投资收益保持未映射，空差额保持 null。
- [x] 3. `_paragraphs_todo` 带章节、位置、句数余量、证据和缺失限制。四条核心 statement 时定性段落最多一句。
- [x] 4. compute 与 pack_context 都暴露顶层 packet.next_cursor。非法游标返回 failed，且 ended=false。
- [x] 5. 无支持的主要归因、确认转固和杜邦同比驱动会在校验中拦截。其余定性句子仍留给人工复核。
- [ ] 6. stock-info-dingding 的 f10-v3 提示词已在本地改完，尚未部署。Hermes 终态停循环和读源码权限仍未改。
- [ ] 7. 本地 pytest 与 Ruff 已跑。MiniMax 三次回放和真实会话耗时尚未执行，不能声称工具次数已下降。

## 验证入口（实施时先核验环境与路径）

```powershell
python -m pytest finance-macro/financial-statement-analysis/tests -q
python -m ruff check finance-macro/financial-statement-analysis
python -X utf8 C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py finance-macro/financial-statement-analysis
git diff --check
```

样本回放用隔离目录，不复用正式产物目录，不发送真实钉钉/RSS。模型服务调用及部署按后续实施范围执行。本次仅文档建档，无需业务测试。

## 交付门槛

- [ ] 保留所有既有负例，更新真实实现对应的 spec，明确方案与已实现能力。
- [ ] 性能结果含中位数/范围、工具/API、源码访问、可得 token 统计和语义质量。
- [ ] 不重置修复预算、不以减少必要覆盖换速度、不承诺未经实测的固定分钟数。
