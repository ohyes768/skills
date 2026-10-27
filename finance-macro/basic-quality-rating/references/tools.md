# 固定工具用法

以下 `<skill目录>` 是当前 skill 的实际目录；运行数据放在宿主指定的工作目录，不放源码目录。
财务计算、算分与校验只需 Python 3 标准库。PDF 依赖在安装时准备，见 [安装与兼容迁移](setup-and-migration.md)。

A-D 取证开工先按 [有预算的取证与失败换路](research-control.md) 初始化 research.json，保存渠道故障、当前缺口、紧凑证据与轮次；已查清就复用，缺证则以 null 收口。

## 1. 财务 E：企业原始输入与银行证据包

```text
python3 <skill目录>/scripts/rating_math.py financial --input <工作目录>/stock.json
```

返回一个 JSON 对象：

- `score`：1–5 整数或 null；`status`：scored / insufficient_data / not_applicable。
- `checks`：各项 rule、原始 input、period、result、cap 和 reason；可直接用于报告说明。
- `issues`：缺失、无效、口径无法对齐或专用指标缺口；写入待验证事项。
- `risks`：已知的财务弱项；不要把 issues 自动改写成经营风险。
- `sector`：ordinary / utility_transport / bank / insurance / nonbank_financial 或 null。

普通企业只读取原始输入，不取外部数字，不计算缺失的 roe_avg_3y，不把字符串、布尔值或 null 当数字。
字段中的 0 和负数有效。所需年度字段为 `roe_year` 与 `annual_profit_year`，接受整数或四位年份字符串，二者须一致。
ROE 历史取 roe_year 及前两年；同年相同值可去重，同年冲突、最近缺年或晚于锚点年份的记录会阻止评分。

`previous_quarter_label` / `latest_quarter_label` 须相邻，支持跨年 Q4→Q1。
可用 `2026Q1`、`2026年第一季度`、`2026一季报`；其他报表名须显式写单季，如 `2026半年报（单季）`。
累计、YTD、H1/H2、未注明单季的半年报/三季报/年报均不能替代单季标签。
不因标签无法识别而擅自改写原始输入；向调用方反馈具体缺口。

行业以 `sw_level1/sw_level2` 显式识别。普通申万行业用普通负债率阈值，公用事业/交通运输用宽容阈值；
行业缺失、不支持或两级冲突时未评分，不从公司名字猜。银行和保险使用下述各自独立证据包；其他非银金融仍返回 null，保留子行业缺口说明。
完整支持的行业集合与标签解析由 `financial_score.py` 维护；脚本返回具体问题，无需为常规运行读取源码。

五维确定后继续用主 skill 的 calculate/finalize。正常 finalize 加 `--stock stock.json --check-financial --research-state research.json`，
能拦截手抄 E 分数错误。若有已披露的外部口径冲突，只能按主 skill 的受限兼容入口交付，不能偷偷替换输入数字。

### 银行分支

先读 [银行证据与评分](bank-financial.md)。官方披露候选定位、证据包模板/校验只需使用固定工具，
不修改 stock.json。银行补数明确传 --bank-data；不带时 E 为 insufficient_data，而非认定银行不适用评级。

```text
python3 <skill目录>/scripts/bank_financial.py template --stock stock.json --as-of 2026-10-27
python3 <skill目录>/scripts/bank_evidence.py --document-dir <document_dir> --max-chars 6000
python3 <skill目录>/scripts/bank_financial.py validate --stock stock.json --input bank-data.json
python3 <skill目录>/scripts/rating_math.py financial --input stock.json --bank-data bank-data.json
```

模板 stdout 保存为 bank-data.json，填入已确认的官方数据。候选数字不自动入分，表格多年份、
累计/年化、集团/母行须核对。银行四类规则及三年窗口、资本适用要求和辅助指标见银行参考。
正常银行 finalize 和只读 validator 均加 --bank-data bank-data.json --stock stock.json --check-financial；
research.json 先 init --bank-research，E 也须结案。研究分档未实证校准，报告不得称为监管评级。

## 2. PDF：准备一次，搜索和读页复用

保险先读 [保险证据与评分](insurance-financial.md)：用 insurance_financial.py template/validate
及 insurance_evidence.py 候选定位，计算/交付加 --insurance-data insurance-data.json。
集团/法人分开，金额与百分比单位显式校验；E 账本先 init --insurance-research。
保险不套银行数据包，二者不能同时提供。上述银行命令和普通企业命令保持兼容。

运行环境安装好后，用宿主已有 Python；也可用 `uv run --no-sync --project <skill目录> python ...` 调用已准备的环境。

```text
python3 <skill目录>/scripts/pdf_evidence.py prepare --url <原始PDF链接> --cache-dir <缓存目录>
```

返回 `document_dir`、来源 URL/哈希、页数、自动识别的公司/期间与 warnings；不输出全文。
每个 URL 对应独立目录，缓存以 PDF、来源记录、文档元数据和页索引的哈希绑定。
相同 URL 缓存命中不下载、不重新解析；URL 内容更新需显式 `--refresh`，刷新失败保留原缓存。
缓存命中不代表远程来源没有更新：定期复评应先判断是否需要新公告/新 URL 或 refresh。

```text
python3 <skill目录>/scripts/pdf_evidence.py search --document-dir <上一步document_dir> --query 主营业务 --query 公司治理
python3 <skill目录>/scripts/pdf_evidence.py read --document-dir <document_dir> --pages 12,20-22 --max-chars 6000
```

`search` 为逐页字面匹配，不是语义判断，每页每个 query 返回首个命中附近的短片段。
`match_count` 是命中的“页面/query”数，不是所有出现次数；需要上下文时用 read 读取相关页。
可重复传最多 16 个 query，每个不超过 256 字符。PDF 换行/空格可能影响命中，可用较短关键词定位。

返回 `items` 中的 `page` 是 **PDF 文件 1 起算页码**，不是印刷页码；`printed_page` 仅作辅助。
共享的 `source` 包含 requested_url/final_url/sha256。引用时保留来源、PDF 页码与期间，不把不同公司、年度、合并/母公司表混用。
扫描页或文字提取不足会明确警告：未做 OCR，也不能据此认定资料不存在。

每包正文默认 ≤6000 字符，上限 12000；read 一次最多选 100 页。
`next_cursor` 非 null 时，以相同 document_dir 和选择条件追加 `--cursor <游标>` 续读。
游标绑定来源、索引与查询条件；源文件刷新后旧游标失效。搜索/读取不调用网络或 PDF 解析器。
缓存损坏时返回错误，按原 URL 使用 prepare --refresh 重建，不手改索引哈希。

## 3. 只读校验已有结果

```text
python3 <skill目录>/scripts/validate_rating_json.py <rating.json> --stock <stock.json> --check-financial --research-state <research.json>
```

输出 `status/errors/warnings/scope`。退出 0 表示数值结构通过，退出 2 表示输入或合同失败。
不修改原文件；复用 rating_math 的权重、星级、null 传播和规范 boundary，禁止另写第二套算分。
正文缺章节、来源格式、未评级标注或疑似交易措辞仅提醒人工复核，不证明或否定语义正确性。
免责声明、同值的财务指标不会成为机械拒绝原因。是否有真实证据、是否正确回答判别问题仍由分析者检查。
