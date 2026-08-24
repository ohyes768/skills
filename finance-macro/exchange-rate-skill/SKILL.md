---
name: exchange-rate-skill
description: |
  汇率与资金流向分析 Skill，通过美元指数、人民币汇率、北向/南向资金、TED利差
  对当前或近期全球资金流向和市场风险偏好进行综合判断。

  触发场景（必须使用本 Skill）：
  - 询问"美元指数走势"或"人民币汇率"
  - 询问"北向资金"或"南向资金"流向，包括净流入、累计净流入
  - 询问"TED利差"、"SOFR"、"银行间流动性"或"美元资金成本"
  - 询问"当前市场风险偏好"或"全球资金流向"
  - 需要分析"外资动向"、"北向持续性"、"汇率压力"等场景
  - 任何涉及美元、人民币、汇率、资金流向、流动性指标的问题

  本 Skill 不处理：个股分析、融资融券（用 risk-appetite-skill）、CPI/PPI等宏观经济数据
---

# 汇率与资金流向分析 Skill

## 触发条件

当用户需要分析**汇率、资金流向或全球市场风险偏好**时触发此 Skill。

**具体场景：**
- 询问"美元指数走势"或"人民币汇率"
- 询问"北向资金"或"南向资金"流向
- 询问"TED利差"或"银行间流动性"
- 询问"当前市场风险偏好"（需要多个指标综合判断）
- 了解全球资金流向和风险情绪的场景

**本 Skill 不处理：** 个股分析、融资融券（用 risk-appetite-skill）、CPI/PPI等宏观经济数据

## 数据获取流程

### 第一步：数据抓取

运行 `scripts/run_all.py` 获取所有汇率与资金流向指标数据：

```bash
# 在 skill 目录下运行，默认写入统一输出目录
export FRED_API_KEY=your_fred_api_key
uv run python scripts/run_all.py --days 30
```

参数说明：
- `--days N`: 回溯天数，默认30日
- `--output`: JSON 数据文件路径（默认 `finance-macro/output/exchange-rate-skill/exchange_rate_data.json`）
- `--report`: Markdown 报告路径（默认 `finance-macro/output/exchange-rate-skill/exchange_rate_report.md`）
- `--upload`: 抓取后构建 macro_signal.json 并推送到线上 macro 后端（需先配置 token，见第三步）

### 数据源说明

| 指标 | 数据源 | 接口/代码 |
|------|--------|-----------|
| 美元指数 | FRED | DTWEXBGS |
| 美元兑人民币 | FRED | DEXCHUS |
| 北向资金（成交总额） | 东方财富 | RPT_MUTUAL_DEALAMT → NF_DEAL_AMT |
| 南向资金 | 东方财富 | 暂不处理 |
| SOFR | FRED | SOFR |
| 3个月美债收益率 | FRED | DGS3MO |
| TED利差 | 计算得出 | SOFR - DGS3MO |

### 第二步：数据交叉确认

脚本获取的数据可能存在误差，引导用户核对：

---

**请核对以下数据是否与官方来源一致：**

| 指标 | 脚本获取值 | 官方数据来源 |
|------|-----------|-------------|
| 美元指数 | {dollar_index} | FRED (Federal Reserve Economic Data) |
| 美元兑人民币 | {usd_cny} | 中国人民银行/Wind |
| 北向成交总额 | {north_turnover}亿元 | 东方财富/沪深港通 |
| 北向7日日均成交额 | {north_7d_avg}亿元 | 东方财富/沪深港通 |
| 北向7日环比变化 | {north_7d_change}% | 计算得出 |
| TED利差 | {ted_spread}% | 纽约联储银行 (SOFR) / 美国财政部 (3个月美债) |

**如果数据不一致，请提供正确数值。**

---

### 第三步：构建契约结构并推送到线上 macro 后端（可选）

将抓取数据转换为后端契约结构 `macro_signal.json`（`conclusion` / `data_date` / `total_score` / `details`）并推送，web 宏观界面维度卡右上角展示 `total_score` 评分徽章。
对接契约见 `personal-web/.trellis/spec/guides/macro-signal-upload.md` 第 2.3.A 节。

### 日频推送契约（month_avg 与 data_date 规则）

本 skill 为日频调度：**每交易日盘后**跑 `run_all.py --upload`。

1. **顶层 `data_date` = 推送当日**（不是指标读数日）。后端归档月份按 data_date 提取，月初盘后推送若写上月末读数日会归错月；手动补推历史月份时用 `--data-date YYYY-MM-DD` 指定。
2. **`indicator_meta`**：日频指标（美元指数 / 美元兑人民币 / TED利差）附带读数日、`frequency: "daily"` 与 `month_avg`（后端已上线透传，前端上月卡片展示月均值）；北向资金为 7 日均量衍生指标，不附 month_avg。
3. **month_avg 口径**（全 skill 统一）：读数日所在月内、截至最新读数的全部交易日算术平均；只取实际取得的交易日，缺失日跳过、分母用实际取到的交易日数；当月仅 1 个读数时退化为当日值；月末最后一推自然收敛为全月均值。汇率/TED 月均由 FRED 区间序列（本就按天拉取）筛当月计算，零额外请求。

**前置配置**：在 `finance-macro/.env`（已被 .gitignore 忽略，不入库）配置：

```env
FRED_API_KEY=<key>                # 汇率/TED 数据必需
MACRO_SIGNAL_UPLOAD_TOKEN=<token> # 推送鉴权，来自 personal-web 根 .env
MACRO_SIGNAL_UPLOAD_URL=https://web.duomi77.cn:9443/api/macro/signal/upload
MACRO_UPLOAD_SSL_VERIFY=0        # NAS 自签证书场景跳过 TLS 校验（仅限内网自建服务）
```

**方式一：抓取+转换+推送一条龙**

```bash
uv run python scripts/run_all.py --upload
```

**方式二：分步执行**

```bash
# 转换：抓取数据 → 契约结构 + 内置规则评分（可用 --conclusion 覆盖结论）
uv run python scripts/build_macro_signal.py

# 推送（先 dry-run 预检）
uv run python scripts/upload_signal.py --dry-run
uv run python scripts/upload_signal.py --verify
```

**内置规则评分**：`build_macro_signal.py` 按 SKILL.md 评分框架自动计算
（美元指数30% + 人民币20% + 北向25% + TED25%，缺失维度按剩余权重归一化），
高分=风险规避（注意与 risk-appetite-skill 方向相反）。agent 按框架精调后
可用 `--conclusion` 覆盖自动结论。

**上传前本地预检**（`upload_signal.py` 自动执行，不通过则不上传）：
- skill/file 白名单与配对（exchange-rate-skill 只能推 `macro_signal.json`）
- `conclusion`、`data_date`（取各指标最新日期的最大值）、`details` 数值字段
- 数据日期距今超过 10 天时警告确认

**错误处理**：401 → 检查 token；400 → 检查白名单/data 结构；网络错误最多重试 2 次。后端同名 file 直接覆盖（原子写），可重复推送。

---

## 评分框架（由 LLM 驱动）

数据获取后，**由 LLM 按照以下评分框架计算综合得分**：

### 指标一：美元指数（权重30%）

**数据说明：** DTWEXBGS 为美联储发布的名义广义美元指数（包含人民币等26种货币），以 2006年1月 为基期设 100，历史极值可达 125-130（2022年加息周期峰值）。截至2025年末约为 118-121，120 已是较高水平，对应 DXY 时代约 105 左右的美元强度。

| DTWEXBGS 指数值 | 市场状态 | 得分区间 |
|----------------|---------|---------|
| > 125 | 强势美元（极强） | 70–100 |
| 115–125 | 中性偏强（偏强） | 50–70 |
| 105–115 | 中性 | 40–50 |
| 95–105 | 中性偏弱 | 30–40 |
| < 95 | 弱势美元 | 0–30 |

**解读：**
- DTWEXBGS > 120 表示资金避险情绪较强
- DTWEXBGS < 105 表示风险偏好较高

### 指标二：人民币汇率（权重20%）

| 美元兑人民币 | 市场状态 | 得分区间 |
|-------------|---------|---------|
| < 7.0 | 人民币强势 | 70–100 |
| 7.0–7.2 | 中性 | 50–70 |
| 7.2–7.5 | 人民币偏弱 | 30–50 |
| > 7.5 | 人民币弱势 | 0–30 |

**解读：**
- 人民币升值（USD/CNY下降）利于A股
- 人民币贬值压力通常伴随资本外流

### 指标三：北向资金（权重25%）

#### 指标说明

- **成交总额**：北向资金当日买入与卖出的总量（反应外资参与活跃度）
- **7日日均成交额**：近7个交易日成交总额的均值（平滑波动）
- **环比变化**：本期7日日均成交额较上期（上周同期）的变化率

#### 数据获取

通过东方财富 `RPT_MUTUAL_DEALAMT` 接口获取近30日日频成交总额：

- 接口：`https://datacenter-web.eastmoney.com/securities/api/data/v1/get`
- 字段：`NF_DEAL_AMT`（北向成交总额）、`SSC_DEAL_AMT`（沪股通）、`ST_DEAL_AMT`（深股通）
- 单位：东方财富返回万元，需除以10000转为亿元

```python
# 计算公式（由 run_all.py 执行）
7日成交总额 = sum(近7日 NF_DEAL_AMT) / 10000
7日日均成交额 = 7日成交总额 / 7
上期7日成交总额 = sum(第8-14日 NF_DEAL_AMT) / 10000
环比变化 = (本期7日日均 - 上期7日日均) / 上期7日日均 × 100%
```

**注意**：`RPT_MUTUAL_NETINFLOW_STATISTICS` 的 `TOTAL_INFLOW_BOTH` 是"成交净买额"（买卖轧差），不等于本页所用的"成交总额"，请勿混淆。

#### 评分标准

| 7日日均成交额环比变化 | 市场状态 | 得分区间 |
|---------------------|---------|---------|
| 环比+20%以上 | 外资极度活跃，积极关注A股 | 70–100 |
| 环比+5%～+20% | 外资活跃度提升 | 60–70 |
| 环比-5%～+5% | 活跃度平稳 | 40–60 |
| 环比-5%～-20% | 外资参与度下降 | 20–40 |
| 环比-20%以下 | 外资大幅观望，参与度显著回落 | 0–20 |

**解读：**
- 北向成交总额环比大幅增长表明外资对A股参与度显著提升
- 成交总额较净流入更能反映外资真实的交易活跃程度
- 7日均线可平滑单日异常波动，更准确反映趋势

**辅助加减分：**
- 成交总额创近30日新高：+5分
- 连续3日成交额递减：-3分
- 单日成交额超100亿：+3分

---

### 指标四：TED利差（权重25%）

| TED利差 | 市场状态 | 得分区间 |
|---------|---------|---------|
| > 1.0% | 流动性紧张 | 0–30 |
| 0.5%–1.0% | 正常偏紧 | 30–50 |
| 0.3%–0.5% | 正常 | 50–70 |
| 0%–0.3% | 宽松 | 70–90 |
| < 0% | 极度宽松 | 90–100 |

**解读：**
- TED利差 = SOFR - 3个月美债收益率
- TED利差扩大表示银行间借贷风险上升
- 正常区间为 0.3%–0.5%

### 综合评分计算

```
加权总分 = 美元指数得分×30% + 人民币汇率得分×20% + 北向资金得分×25% + TED利差得分×25%
```

| 总分 | 结论 | 操作建议 |
|------|------|---------|
| ≥80分 | 极度风险规避 | 全球避险情绪高涨，A股承压 |
| 60–79分 | 风险偏好偏低 | 资金观望，外资可能流出 |
| 40–59分 | 中性 | 多空均衡，正常观察即可 |
| 30–39分 | 风险偏好偏高 | 关注北向资金持续性 |
| <30分 | 极度乐观 | 全球风险偏好高涨，A股有利 |

### 指标分歧处理

1. **若美元强势但北向流入**：优先信任北向资金（外资更关注A股盈利）
2. **若人民币贬值但北向流入**：说明外资看好A股盈利前景
3. **TED利差与北向背离**：TED利差反映全球流动性，北向反映A股配置偏好

## 输出格式

### 数据获取后的 JSON 格式

脚本输出的 JSON 结构：

```json
{
  "fetched_at": "2026-05-12T10:30:00Z",
  "period_days": 30,
  "data": {
    "exchange_rates": {
      "dollar_index": { "value": 104.5, "date": "2026-05-09" },
      "usd_cny": { "value": 7.15, "date": "2026-05-09" }
    },
    "fund_flow": {
      "north": {
        "turnover_yi": 61.87,
        "date": "2026-05-12"
      },
      "south": {},
      "north_cumulative": {
        "turnover_7d_sum_yi": 373.18,
        "turnover_7d_avg_yi": 53.31,
        "turnover_7d_change_pct": 12.5
      },
      "south_cumulative": {
        "turnover_7d_sum_yi": 89.08,
        "turnover_7d_avg_yi": 12.73,
        "turnover_7d_change_pct": -3.2
      }
    },
    "ted_spread": {
      "sofr": 3.66,
      "us_3m": 3.68,
      "ted_spread": -0.02
    }
  },
  "errors": []
}
```

### 完整分析报告格式（LLM 生成）

```markdown
# 汇率与资金流向分析报告

## 核心结论
**中性偏弱**（综合评分: 52分）
> 美元指数走强压制人民币，北向资金观望情绪浓厚

## 核心指标

| 指标 | 当前值 | 变化 | 信号 | 得分 |
|------|--------|------|------|------|
| 美元指数 | 104.5 | +0.8% | 🟡 | 65 |
| 美元兑人民币 | 7.15 | +0.3% | 🟠 | 45 |
| 北向7日累计 | -168亿 | 转负 | 🔴 | 35 |
| TED利差 | 0.35% | 持平 | 🟢 | 60 |

## 评分明细

| 维度 | 得分 | 权重 | 加权得分 |
|------|------|------|---------|
| 美元指数 | 65分 | 30% | 19.5分 |
| 人民币汇率 | 45分 | 20% | 9分 |
| 北向资金 | 35分 | 25% | 8.75分 |
| TED利差 | 60分 | 25% | 15分 |
| **综合评分** | | | **52.25分** |

## 分析解读

[当前汇率背景、资金流向逻辑、关键信号梳理]

## 风险提示

[若得分处于极值区间或指标背离，需说明原因]
```

---

## 注意事项

1. **评分由 LLM 驱动**：脚本只获取和格式化数据，评分由 LLM 按照本 SKILL.md 的评分框架计算
2. **FRED API Key**：需要从 https://fred.stlouisfed.org/docs/api/api_key.html 申请
3. **数据延迟**：FRED数据通常有1-2天延迟，AKShare北向资金当日09:45更新
4. **TED利差**：可能为负值（3个月美债收益率高于SOFR），表示极度宽松
5. **指标权重**：美元指数30%、人民币汇率20%、北向资金25%、TED利差25%
6. **信号优先级**：当多个指标出现分歧时，优先信任北向资金（外资配置行为）

---

## 文件结构

```
exchange-rate-skill/
├── SKILL.md                    # 本文件（评分框架）
└── scripts/
    ├── fetch_common.py         # 公共工具（logging、HTTP会话、类型转换）
    ├── fetch_exchange_rates.py # 美元指数+人民币汇率（FRED DTWEXBGS/DEXCHUS）
    ├── fetch_north_flow.py     # 北向资金成交总额（东方财富 RPT_MUTUAL_DEALAMT）
    ├── fetch_ted_spread.py     # TED利差（FRED SOFR/DGS3MO）
    ├── build_macro_signal.py   # 构建契约结构（转换+内置规则评分）
    ├── upload_signal.py        # 推送 JSON 到线上 macro 后端（6 skill 通用）
    └── run_all.py              # 统一入口（数据抓取，--upload 可选推送）

# 运行产物统一写入（不入代码库）：
finance-macro/output/exchange-rate-skill/
├── exchange_rates.csv          # 汇率数据（追加式）
├── fund_flow.csv               # 资金流向数据（北向成交总额 + 日频明细）
├── ted_spread.csv              # TED利差数据
├── exchange_rate_data.json     # JSON 数据输出
└── exchange_rate_report.md     # 文本报告（数据层面）
```