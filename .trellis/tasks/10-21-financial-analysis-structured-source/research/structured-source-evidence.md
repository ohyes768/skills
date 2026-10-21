# 结构化数据源实测证据

来源：2026-10-21 本机实测（curl 直连 + uv 临时环境 akshare 1.19.1）。样本：凡拓数创（301313.SZ）2026 年半年报，即 run_968d6c8e 实跑所用的同一份 PDF（http://static.cninfo.com.cn/finalpage/2026-08-26/1225506533.PDF）。

## 东财 datacenter F10 接口（可用，推荐）

端点：`https://datacenter.eastmoney.com/securities/api/data/v1/get`

| 报表 | reportName | 关键过滤 |
|---|---|---|
| 资产负债表 | RPT_F10_FINANCE_GBALANCE | `(SECUCODE="301313.SZ")(REPORT_DATE='2026-06-30')` |
| 利润表 | RPT_F10_FINANCE_GINCOME | 同上 |
| 现金流量表 | RPT_F10_FINANCE_GCASHFLOW | 同上 |

`columns=ALL&source=HSF10&client=PC`，需常规浏览器 UA。

### 数据质量（2026-06-30 期）

- 披露日 NOTICE_DATE=2026-08-26，与 PDF 同日更新。
- 资产负债表非空字段 140 个；MONETARYFUNDS、TOTAL_CURRENT_LIAB、TOTAL_PARENT_EQUITY、ACCOUNTS_RECE、INVENTORY、SHORT_LOAN 等合同全部指标可映射。
- 利润表 TOTAL_OPERATE_INCOME=230,730,296.15、PARENT_NETPROFIT=-77,252,801.33，与 Hermes 从 PDF 实抽的数值**完全一致**。
- 现金流量表 NETCASH_OPERATE/INVEST/FINANCE、END_CCE（期末现金及等价物）、CONSTRUCT_LONG_ASSET（购建长期资产）齐备，可直接喂 `_cash_reconciliation`。

### 简化接口与 F10 接口的口径冲突（重要）

同一报告期，简化版 RPT_DMSK_FN_BALANCE 的 TOTAL_ASSETS=1,397,677,219.66，F10 版 RPT_F10_FINANCE_GBALANCE=1,366,525,227.25，**差 31,151,992.41**。结论：只用 F10 版；且任何结构化源与 PDF 双源核对不可省——两个"权威"源之间都可能不一致。

## akshare（不可依赖）

- 1.19.1 实测：`stock_balance_sheet_by_report_em` / `stock_profit_sheet_by_report_em` / `stock_cash_flow_sheet_by_report_em` 对 301313 全部返回 `TypeError: 'NoneType' object is not subscriptable`（库内请求层问题），同机 curl 直连同一后端正常。
- 接口名随版本变动（同花顺/新浪函数在部分版本不存在），社区 issue 多次记录源站改版导致的失效。
- 结论：直接封装东财 HTTP（与 fetch_pdf 同风格：自控 UA/超时/重试/哈希缓存），不引入 akshare 中间层。

## 巨潮 XBRL（不采用）

未找到公开可直接调用的 XBRL 数据接口；巨潮公开 query 接口为公告检索（skill 已用于取 PDF URL）。XBRL 原始实例文档获取路径不明确，放弃。

## 对 skill 的影响评估

- LLM 职责可从「抽数 + 定位 + 填表」缩减为「抽查关键数字回原页验证 + 分析判断」。
- 免疫系统全部保留：勾稽、维度、期间检查照旧；表格 locator 逐格核对降级为抽样核对。
- 新增失败面：结构化源不可用/字段缺失/口径冲突 → 必须能回退纯 PDF 模式。
