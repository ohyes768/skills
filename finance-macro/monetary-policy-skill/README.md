# Monetary Indicators Fetcher

抓取 MLF 月度净投放与 LPR（1 年期、5 年期以上）的最新数据，并输出 JSON。

## 运行

```powershell
uv run python scripts/run_all.py --month YYYY-MM
uv run python scripts/run_all.py --month YYYY-MM --upload
```

默认输出目录为 `finance-macro/output/monetary-policy-skill/`：

- `monetary_indicators_latest.json`：MLF 与 LPR 原始数据。
- `macro_signal.json`：可上传到宏观信号接口的评分结果。

## 环境变量

- `TAVILY_API_KEY`、`DEEPSEEK_API_KEY`：用于抓取 MLF 净投放。
- `MACRO_SIGNAL_UPLOAD_TOKEN`：启用 `--upload` 时必须配置。
- `MACRO_SIGNAL_UPLOAD_URL`：可选；未设置时使用默认接口地址。

## 评分口径

MLF 净投放与 LPR 各占 50%。任一数据缺失时，按剩余有效指标的权重归一化。