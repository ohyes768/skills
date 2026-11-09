# 设计：保留既有工具，把模型从编程返工中移出来

## 1. 边界与核心决策

新增3个脚本，复用既有10个文件；不新增第二套财务分析Skill、不接入额外模型。模型判断事实语义和财务含义，程序维护合同、数值格式、引用关系和流程状态。

新入口只是确定性编排，不在脚本内偷偷再调用模型。日常分析与维护开发使用不同权限；历史数据不原地覆盖。固定版本校验器是判定依据，模型不能通过修改它完成任务。

## 2. 新增脚本与拟定接口

### run_pipeline.py：阶段入口

命令均从任意cwd执行，内部路径以__file__定位；--run-dir必须明确且不得覆盖Skill源码目录。

- prepare --url URL --run-dir DIR：预检依赖与路径，调用fetch/inspect/extract，返回有预算的映射包。缺失或未核实章节明示，非盲目提取全文。
- compute --run-dir DIR：读取模型写的fact_inputs.json，调用build_financials/financial_schema/calculate_metrics，再返回分析包。
- report --run-dir DIR：读取report_inputs.json，调用render_report及固定validate_report，返回完成状态或集中修复清单。
- review --run-dir DIR：返回当前阶段、有限错误和必要证据，不触发重提取/重算/重置预算。

默认最多初检+2次修复，持久记录输入摘要和次数，重复相同请求不无限运行。run_state.json是诊断状态，不是安全权威；受保护模式的预算及最终校验由agent不可修改的宿主控制。初次prepare的0仅表示该阶段成功，不能等同报告通过。

阶段结果沿用status/artifacts/issues，另提供stage、next_action、error_counts、examples、remaining_repairs、quality_status。退出码0=阶段成功，1=致命合同/维护错误，2=可保留但未通过或需要修复。quality_status区分verified/partial/maintenance_required，发布方只把verified视为正式完成。

### build_financials.py：构造事实

输入fact_inputs.json，输出financials.json及mapping_validation.json。输入只保留metric、raw_label/raw_value/raw_unit、evidence定位和必要维度；公共公司、币种、目标期间由可信元数据提供。元数据不确定就返回需要澄清，不猜默认值。

按有限白名单映射别名，例如cost_of_revenue→cost_of_sales；声明可用的metric及维度表。不能把货币资金映射成现金等价物，也不能为了计算把owners改成group。duration与instant分别有明确模板，程序补missing_reason、标准日期结构、文档hash和稳定fact_id。

优先绑定table evidence行列，核对原始单元格与金额；文字证据绑定具体行/片段。程序确认结构/原文匹配不等于理解会计语义，语义仍由模型核实；找不到定位或截图待核实时不得自动verified。source_pages从实际evidence解析，模型不手写。披露ratio、percentage_point与金额分型，未知单位拒绝，不全按金额解释。

### render_report.py：同源生成正文与claims

输入report_inputs.json中的section、陈述模板、typed bindings和支持依据，输出analysis.md/report_claims.json。绑定引用fact_id或computed metric_id，金额单位/精度由格式器处理；每个正文片段的claim随片段生成，锚点来自实际section。

计算型句子绑定指标；公司披露的百分比绑定披露事实；额外派生值只支持允许的确定性运算及完整输入，不执行模型给出的任意Python公式。下降/亏损与符号、百分比/百分点明确建模。禁止根据正文数值在所有facts中搜索碰巧相等的值来补引用。

支持定性分析自由文字，但定量陈述需显式绑定。日期、3D等非财务数字采用明确token类型或可审计规则，不能把所有未绑定数字放行。renderer生成来源集合，validator独立验证；同源生成不代替验证。

## 3. 现有脚本改造

- pack_context.py：统一列表/范围页码解析和边界错误；修locate预算；map供证据，analyze优先事实/指标/异常，review供失败陈述及证据，不三阶段都重复全部原文。
- report_values.py：集中处理方向词、日期、页码范围、百分比/百分点、产品术语数字；先明确类型再比较Decimal。精度与单位规则公开，不能用宽泛容差掩盖错误。
- validate_report.py：绑定到具体陈述值，区分被展示值与仅作计算输入的facts；返回具体claim/字段/实际值/期望值/解析页码/来源页码。摘要有限，完整诊断落盘。禁止正文或合同仅因更方便生成而跳过检查。
- financial_schema.py：公开构造输入所需的metric/维度及数量类型合同，保持旧financials读取兼容；新增严格语义检查由已知指标定义驱动。
- artifacts.py：统一阶段结果和原子写入；可信最终验收副本由宿主持有。
- fetch_pdf.py：缓存复用校验requested URL与hash，防新任务误用旧PDF。
- inspect_pdf.py/extract_sections.py：保留算法，补跨页表尾和同页下一个表头的真实布局回归；section标签仅作定位提示，不能自动赋予整页同一报表口径。只有实证重现的边界缺陷才修实现。
- calculate_metrics.py/fact_selection.py：保持既有公式与选择层，只适配标准化输入；缺失FX不默认为已核实零，现金勾稽以现金等价物为准。

SKILL.md改成阶段入口与边界说明，按需加载合同。提供一个完整紧凑输入示例，避免运行时读源码猜字段。删除与实际CLI不一致的范围/目录用法。

## 4. 权限与Hermes部署

提示层：明确可修改本次fact_inputs/report_inputs；有原文依据可修事实，不允许改源码、依赖、manifest、metrics和校验结果。

执行层：Skill目录采用agent凭据无权改动的所有者/只读挂载；仅允许受限写入运行输入，确定性程序由受控入口执行。若agent仍有同用户通用terminal/execute_code，可绕过普通chmod或改写运行结果，不能宣称硬隔离。需专用profile配合实际进程/文件系统/工具权限分离，最终由独立宿主固定版本重验。只读边界预检失败就标记不具备受保护模式，不静默降级为安全。

Hermes与stock-info-dingding不在本地修改授权目录内，本轮提供部署/调用合同，实际变更分开执行。RSS/钉钉发送不放进Skill；调用端兼容quality_status后只发送对应状态的内容，不把partial宣传为完整高质量结果。

## 5. 性能、迁移与回滚

性能目标：先减少模型输出和串行返工，不承诺单纯提高token速度。必要覆盖优先，不限制必须收集的事实总量。使用已有原始PDF与全新运行目录，按同模型/配置比较工具次数、模型次数、输入/输出/缓存tokens、阶段耗时和正确性。

保留原CLI作为底层接口，旧产物只读。新结构以schema_version区分，旧版本不受自动覆写；新生成逻辑失败时可以回到旧Skill固定版本，但不能沿用新版本passed结果。NAS部署先单份样本无发布试跑，再接日常任务；不替用户自动发送历史结果。
