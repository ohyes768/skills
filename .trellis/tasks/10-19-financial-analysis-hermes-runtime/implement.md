# 执行计划（P0-P3 已完成实现，P4 部分完成）

## P0：锁住运行边界并补失败样本 ✅

- [x] 去敏负例回归 tests/test_hermes_regressions.py：3D、范围页码 56-57、下降正幅度、2026上半年、百分点（10 例）；不提交原始私有日志。
- [x] 分析/维护权限区分写入 SKILL.md 运行时边界；宿主只读预检与最终重验的合同已定义，实际隔离由宿主执行（另行验收）。
- [x] 先复现负例（7 RED）再修 report_values.py、validate_report.py；原 160 例回归保留全过，错误金额/符号/页码负例仍拦截。

## P1：减少模型写数据和修格式 ✅

- [x] fact_inputs.json 合同与示例 references/fact-inputs-example.md；METRIC_CONTRACTS 公开于 financial_schema.py；新增 build_financials.py。
- [x] 回归期初/期末、本期/比较期、归属/范围、null、扫描证据降级、错误行列定位（tests/test_build_financials.py，13 例）；attribution 不可改写由合同强制。
- [x] pack_context.py 页码范围语法（1,3,5-9）与文档边界校验；fetch_pdf 缓存核对 requested_url。
- [ ] 真实混合表边界夹具：依赖实际 PDF 样本，待样本到位后补（只对实证边界缺陷修改 inspect/extract）。

## P2：正文和claims同源生成 ✅

- [x] report_inputs.json 合同与示例 references/report-inputs-example.md；新增 render_report.py（statements/tables/paragraphs + 格式符）。
- [x] 页码与公式输入自动从台账绑定；篡改正文、碰巧同值依赖固定 validate_report 独立复验（tests/test_render_report.py 12 例含闭环与篡改负例）。
- [x] 披露比例、计算比例、百分点、方向词（decline_* 格式与正值矛盾阻塞）及部分缺失处理。

## P3：统一入口与有限修复 ✅

- [x] run_pipeline.py：prepare/compute/report/review，任意 cwd 运行；run-dir 预检禁止指向 Skill 源码目录。
- [x] 初检+2次修复预算、run_state.json 持久、重启幂等、相同输入重跑不消耗、失败有限反馈（示例+计数，完整诊断落盘）；受保护预算由宿主持有（另行部署）。
- [x] SKILL.md 阶段入口与边界重写；artifact-contracts.md 新产物合同；fact-inputs / report-inputs 示例覆盖 MiniMax 实际犯过的合同错误。

## P4：验证与Hermes小流量验收（部分）

- [x] 全量 pytest 218 例（保留 160 例原回归）、Ruff 全过、skill-creator quick_validate 通过。
- [x] 新离线端到端：构造→标准化→计算→渲染→校验→review verified；两轮失败预算停止链（tests/e2e/test_pipeline_offline.py）。
- [ ] 用固定凡拓样本复现原失败，添加金盾样本：需要真实 PDF，待用户提供或另行执行。
- [ ] 同 MiniMax-M3 新旧各 3 次运行对比耗时/轮次/usage：需要 Hermes 环境，另行执行。
- [ ] 宿主只读隔离 + 专用 Hermes profile 试跑：另行执行，未验证前不宣称受保护运行。
- [ ] 按用户指令提交/部署，不自行发布。

## 验证命令（Windows）

使用skill自带.venv运行pytest，--basetemp指向独立工作区临时目录，避免系统临时目录权限问题。Ruff检查scripts/tests；元数据验证使用python -X utf8执行skill-creator的quick_validate.py。

## 回滚点

每阶段保留旧CLI/只读旧产物；产物schema或校验器版本改变时新建运行目录。测试失败停在对应阶段，不能通过改验收文件、提升权限或扩大豁免继续运行。新profile未验收不替换日常任务。
