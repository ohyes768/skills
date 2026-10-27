# 有预算的取证与失败换路

银行 E 同样使用本工具：init 增加 --bank-research，dimension=financial，主题为 profitability、
asset_quality、capital、liquidity。已有 A-D 账本可原样追加该模式，保留预算和故障；详细数字
保存在 [银行证据包](bank-financial.md)。其他行业不启用银行模式。

保险 E 用 init --insurance-research，主题为 profitability、solvency、insurance_business、asset_liability，
详见 [保险参考](insurance-financial.md)。同一 financial 账本模式不能银行/保险互换；旧银行账本仍兼容。

用于 A–D，以及显式启用的银行/保险 E，不改变最终 10 字段；其他行业 E 用原始输入直接计算。
工具只需标准库，不联网、不安装依赖、不执行网页中的命令。

## 开工一次

```text
python3 <skill目录>/scripts/research_state.py init --state <工作目录>/research.json --stock <工作目录>/stock.json --providers primary backup official
```

渠道 ID 对应宿主已经可用的检索/读取路径，按优先顺序配置，最多四个。
开工时明确它们分别对应哪个现有工具/来源；没有备用能力就不配置，不能虚构工具、临时开发爬虫或扫描端口找服务。
只保存渠道 ID 和故障状态，不保存密钥或整篇网页。

状态绑定原始 stock 的身份及内容。重复 init 保留计数、证据和停用渠道，不能换配置重置。
续跑使用同一文件；不能删除状态、改计数或另建目录绕过本轮预算。原文复用 PDF 缓存。

## 一轮：具体问题 → 宿主工具 → 结果回执

```text
python3 <skill目录>/scripts/research_state.py start --state <工作目录>/research.json --dimension business --question 定价方式是否支持当前分档 --impact 可能改变业务模式3或4分 --request-id biz-1
```

每维共享一次初查和两轮补查，换问题名/关键词不增加轮次；一轮指围绕具体缺口检索并读取相关候选内容。
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
- `stop`：所有配置渠道不可用，当前维度自动记 gap 并保留已得事实，不开发临时工具继续追搜。

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
  "url": "https://example.com/annual.pdf", "locator": "PDF p12，主营构成表", "period": "2025年度"
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
python3 <skill目录>/scripts/research_state.py close --state <工作目录>/research.json --dimension industry --status gap --reason 两轮补查后仍缺需求驱动的一手证据
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

正常 finalize 加 `--research-state <工作目录>/research.json`，A–D 必须 complete/gap，gap 对应分项必须 null。
无标志入口保留旧调用兼容，新分析按本流程交付。锁冲突或状态损坏时返回错误，不用 init 清空修复；
遗留锁由维护者确认没有写进程后处理。

宿主搜索仍由 agent 实际调用。本工具检查调用前后状态与交付，不物理拦截跳过它的外部调用；
宿主层完全强制执行需要调用方接入回执，属于另行集成工作。
