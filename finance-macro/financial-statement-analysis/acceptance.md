# F10-only 验收

本版本以代码和报告期取东财合并三表。旧取数链路及依赖已移除。

自动化验证覆盖：精确数值留档、增量缓存、接口错误与空记录、证券/期间拒绝、事实映射、缺失值、派生毛利润、来源篡改、指标期间配对、独立复算、报告数值/正文/来源变异、修复预算和端到端交付。

运行：

```bash
uv run --project finance-macro/financial-statement-analysis pytest finance-macro/financial-statement-analysis/tests
uv run --project finance-macro/financial-statement-analysis ruff check finance-macro/financial-statement-analysis
```

本地离线测试使用 mock HTTP 及真实映射/计算/渲染，不以测试通过宣称实时接口一定可用。不覆盖 Hermes 部署或调用端迁移。新版调用必须传 --code 和 --period。

## 2026-10-28 验证与耗时样本

- 127 项 skill 测试、Ruff、skill 元数据校验通过；关联基本面测试 36 项及 135 个子测试通过。
- 国脉科技 002093、2026-06-30：真实 F10 prepare 入口约七秒（单次）；70 条事实、13 项可用指标。汇率影响为空时现金勾稽保持资料不足。
- 同一份 F10 留档、已撰写报告输入，本机三轮独立 Python CLI 计时中位数：缓存 prepare 1.115 秒、compute 0.486 秒、生成骨架 0.338 秒、report 含独立复核 0.579 秒。该计时不含模型读取上下文与撰写判断。
- 独立代理从留档计算、读取六个限量包、撰写报告到 verified 约两分钟，独立复核 414 项通过。这不是 MiniMax/Hermes 压测，不保证相同总时长。
