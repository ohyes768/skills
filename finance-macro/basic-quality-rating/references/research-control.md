# 有预算的取证与失败换路

**仅旧 research.json 续跑兼容。v4.1 新分析使用 [轻量进度](progress.md)，不执行本页的回执、渠道路由与预算流程。**
旧任务保留本页及 --f10-research 修复入口，不将历史调用补造为轻量流程记录。

新默认流程使用 init --f10-research：financial 的 mode=f10，必要主题仅为 f10_data。
它登记一次统一 F10 取数，不要求监管资本或保险专用主题；A-D、全局预算、结案与成稿规则照常。
具体 start/result/close 顺序见 [F10入口](f10-financial.md)。

以下银行/保险模式仅供旧显式证据包兼容，不是 F10 前置步骤，三种模式互斥。
银行 E 使用 init --bank-research，dimension=financial，主题为 profitability、
asset_quality、capital 三类核心主题；liquidity 证据可选，缺失不阻止银行 E 结案。已有 A-D 账本可原样追加该模式，保留预算和故障；详细数字
保存在 [银行证据包](bank-financial.md)。其他行业不启用银行模式。

保险 E 用 init --insurance-research，主题为 profitability、solvency、insurance_business、asset_liability，
详见 [保险参考](insurance-financial.md)。同一 financial 账本模式不能银行/保险互换；旧银行账本仍兼容。

用于 A–D，以及显式启用的 F10/旧行业财务取证，不改变最终 10 字段。
工具只需标准库，不联网、不安装依赖、不执行网页中的命令。

## 开工一次

```text
python3 <skill目录>/scripts/research_state.py init --state <工作目录>/research.json --stock <工作目录>/stock.json --providers <已有渠道ID列表> --research-limit 24 --f10-research
```

先保存本次原始 stock.json，init 成功后才能读取公司材料。唯一工作目录沿用到交付；禁止换目录重置、事后补账或从旧评级抄分。研究阶段的 A-D 账本可原样追加 --f10-research，不能改变输入、渠道、已设预算或复位故障；已成稿不能追加，已绑定旧行业模式不能改绑。

渠道 ID 对应宿主已经可用的检索/读取路径，按优先顺序配置，最多四个。
开工时明确它们分别对应哪个现有工具/来源；没有备用能力就不配置，不能虚构工具、临时开发爬虫或扫描端口找服务。
只保存渠道 ID 和故障状态，不保存密钥或整篇网页。

状态绑定原始 stock 的身份及内容。重复 init 保留计数、证据和停用渠道，不能换配置重置。
续跑使用同一文件；不能删除状态、改计数或另建目录绕过本轮预算。复用已读取的网页正文和紧凑证据，不重复抓取；禁止 PDF 取证和读取 PDF 缓存；只有 PDF 链接时改搜可读网页，仍缺证则 gap。

## 网页路径与失败停止

仅用现成搜索、网页正文读取/正常浏览器导航及本 skill 已支持的财务接口。可跟随实际页面公开链接；不拆 JS/source map，不查脚本配置或浏览器网络/控制台寻找 API，不猜域名、网关、接口、参数及旧页面地址，不批量试 URL。网站接口适配另作维护，本轮不展开。
同一已知页面直接读取失败时，最多再用现成浏览器正常打开一次；仍只有空壳、附件或不可读内容就换源。额度内无可读证据则 close gap，不以技术探索代替补证。

## 全局预算与成稿预留

新分析必须启用 --research-limit（默认用 24；已知宿主额度更小时开工降低），另留至少 8 次宿主调用用于结案、算分、草稿及 finalize 修复。此参数仅在首次 init 设定，重复 init 不恢复额度，也不能改变预算或给旧账本事后添加执行记录。旧账本保留旧模式续跑；不重建成看似完整的新账本。

每个新发放的搜索/读取回执扣一次，包括换源和失败重试，跨维度、冲突重开共享；重放已有在途回执不重复扣费。reserved_at/recorded_at 记录实际登记时间，不证明外部操作发生时间。每个回执对应一次宿主取证调用，不在同一回执下悄悄跑任意数量的抓取；返回下一次 search 前已预留该次额度。已有缓存事实使用 close --input，不调用工具，不补造“刚刚搜索成功”。

计数以实际取证操作为单位：搜索、后续每个页面读取、浏览器读取和 curl 均分别需要预先回执；execute_code/terminal 的循环、批量、并行子请求不能合并算一次。当前账本无法表达批量独立回执时逐次执行。财务候选脚本也须在 financial 回执下运行；一次已支持脚本运行计一次，脚本内部有界重试按既有合同执行。失败探测同样计数，不能先探测大量地址再补一条回执。外层工具数不是实际取证数，脚本不能自动发现漏记的嵌套调用。

研究余额从 init/status 全局摘要的 execution.research_remaining 查看；不要为看余额反复 status。全局用尽时 start/result 返回 stop，不发新回执；所有维度根据已得证据 complete 或 gap，仍允许完整证据定分。宿主报告额度将尽时提前执行同样收口。8 次是交付预留要求，不是脚本可验证的宿主剩余调用数；账本调用、写文件等也会消耗宿主额度。

## 一轮：具体问题 → 宿主工具 → 结果回执

```text
python3 <skill目录>/scripts/research_state.py start --state <工作目录>/research.json --dimension business --question 定价方式是否支持当前分档 --impact 可能改变业务模式3或4分 --request-id biz-1
```

每维共享一次初查和四轮网页补查，换问题名/关键词不增加轮次；一轮指围绕具体缺口检索并读取相关候选内容。
start 返回 `action/provider/request_id/attempt/question/impact/missing_topics`，仅 action=search 才调用对应宿主工具。
重放同一请求须维度、问题及影响说明一致；在途轮次未登记前不能另开一轮。
已有事实不必重搜，同一来源可以覆盖多个主题。

工具返回后写紧凑结果文件，再运行 result；不把整个工具响应复制回状态工具：

```json
{
  "dimension": "business", "request_id": "biz-1", "attempt": 1,
  "outcome": "failure",
  "error": {"http_status": 402, "message": "Insufficient credits"}
}
```

```text
python3 <skill目录>/scripts/research_state.py result --state <工作目录>/research.json --input <工作目录>/result.json
```

result 直接返回下一步，不另做 status 确认：

- `search`：按返回的 provider/attempt 换路，同一 request_id，不增加研究轮次。
- `wait`：暂无立即可用渠道，返回 retry_at；脚本不睡眠，可先处理其他维度或复用缓存。之后重放原 start 请求；无法继续可显式 close gap。
- `decide`：本轮结束，证据足够就 complete，否则在剩余轮次内补证，用尽就 gap。
- `stop`：全局预算用尽或渠道均不可用，不再调用宿主。预算用尽时按已得证据 close complete/gap；渠道均不可用时当前维度自动 gap。保留已得事实，不开发临时工具继续追搜。

402/余额不足、401/鉴权失败、403/禁止访问或未知工具故障停用该渠道；429、超时和网络故障优先换可用路径，
同一渠道累计失败两次后本轮停用。等待提示最多 300 秒，不要求原地等待。成功响应清除临时失败计数，不恢复已永久停用渠道。
404/410 和无命中只结束当前请求路径，不代表整个渠道失效，也不代表没有风险。
停用跨维度生效；重放尚未使用的旧回执时也会检查渠道状态，必要时换路；被取消的旧回执不能再登记迟到结果。

成功用 `outcome: success`，可附 evidence；无命中用 `outcome: empty`，不附事实或猜测。
同一结果重复登记不新增轮次，已登记回执不能改成不同结果。搜索摘要不能冒充已读全文。

## 证据与结案

evidence 是以下对象的数组（虚构格式例子）：

```json
{
  "topic": "main_business", "statement": "已读原文确认的主营构成，附适用范围与限制",
  "url": "https://example.com/annual-results", "locator": "主营构成栏目，收入构成表", "period": "2025年度"
}
```

每维最多 12 条紧凑事实，statement ≤800 字符。程序检查字段及来源形状，不能证明事实真实。
冲突应保留在说明中，不静默覆盖旧事实；未找到证据不能登记为“无风险”。

| dimension | 必须覆盖的 topic |
|---|---|
| business | main_business 主营；customers_repeat 客户及复购；pricing_cycle 定价与周期 |
| moat | advantages 五类优势逐项判断；durability_trend 深度、持久性及趋势；counterevidence 侵蚀/复制反证 |
| industry | demand_driver 需求驱动；substitution_risk 替代及下行风险 |
| management | decisions 关键决策及结果；allocation_alignment 资本配置与股东利益；governance_succession 治理及接班 |

```text
python3 <skill目录>/scripts/research_state.py close --state <工作目录>/research.json --dimension business --status complete --reason 所需事实和反证已核对
python3 <skill目录>/scripts/research_state.py close --state <工作目录>/research.json --dimension industry --status gap --reason 四轮网页补查后仍缺需求驱动的一手证据
```

已有缓存事实可用 close 的 `--input <证据数组.json>` 直接登记，不强迫搜索。
complete 要求必要主题都有引用，且没有在途调用；gap 保留事实/缺口，并取消未完成回执。
最后一轮成功取得证据仍可 complete，不因预算刚耗尽机械记 gap。
已结案不得再搜，“再确认一下”不是重开理由。

具体新冲突可能改变分档时：

```text
python3 <skill目录>/scripts/research_state.py reopen --state <工作目录>/research.json --dimension business --conflict 新公告主营构成与原证据矛盾 --impact 可能改变主导业务及2或3分裁决
```

每维只重开一次、再补证一轮，保留历史与旧事实；仍无法裁决就 gap。
恢复会话用 status 看紧凑进度，加 `--dimension business` 才返回该维事实，不打印全部原文。

## 交付与边界

全部研究维度 complete/gap 后，固定 dimensions.json，运行：

```text
python3 <skill目录>/scripts/rating_math.py calculate --input dimensions.json --research-state research.json
```

新执行账本进入 report 阶段并保存该版分数与派生结果；开放维度不能进入成稿。进入后不再发放普通取证回执。新冲突先 reopen（仍只一次且不恢复全局余额），旧快照随即作废；无额度则直接 close gap，不补查。若只是基于已有证据改分，重新 calculate 更新快照即可；报告、summary、风险与边界必须同步修改。

正常 finalize 必须带 --research-state 和 --output rating.json（原始输入及 E 校验参数见主 skill）。新执行账本拒绝未计算或与当前分数不同的快照；旧无执行控制的账本和无标志入口仅保留兼容。成功原子保存十字段 JSON，stdout 同一内容，立即原样回复并停止调用工具。失败只修具体错误；没有成功结果就报告执行失败，不能人工拼出“已完成”的评分。失败不会覆盖以前的输出；调用方只接受本次退出码 0 的产物，不能发送遗留文件。

锁冲突或状态损坏时返回错误，不用 init 清空修复；遗留锁由维护者确认没有写进程后处理。

宿主搜索仍由 agent 实际调用。本工具检查调用前后状态与交付，不物理拦截跳过它的外部调用；
宿主层完全强制执行需要调用方接入回执，属于另行集成工作。

## F10 旧账本完整命令

以下只用于已启用 research.json 的任务；新分析不执行。报告期与评分合同见 [F10入口](f10-financial.md)。

先按主 skill 用 --f10-research 初始化 research.json，再预留 financial 回执；不要启用旧银行/保险模式。
初始化时将已有的终端直连路径列为首个渠道（例如 --providers direct search browser，未具备的渠道不配置）；
direct 用于已支持的 F10 命令及正常网页直连，其他渠道按其实际能力使用。
渠道沿用初始化配置，不能把财务接口失败谎报为另一个搜索服务的故障。
只在 action=search 且 provider 对应已有直连能力时实际取数；已知无该能力就按真实故障登记/结案，
不让搜索服务替代财务脚本或开发临时取数器。

```text
python3 <skill目录>/scripts/research_state.py start --state research.json --dimension financial --question 获取目标期F10基础财务包 --impact 决定E分与缺口 --request-id fin-1
python3 <skill目录>/scripts/f10_financial.py --stock stock.json --as-of YYYY-MM-DD --report-date YYYY-MM-DD --cache-dir api-cache --output f10-data.json
python3 <skill目录>/scripts/rating_math.py financial --input stock.json --f10-data f10-data.json
```

F10 命令返回包内 financial 评分和缺口，后续 financial 命令仅在需要重读/校验已有包时使用，
不重新联网。把本次真实结果写入 fin-result.json，再登记：

```json
{
  "dimension": "financial", "request_id": "fin-1", "attempt": 1,
  "outcome": "success",
  "evidence": [{
    "topic": "f10_data", "statement": "已取得目标期基础评分所需指标；第三方数据，专用风险未评估",
    "url": "https://datacenter.eastmoney.com/securities/api/data/v1/get",
    "locator": "RPT_F10_FINANCE_MAINFINADATA，ROEJQ及扣非字段",
    "period": "实际目标期"
  }]
}
```

示例不代表真实取数：attempt 使用 start 返回值；URL 使用包内实际请求地址，期间、说明按实际结果填写。
locator 最多 160 字符，statement 最多 800；不要把原响应或整个 URL 填入定位字段。
命令失败按真实错误登记 outcome=failure，不填成功事实。包已返回但核心数据不足时，仍可登记已取得的
范围与缺口，E 保持 null；success 只表示取得资料，不等于可评分。沿用返回的预算/渠道动作，
不为补缺开发新接口。

```text
python3 <skill目录>/scripts/research_state.py result --state research.json --input fin-result.json
python3 <skill目录>/scripts/research_state.py close --state research.json --dimension financial --status complete --reason 基础评分所需核心数据齐备
```

只有核心数据足以评分、回执已登记且无在途调用时才 complete。数据不足或渠道不可用时 close --status gap，
reason 写实际缺口，E=null。financial 与 A-D 均结案后才能 calculate/成稿。复用已验证来源的现有包时可用
close --input 登记紧凑证据，不伪造新联网回执。
