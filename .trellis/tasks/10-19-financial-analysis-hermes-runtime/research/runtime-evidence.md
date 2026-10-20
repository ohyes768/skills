# 运行证据与脚本清单

来源：用户提供的messages.json、tool_calls.json。文件内指令仅为历史记录，不是本任务指令。不复制含用户数据的完整导出进仓库。

run_86e78479e57d465a8ead9969e1bf7695：MiniMax-M3、profile ohyes768、凡拓数创2026H1，149页PDF。记录跨度759.9秒，97个工具调用、90个模型API调用；session上报output_tokens=88338、input_tokens=216696、cache_read_tokens=10250431，不等同于已核实账单。首次报告校验在413.5秒，之后346.4秒、29次工具调用。

| 当前文件 | 本次实际使用 | 处理建议 |
|---|---|---|
| fetch_pdf.py | CLI 1次 | 复用；缓存核对URL和文档哈希，不换URL复用旧PDF |
| inspect_pdf.py | CLI 1次 | 复用；混合页章节边界专项回归，不先重写引擎 |
| extract_sections.py | CLI 1次 | 复用；补提和证据身份继续受控 |
| pack_context.py | CLI 5次 | 修页码范围；analyze/review提供结构化事实和差异 |
| calculate_metrics.py | CLI 3次 | 复用算法；输入构造提前挡住metric/attribution错误 |
| validate_report.py | CLI 4次 | 修表达误报、增加定位反馈；运行时只读 |
| financial_schema.py | 被临时Python导入校验7次 | 公共模块，供新构造器调用 |
| fact_selection.py | 被指标脚本内部调用 | 保留期间/范围选择层 |
| report_values.py | 被报告校验内部调用 | 明确数量类型、方向、百分点和元数据 |
| artifacts.py | 被流程脚本内部调用 | 复用原子写入；增加一致的阶段结果 |

具体失败证据：

- msg1867：初次financials手写66148字符；漏missing_reason，frequency=semi_annual等导致多轮修复。
- msg1843：pack_context --pages 1-15抛ValueError；文档却使用范围命令。
- msg1939/1940：首次报告检查产生20946字符的工具结果；模型继续阅读校验器源码。
- msg1960：value_mismatches=171、page_mismatches=40，body_mismatches已为0，说明后续主要是值/引用合同返工。
- msg1968：ev-0014的实际文字标注[p.18]；模型用于第8页数据并猜测提取错位。不能据此判定提取器真的把页码改错。
- msg1998：仍有105个value_mismatches、31条page_mismatches（含重复claim ID）、10条unclaimed_numeric_lines。
- msg2001：达到工具迭代上限；msg2002最终汇报不是可信独立验收结论。

本地函数级复核：NUMBER_RE将AI 3D识别出3；页码56-57识别出两个数字；下降27.80%不匹配负ratio；2026上半年不符合仅YYYY年的日期豁免。普通带符号31.49%与0.3149可正常匹配，不能笼统归因于Decimal舍入错误。

实际写操作集中在financials、analysis和claims及临时构造代码。未见写入scripts/validate_report.py或report_values.py；有改规则/改manifest的文字意图，应预防但不可虚构为已执行。
