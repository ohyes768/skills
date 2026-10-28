# report spec 自动生成

```bash
uv run --project finance-macro/financial-statement-analysis python finance-macro/financial-statement-analysis/scripts/build_report_spec.py --run-dir <目录> --out report_spec.json
```

构造器把骨架 FACT_* 换成真实 fact_id，按精确期间选择事实；指标必须 computed。缺少事实的普通行会删除，风险项保留资料不足状态，数据限制会汇总。零是有效披露值，不等于字段缺失。

输出的 `_paragraphs_todo` 列出需要 agent 改写的定性段落。按本次 facts、metrics 与 red_flags 写判断，删除已完成的待办标记。不要修改数据源、计算结果或校验文件来适配草稿。

本期收入缺比较期时只陈述本期，不构造同比结论。定性段落不含数字；引用由正式 report 渲染器自动插入。最后执行 `report --spec <目录>/report_spec.json --independent-review`，不要在最终调用重新生成骨架覆盖写好的段落。
