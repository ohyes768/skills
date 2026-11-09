# 四挡位估值 Skill Implementation Plan

> For agentic workers: use subagent-driven-development for isolated tools implementation and sequential spec/quality reviews; use test-driven-development and writing-skills for RED → GREEN → REFACTOR. No commits, push, deployment, or website access.

**Goal:** 实现已批准的独立单股研究 Skill、精确计算和结果校验工具。

**Architecture:** Agent 读取调用方给定研究材料，补证后填入严格 draft JSON。计算工具只拥有白名单公式，finalize 重新计算四点/比率/情景与敏感性并同源生成报告；未知状态不输出价格。两者是独立 Python 标准库模块，不引用兄弟 Skill 源码。

**Tech Stack:** Python >=3.12 标准库（Decimal、json、argparse、unittest）、Markdown Skill、pytest/Ruff 开发校验。

**Authorization:** 2026-11-08 用户审阅设计后说“好的，开干”；随后选择当前目录直接实施，允许在 master 工作目录改动，不授权 git commit/push 或部署。本计划由主 agent 自审后执行，不新增产品范围。

---

## 文件职责

- `investment-analysis/stock-four-level-valuation/SKILL.md`：主指令、边界和停止条件。
- `references/input-and-reuse.md`、`valuation-methods.md`、`output-contract.md`：分别负责复用/行业研究/可执行 JSON 合同。
- `scripts/valuation_math.py`：数值解析、白名单公式、舍入、复算和有限敏感性。
- `scripts/validate_result.py`：输入/草稿合同、证据引用/日期、状态、报告生成、finalize 和 check CLI；确有职责需要可拆 report_render.py 和 contracts.py，不建通用框架。
- `tests/test_valuation_math.py`、`test_result_contract.py`：算术、错误和真实 CLI 测试。
- `tests/fixtures/ready.json`、`insufficient.json`：虚构最小样本；ready 是 draft 而不是实际推荐。
- `evals/scenarios.md`：可重放行为场景。
- 任务目录 `research/baseline.md`、`research/behavior-results.md`：真实对照结果，不作为未来公司证据。
- README 新增一行；新增 `.trellis/spec/backend/stock-four-level-valuation.md`（英文）并登记索引。旧 Skill 不修改。

## 固定工具合同（供实施与文档共同使用）

### 数学节点

`evaluate(node) -> Decimal`，node 必有 `method`，可有 `margin`（缺省0、0<=margin<1）；严格拒绝未知参数、bool、非有限、空串和任意表达式。

```json
{"method":"pe_multiple","eps":"2","multiple":"10","margin":"0"}
{"method":"pb_multiple","bvps":"10","multiple":"0.8"}
{"method":"equity_cashflow_pv","cashflows":["1","1"],"discount_rate":"0.1","cashflow_basis":"dividend","finite_life":false,"terminal":{"kind":"exit_pe","eps":"2","multiple":"10"}}
```

PE eps/multiple 和 PB bvps/multiple 均 >0。现金节点 cashflow_basis 为 dividend/fcfe；cashflows 年末序列 1..N，1<=N<=100，r>0；可有负现金流但最终价值必须正。finite_life 必为 bool，有限期禁止 perpetuity。

terminal 三种且不能混用字段：

```json
{"kind":"value","value":"0"}
{"kind":"exit_pe","eps":"2","multiple":"10"}
{"kind":"perpetuity","next_cashflow":"2","growth":"0.02"}
```

value>=0；exit_pe 的 eps/multiple>0；next_cashflow>0、growth>-1 且 growth<r；终值为第 N 年末值。最终 `Σ CF_t/(1+r)^t + TV_N/(1+r)^N` 再乘 (1-margin)。精度28或更高，ROUND_HALF_UP 到分。rate 比率用小数0.1，display yield 用10.00(%)。参数拒绝极端指数/长度，避免意外资源爆炸。

`level_metrics(price, ttm_eps, common_bvps, annual_dps)`：PE/PB 正分母才可算，缺失/非正为 null；DPS 缺失为 null，0为有效0%但负股利拒绝；指标以最终舍入价格计算，4位小数或明确统一的2位，文档与测试一致。

### 草稿输入

`finalize --input draft.json --stock stock.json --output result.json`。stock 为 {code,name,as_of,currency}；as_of 严格 YYYY-MM-DD、currency=CNY；用户不提供时 agent 在建立 stock.json 时读执行日期，不由计算器静默猜测。

draft 不接收已算 levels、report_md 或版本号，防止 agent 篡改它们；只接收以下键：

```text
code, name, as_of, currency, status,
summary, confidence, risks, invalidation_conditions, data_gaps,
evidence, analysis, valuation
```

- status: ready / insufficient_data / blocked / not_applicable。
- confidence: {level: high|medium|low|unavailable, reason:非空文本}。
- risks/invalidation_conditions/data_gaps: 非空字符串数组（允许风险数组空，非ready须有可解释的 gap 或 risk）。
- analysis: {business,normalization,dividend,valuation,risk} 五个非空中文段落；这里的文字是模型判断，不由脚本证明真实性。
- evidence: 数组，每项 {id,title,kind,origin,locator,period,published_at,accessed_at,verification}。kind 是 official/data_platform/research/media/upstream/input；origin 为用户明确的路径或http(s)URL，禁止javascript等协议；日期是 YYYY-MM-DD 或 null，published_at 不得晚于 as_of。verification 为 read/reused/unverified；仅 unverified 的证据不能支持 ready。
- valuation: 非ready 为 null；ready 是 {primary_method,anchor,scenarios,decisions,metric_inputs,sensitivity}。
- anchor: 非空文本，解释四点共同盈利/权益/现金流基础。
- scenarios: 恰好 bear/base/bull；每项 {model,rationale,evidence_ids}，计算现值必须 bear<=base<=bull，不能自动排序。
- decisions: 恰好 heavy_position/add_position/reduce_position/full_exit；每项 {model,rationale,evidence_ids}。同一种 primary_method，PE共用eps、PB共用bvps；舍入后严格递增，不自动排序/加一分。
- metric_inputs: {ttm_eps,common_bvps,annual_dps,dps_basis,period,share_basis,evidence_ids}；数值可 null；dps_basis为ttm_ordinary/forward_ordinary/none；提供DPS时basis非none。period/share_basis 非空，数值存在则至少一个可用证据引用。
- sensitivity: 至少两个、至多八个 {label,base_level,model,rationale,evidence_ids}；base_level 为上述某点；模型必须比基准节点至少变一个参数，不能复制换标签。须保持同模型类型。每项重算而非输入price。
- 每个 model 的参数依据在同条 rationale 里写明；evidence_ids 必须有定义且已读/复用，不把假设称为事实。ready 至少1项可用证据，data_gaps 可记录次要限制。

最终输出顶层恰为17字段：schema_version,skill_version,code,name,currency,as_of,status,levels,valuation,evidence,data_gaps,confidence,risks,invalidation_conditions,summary,analysis,report_md。analysis保留五段原始判断，使所有状态的report_md均能从结果无损重放；非ready的valuation仍为null。valuation 保留审计参数并添加 calculated/scenario_values/sensitivity_values/level_metrics 等派生结果，字段名需文档确定一致。level 值 JSON number 或 null，内部精确结果十进制字符串保存；不接受输入覆盖计算结果。非ready的四个节点均为 {price:null,pe:null,pb:null}。

`check --input result.json --stock stock.json` 从审计参数重跑 finalize 并比较全部派生部分（包括报告和版本），成功 stdout 只返回短 JSON 回执；finalize 成功 stdout 为与文件一致的完整结果。错误 stderr、exit=2、stdout为空；输出原子写入，失败不能覆盖已有文件，也不能拿旧文件冒充本轮成功。不允许 output 与 input/stock 同路径；脚本不联网、不扫描输入目录、不读取origin路径、不给网站写指令。CLI UTF-8，JSON 禁重复键、NaN、Infinity。

## Task 1 — 激活、基线与测试夹具

- [ ] 写上下文 jsonl 并运行 `task.py start`，使用明确 session identity。
- [ ] 在任务目录保存三个固定离线行为场景（旧报告+截止日、银行+缺资本、未来价+分红+压力），子 agent 不读新 Skill/设计，按普通单股分析回答。
- [ ] 记录原文及失败/合规结果；不得为凑失败虚构评价。
- [ ] 数学子任务写测试先红，再实现；基线完成前不写主 Skill。

核心测试形状：

```python
from decimal import Decimal
import unittest
from valuation_math import evaluate
class ArithmeticTests(unittest.TestCase):
    def test_pe(self):
        self.assertEqual(evaluate({'method':'pe_multiple','eps':'2','multiple':'10'}), Decimal('20'))
    def test_future_price_discounted(self):
        node={'method':'equity_cashflow_pv','cashflows':['1','1'],'discount_rate':'0.1','cashflow_basis':'dividend','finite_life':False,'terminal':{'kind':'value','value':'20'}}
        self.assertAlmostEqual(evaluate(node), Decimal('1')/Decimal('1.1')+Decimal('21')/Decimal('1.21'))
```

红色：未实现函数/模块测试明确失败；绿色：用独立手工期望值验证，不以同一函数生成期望。

## Task 2 — 计算/输出工具（单个实施子 agent）

- [ ] 写数学测试：PE/PB、折现、永续第N+1年、负现金流、分红不重复、安全边际、bool/NaN/Infinity/未知字段/数值边界、有限期禁永续、舍入。
- [ ] 运行 `python -m unittest discover -s investment-analysis/stock-four-level-valuation/tests -p 'test_valuation_math.py' -v` 记录红色；实现 valuation_math，再运行记录绿色。
- [ ] 写结果测试与两个虚构fixture：有效ready、三种非ready、身份/截止日、证据引用、未核验、倒序/舍入重合、PE与TTM口径、未知字段、重复JSON key、CLI失败输出和原子保存、tampered check。
- [ ] 先运行红色，再实现最小 validator/renderer 和CLI；为版本读取提供临时fixture SKILL.md，不要求主Skill提前存在。
- [ ] 全部绿色后做有限重构，运行 Ruff；回传文件列表、红绿证据和准确CLI/字段名。

## Task 3 — 研究 Skill 与使用参考（主 agent）

- [ ] 按基线失败写精简 SKILL.md，frontmatter name=stock-four-level-valuation、description 只写触发场景、metadata.version=1.0.0。
- [ ] 写三个 references，遵循上方实际实现合同；解释原材料如何人工提取为证据、事实/假设区别、freshness、行业门槛、拒绝信息不足、非个性化仓位线。
- [ ] 同一个可运行的虚构PE示例作为唯一完整示例；不提供伪造真实股票结论。
- [ ] 用同样场景加Skill重跑，另做可执行任务读取示例并finalize/check；记录行为与工具结果。
- [ ] 发现失败则先保存失败记录后补规则/测试并重跑。

## Task 4 — 审查、整体验收和交付

- [ ] 独立 spec reviewer 检查 R1-R6/AC1-AC9/设计，修复确认缺口后再做 code quality review。
- [ ] 运行 `python -m unittest discover -s investment-analysis/stock-four-level-valuation/tests -v`（或pytest同目录）、`ruff check investment-analysis/stock-four-level-valuation`。
- [ ] 真实命令执行 fixture finalize/check；更改 price 再 check 必失败；原输入哈希前后相同。
- [ ] 检查 skill frontmatter、本地参考链接、无硬编码NAS/网站调用、无凭证、无任意表达式执行。
- [ ] README只新增独立Skill行；新增英文spec登记实际合同，不重写旧Skill。
- [ ] 更新任务产物及验证日志；不提交、不推送、不部署，最终明确本地验证与真实投资判断/宿主部署的区别。

## 回退与停止

只撤回本次新增文件及本次README/spec登记行，保留所有用户文件和上游材料。遇到金融事实不足交付状态，不放宽守卫；遇到实现错误先写回归再修。任务完成但未授权提交时保持可审阅改动，不伪装已发布。
