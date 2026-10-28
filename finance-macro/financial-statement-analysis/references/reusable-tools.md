# 可复用工具

| 工具 | 输入与产出 |
|---|---|
| run_pipeline.py prepare | --code、--period、--run-dir；建立代码/报告期绑定并拉取 F10 |
| run_pipeline.py compute | --run-dir；自动映射留档字段，输出事实、指标、analysis_pack.json 与限量上下文。续读字段是顶层 packet.next_cursor |
| pack_context.py | --run-dir、--stage analyze、--request-id、--cursor。stdout 与 compute 一样使用顶层 packet.next_cursor；null 为结束，非法游标是失败 |
| build_report_spec.py | --run-dir，默认 --out report_spec.json；只生成报告输入草稿 |
| run_pipeline.py report | --run-dir、--spec、--independent-review；正式校验与交付 |
| run_pipeline.py review | --run-dir；只读阶段与修复余量 |

不需要 agent 抽数、手写利润桥或构造事实输入。常规报告使用 analysis_pack.json 和分页包里的覆盖、差额、比率与来源 ID。原始接口响应保存在 structured_financials.json；不要为了确认合同去读脚本源码。

脚本 stdout 是 JSON；退出码零为成功、一为致命或维护错误、二为未通过或不完整，具体看 status/quality_status。报告 terminal=true 后不追加研究工具调用。
