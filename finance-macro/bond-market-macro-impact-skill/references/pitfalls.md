# bond-market-macro-impact-skill 踩坑案例集

按现象-根因-修复模式收录。每次推送报告前扫一遍，能避免在常见路径上反复重试。

## 1. 范围漂移：信用债 / 收益率目标 / 概率赋值 / 配置评级

**现象** （来自 2026-09-24 报告）：标题是 "利率债展望"，正文却出现：
- "信用债优于利率债（信用利差未走阔）" —— 信用债判断，API 无信用利差数据
- 基准情景写 "10Y 国债利率 1.65%-1.75% 区间震荡" —— 明确收益率区间目标
- "基准情景（概率最高）" —— 概率赋值
- "配置建议" 表 + ⭐ 配置评级 —— 明确加减仓建议

**根因**：SKILL.md 已明文禁止（"不编造概率、收益率目标或政策决定"、"信用债不纳入结论"），但流程里没有强校验。报告生成时模型倾向于 "完整性 > 严格性"，容易把视野外的内容也写进去。

**修复**：
- 报告生成完毕后，自检这 4 个关键词是否出现在正文：`信用债`、`⭐`、`概率最高`、明确数字区间如 `X.XX%-X.XX%`
- 信用债内容只在 "数据限制" 一节作为 "上一份报告遗留" 提及，不当作本期判断
- 基准情景写方向描述（如 "10Y 国债窄幅震荡于前低附近"），不写具体区间数字
- 配置建议一律删除，最多留 "配置含义（仅供参考，非建议）" 节并明确标注非建议

## 2. 曲线方向词与上期脱节

**现象** （2026-09-28 推送）：上期（9/24）报告写 "曲线趋陡"，本期数据明确显示 9/21→9/24 利差从 0.42pp 压缩到 0.40pp（-1.71bp），属于 bear flattener 形态，曲线方向应翻为 "趋平"。如果在核心判断章节不明确写出反转原因，读者会以为本期是上期方向的延续。

**根因**：流程 6 "复盘" 说 "比较上次主要驱动如何变化"，但没说必须包含**曲线方向词的反转检测**。模型可能只描述数据变化，不主动声明反转。

**修复**：
- 写报告前先把上期报告标题第三段（曲线方向词）和本期计算结果（10Y-2Y 利差变化符号）写在一行
- 不一致时，核心判断首段必须有这句话模板：`较上期 [上期词] 翻转为 [本期词]（10Y-2Y 利差 [Δ]bp）`
- 标题第三段必须用本期词，不要继承上期

## 3. 日频全部 is_asof_fallback 时如何呈现

**现象** （2026-09-28）：5 个日频采样点全部 `is_asof_fallback: true`，最新日期 2026-09-24，比分析日 2026-09-28 早 4 天（中间是周六周日）。API 本身合法，但读者按 "分析日" 误判新鲜度可能误读。

**根因**：SKILL.md 已说明 "回退只是观测日期早于分析日，不自动判失效" 和 "五个采样点不等于完整日线"，但没说怎么在报告开头标注。

**修复**：
- 报告开头标注 **"最新日频所属期：YYYY-MM-DD（距分析日 N 天）"**，把日期差写出来
- 不需要降把握（按 SKILL.md 走），但要让读者意识到

## 4. bull/bear flattener 标签的误用

**现象**：两端方向相反（10Y 下 + 2Y 上）时，本能反应是贴 "bear flattener" 标签，显得专业。

**根因**：framework 明确写了 "两端方向相反或一端不变：直接描述各端及斜率变化，不强套牛熊标签"。但模型容易为了让读者觉得专业而硬贴。

**修复**：
- 两端同向且变化幅度明显时，才用 framework 给的 4 类标签（牛陡/牛平/熊陡/熊平）
- 两端方向相反、或一端变化 < 0.5bp 时，只描述两端各自变化 + 斜率变化，不贴标签
- 推导值（2Y 由 10Y - 利差 算出）的精度本身有 0.01pp 量级误差，< 1bp 的变化不应作为分类依据

## 5. 复盘表缺失对比维度

**现象**：上期报告（9/24）"复盘" 章节只有一段话描述 "较上期变化"，没有结构化对比。本期如果照搬，复盘就退化成段落文字，复用性差。

**根因**：SKILL.md 流程 6 写 "比较上次主要驱动如何变化"，没说必须用表格。

**修复**：
- 复盘章节必须含表，至少 5 行（整体 / 短端 / 长端 / 曲线 / 中美利差数值）
- 表的列：上期判断 / 本期判断 / 变化原因（一句话）
- 反转项加粗或单独标注

## 6. LPR 间隔 2 个月的 "环比" 假象

**现象**：evidence.json 里 LPR 1Y/5Y 的 `latest_change.month_gap = 2`，脚本会打 warning `non-adjacent months; not a month-on-month comparison`。如果直接读 `difference` 写 "LPR 维持不变"，是正确的；但如果不看 gap 就以为 9/20 和 7/20 是相邻月份写 "LPR 2 个月来首次维持不变"，就是误读。

**根因**：8 月 LPR 没公布是正常发布间隔（API 没数据），但脚本会保留 7 月和 9 月两个观察点形成 "2 个月 gap" 的对比。

**修复**：
- 写 LPR 时显式注明 "9 月 LPR 与 7 月持平（8 月未公布）"，不写 "连续维持"
- 跨月 gap > 1 时一律注明缺失月份

## 7. 第一次推送时容易漏掉 --insecure

**现象**：内网 nginx 自签证书的 RSS endpoint（`web.duomi77.cn:9443`），直接 `python scripts/push_rss.py` 会因证书校验失败抛 `ssl.SSLCertVerificationError`。

**修复**：
- 一律加 `--insecure`，已在 SKILL.md 流程 7 中标出
- 若仍报 TLS 错，先 `curl -kI <endpoint>` 验证可达

## 8. push_rss.py 标题与正文一致性强校验

**现象**：标题写 "中性偏支持债券价格｜曲线趋平"，但核心判断章节漏掉这两个词的任何一个，push 会被标题校验拦下。

**根因**：脚本的 `validate_title` 会检查 `parts[1]`（整体方向词）是否出现在 "核心判断" 章节。Curve 方向词不在脚本强校验范围，但用户视觉上会看。

**修复**：
- 标题三段词必须在核心判断章节逐字出现
- 写完报告后用标题三段做 grep 验证
- 标题不要加副词（如 "中性偏支持"），保持词表严格匹配（偏支持债券价格/中性分化/偏压制债券价格）

## 9. skill_view 名称歧义：必须用带分类前缀的 qualified name

**现象** （2026-10-05 cron 首次触发）：`skill_view(name='bond-market-macro-impact-skill')` 返回 `Ambiguous skill name 'bond-market-macro-impact-skill': 2 skills match across your local skills dir and external_dirs`。

**根因**：仓库下存在两个同名 skill 安装位置——一个在 `~/.hermes/skills/bond-market-macro-impact-skill/`（裸名），另一个在 `~/.hermes/skills/finance/bond-market-macro-impact-skill/`（带 `finance/` 前缀，是当前真正在用的活跃安装）。裸名那份可能是早期版本残留。skill_view 在出现歧义时**拒绝猜测**，直接报错。

**修复**：
- 加载时一律用 qualified 形式：`skill_view(name='finance/bond-market-macro-impact-skill')`
- 排查时 `ls ~/.hermes/skills/bond-market-macro-impact-skill/ ~/.hermes/skills/finance/bond-market-macro-impact-skill/ 2>/dev/null` 对比两份 SKILL.md 时间戳和内容，确认用哪个；若带前缀那份是当前 active，裸名那份可直接删除或合并
- 后续 cron / 引用都应固定用 `finance/bond-market-macro-impact-skill` 路径

## 10. cwd 不是 skill 目录：cron 触发前必须先 cd 到脚本所在位置

**现象** （2026-10-05）：系统提示的 working directory 是 `/home/ohyes768/skills/finance-macro/a-share-macro-impact-skill`（同级兄弟 skill 的目录），不是 `bond-market-macro-impact-skill/`。若直接 `python3 scripts/fetch_snapshot.py` 会 `FileNotFoundError`；若按 SKILL.md 写的 `from skill 目录执行` 去找，会定位到兄弟 skill 的目录。

**根因**：cron 触发时 Hermes 给的 cwd 是 skill 集合的根目录（这里是 `finance-macro/`），不是具体子 skill 目录；而 SKILL.md 流程 2 明确要求 "从 skill 目录执行 `python scripts/fetch_snapshot.py`"。

**修复**：
- 脚本调用前显式 cd：`cd /home/ohyes768/skills/finance-macro/bond-market-macro-impact-skill && python3 scripts/fetch_snapshot.py`；或者用绝对路径 `python3 /home/ohyes768/skills/finance-macro/bond-market-macro-impact-skill/scripts/fetch_snapshot.py --output-dir /tmp/...`
- push_rss.py 同理：`<绝对路径>/scripts/push_rss.py <report.md 绝对路径> --title ... --insecure`
- 不要依赖 SKILL.md 里写的 "skill 目录" 相对路径——Hermes cron 不一定会 cd 进去

## 11. 重复跑同一标题的"duplicate"是预期行为，不是错误

**现象** （2026-10-05）：上一份报告（9/28）标题为 "中性偏支持债券价格｜曲线趋平"，本期基本面和曲线方向均无反转，标题完全一致，RSS 推送返回 `pushed: true` 且 `id: 20261005-180800-cf3aa0`，与 9/28 的 id 完全不同——脚本并不因为标题重复就拒绝推送（`is_duplicate` 只在严格匹配且用户没传 `--allow-duplicate` 时才返回 `duplicate: true`，但实际 push 时仍允许新 id 写入）。如果 push 真的返回 `duplicate: true`，那才是真正的重复。

**根因**：SKILL.md 流程 7 已经写了 "标题与已发布条目完全相同（同日重跑且结论未变）时脚本返回 `duplicate: true`，属预期行为，不要重推"——但描述不完整。实际行为是：duplicate 检查发生在 push 前，若发现已存在则直接返回 `duplicate: true` 且不调用 RSS endpoint；若要覆盖需加 `--allow-duplicate`。

**修复**：
- 周更时若结论与上期一致，标题自然相同——这时直接跑就行，push 会成功生成新 id
- 若脚本返回 `duplicate: true`，先确认结论是否真的与上期一致；若确实一致**不要重推**；若结论有变化（比如本期 PMI/资金有更新）但标题仍撞车，必须改标题再推
- macro 看板推送返回 `skipped_no_token` 不影响 RSS 成功判定，无需重试

## 12. 方向词下调但价格几乎没动时，必须说明是「证据性质变化」（2026-10-20 实战新增）

**现象** （2026-10-20）：上期长端判"偏支持"，本期下调为"中性"，但 10Y 实际只从 1.6480% 微升到 1.6497%（**+0.17bp**）。若报告只写"长端由偏支持下调为中性"，读者会以为长端收益率已经上行，与事实不符。

**根因**：长端判断的依据不止 10Y 价格，还包括**月度背景的性质**。本期 9 月数据落地后，PMI 重回 50 上方（+0.3 指数点）+ FAI 收窄 3.8pp + 社零 +0.7pp = 中期增长预期抬升；PPI +1.2pp = 成本端压力。两者是**约束条件**，但都不体现为长端价格已经上行。

**修复**：方向词下调时核心判断章节必须用一句话点明变化类型：

```
长端由"偏支持"下调至"中性"——**这是证据性质变化而非价格变化**：
10Y 实际仅上行 0.17bp，下调理由来自 9 月增长改善与 PPI 上行构成的约束，
而非长端已出现价格上行压力。
```

整体方向翻转时同样要说明是"月度背景变了"还是"日频信号变了"。

**反例**：❌ 只写"长端由偏支持下调为中性"（读者会以为收益率在涨）；❌ 回避下调理由只强调"总体仍偏支持"（回避证据变化 = 隐性硬翻方向）。

## 13. 曲线 slope 变化在 bp 量级以下不算方向翻转（2026-10-20 实战新增）

**现象** （2026-10-20）：本期 slope 从上期报告所用的 0.3933pp（10-16）微升到 0.3975pp（10-19，**+0.42bp**），看起来像"趋陡"；但本期实际路径是 10-13 的 0.4047pp → 10-19 的 0.3975pp，**仍然是趋平**。两个日期口径不同会得出相反结论。

**根因**：5 个采样点、每日波动 1-2bp 的量级下，0.42bp 的差异远小于噪声。SKILL.md 已说"五个日频采样点允许描述观察到的变化，不能据此声称趋势连续"，但没说具体阈值。

**修复**：
- 比较 slope 变化时**用同一个口径的日期对**（本期用 10-13→10-19，别拿上期报告里的 10-16 当起点）
- **变化 < 1bp 不作为方向翻转依据**（呼应 pitfall #4 的精度约束）
- 方向词维持上期时，在复盘表里写清"slope 0.4047pp→0.3975pp（-0.72bp），维持趋平"，避免读者以为漏判

## 14. 推送前先本地跑校验，别用真推送试错（2026-10-20 实战新增）

**现象**：`push_rss.py` 有多重校验（标题正则、标题日期 vs 正文分析时点、方向词是否出现在核心判断章节、必填章节、字符数、来源链接）。直接拿真推送试错，一个方向词没写对就会在 RSS 上留下正文残缺的条目，且 macro 看板可能已推了一半。

**修复**：写完 report.md 后先本地 import 校验函数，零成本查完全部规则：

```bash
cd <skill 目录> && python3 -c "
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location('p', 'scripts/push_rss.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
c = Path('<report.md 绝对路径>').read_text()
c2, w = m.sanitize_report(c)
title = '<完整标题>'
errs = m.validate_report(c2) + m.validate_title(title, c2)
print('warnings:', w)
print('errors:', errs if errs else '（无）')
print('chars:', len(c2))
sec = m.extract_section(c2, '核心判断')
print('方向词1命中:', '<方向词1>' in sec)
print('方向词2命中:', '<方向词2>' in sec)
"
```

**注意 `validate_report` 要求正文含 `复盘` 字样**（本 skill 的 REQUIRED_MARKERS 是 `["核心判断","驱动","未来四周情景","观察清单","复盘"]`），A 股 skill 的是 `数据限制`——两个 skill 的必填章节不同，别互相照抄。

**推送三件套**（token 注入 + `--allow-duplicate` + `--source <skill 目录名>`）与 A 股 skill 相同，见 `a-share-macro-impact-skill-pitfalls` 的 pitfall #2 / #16。

**反例**：❌ 靠反复真推送来发现标题格式错（会在 RSS 留垃圾条目）；❌ 只 `grep` 方向词就算校验过——脚本是**按章节抽取后匹配**，别处出现不算。

## 15.「数据真空期」到「数据落地」的过渡写法（2026-10-20 实战新增）

**现象**：上期（10-19）报告写"9 月月度数据全部未发布，处于等待验证窗口"。本期 9 月数据全部到齐（evidence 里 9 月观测 status=ok），两个新陷阱：

**陷阱 A：两类证据对冲时别硬选一端**。本期增长／通胀／政策端偏空（PMI 50.1、FAI -9.7%、PPI 5.0%），但资金端与外部端偏多（DR007 1.3212% 新低、美元回落、中美利差收窄 10.43bp、HIBOR -29.5bp）。整体维持"中性偏支持债券价格"是**对冲后的结果**，要在核心判断里讲明白是哪两组力量在抵消。

**陷阱 B：上期的前瞻性预期可能不兑现**。上期写"9 月 CPI/PPI 因节假日顺延到 11-09 公布"，实际本期已取到 9 月 CPI 0.9% / PPI 5.0%——**顺延预期没兑现**。上期写"10-20 LPR 下调 5-10bp"是转强触发条件，实际 LPR 维持 3.0%/3.5% **未下调**。

**修复**：
1. 开头元数据写明**上期"数据真空"状态已终结**，列出本期拿到的月份区间
2. 复盘章节显式核对上期预期哪些兑现、哪些没兑现：
   ```
   - **未实现预测复核**：上期写"9 月 CPI/PPI 因节假日顺延到 11-09 公布"，
     实际 API 已取到 9 月 CPI 0.9% 与 PPI 5.0%，**顺延预期未兑现**，本期已纳入；
     上期写"10-20 LPR 下调 5-10bp"，**实际维持 3.0%/3.5% 未下调**
   ```
3. **不要因为"数据终于来了"就把把握从"中"调到"高"**：一个月新数据只是"从空白到有证"，趋势确认要看下一个月
4. 复盘表保留"数据时效评估"行：本期 49 天 vs 上期 79 天，时效改善是把握度的重要支撑

**反例**：❌ 上期说"待 11-09 公布"，本期发现已发布就直接引用而不核对；❌ 因 9 月数据漂亮就把长端判断连跳两档。

## 16. 别把 `next_release_at` 当成一定兑现的承诺（2026-10-20 实战新增）

**现象**：`api_quality.missing_keys` 指标带 `next_release_at` 日期（节假日顺延后尤其容易不准）。上期按 API 给的日期写"待 11-09 公布"，实际数据提前到来了。

**根因**：`next_release_at` 是发布日历的**预估**，节假日顺延规则不总是准。

**修复**：
- 观察清单照写 API 给的日期（当前最佳估计），但**不要在核心判断里依赖"某日必然公布"来论证"判断暂时无法验证"**
- 每期用 `evidence.json` **实际取到的月份**判断"数据到没到"，而不是靠观察清单日期推断
- 复盘章节核对上期日期预期是否兑现（见 pitfall #15 陷阱 B）

## 17. `evidence.json` 不含 core_cpi_yoy —— 别把"提取器没抓"当成"数据没有"（2026-10-26 实战新增）

**现象**（2026-10-26）：上期（10-20）报告在"数据限制"里写"**核心 CPI 在 9 月期亦无有效观测**，通胀判断只能基于 CPI 与 PPI 两项"，并据此在反证里说"无法评估核心通胀粘性"。实际打开 `raw_snapshots.json` 的 2026-09 期 inflation 卡片，`core_cpi_yoy = 1.0`，`status = ok`（2026-07 期亦有 0.9）。

**根因**：`scripts/fetch_snapshot.py` 顶部的 `MONTHLY` 字典只声明了 `inflation: cpi_yoy ppi_yoy`，**没有 `core_cpi_yoy`**。`prepare()` 的 `add()` 会静默丢弃不在 target 字典里的指标（`if name not in target: return`），因此核心 CPI 既不进 `evidence.json`，也不产生 warning——**从 evidence.json 看不出来它被丢了**。API 侧其实一直有 `core_cpi_yoy`（`next_release_note` = "核心 CPI 随 CPI 同步发布"）。

**修复**：
- **判断"某指标无观测"时，必须同时查 `raw_snapshots.json`**，不能只看 `evidence.json` 的 `missing_keys` / warnings
- `missing_keys` 里出现 `core_cpi_yoy` 只说明**当月（2026-10）未发布**，不说明历史月份没有
- 想让核心 CPI 进证据，下期可考虑在 `MONTHLY['inflation']` 里加 `core_cpi_yoy`（改脚本前先跑 `tests/test_bond_evidence.py`）
- 若上期结论建立在"核心 CPI 缺失"之上，本期必须在"数据限制"章节**显式更正**（口径错误要写出来，不要静默改口）

**反例**：❌ 直接写"核心 CPI 无有效观测"而不查 raw；❌ 静默把上期的错误结论改掉而不说明。

## 18. API 历史值会被修订 —— 两期数值不可直接相减（2026-10-26 实战新增）

**现象**（2026-10-26）：同一日期（2026-10-19）的中美 10Y 利差，上期抓取（10-20 运行）得到 `-3.4403%`，本期抓取（10-26 运行）得到 `-3.5003%`，差异 6.00bp。若按上期报告写的"较 10-13 收窄 10.43bp"再叠加本期"较 10-19 收窄 18.03bp"，会算出与实际不符的累计值。

**根因**：API 的历史日频值会被上游修正（`previous_value` 链也在动）。`api-contract.md` 已写"历史月度记录可能修订"，**日频同理**。

**修复**：
- 跨期比较**一律限定在本次抓取的同一序列内**（本次 5 个采样点自己比），不要拿上期报告里的数值当起点做加减
- 复盘表里若要对比上期数值，必须注明"上期引用值 vs 本次抓取值"，并说明存在修订差异、**两期不可直接相减**
- `raw_snapshots.json` 里每个 daily 指标都带 `previous_value` / `change`，但 API 不标注 `previous_value` 的实际间隔，`fetch_snapshot.py` 的 `latest_change` 用的是**本次抓取的独立历史请求**（同日期 as_of 配对），这才是可靠口径
- 涉及"外部约束数值"这一复盘维度时（SKILL.md 强制要求的第 ⑤ 项），若发现修订，直接在表中加注

**反例**：❌ "上期收窄 10.43bp + 本期收窄 18.03bp = 累计收窄 28.46bp"（跨报告相加）；❌ 不核对就沿用上期报告里的 -3.4403% 当 10-19 的真值。
