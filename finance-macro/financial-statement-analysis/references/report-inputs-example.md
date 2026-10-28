# 报告输入

从 build_report_spec.py 生成 report_spec.json 再编辑定性段落。fact_id 使用本次返回的 ID，metric_id 查指标目录。下面仅演示形状，完整结构由骨架生成。

```json
{
  "schema_version": 1,
  "sections": [{
    "anchor": "## 核心结论",
    "statements": [{
      "template": "本期营业收入 {rev:amount_wan}。",
      "bindings": {"rev": {"fact_id": "fact-revenue-current"}},
      "claim_type": "fact"
    }],
    "paragraphs": ["经营现金回收情况需结合本期利润与营运资金变化判断。"]
  }]
}
```

表格 columns 包括科目与各 cells；一行 cells 数等于 columns 数减一。末尾空字符串自动生成该行完整 F10 来源，不能自己填来源数字或日期。

格式：amount_yuan、amount_wan、amount_yi；percent0/1/2；pp0/1/2。decline_ 前缀仅用于非正值的下降幅度。普通金额和比率保留实际符号。claim_type 可为 fact、calculation、inference；不把自行推断标为公司解释。

statements 通过绑定引用数值；paragraphs 严格不含任何数字。cite_sources 默认开启。预检只检查输入不消耗正式预算；正式 report 执行独立复核。

毛利润等派生事实仍通过 fact_id 绑定并使用 claim_type=fact；claim_type=calculation 专用于 metric_id 指标绑定，派生事实的计算输入由来源链自动追溯。
