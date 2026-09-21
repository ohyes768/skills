# A+H 双重上市 H 股 IPO 研究模板

适用于：已在 A 股上市、赴港二次上市或发行 H 股的港股 IPO（典型 code 提示：`6` 开头主板 + A 股母公司同期财报可查；招股书首页会写"已发行 A 股 XXXXX 股，本次拟发行 H 股 XXX 万股"）。

**核心策略：A 股数据是 H 股 IPO 财务/股东事实的最高质量源。** A 股年报、季报、招股书附属 PDF 通常 SSR 可达（与 HKEX PDF 不同），而港交所招股书 PDF 几乎抓不到（见 PITFALLS #2）。A 股公告的实控人/股权结构与 H 股发行后稀释比例 1:1 同源，**完全可作为 H 股报告的主源**。

## 数据源优先级

| 字段 | 首选源 | 备选源 | 不要用 |
|---|---|---|---|
| 招股条款（价格/期/规模） | jisilu list --json | 港交所披露易 / AAStocks per-code | — |
| 孖展/超购 | tradesmart tracker | — | hkex active |
| 基石名单 | 智通财经 / 雪球招股条目 / 360kuai 招股速递 | HKEX 招股书 P.X（仅供核验） | etnet |
| **历史营收/净利（≥3 年）** | **A 股巨潮年报 / 东方财富年报页** | 同花顺 F10 / 雪球年报摘要 | HKEX PDF |
| **最新季报业绩（Q3/Q4）** | **A 股巨潮季报 / 东方财富季报页** | 同花顺 / 凤凰网财经 | HKEX PDF |
| **实控人 + 持股比例** | **同花顺金融服务网 F10 股东研究** | 雪球实控人帖 + 公司互动平台答复 | HKEX PDF |
| 早期战投/产业股东 | A 股招股书 + 历年减持公告 | 雪球 | — |
| **A+H 总市值与折价** | **A 股最新收盘价 + H 股发行价上限**（按总股本折算） | 凤凰网 / 财经媒体招股速递 | — |
| 行业可比公司 PE | 东方财富行业数据中心 | 同花顺 F9 | — |
| 保荐人历史战绩 | `jisilu list --sponsor <中文>` | — | `sentiment sponsor-search`（不模糊匹配） |

## 实操：拿到 A 股母公司代码后

1. **从 jisilu 拿到 H 股 code 后立刻找 A 股 code**：搜 `{公司名} {H股代码} A股 代码`，通常第一条就是同花顺/东方财富的"对照表"。
2. **A 股财务优先源**（SSR 稳定，PDF 可读）：
   - `https://data.eastmoney.com/notices/getdata.ashx?StockCode=300XXX`（东方财富公告页）
   - `http://www.cninfo.com.cn/new/disclosure/stock?stockCode=300XXX`（巨潮资讯网，深交所/创业板）
   - `https://paper.cnstock.com/html/yyyy-mm/...`（中国证券网）
3. **A 股实控人优先源**：
   - `https://basic.10jqka.com.cn/{A_CODE}/holder.html`（同花顺 F10 股东研究）—— **直接显示"实际控制人"、"最终控制人"姓名 + 持股比例**，是 cron 场景最快路径
   - `https://q.stock.sohu.com/cn/{A_CODE}/lscjmx.shtml`（搜狐股东信息）
4. **A+H 折价标准算式**：
   ```
   H_total_shares = A_total_shares + H_global_offering_shares × (1 + greenshoe_pct)
   H_market_cap_top = H_total_shares × H_offer_price_top
   A_market_cap = A_total_shares × A_recent_close
   AH_premium_top = (H_offer_price_top × HKD_to_CNY_fx - A_recent_close × 1) / (A_recent_close × 1)
   ```
   - HKD→CNY 实时汇率取 0.92 左右（按当日）；A 股汇率 1.0
   - **报告里**直接给两个口径：H 股市值（A+H 总市值）与 A 股市值，标"按发行价上限 vs A 股最新收盘"对比

## 报告"业务与股东"章节标准模板

```
- 实际控制人：刘强（直接持股 X.XX%）、李杰（X.XX%），最终控制比例合计 X.XX%
  （来源：A 股 2024 年报 P.X / 同花顺 F10 / 招股章程 P.X）
- 早期战略股东：屹唐盛芯半导体（A 股前 X 大股东，2025Q3 减持套现近 4 亿）
- 本次发行后实控人地位不变（按招股书"控股股东承诺函"），合计持股稀释至约 X-X%
- 11 家基石（合共 ~46.74% / 15.03 亿港元，锁定期 6 个月）：
  Emerald Prime (创客天地) 6000 万 / 广发基金 3000 万 / Perseverance 965 万 / 
  高毅资产 / 华勤技术 / 工银理财 / Arrow Target / 汇添富 / 奇点资产 / 
  Heading Pioneer 10 Fund (清华教育基金会) / Dr.（雪球截断需查招股书 P.X）
```

## 报告"财务基本面"章节标准模板（A+H 口径）

```
| 期间 | 营收 | 归母净利 | 同比 | 来源 |
|---|---|---|---|---|
| 2023A | X.XX 亿 | X.XX 亿 | -X.X% | A 股 2023 年报 |
| 2024A | X.XX 亿 | X.XX 亿 | -X.X% | A 股 2024 年报 |
| 2025A | X.XX 亿 | X.XX 亿 | +X.X% | A 股 2025 年报 |
| 2026Q1 | X.XX 亿 | X.XX 亿 | +X.X%（已恢复）| A 股 2026 一季报 |
| 2026H1E | — | — | — | 行业媒体推算（如有） |
| H 股发行 PE（按上限价） | — | — | 17.8-21.1 倍 | 推算（来自 ofweek/招股速递）|
```

## cron 场景的快速研究顺序（≤ 6 次工具调用）

1. `python3 hkipo.py jisilu list --json` → 拿到 code + 公司名 + A 股母公司信息
2. `python3 hkipo.py tradesmart tracker <CODE>` → 孖展
3. `python3 hkipo.py analyze <CODE>` → 聚合字段（招股期、价格、保荐人）
4. **单次 `web_search`**：`{公司名} {H股代码} 基石 招股` → 基石名单
5. **单次 `web_search`**：`{公司名} {H股代码} 营收 净利 2024 2025` → A 股业绩
6. **单次 `web_search`**：`{公司名} {A代码} 实控人 持股` → 实控人 + 股东结构
7. **可选 `web_extract`** 单个高价值页面（如东方财富年报 PDF 链接）

写报告 + push_rss 共 2 次工具调用。**总计 ≤ 8 次，符合 PITFALL #10 限制**。

## 历史验证

- **2026-08-17/20 君正股份（03223.HK，母公司 A 股 300223）**：
  - jisilu 一次返回 12 个结构化字段
  - tradesmart tracker 拿到 1811 亿港元 / 557 倍（招股末期，observed_at 早于今日截止）
  - 4 次 web_search（基石 / 财务 / 实控人 / 保荐人）+ 1 次 web_extract 失败（SearXNG 不做提取）→ 完整基石名单 11 家全部从搜索 snippet 拼出
  - 报告 13890 字节，8 个必备章节齐，RSS ID `20260820-083222-6e67f2`
  - **全部工具调用 ≤ 12 次**，远在 30 次预算内