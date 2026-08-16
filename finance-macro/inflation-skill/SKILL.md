---
name: inflation-skill
description: 当用户询问"本月通胀情况"、"CPI/PPI多少"、"物价水平"、"通货膨胀"、"通胀走势"、"PPI对周期股影响"、对比分析多个时期的通胀数据、或要求分析通胀数据时触发。本skill自动抓取CPI、PPI、核心CPI数据，给出综合评分和结论。适用于宏观研究、经济分析、周期股研究等场景。
---

# 通胀分析 Skill

## 数据指标

### CPI（居民消费价格指数）
| 字段 | 说明 |
|------|------|
| cpi_national_yoy | 全国同比（%） |
| cpi_national_mom | 全国环比（%） |
| cpi_national_cumulative | 全国累计同比 |
| cpi_urban_yoy | 城镇同比 |
| cpi_rural_yoy | 农村同比 |
| core_cpi_yoy | 核心CPI同比（Tavily+DeepSeek搜索权威媒体） |

### PPI（工业生产者出厂价格指数）
| 字段 | 说明 |
|------|------|
| ppi_current | 当月值（上年=100定基） |
| ppi_yoy | 同比（%） |
| ppi_cumulative | 累计同比 |

## 数据发布时间

- **CPI / PPI**：国家统计局每月9日发布上月数据（如3月数据 → 4月9日发布）
- **核心CPI**：随CPI数据同步发布，来源为权威媒体（新华网、财新等）报道

脚本自动处理月份降级：若查询月份数据尚未发布，自动降级到最近已发布的月份。

## 数据来源

- **CPI / PPI**：akshare `macro_china_cpi()` / `macro_china_ppi()`
- **核心CPI**：Tavily 搜索权威媒体报道 → DeepSeek 提取（数据源：新华网、财新等）
- East Money: https://data.eastmoney.com/cjsj/cpi.html | https://data.eastmoney.com/cjsj/ppi.html

## 环境变量

核心CPI搜索需要以下环境变量（请在 skill 根目录的 `.env` 文件中配置）：

```
TAVILY_API_KEY=your_tavily_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key
```

## 使用方式

```bash
# 抓取最新数据（需要先安装依赖）
bash scripts/run.sh

# 或直接运行（需在 skill 目录下执行）
uv run scripts/fetch_all.py

# 抓取指定月份数据
uv run scripts/fetch_all.py --month 2026-03

# 抓取+评分+推送到线上 macro 后端（可选，见下文「推送到线上 macro 后端」）
uv run scripts/run_all.py --upload
```

## 输出说明

成功时输出包含：
- `month`：实际数据月份（可能因发布日降级）
- `cpi`：CPI完整数据
- `ppi`：PPI完整数据
- `core_cpi`：核心CPI数据（含来源URL）
- `fetched_at`：抓取时间

输出路径（统一输出目录，不入代码库）：
- 最新数据：`finance-macro/output/inflation-skill/inflation_latest.json`
- 按月缓存：`finance-macro/output/inflation-skill/YYYY-MM/inflation.json`

## 分析框架

### 综合评分（满分100分）

**综合评分 = CPI得分×40% + PPI得分×30% + 核心CPI得分×30% + 辅助分**

| 总分 | 结论 | 政策语境 |
|------|------|---------|
| ≥80 | 明显通胀偏高 | 央行或收紧，抑制需求 |
| 60-79 | 通胀温和偏高 | 政策以稳为主 |
| 40-59 | 通胀温和/低位（中性） | 经济回升但无明显压力 |
| 20-39 | 低通胀（偏冷） | 总需求不足，需宽松 |
| <20 | 通缩风险 | 价格持续下跌，需刺激 |

### CPI同比（权重40%）

| 同比区间 | 含义 | 分数 |
|---------|------|------|
| >2.5% | 明显偏高 | 80-100 |
| ≤2.5%，>2.0% | 温和偏高 | 60-80 |
| ≤2.0%，>1.0% | 温和/低位（中性） | 40-60 |
| ≤1.0%，>0% | 低通胀（偏冷） | 20-40 |
| ≤0% | 通缩风险 | 0-20 |

**辅助加减分**：环比连续2月+正 → +3-5分；非食品价格同比>1.5%加速 → +3-5分

### PPI同比（权重30%）

| 同比区间 | 含义 | 分数 |
|---------|------|------|
| >3% | 明显偏高 | 80-100 |
| ≤3%，>2% | 温和偏高 | 60-80 |
| ≤2%，>0% | 温和或低位（中性） | 40-60 |
| ≤0%，>-2% | 低通胀（偏冷） | 20-40 |
| ≤-2% | 通缩风险 | 0-20 |

**辅助加分**：环比连续3月+正且扩大 → +5分；采掘业PPI低位反弹转正 → +5分

### 核心CPI同比（权重30%）

| 同比区间 | 含义 | 分数 |
|---------|------|------|
| >2.5% | 明显偏高 | 80-100 |
| ≤2.5%，>2.0% | 温和偏高 | 60-80 |
| ≤2.0%，>1.0% | 温和/低位（中性） | 40-60 |
| ≤1.0%，>0.3% | 低通胀（偏冷） | 20-40 |
| ≤0.3% | 通缩风险 | 0-20 |

**辅助加分**：核心CPI环比连续3月+正且加速 → +5分

### 分歧处理规则

1. **核心CPI优先** — 核心CPI代表趋势性，过滤短期扰动
2. **PPI环比拐点信号强** — 商品价格拐点时权重优先
3. **春节错月需备注** — 同比跳变不可视为趋势（如2月数据）

## 推送到线上 macro 后端（可选）

将抓取数据转换为契约结构 `macro_signal.json`（`conclusion` / `data_date` / `total_score` / `details`）并推送，web 宏观界面每个维度右上角展示评分徽章。
对接契约见 `personal-web/.trellis/spec/guides/macro-signal-upload.md` 第 2.3.A 节。

**前置配置**：在 `finance-macro/.env`（不入库）配置：

```env
MACRO_SIGNAL_UPLOAD_TOKEN=<token> # 推送鉴权，来自 personal-web 根 .env
MACRO_SIGNAL_UPLOAD_URL=https://web.duomi77.cn:9443/api/macro/signal/upload
MACRO_UPLOAD_SSL_VERIFY=0        # NAS 自签证书场景跳过 TLS 校验（仅限内网自建服务）
```

**方式一：抓取+评分+推送一条龙**

```bash
uv run scripts/run_all.py --upload
```

**方式二：分步执行**

```bash
uv run scripts/build_macro_signal.py    # 按评分框架计算总分并构建契约结构
uv run scripts/upload_signal.py --dry-run
uv run scripts/upload_signal.py --verify
```

**内置规则评分**：`build_macro_signal.py` 按 SKILL.md 评分框架自动计算
（CPI×40% + PPI×30% + 核心CPI×30%，核心CPI 缺失时按剩余权重归一化），
`total_score` 随推送上线。月度数据 `data_date` 落在 `YYYY-MM-01`；
上传前自动预检（skill/file 白名单、字段结构、数据新鲜度 45 天）。

## 不处理范围

- 货币政策（用 monetary-policy-skill）
- 货币供应量/社融（用 money-supply-skill）
- 实体经济综合判断（用 entity-economy-skill）
