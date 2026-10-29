# 统一 F10 基础财务入口（v4 MVP）

本流程接受东方财富第三方数据，不逐项官方网页复核，不下载 PDF。不再补银行/保险专用指标。

## v4.1 新任务：直接取数，不登记回执

先按主 skill 初始化 progress.json，再运行下面的财务命令即可，不需要 financial 模式或回执：

```text
python3 <skill目录>/scripts/f10_financial.py --stock stock.json --as-of YYYY-MM-DD --report-date YYYY-MM-DD --cache-dir api-cache --output f10-data.json
```

读取返回的 financial.score/explanation/checks/issues/limitations。explanation 直接给出基础档、
各规则封顶与最终分数；例如“基础档5分；盈利上限3分；趋势上限4分；最终3分”。
普通企业解释复用既有 scorer 的 checks，不另设阈值；缺核心数据时 final_score=null，保留具体 issues，
不能从已知部分自行拼出参考总分。coverage.sources 提供实际请求 URL、报告名、目标期披露日期与字段定位，
由 sources 命令生成来源表；不把第三方响应称为官方核验。需要重读已有包时才用
`rating_math.py financial --input stock.json --f10-data f10-data.json`，不重新联网。
不要拆原始响应、猜编码或重新计算指标。F10 的工作文件不复制进 progress.json；
影响 A-D 的已有财务事实可按实际来源保存为紧凑事实并跨维复用。

新任务交付用 `rating_math.py finalize --input draft.json --stock stock.json --check-financial --f10-data f10-data.json --progress progress.json --output rating.json`。
--progress 与旧 --research-state 不混用。F10 无法取得文件时不伪造空包：记具体取数失败，
本次按失败处理；已返回有效包但核心指标缺失时按包内结果 E=null，仍可交付未评级报告。

本页下半部的报告期、数据口径、评分及范围限制继续适用。

旧 research.json 续跑的 --f10-research 与回执命令已移到 [旧账本兼容](research-control.md#f10-旧账本完整命令)，新任务不加载。

## 报告期与评分合同（新旧共用）

report-date 是已知目标季度末，不凭日历假定已披露。可省略，届时只表示接口最新可用期，不保证公司最新官方财报。目标期不存在则不回退旧期补完整评级。

四个数据集：RPT_F10_FINANCE_MAINFINADATA、RPT_F10_FINANCE_GBALANCE、RPT_F10_FINANCE_GINCOME、RPT_F10_FINANCE_GCASHFLOW。一次工具运行最多四组有界查询，每组最多两次HTTP请求、12秒超时；窗口为截止年及前四年，缓存一小时。--refresh 显式刷新；失败记录缺口，不用旧缓存冒充刷新成功。

包内 datasets 保存原响应、请求URL、哈希和抓取时间；financial 保存规范化输入和评分。原 stock 不覆盖。主要指标 ROEJQ 用作披露加权ROE，不能用集团简单ROE替代；KCFJCXSYJLR 为累计扣非净利润，KCFJCXSYJLRTZ 为年度同比。相邻季用累计差额推单季，同期单季同比=(本期−同期)/abs(同期)×100，基数为零或缺值则 null。三年ROE均值由完整连续年度计算。资产负债率来自同期间合并资产负债表，不使用输入旧值回填。

普通企业 E 沿用现有阈值；金融企业（银行/保险/其他金融）用三年ROE阈值 ≥15/12/8/5 得5/4/3/2，否则1。年度及两季同比均正不降档；两季非负但有非正项封顶4；一季负封顶3；两季负封顶2。三年ROE连续下降封顶4。各项取低。负债率不用于金融企业，不称为银行/保险完整质量评分。监管资本、偿付能力、流动性、逐法人风险均未评估。

金融企业 report_md 及 watch_points 必须原样写“基础财务评分：未评估监管资本、偿付能力、流动性及逐法人风险”，否则 checked finalize 拒绝。缺核心ROE或扣非期间数据 E=null，不搜索补齐。

金额单位元、百分数15表示15%；缺失不填零。重复期全部排除；代码/名称不符拒绝；晚于截止日披露或修订的行排除。这不是历史版本数据库，不保证消除全部重述影响。三表可能无覆盖，财报期缺少主指标仍不评级；现金流和利润表当前主要留作背景，本版不新增现金流评分权重。

finalize 使用 --f10-data --stock --check-financial，重算原始响应而不信任包内 financial 缓存。新任务另带 --progress；仅旧账本续跑带 --research-state research.json，此时账本必须为 f10 模式且 financial 已结案，不能拿旧行业账本替代。--f10-data 与旧 --bank-data/--insurance-data 互斥。旧脚本保持兼容，正常新任务不再加载旧行业参考。
