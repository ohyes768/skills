# 轻量进度：记事实，不逐次记调用

新分析使用 progress.json。它保留事实、出处、A-D 判别主题、分数/缺口和失败渠道，
不发放回执、不维护调用余额。F10 独立保存 f10-data.json，财务 E 由既有工具计算。
旧 research.json 续跑按 [旧账本兼容](research-control.md) 执行，不把旧记录自动转换成新取证。

## 开工一次

先保存原始 stock.json，在本轮唯一工作目录运行：

```text
python3 <skill目录>/scripts/research_progress.py init --stock stock.json --output progress.json
```

init 原子创建模板，stdout 只返回紧凑摘要；已有同输入文件原样保留，不清空事实或失败渠道。
模板绑定 code/name 和原始输入哈希，不能手改哈希换股票。单次运行单写入者，不共享进度文件。
续跑直接读取原文件。仅需要紧凑状态时用 `research_progress.py status --output progress.json`，
不为每次读取额外运行 status。

## 每取得一批来源，直接更新同一个文件

不用 start/result/close。用宿主文件编辑工具将来源与紧凑事实一次写入 sources/facts，
并同时更新它支持的各维 topics；同一个事实 id 可跨维度引用。不要把网页全文写进去。
失败只记录实际渠道/后端与原因；同一后端的搜索和正文读取一起考虑，已知余额/鉴权失败不再试。

以下是局部格式例子，不是可以直接评分的真实证据：

```json
{
  "sources": [{
    "id": "S1", "title": "公司：年度经营公告", "url": "https://example.com/annual",
    "source_type": "official", "published_at": null, "accessed_at": "2026-10-29"
  }],
  "facts": [{
    "id": "F1", "source_id": "S1", "statement": "已读正文确认的主营构成及适用限制",
    "locator": "主营业务栏目及收入构成表",
    "period": "2025年度"
  }],
  "failed_sources": [{"provider": "实际后端名称", "reason": "余额不足，本轮停用"}],
  "dimensions": {
    "business": {
      "status": "open", "score": null, "reason": "仍缺定价与客户复购证据",
      "topics": {"main_business": ["F1"]}, "gaps": ["客户复购与定价情况尚未核实"]
    }
  }
}
```

保留模板的 progress_type/schema_version/stock/input_sha256 和完整四维，不用这个片段覆盖整个文件。
新模板 schema_version=2，来源和事实分开；S1 等来源编号稳定保存，正文引用同一编号。
来源类型为 official（公司/交易所/监管）、research（研报）、data_platform（第三方数据平台）或 media（媒体）。
published_at 为实际披露日 YYYY-MM-DD，未知用 null；accessed_at 为实际访问日，不能互相替代。
不为补标题或日期另行搜索；只在实际读到的页面上记录准确标题，日期未知仍可使用并明示。
sources/facts 各最多48条，id 各自唯一；title≤240、statement≤800、url≤512、locator≤160、period≤80字符。
URL 用实际读过的正文地址，定位只写栏目/表格，不复制长链接。
每维展开后最多12条主题事实引用；事实可复用，不能为填主题把无关事实强行挂上。
原 schema_version=1 和内联 url 事实仍可续跑，不强制迁移、不补造过去的来源元信息。

| 维度 | topics 必须回答的问题 |
|---|---|
| business | main_business、customers_repeat、pricing_cycle |
| moat | advantages、durability_trend、counterevidence |
| industry | demand_driver、substitution_risk |
| management | decisions、allocation_alignment、governance_succession |

status=complete：必要主题均有事实引用，按主 skill 作出判断；score 为1–5整数，reason 写分档理由，
gaps 为空。次要限制写 reason 或事实说明，不混成阻止评分的核心缺口。
status=gap：score=null，reason 和 gaps 写具体未解决问题；已核实事实及引用保留。
status=open：尚未裁决，score=null，可以阶段性保存；calculate/finalize 会拒绝未收口状态。
只补缺口；维度完成后不重新搜索。具体重大冲突才改回 open，保留原事实并在 reason 说明冲突，
沿用主 skill 的补证上限。工具检查引用形状与分数一致性，不能证明主题真的被回答。

## 算分、写报告、校验

来源表直接生成，不重复整理标题、编号与日期：

```text
python3 <skill目录>/scripts/research_progress.py sources --output progress.json --stock stock.json --f10-data f10-data.json
```

只读返回 Markdown 表，只列 A-D 引用的事实来源和 F10 实际参与基础评分的主指标/适用负债率来源。
F10 从原响应重算并核对输入，不信任缓存分数；同 URL 复用编号，不自动加入未用于判断的其他三表。
若额外财务事实用于 A-D，则按实际来源登记。来源表截取每条事实前120字符作为支持提示，完整论据留在 facts。
旧内联来源没有标题/日期时明确“未记录”，不编造；只输出表头表示无可列来源，应在报告说明缺口。
此命令不联网、不改进度文件，原样纳入 report_md，正文使用表中来源编号。
调用方背景只有实际用于报告才手动追加 [I1]，按 [输出合同](output-contract.md) 标明未独立核验。

A-D 全部 complete/gap 后，按进度中的分数和 F10 的 E 保存 dimensions.json：

```text
python3 <skill目录>/scripts/rating_math.py calculate --input dimensions.json --progress progress.json
python3 <skill目录>/scripts/rating_math.py finalize --input draft.json --stock stock.json --check-financial --f10-data f10-data.json --progress progress.json --output rating.json
```

calculate 只读进度，返回总分/星级/边界；不再 seal 或创建账本快照。finalize 核对原始输入、
A-D 完成状态和分数，并从 F10 原响应重算 E；缺证据维度为 null。语义检查由分析者完成。
只读复核时 `validate_rating_json.py rating.json --stock stock.json --check-financial --f10-data f10-data.json --progress progress.json`。
--progress 与旧 --research-state 互斥。成功仍交付固定十字段 JSON，进度文件不进入最终对象。

## 时间与调用边界

不显示 research_remaining 或声称已拦截调用。宿主提示额度将尽时立即停止取证，
将未完成项按实际缺口改为 gap，保存后完成计算和校验。没有宿主提示也不能无限追查：
沿用主 skill 的定向补查停止规则，已失败来源不反复探测。不设置未经实跑验证的完成时间承诺。
