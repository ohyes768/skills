# 可复用工具

| 工具 | 输入与产出 |
|---|---|
| run_pipeline.py prepare | --code、--period、--run-dir；建立代码/报告期绑定并拉取 F10 |
| run_pipeline.py compute | --run-dir；自动映射留档字段，输出事实、指标与限量上下文 |
| pack_context.py | --run-dir、--stage analyze、--request-id，按 next_cursor 续读 |
| build_report_spec.py | --run-dir，默认 --out report_spec.json；只生成报告输入草稿 |
| run_pipeline.py report | --run-dir、--spec、--independent-review；正式校验与交付 |
| run_pipeline.py review | --run-dir；只读阶段与修复余量 |

不需要 agent 抽数或构造事实输入。原始接口响应保存在 structured_financials.json；指标与来源合同足以完成常规报告，不逐个读源码寻找接口。

脚本 stdout 是 JSON；退出码零为成功、一为致命或维护错误、二为未通过或不完整，具体看 status/quality_status。报告 terminal=true 后不追加研究工具调用。
