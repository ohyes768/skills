# Monetary Indicators Fetcher

抓取以下货币政策指标的最新一期数据，并输出 JSON：

- DR007（银行间 7 天期质押式回购利率）
- MLF（月度净投放：财联社口径；并保留央行招标金额/期限口径）
- LPR（1 年期、5 年期以上）

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行

在 `monetary-policy-skill` 目录下执行：

```bash
python scripts/run_all.py
```

默认输出文件：

- `data/monetary_indicators_latest.json`

指定输出路径：

```bash
python scripts/run_all.py --output data/latest.json
```

按月抓取 MLF 月度净投放（推荐，DeepSeek WebSearch）：

```bash
python scripts/run_all.py --month 2026-03 --mlf-provider deepseek
```

如需使用旧版页面抓取逻辑（legacy）：

```bash
python scripts/run_all.py --month 2026-03 --mlf-provider legacy --mlf-cls-url https://www.cls.cn/detail/2333564
```

`run_all.py` 输出结构中：

- `mlf`：默认指向财联社月度净投放（主口径）
- `mlf_monthly_net`：同 `mlf`，保留显式字段便于下游迁移
- `mlf_auction`：央行招标口径（金额、期限）

## DeepSeek 配置

1. 复制示例配置文件：

```bash
copy .env.example .env
```

2. 编辑 `.env`，至少配置：

```dotenv
DEEPSEEK_API_KEY=your_deepseek_api_key
```

可选配置：

- `DEEPSEEK_BASE_URL`（默认 `https://api.deepseek.com/v1`）
- `DEEPSEEK_MODEL`（默认 `deepseek-chat`）

说明：`.env` 已在本目录 `.gitignore` 中忽略，不会被提交。

## 单独抓取

```bash
python scripts/fetch_dr007.py
python scripts/fetch_mlf.py --source auction
python scripts/fetch_mlf_deepseek.py --month 2026-03
python scripts/fetch_mlf.py --source monthly_net --month 2026-03
python scripts/fetch_mlf.py --source monthly_net --month 2026-03 --cls-url https://www.cls.cn/detail/2333564
python scripts/fetch_mlf.py --source both --month 2026-03
python scripts/fetch_lpr.py
```

## 常见问题

- 中国人民银行页面可能出现 `403`，脚本会自动尝试备用地址并记录失败原因。
- DeepSeek 模式若报 `缺少 DEEPSEEK_API_KEY`，请检查 `.env` 或环境变量是否正确加载。
- DeepSeek 返回若不是 JSON 或 `source_url` 非 `cls.cn/detail`，结果会标记 `failed/partial` 并附带 `error/warning`。
- DeepSeek 模式建议总是传 `--month YYYY-MM`，否则 `run_all.py` 会回退 legacy。
- 财联社页面若改版，可能导致 `MLF净投放` 正则未命中，`parse_status` 会变为 `partial/failed`，请检查：
  - 自动发现是否命中当月“央行XX月流动性投放情况”相关新闻；
  - 正文是否包含“中期借贷便利（MLF）净投放X亿元”语句；
  - `--month` 传参与页面月份是否一致（不一致会标记 `partial` 并给出 warning）。
- ChinaMoney 页面若改版为更强动态渲染，可能只能解析到部分字段，此时 `parse_status` 为 `partial`。
- 请定期人工核对关键数值，确保与官网一致。
